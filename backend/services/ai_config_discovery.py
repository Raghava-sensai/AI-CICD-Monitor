import os
import json
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger(__name__)

class AIConfigDiscovery:
    """
    Uses Generative AI to analyze DEPLOYMENT.md or README.md to infer project configuration.
    Outputs strict JSON with 'runtime', 'working_directory', and 'confidence'.
    Never outputs exact execution commands to prevent AI hallucinations/injection.
    """
    def __init__(self):
        self.api_key = os.environ.get("GEMINI_API_KEY", "")
        self.enabled = bool(self.api_key)

    def discover(self, project_path: str) -> dict:
        """
        Looks for DEPLOYMENT.md or README.md, parses it, and returns:
        { "runtime": "node", "working_directory": "frontend", "confidence": 0.95 }
        """
        if not self.enabled:
            logger.warning("AIConfigDiscovery skipped: GEMINI_API_KEY not set.")
            return self._fail()

        root = Path(project_path)
        content = ""
        source_file = ""

        # Priority 1: DEPLOYMENT.md
        for filename in ["DEPLOYMENT.md", "deployment.md"]:
            p = root / filename
            if p.exists():
                content = p.read_text(encoding="utf-8", errors="ignore")
                source_file = filename
                break

        # Priority 2: README.md
        if not content:
            for filename in ["README.md", "readme.md", "README"]:
                p = root / filename
                if p.exists():
                    content = p.read_text(encoding="utf-8", errors="ignore")
                    source_file = filename
                    break

        if not content:
            logger.info("No DEPLOYMENT.md or README.md found for AI analysis.")
            return self._fail()

        # Truncate content to avoid token limits (keep first 10,000 chars)
        content = content[:10000]

        logger.info(f"Analyzing {source_file} with AI for configuration discovery.")

        prompt = f"""
You are a CI/CD pipeline configuration expert.
Analyze the following markdown file ({source_file}) from a code repository.
Determine the primary programming language/runtime and the relative working directory for the application.

Valid runtimes are: python, javascript, typescript, java, java-gradle, go, ruby, rust, php.
If the app requires Node.js, the runtime is 'javascript' or 'typescript'.

Output EXACTLY AND ONLY a JSON object with this schema:
{{
  "runtime": "string (one of the valid runtimes)",
  "working_directory": "string (relative path to the folder containing the project, e.g. '.' or 'frontend')",
  "confidence": number (float between 0.0 and 1.0, where 1.0 means you are absolutely certain)
}}

Do NOT include markdown backticks or any other text. Only valid JSON.

File Content:
{content}
"""

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            response = model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Remove possible markdown formatting from the response
            if result_text.startswith("```json"):
                result_text = result_text[7:]
            if result_text.endswith("```"):
                result_text = result_text[:-3]
            result_text = result_text.strip()

            data = json.loads(result_text)
            
            confidence = float(data.get("confidence", 0.0))
            runtime = data.get("runtime", "unknown")
            work_dir = data.get("working_directory", ".")
            
            # Sanitize paths to prevent directory traversal
            if ".." in work_dir or work_dir.startswith("/"):
                work_dir = "."
                confidence = 0.0
                
            return {
                "runtime": runtime,
                "working_directory": work_dir,
                "confidence": confidence,
                "source": source_file
            }

        except Exception as e:
            logger.error(f"AI config discovery failed: {e}")
            return self._fail()

    def _fail(self) -> dict:
        return {
            "runtime": "unknown",
            "working_directory": ".",
            "confidence": 0.0,
            "source": None
        }
