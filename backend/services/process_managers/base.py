from abc import ABC, abstractmethod

class ProcessManager(ABC):
    """Base interface for all deployment process managers (PM2, Systemd, etc.)"""
    
    @abstractmethod
    def start(self, project_name: str, start_command: str, work_dir: str, port: int, log_file) -> dict:
        """
        Starts the application in the background.
        Should return a dictionary with success boolean, pid (if available), and output.
        """
        pass

    @abstractmethod
    def stop(self, project_name: str) -> bool:
        """Stops the application"""
        pass
