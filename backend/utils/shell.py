"""
Shell Utility - Safe subprocess wrapper for running system commands.
"""

import subprocess
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)


def run_command(
    cmd: list[str],
    cwd: Optional[str] = None,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> tuple[str, str, int]:
    """
    Execute *cmd* in a subprocess.

    Args:
        cmd:     Command tokens, e.g. ["git", "clone", url, dest].
        cwd:     Working directory for the subprocess.
        timeout: Maximum seconds to wait before raising TimeoutExpired.
        env:     Optional environment variables to merge with the current env.

    Returns:
        (stdout, stderr, return_code)
    """
    logger.debug(f"Running: {' '.join(cmd)} (cwd={cwd})")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            logger.warning(
                f"Command exited {result.returncode}: {' '.join(cmd)}\n"
                f"stderr: {result.stderr[:500]}"
            )
        return result.stdout, result.stderr, result.returncode

    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        return "", f"Timed out after {timeout}s", -1

    except FileNotFoundError:
        msg = f"Executable not found: {cmd[0]}"
        logger.error(msg)
        return "", msg, -1

    except Exception as exc:
        logger.error(f"Unexpected error running command: {exc}")
        return "", str(exc), -1
