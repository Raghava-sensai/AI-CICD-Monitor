"""
Port Manager - Allocates and reclaims TCP ports for deployments.
"""

import socket
from utils.logger import setup_logger

logger = setup_logger(__name__)

DEFAULT_PORT_RANGE_START = 8100
DEFAULT_PORT_RANGE_END = 9000


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
        """Return True if the OS reports the port as unbound."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return True
            except OSError:
                return False
