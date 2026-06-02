"""
AI Error Solver - Uses an LLM to suggest fixes for pipeline and runtime errors.
"""

import os
import json
from typing import Optional
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Optionally use OpenAI or Gemini based on available env vars.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


class AIErrorSolver:
    """
    Provides AI-powered root-cause analysis and fix suggestions
    for build / deployment errors.
    """

    def __init__(self):
        self._backend = self._detect_backend()
        logger.info(f"AIErrorSolver using backend: {self._backend}")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def suggest_fix(self, error_text: str, context: Optional[dict] = None) -> dict:
        """Legacy fix endpoint."""
        context = context or {}
        if self._backend == "gemini":
            return self._ask_gemini_fix(error_text, context)
        elif self._backend == "openai":
            return self._ask_openai_fix(error_text, context)
        else:
            return self._rule_based_fallback_fix(error_text)

    def explain_error(self, error_text: str, context: Optional[dict] = None) -> dict:
        """
        New explanation endpoint.
        Returns:
        {
          "explanation": "...",
          "likely_file": "...",
          "suggested_code": "...",
          "confidence": 0.94
        }
        """
        context = context or {}
        if self._backend == "gemini":
            return self._ask_gemini_explain(error_text, context)
        elif self._backend == "openai":
            return self._ask_openai_explain(error_text, context)
        else:
            return self._rule_based_fallback_explain(error_text)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _ask_gemini_explain(self, error_text: str, context: dict) -> dict:
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = self._build_explain_prompt(error_text, context)
            response = model.generate_content(prompt)
            return self._parse_json_response(response.text)
        except Exception as exc:
            logger.warning(f"Gemini call failed: {exc}. Falling back.")
            return self._rule_based_fallback_explain(error_text)
            
    def _ask_gemini_fix(self, error_text: str, context: dict) -> dict:
        return {"summary": "Gemini fix not implemented", "root_cause": "", "steps": [], "references": [], "confidence": 0.0}

    def _ask_openai_explain(self, error_text: str, context: dict) -> dict:
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = self._build_explain_prompt(error_text, context)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
                response_format={"type": "json_object"}
            )
            return self._parse_json_response(completion.choices[0].message.content)
        except Exception as exc:
            logger.warning(f"OpenAI call failed: {exc}. Falling back.")
            return self._rule_based_fallback_explain(error_text)
            
    def _ask_openai_fix(self, error_text: str, context: dict) -> dict:
        return {"summary": "OpenAI fix not implemented", "root_cause": "", "steps": [], "references": [], "confidence": 0.0}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_backend() -> str:
        if GEMINI_API_KEY:
            return "gemini"
        if OPENAI_API_KEY:
            return "openai"
        return "rule_based"

    @staticmethod
    def _build_explain_prompt(error_text: str, context: dict) -> str:
        ctx_str = "\n".join(f"{k}: {v}" for k, v in context.items())
        return (
            "You are an expert developer. Explain the following error and provide a fix.\n"
            "Return ONLY a valid JSON object with EXACTLY these keys:\n"
            '{"explanation": "String explaining the error", '
            '"likely_file": "File name where it happened", '
            '"suggested_code": "The code snippet to fix it", '
            '"confidence": Float between 0.0 and 1.0}\n\n'
            f"Context:\n{ctx_str}\n\nError:\n{error_text}"
        )

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        try:
            # Strip markdown blocks if any
            clean = text.strip()
            if clean.startswith("```json"):
                clean = clean[7:]
            if clean.startswith("```"):
                clean = clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            return json.loads(clean.strip())
        except Exception:
            return {
                "explanation": "Failed to parse AI response as JSON.",
                "likely_file": "unknown",
                "suggested_code": "",
                "confidence": 0.0
            }

    @staticmethod
    def _rule_based_fallback_explain(error_text: str) -> dict:
        """Simple keyword-based explanation when no LLM is available."""
        if "ModuleNotFoundError" in error_text:
            return {
                "explanation": "A required Python package is missing from the environment.",
                "likely_file": "requirements.txt",
                "suggested_code": "flask\nrequests",
                "confidence": 0.98
            }
        elif "npm ERR!" in error_text:
            return {
                "explanation": "NPM failed to install dependencies, likely due to a missing package or network issue.",
                "likely_file": "package.json",
                "suggested_code": "npm install",
                "confidence": 0.85
            }
        else:
            return {
                "explanation": f"Rule-based generic explanation for: {error_text[:80]}...",
                "likely_file": "unknown",
                "suggested_code": "# Needs manual review",
                "confidence": 0.35
            }
            
    @staticmethod
    def _rule_based_fallback_fix(error_text: str) -> dict:
        return {
            "summary": "Use the /explain endpoint instead.",
            "root_cause": "",
            "steps": [],
            "references": [],
            "confidence": 0.0,
        }
