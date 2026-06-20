import time
import requests
from typing import Dict, Any

class HealthChecker:
    """
    Polls the application's health endpoint to verify it started correctly.
    """
    def check(self, port: int, endpoint: str, timeout_sec: int = 30) -> Dict[str, Any]:
        """
        Poll the given port and endpoint for a 200 OK response.
        Returns a standardized dictionary.
        """
        if not endpoint.startswith("/"):
            endpoint = "/" + endpoint
            
        url = f"http://localhost:{port}{endpoint}"
        start_time = time.time()
        
        last_error = None
        
        while time.time() - start_time < timeout_sec:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    return {
                        "status": "success",
                        "url": url,
                        "duration": round(time.time() - start_time, 2)
                    }
                else:
                    return {
                        "status": "failed",
                        "error_type": "HEALTH_ENDPOINT_MISSING" if response.status_code == 404 else "PROCESS_CRASHED",
                        "message": f"Health check returned HTTP {response.status_code}",
                        "recommendation": "Verify the health_check endpoint in deployment.txt is correct and returns 200 OK."
                    }
            except requests.exceptions.ConnectionError as e:
                last_error = "ConnectionError"
                time.sleep(1)
            except requests.exceptions.Timeout as e:
                last_error = "Timeout"
                time.sleep(1)
            except Exception as e:
                return {
                    "status": "failed",
                    "error_type": "STARTUP_FAILURE",
                    "message": f"Unexpected error during health check: {str(e)}",
                    "recommendation": "Review application startup logs."
                }
            
        # If we exit the loop, it means we timed out
        if last_error == "ConnectionError":
            return {
                "status": "failed",
                "error_type": "PORT_NOT_OPEN",
                "message": f"Port {port} not listening or connection refused.",
                "recommendation": "Verify start_command and ensure the application binds to 0.0.0.0 and not just 127.0.0.1."
            }
        else:
            return {
                "status": "failed",
                "error_type": "TIMEOUT",
                "message": f"Health check timed out after {timeout_sec} seconds.",
                "recommendation": "Increase startup timeout or optimize initialization."
            }
