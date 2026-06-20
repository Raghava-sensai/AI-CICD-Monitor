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
    "index.html": "static",
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
    "static": "nginx:alpine",
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
                "method": str,
                "manifests": list
            }
        """
        root = Path(project_path)

        # 1. Check manifest files
        manifests = self._find_all_manifests(root)
        
        # If we found static HTML but ALSO found other strong manifests (like package.json), remove the static HTML manifest.
        non_static_manifests = [m for m in manifests if m["language"] != "static"]
        if non_static_manifests and len(non_static_manifests) < len(manifests):
            manifests = non_static_manifests
            
        # We might find multiple package.jsons in frontend/ and backend/, etc.
        if len(manifests) == 1:
            return self._result(manifests[0]["language"], confidence="high", method="manifest", manifests=manifests)
        elif len(manifests) > 1:
            return self._result("ambiguous", confidence="low", method="multiple_manifests", manifests=manifests)

        # 2. Count source file extensions
        language = self._count_extensions(root)
        if language:
            return self._result(language, confidence="medium", method="extension_count", manifests=[])

        logger.warning(f"Could not detect language for {project_path}")
        return self._result("unknown", confidence="low", method="none", manifests=[])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _find_all_manifests(self, root: Path) -> list[dict]:
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            # Skip irrelevant directories
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "vendor", "venv", "__pycache__", "build", "target", "dist")]
            
            # Limit depth to 2 levels to avoid deep scanning into obscure sub-packages
            try:
                depth = Path(dirpath).relative_to(root).parts
                if len(depth) > 2:
                    continue
            except ValueError:
                continue
                
            for filename in filenames:
                for pat, lang in MANIFEST_MAP.items():
                    if (pat.startswith("*") and filename.endswith(pat[1:])) or filename == pat:
                        rel_file = os.path.relpath(os.path.join(dirpath, filename), root)
                        rel_dir = os.path.relpath(dirpath, root)
                        found.append({
                            "file": rel_file.replace("\\", "/"),
                            "language": lang,
                            "dir": rel_dir.replace("\\", "/")
                        })
        return found

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
    def _result(language: str, confidence: str, method: str, manifests: list) -> dict:
        return {
            "language": language,
            "confidence": confidence,
            "docker_image": DOCKER_IMAGE_MAP.get(language, "ubuntu:22.04"),
            "method": method,
            "manifests": manifests,
        }
