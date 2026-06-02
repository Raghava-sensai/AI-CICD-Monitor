"""
Parser Utility - Helpers for parsing build logs and configuration files.
"""

import re
import yaml
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)


# ------------------------------------------------------------------
# Log Parsing
# ------------------------------------------------------------------


def extract_error_blocks(log_text: str, context_lines: int = 3) -> list[dict]:
    """
    Find error lines in *log_text* and return them with surrounding context.

    Args:
        log_text:      Raw log string.
        context_lines: Number of lines above/below the error to include.

    Returns:
        List of dicts, each with keys: line_number, line, context.
    """
    error_pattern = re.compile(
        r"(error|exception|traceback|failed|fatal)",
        re.IGNORECASE,
    )
    lines = log_text.splitlines()
    results = []
    for i, line in enumerate(lines):
        if error_pattern.search(line):
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)
            results.append(
                {
                    "line_number": i + 1,
                    "line": line.strip(),
                    "context": lines[start:end],
                }
            )
    return results


def extract_build_time(log_text: str) -> Optional[float]:
    """
    Try to parse a build duration like "BUILD SUCCESS in 42.3s" or
    "Finished in 1m 23s".

    Returns seconds as float, or None if not found.
    """
    patterns = [
        re.compile(r"in\s+([\d.]+)s\b"),
        re.compile(r"([\d.]+)\s+seconds"),
        re.compile(r"(\d+)m\s*(\d+)s"),  # "1m 23s" → 83s
    ]
    for pattern in patterns:
        m = pattern.search(log_text)
        if m:
            if len(m.groups()) == 2:
                return int(m.group(1)) * 60 + int(m.group(2))
            return float(m.group(1))
    return None


# ------------------------------------------------------------------
# YAML / Config Parsing
# ------------------------------------------------------------------


def parse_yaml_file(path: str) -> dict:
    """Load and return a YAML file as a dict. Returns {} on error."""
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f) or {}
    except (FileNotFoundError, yaml.YAMLError) as exc:
        logger.error(f"Failed to parse YAML at {path}: {exc}")
        return {}


def parse_yaml_string(content: str) -> dict:
    """Parse a YAML string. Returns {} on error."""
    try:
        return yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        logger.error(f"YAML parse error: {exc}")
        return {}


# ------------------------------------------------------------------
# Text Utilities
# ------------------------------------------------------------------


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes (terminal colours) from *text*."""
    ansi_escape = re.compile(r"\x1B[@-_][0-?]*[ -/]*[@-~]")
    return ansi_escape.sub("", text)


def truncate(text: str, max_length: int = 500, suffix: str = "...") -> str:
    """Truncate *text* to *max_length* characters, appending *suffix*."""
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix
