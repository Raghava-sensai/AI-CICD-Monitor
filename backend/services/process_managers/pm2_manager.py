import os
import subprocess
import time
from .base import ProcessManager

class PM2Manager(ProcessManager):
    def start(self, project_name: str, start_command: str, work_dir: str, port: int, log_file) -> dict:
        log_file.write(f"\n[PM2] Starting {project_name} on port {port}\n")
        
        # Stop existing process if it exists
        subprocess.run(["pm2", "stop", project_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pm2", "delete", project_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        env = os.environ.copy()
        env["PORT"] = str(port)
        
        # We wrap the command in a shell execution so PM2 can run non-js binaries or complex npm commands
        # Example: pm2 start "npm run prod" --name "my-app"
        cmd = ["pm2", "start", start_command, "--name", project_name]
        
        try:
            # We use shell=True because start_command might contain spaces and arguments (e.g., "npm run start")
            # For PM2, the safest way is passing the whole string to PM2.
            # pm2 start "npm run start" --name my-app
            cmd_str = f'pm2 start "{start_command}" --name "{project_name}"'
            
            proc = subprocess.run(
                cmd_str,
                cwd=work_dir,
                env=env,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            
            log_file.write(proc.stdout)
            
            # Save PM2 state
            subprocess.run(["pm2", "save"], stdout=subprocess.DEVNULL)
            
            if proc.returncode == 0:
                return {
                    "success": True,
                    "pid": None, # PM2 manages PID internally
                    "output": f"Successfully started {project_name} via PM2."
                }
            else:
                return {
                    "success": False,
                    "output": f"PM2 start failed with exit code {proc.returncode}"
                }
        except Exception as e:
            return {
                "success": False,
                "output": f"PM2 exception: {e}"
            }

    def stop(self, project_name: str) -> bool:
        res = subprocess.run(["pm2", "delete", project_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return res.returncode == 0
