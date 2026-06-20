"""
Port Manager - Allocates and reclaims TCP ports for deployments.
"""

import socket
from utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_PORT_RANGE_START = 3000
DEFAULT_PORT_RANGE_END = 3999


class PortManager:
    """
    Tracks port allocations across deployments.
    Ports are allocated from a configurable range and returned
    when a deployment ends.
    """

    def __init__(
        self,
        start: int = DEFAULT_PORT_RANGE_START,
        end: int = DEFAULT_PORT_RANGE_END,
    ):
        self._start = start
        self._end = end
        self._allocated: set[int] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def allocate(self) -> int:
        """Find and reserve the next available port."""
        for port in range(self._start, self._end + 1):
            if port not in self._allocated and self._is_free(port):
                self._allocated.add(port)
                logger.info(f"Port {port} allocated.")
                return port
        raise RuntimeError("No free ports available in the configured range.")

    def release(self, port: int) -> None:
        """Return a port to the pool."""
        self._allocated.discard(port)
        logger.info(f"Port {port} released.")

    def is_allocated(self, port: int) -> bool:
        return port in self._allocated

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _is_free(port: int) -> bool:
        """Return True if the OS reports the port as unbound on all interfaces."""
        # IPv4
        for ip in ["0.0.0.0", "127.0.0.1"]:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                try:
                    sock.bind((ip, port))
                except OSError:
                    return False
                    
        # IPv6 (catch Node.js which often binds to :: by default)
        if socket.has_ipv6:
            for ip in ["::", "::1"]:
                with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
                    try:
                        sock.bind((ip, port))
                    except OSError:
                        return False
                        
        return True
