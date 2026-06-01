"""
AI Error Solver - Uses an LLM to suggest fixes for pipeline and runtime errors.
"""

import os
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

    Supported backends (auto-detected):
      1. Google Gemini  (GEMINI_API_KEY)
      2. OpenAI GPT-4   (OPENAI_API_KEY)
      3. Rule-based fallback (no key required)
    """

    def __init__(self):
        self._backend = self._detect_backend()
        logger.info(f"AIErrorSolver using backend: {self._backend}")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def suggest_fix(self, error_text: str, context: Optional[dict] = None) -> dict:
        """
        Analyse *error_text* and return a structured fix suggestion.

        Returns:
            {
                "summary": str,
                "root_cause": str,
                "steps": list[str],
                "references": list[str],
                "confidence": float  # 0.0 – 1.0
            }
        """
        context = context or {}
        if self._backend == "gemini":
            return self._ask_gemini(error_text, context)
        elif self._backend == "openai":
            return self._ask_openai(error_text, context)
        else:
            return self._rule_based_fallback(error_text)

    # ------------------------------------------------------------------
    # Backends
    # ------------------------------------------------------------------

    def _ask_gemini(self, error_text: str, context: dict) -> dict:
        """Call the Gemini Generative Language API."""
        try:
            import google.generativeai as genai  # type: ignore

            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            prompt = self._build_prompt(error_text, context)
            response = model.generate_content(prompt)
            return self._parse_llm_response(response.text)
        except Exception as exc:
            logger.warning(f"Gemini call failed: {exc}. Falling back to rule-based.")
            return self._rule_based_fallback(error_text)

    def _ask_openai(self, error_text: str, context: dict) -> dict:
        """Call the OpenAI Chat Completions API."""
        try:
            from openai import OpenAI  # type: ignore

            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = self._build_prompt(error_text, context)
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512,
            )
            return self._parse_llm_response(completion.choices[0].message.content)
        except Exception as exc:
            logger.warning(f"OpenAI call failed: {exc}. Falling back to rule-based.")
            return self._rule_based_fallback(error_text)

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
    def _build_prompt(error_text: str, context: dict) -> str:
        ctx_str = "\n".join(f"{k}: {v}" for k, v in context.items())
        return (
            "You are a senior DevOps engineer. Analyse the following CI/CD error and "
            "provide: (1) a one-sentence summary, (2) the root cause, "
            "(3) numbered fix steps, (4) any relevant doc links.\n\n"
            f"Context:\n{ctx_str}\n\nError:\n{error_text}"
        )

    @staticmethod
    def _parse_llm_response(text: str) -> dict:
        """Best-effort parse of a free-text LLM response."""
        return {
            "summary": text[:200],
            "root_cause": "",
            "steps": [text],
            "references": [],
            "confidence": 0.75,
        }

    @staticmethod
    def _rule_based_fallback(error_text: str) -> dict:
        """Simple keyword-based suggestions when no LLM is available."""
        steps = []
        if "ModuleNotFoundError" in error_text or "No module named" in error_text:
            steps = [
                "Run `pip install -r requirements.txt`.",
                "Check that you are using the correct virtual environment.",
            ]
        elif "npm ERR!" in error_text:
            steps = [
                "Run `npm install` to restore dependencies.",
                "Delete `node_modules` and `package-lock.json`, then run `npm install` again.",
            ]
        elif "permission denied" in error_text.lower():
            steps = [
                "Check file/directory ownership with `ls -la`.",
                "Run the failing command with appropriate permissions.",
            ]
        else:
            steps = [
                "Review the full log output for context.",
                "Search the error message online or in the project issue tracker.",
            ]

        return {
            "summary": f"Rule-based suggestion for: {error_text[:80]}...",
            "root_cause": "Determined via pattern matching (no LLM configured).",
            "steps": steps,
            "references": [],
            "confidence": 0.5,
        }
