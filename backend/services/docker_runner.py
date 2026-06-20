import os
import time
import datetime
from utils.logger import setup_logger

logger = setup_logger(__name__)

class DockerBuilder:
    """
    Handles Priority 2 Deployments: Dockerfile.
    Builds the image natively and runs it.
    """
    def run(self, work_dir: str, log_path: str, port: int, custom_config: dict = None) -> dict:
        import docker
        client = docker.from_env()
        stages = []
        
        # 1. Build Stage
        build_stage_name = "Docker Build"
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n{'='*60}\n")
            log.write(f"Pipeline Start: DOCKER | port={port}\n")
            log.write(f"Detected via: Dockerfile\n")
            log.write(f"{'='*60}\n")
            log.write(f"\n{'─'*40}\n▶  {build_stage_name}\n   cmd: docker build .\n")
            
        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        # Ensure we just use the port for uniqueness, or a random string.
        image_tag = f"aicicd-app-{port}:latest"
        build_success = False
        build_output = ""
        
        try:
            # client.images.build returns (Image, build_logs)
            image, build_logs = client.images.build(path=work_dir, tag=image_tag, rm=True)
            for chunk in build_logs:
                if 'stream' in chunk:
                    build_output += chunk['stream']
            build_success = True
        except docker.errors.BuildError as e:
            for chunk in e.build_log:
                if 'stream' in chunk:
                    build_output += chunk['stream']
            build_success = False
        except Exception as e:
            build_output = str(e)
            build_success = False
            
        duration = round(time.time() - t0, 2)
        ended_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(build_output)
            level = "[SUCCESS]" if build_success else "[FAILED]"
            log.write(f"\n{level} {build_stage_name}: {'OK' if build_success else 'FAILED'} ({duration}s)\n")
            
        stages.append({
            "stage": build_stage_name,
            "success": build_success,
            "duration": duration,
            "started_at": started_at,
            "ended_at": ended_at,
            "exit_code": 0 if build_success else 1,
            "error_type": "DockerBuildFailed" if not build_success else None,
            "error_message": build_output[-500:] if not build_success else None,
            "output": build_output
        })
        
        if not build_success:
            return {
                "language": "docker",
                "port": port,
                "stages": stages,
                "failed_stage": build_stage_name,
                "success": False,
                "error_summary": self._format_errors(stages)
            }
            
        # 2. Run Stage
        run_stage_name = "Start Application"
        with open(log_path, "a", encoding="utf-8") as log:
            log.write(f"\n{'─'*40}\n▶  {run_stage_name}\n   cmd: docker run -p {port}:{port} {image_tag}\n")
            
        t0 = time.time()
        started_at = datetime.datetime.utcnow().isoformat() + "Z"
        
        try:
            container = client.containers.run(
                image_tag,
                ports={f"{port}/tcp": port, "80/tcp": port, "8080/tcp": port, "3000/tcp": port},
                environment={"PORT": str(port)},
                mem_limit="2g",
                cpu_quota=100000,
                detach=True
            )
            
            cid_file = os.path.join(work_dir, "app.container_id")
            with open(cid_file, "w") as f:
                f.write(container.id)

            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"   [Launched container ID: {container.short_id}]\n")
                log.write(f"[SUCCESS] {run_stage_name}: OK\n")
            
            duration = round(time.time() - t0, 2)
            stages.append({
                "stage": run_stage_name,
                "success": True,
                "port": port,
                "cmd": f"docker run {image_tag}",
                "pid": container.short_id,
                "output": f"App launched in container {container.short_id}",
                "duration": duration,
                "started_at": started_at,
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z"
            })
            
        except Exception as e:
            duration = round(time.time() - t0, 2)
            with open(log_path, "a", encoding="utf-8") as log:
                log.write(f"   [FAILED] {str(e)}\n")
                
            stages.append({
                "stage": run_stage_name,
                "success": False,
                "duration": duration,
                "started_at": started_at,
                "ended_at": datetime.datetime.utcnow().isoformat() + "Z",
                "exit_code": 1,
                "error_type": "DockerRunFailed",
                "error_message": str(e),
                "output": str(e)
            })
            return {
                "language": "docker",
                "port": port,
                "stages": stages,
                "failed_stage": run_stage_name,
                "success": False,
                "error_summary": self._format_errors(stages)
            }

        # 3. Health Check
        # We invoke the health check logic from pipeline_runner by cheating and importing it
        from services.pipeline_runner import PipelineRunner
        runner = PipelineRunner()
        with open(log_path, "a", encoding="utf-8") as log:
            health_res = runner._run_health_check(port, log, custom_config)
            stages.append(health_res)

        return {
            "language": "docker",
            "docker_image": image_tag,
            "port": port,
            "stages": stages,
            "failed_stage": None,
            "success": True,
            "error_summary": ""
        }
        
    def _format_errors(self, error_summary: list) -> list:
        return [
            {"stage": s["stage"], "snippet": s.get("output", "")[-200:], "exit_code": s.get("exit_code")}
            for s in error_summary if not s.get("success")
        ]
