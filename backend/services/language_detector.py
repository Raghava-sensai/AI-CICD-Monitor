"""
Language Detector - Identifies the primary programming language of a repository.
"""

import os
from pathlib import Path
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Extension → language mapping
EXTENSION_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rb": "ruby",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".swift": "swift",
    ".dart": "dart",
}

# Manifest files that unambiguously identify a language/runtime
MANIFEST_MAP: dict[str, str] = {
    "package.json": "javascript",
    "requirements.txt": "python",
    "Pipfile": "python",
    "pyproject.toml": "python",
    "go.mod": "go",
    "Gemfile": "ruby",
    "pom.xml": "java",
    "build.gradle": "java",
    "Cargo.toml": "rust",
    "composer.json": "php",
    "*.csproj": "csharp",
    "pubspec.yaml": "dart",
}

# Language → recommended Dockerfile base image
DOCKER_IMAGE_MAP: dict[str, str] = {
    "python": "python:3.11-slim",
    "javascript": "node:20-alpine",
    "typescript": "node:20-alpine",
    "go": "golang:1.22-alpine",
    "ruby": "ruby:3.3-slim",
    "java": "eclipse-temurin:21-jre-alpine",
    "rust": "rust:1.78-slim",
    "php": "php:8.3-fpm-alpine",
    "csharp": "mcr.microsoft.com/dotnet/sdk:8.0",
    "dart": "dart:stable",
}


class LanguageDetector:
    """
    Detects the primary language of a project directory using:
      1. Manifest file presence (fast, reliable)
      2. Source file extension frequency (fallback)
    """

    def detect(self, project_path: str) -> dict:
        """
        Returns a detection result dict:
            {
                "language": str,
                "confidence": "high" | "medium" | "low",
                "docker_image": str,
                "method": str
            }
        """
        root = Path(project_path)

        # 1. Check manifest files
        language = self._check_manifests(root)
        if language:
            return self._result(language, confidence="high", method="manifest")

        # 2. Count source file extensions
        language = self._count_extensions(root)
        if language:
            return self._result(language, confidence="medium", method="extension_count")

        logger.warning(f"Could not detect language for {project_path}")
        return self._result("unknown", confidence="low", method="none")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_manifests(self, root: Path) -> Optional[str]:
        for filename, language in MANIFEST_MAP.items():
            if "*" in filename:
                # glob pattern
                if any(root.glob(filename)):
                    return language
            elif (root / filename).exists():
                return language
        return None

    def _count_extensions(self, root: Path) -> Optional[str]:
        counts: dict[str, int] = {}
        for path in root.rglob("*"):
            if path.is_file():
                ext = path.suffix.lower()
                lang = EXTENSION_MAP.get(ext)
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return None
        return max(counts, key=counts.__getitem__)

    @staticmethod
    def _result(language: str, confidence: str, method: str) -> dict:
        return {
            "language": language,
            "confidence": confidence,
            "docker_image": DOCKER_IMAGE_MAP.get(language, "ubuntu:22.04"),
            "method": method,
        }
