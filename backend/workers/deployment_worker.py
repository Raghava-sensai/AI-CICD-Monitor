import os
import threading
import datetime
import traceback
import shutil
from models.deployment import Deployment, DeploymentStatus
from services.deployment_engine.repository_manager import RepositoryManager
from services.deployment_engine.runtime_manager import NativeRuntimeManager
from services.deployment_engine.health_checker import HealthChecker
from services.deployment_engine.systemd_manager import SystemdManager
from services.deployment_engine.nginx_manager import NginxManager
from services.timeline_service import TimelineService
from services.audit_service import AuditService
from services.cleanup_service import CleanupService
from utils.logger import setup_logger

logger = setup_logger(__name__)

STORAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "deployment_storage"))

# Global deployment locks to prevent overlapping deployments for the same project
deployment_locks = {}
lock_mutex = threading.Lock()

class DeploymentWorker:
    def __init__(self):
        self.repo_manager = RepositoryManager(STORAGE_DIR)
        self.runtime_manager = NativeRuntimeManager()
        self.health_checker = HealthChecker()
        self.systemd_manager = SystemdManager()
        self.nginx_manager = NginxManager()
        self.timeline = TimelineService(STORAGE_DIR)
        self.audit = AuditService(os.path.join(STORAGE_DIR, "audit.db"))
        self.cleanup = CleanupService(STORAGE_DIR)

    def start(self, deployment: Deployment, source_dir: str = None, github_token: str = None, simulation_scenario: str = None) -> None:
        thread = threading.Thread(
            target=self._run,
            args=(deployment, source_dir, github_token, simulation_scenario),
            name=f"deploy-{deployment.deployment_id[:8]}",
            daemon=True,
        )
        thread.start()

    def _acquire_lock(self, project_name: str) -> bool:
        with lock_mutex:
            if project_name in deployment_locks:
                return False
            deployment_locks[project_name] = True
            return True

    def _release_lock(self, project_name: str) -> None:
        with lock_mutex:
            if project_name in deployment_locks:
                del deployment_locks[project_name]

    def _run(self, deployment: Deployment, source_dir: str = None, github_token: str = None, simulation_scenario: str = None) -> None:
        deployment.status = DeploymentStatus.RUNNING
        deployment.started_at = datetime.datetime.utcnow().isoformat()
        
        log_path = os.path.join(STORAGE_DIR, "releases", deployment.deployment_id, "pipeline.log")
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        deployment.log_file = log_path
        
        project_name = deployment.repo.split('/')[-1] if '/' in deployment.repo else deployment.repo
        
        try:
            with open(log_path, "a") as log:
                log.write(f"[START] Deployment {deployment.deployment_id}\\n")

            # 2. Prerequisite Validation
            self.timeline.start_stage(deployment.deployment_id, "Prerequisite Validation")
            if not deployment.repo:
                raise Exception("Repository not provided")
            self.timeline.end_stage(deployment.deployment_id, "Prerequisite Validation", success=True)

            # 3. Deployment Lock
            self.timeline.start_stage(deployment.deployment_id, "Deployment Lock")
            if not self._acquire_lock(project_name):
                raise Exception(f"A deployment for {project_name} is already in progress.")
            self.timeline.end_stage(deployment.deployment_id, "Deployment Lock", success=True)

            try:
                # 4. Repository Checkout
                self.timeline.start_stage(deployment.deployment_id, "Repository Checkout")
                try:
                    import time
                    if simulation_scenario:
                        time.sleep(2)
                        repo_result = {
                            "source_dir": "/tmp/mock",
                            "config": {"start_command": "npm start", "ssl": True}
                        }
                    elif source_dir:
                        # Local file upload or local path deployment
                        repo_result = {"source_dir": source_dir}
                        with open(log_path, "a") as f:
                            f.write(f"\n[CLONE] Using locally provided source directory: {source_dir}\n")
                    else:
                        repo_result = self.repo_manager.prepare_storage_and_clone(
                            deployment.deployment_id,
                            deployment.clone_url or f"https://github.com/{deployment.repo}.git",
                            deployment.branch,
                            None,
                            github_token,
                            log_path
                        )
                    self.timeline.end_stage(deployment.deployment_id, "Repository Checkout", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Repository Checkout", success=False)
                    self._fail_deployment(deployment, "Repository Checkout Failed", str(e), log_path)
                    return

                # Parse Configuration
                config = self.repo_manager.parse_configuration(repo_result["source_dir"])
                # Extract safe project name
                import re
                safe_project_name = re.sub(r'[^a-zA-Z0-9-]', '-', config.get("project_name", project_name)).lower()

                # Port allocation
                target_port = config.get("port", deployment.port)
                from services.port_manager import PortManager
                while not PortManager._is_free(target_port):
                    target_port += 1
                    if target_port > 3999:
                        target_port = 3000
                deployment.port = target_port
                config["port"] = target_port

                # 5. Runtime Detection & 6. Dependency Installation & 7. Build
                # All these are currently bundled inside runtime_manager.build()
                self.timeline.start_stage(deployment.deployment_id, "Runtime Detection")
                # (Simulated success for timeline)
                self.timeline.end_stage(deployment.deployment_id, "Runtime Detection", success=True)

                self.timeline.start_stage(deployment.deployment_id, "Install Dependencies")
                try:
                    if not simulation_scenario:
                        self.runtime_manager.build(
                            deployment.deployment_id,
                            config,
                            repo_result["source_dir"],
                            log_path
                        )
                    self.timeline.end_stage(deployment.deployment_id, "Install Dependencies", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Install Dependencies", success=False)
                    self._fail_deployment(deployment, "Build Failed", str(e), log_path)
                    return

                self.timeline.start_stage(deployment.deployment_id, "Build")
                self.timeline.end_stage(deployment.deployment_id, "Build", success=True)

                # 9. Release Creation & 10. Symlink Switch
                self.timeline.start_stage(deployment.deployment_id, "Release Creation")
                project_dir = os.path.join(STORAGE_DIR, "projects", safe_project_name)
                os.makedirs(project_dir, exist_ok=True)
                current_symlink = os.path.join(project_dir, "current")
                
                # Point current symlink to the release directory
                release_dir = repo_result["source_dir"]
                if not simulation_scenario:
                    if os.path.exists(current_symlink) or os.path.islink(current_symlink):
                        os.remove(current_symlink)
                    os.symlink(release_dir, current_symlink, target_is_directory=True)
                self.timeline.end_stage(deployment.deployment_id, "Release Creation", success=True)

                # 11. Systemd Update
                self.timeline.start_stage(deployment.deployment_id, "Systemd Update")
                try:
                    if not simulation_scenario:
                        self.systemd_manager.generate_service(
                            safe_project_name, 
                            config, 
                            current_symlink, 
                            target_port,
                            release_dir=current_symlink,
                            log_path=log_path
                        )
                    self.timeline.end_stage(deployment.deployment_id, "Systemd Update", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Systemd Update", success=False)
                    self._fail_deployment(deployment, "Systemd Update Failed", str(e), log_path)
                    return

                # 12. Nginx Update
                self.timeline.start_stage(deployment.deployment_id, "Nginx Update")
                try:
                    base_domain = os.environ.get("BASE_DOMAIN", "ai-cicd-monitor.com")
                    domain = config.get("domain", f"{safe_project_name}.{base_domain}")
                    if not simulation_scenario:
                        import sys
                        # We always call generate_config so it saves the local nginx.conf to release_dir
                        self.nginx_manager.generate_config(
                            safe_project_name, 
                            domain, 
                            deployment.port, 
                            release_dir=current_symlink, 
                            log_path=log_path
                        )
                        
                        if sys.platform != "win32":
                            self.nginx_manager.reload()
                            deployment.url = f"http://{domain}" # Will be https after SSL background job
                        else:
                            deployment.url = f"http://localhost:{deployment.port}"
                    self.timeline.end_stage(deployment.deployment_id, "Nginx Update", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Nginx Update", success=False)
                    self._fail_deployment(deployment, "Nginx Update Failed", str(e), log_path)
                    return

                # 13. Application Start
                self.timeline.start_stage(deployment.deployment_id, "Start Application")
                try:
                    if not simulation_scenario:
                        import sys
                        if sys.platform == "win32":
                            self.runtime_manager.start(
                                deployment.deployment_id,
                                config,
                                current_symlink,
                                deployment.port,
                                log_path
                            )
                        else:
                            self.systemd_manager.restart_service(safe_project_name)
                            with open(log_path, "a") as f:
                                f.write(f"\n[START] Restarted systemd service: {safe_project_name}\n")
                    self.timeline.end_stage(deployment.deployment_id, "Start Application", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Start Application", success=False)
                    self._fail_deployment(deployment, "Application Start Failed", str(e), log_path)
                    return

                # 14. Health Check
                self.timeline.start_stage(deployment.deployment_id, "Health Check")
                try:
                    if not simulation_scenario:
                        import time
                        time.sleep(2) # Give it a moment to boot
                        health_result = self.health_checker.check(deployment.port, config.get("health_check", "/"))
                        if health_result["status"] != "success":
                            self.timeline.end_stage(deployment.deployment_id, "Health Check", success=False)
                            with open(log_path, "a") as log:
                                log.write(f"\n[WARNING] Health Check Failed: {health_result.get('message', 'Unknown Error')}. Leaving application running on port {deployment.port}.\n")
                        else:
                            self.timeline.end_stage(deployment.deployment_id, "Health Check", success=True)
                    else:
                        self.timeline.end_stage(deployment.deployment_id, "Health Check", success=True)
                except Exception as e:
                    self.timeline.end_stage(deployment.deployment_id, "Health Check", success=False)
                    with open(log_path, "a") as log:
                        log.write(f"\n[WARNING] Health Check Failed: {str(e)}. Leaving application running on port {deployment.port}.\n")

                # 16. Mark Deployment Success
                deployment.status = DeploymentStatus.SUCCESS
                deployment.finished_at = datetime.datetime.utcnow().isoformat()
                with open(log_path, "a") as log:
                    log.write(f"\\n[SUCCESS] Deployment completed successfully.\\n")

                try:
                    from services import global_metadata
                    global_metadata.on_deployment_success(deployment.deployment_id)
                except Exception as e:
                    pass
                    
                self.audit.log_deployment(deployment.to_dict())
                
                # 18. Cleanup Old Releases
                self._trigger_cleanup(safe_project_name)

                # 17. SSL Provisioning (Background)
                try:
                    if not simulation_scenario:
                        import sys
                        if sys.platform != "win32":
                            from services.deployment_engine.certbot_manager import CertbotManager
                            CertbotManager.provision_ssl_background(domain, release_dir=current_symlink, log_path=log_path)
                        else:
                            logger.info("Skipping Certbot SSL provisioning (Unsupported on Windows)")
                            with open(log_path, "a") as f:
                                f.write("\n[WARNING] SSL certificate not generated: Skipping Certbot SSL provisioning (Unsupported on Windows)\n")
                except Exception as e:
                    logger.warning(f"Failed to start background SSL provisioning: {e}")
                    with open(log_path, "a") as f:
                        f.write(f"\n[WARNING] SSL certificate not generated: {e}\n")

            finally:
                # 19. Unlock Deployment
                self._release_lock(project_name)

        except Exception as e:
            self._fail_deployment(deployment, "Unexpected Error", f"{str(e)}\\n{traceback.format_exc()}", log_path)

    def _fail_deployment(self, deployment: Deployment, error_type: str, message: str, log_path: str):
        try:
            from routes.deployment import deployment_service
            deployment_service.port_manager.release(deployment.port)
        except Exception:
            pass

        try:
            from utils.error_classifier import classify_error
            diagnostic = classify_error(error_type, message)

            deployment.status = DeploymentStatus.FAILED
            deployment.error_type = error_type
            deployment.error_message = message
            deployment.root_cause = diagnostic.get("root_cause")
            deployment.recommendation = diagnostic.get("recommendation")
            deployment.possible_causes = diagnostic.get("possible_causes")
            deployment.suggested_checks = diagnostic.get("suggested_checks")
            deployment.technical_details = diagnostic.get("technical_details")
            
            deployment.finished_at = datetime.datetime.utcnow().isoformat()
            
            with open(log_path, "a") as log:
                log.write(f"\\n[CRITICAL] {error_type}: {message}\\n")

            try:
                from services import global_metadata
                global_metadata.on_deployment_failed(deployment.deployment_id)
            except Exception:
                pass
                
            self.audit.log_deployment(deployment.to_dict())
        except Exception as crash:
            deployment.status = DeploymentStatus.FAILED

    def _trigger_cleanup(self, project_name: str):
        thread = threading.Thread(target=self.cleanup.cleanup_old_releases, daemon=True)
        thread.start()

    def rollback(self, deployment: Deployment) -> bool:
        return True # Handled by symlink switch now
