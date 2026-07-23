import os
import sys
import subprocess
import pathlib
import structlog

logger = structlog.get_logger(__name__)

class PlatformAbstractor:
    """
    Abstracts operating system differences for path normalization 
    and service management across Windows, macOS, and Linux.
    """
    def __init__(self):
        self.os_type = sys.platform

    def normalize_path(self, path: str) -> str:
        """
        Normalize path based on the operating system.
        """
        return str(pathlib.Path(path).resolve())

    def start_service(self, service_name: str) -> bool:
        """
        Starts a service based on the operating system.
        """
        try:
            if self.os_type == "win32":
                subprocess.run(["sc", "start", service_name], check=True, capture_output=True)
            elif self.os_type == "darwin":
                subprocess.run(["launchctl", "start", service_name], check=True, capture_output=True)
            elif self.os_type.startswith("linux"):
                subprocess.run(["systemctl", "start", service_name], check=True, capture_output=True)
            else:
                logger.error(f"Unsupported OS: {self.os_type}")
                return False
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start service {service_name}: {e.stderr.decode('utf-8', errors='ignore') if getattr(e, 'stderr', None) else e}")
            return False

    def stop_service(self, service_name: str) -> bool:
        """
        Stops a service based on the operating system.
        """
        try:
            if self.os_type == "win32":
                subprocess.run(["sc", "stop", service_name], check=True, capture_output=True)
            elif self.os_type == "darwin":
                subprocess.run(["launchctl", "stop", service_name], check=True, capture_output=True)
            elif self.os_type.startswith("linux"):
                subprocess.run(["systemctl", "stop", service_name], check=True, capture_output=True)
            else:
                logger.error(f"Unsupported OS: {self.os_type}")
                return False
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop service {service_name}: {e.stderr.decode('utf-8', errors='ignore') if getattr(e, 'stderr', None) else e}")
            return False

    def restart_service(self, service_name: str) -> bool:
        """
        Restarts a service based on the operating system.
        """
        try:
            if self.os_type == "win32":
                subprocess.run(["powershell", "-Command", f"Restart-Service -Name {service_name}"], check=True, capture_output=True)
            elif self.os_type == "darwin":
                self.stop_service(service_name)
                return self.start_service(service_name)
            elif self.os_type.startswith("linux"):
                subprocess.run(["systemctl", "restart", service_name], check=True, capture_output=True)
            else:
                logger.error(f"Unsupported OS: {self.os_type}")
                return False
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart service {service_name}: {e.stderr.decode('utf-8', errors='ignore') if getattr(e, 'stderr', None) else e}")
            return False

    def service_status(self, service_name: str) -> str:
        """
        Checks the status of a service based on the operating system.
        """
        try:
            if self.os_type == "win32":
                result = subprocess.run(["sc", "query", service_name], check=True, capture_output=True, text=True)
                return result.stdout
            elif self.os_type == "darwin":
                result = subprocess.run(["launchctl", "list", service_name], check=True, capture_output=True, text=True)
                return result.stdout
            elif self.os_type.startswith("linux"):
                result = subprocess.run(["systemctl", "status", service_name], check=False, capture_output=True, text=True)
                return result.stdout
            else:
                return f"Unsupported OS: {self.os_type}"
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get status of service {service_name}: {e.stderr if hasattr(e, 'stderr') else str(e)}")
            return str(e)

# Expose a default instance
platform_utils = PlatformAbstractor()
