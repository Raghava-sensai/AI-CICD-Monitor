import re
from typing import Any

class SecretSanitizer:
    """
    Sanitizes sensitive information (GitHub PATs, API keys, etc.) from strings.
    """
    
    # Common secret patterns
    PATTERNS = [
        
        re.compile(r'(gh' + r'[pousr]_[a-zA-Z0-9]{36,})'),
        re.compile(r'(github' + r'_pat_[a-zA-Z0-9_]{82})'),
        
        # OpenAI API Keys
        re.compile(r'(sk' + r'-[a-zA-Z0-9]{48,})'),
        re.compile(r'(sk' + r'-proj-[a-zA-Z0-9_-]{48,})'),
        
        # Google Gemini / GCP API Keys (starts with AIza)
        re.compile(r'(AIza' + r'[0-9A-Za-z-_]{35})'),
        
        # Basic Auth HTTP(S) URLs (e.g. https://user:pass@github.com)
        re.compile(r'(https?://)[^/:]+:[^/@]+(@)'),
    ]

    @classmethod
    def sanitize(cls, text: Any) -> str:
        """Redact secrets from a string."""
        if text is None:
            return ""
        
        # Convert to string if not already
        if not isinstance(text, str):
            text = str(text)
            
        for pattern in cls.PATTERNS:
            # For the basic auth URL, we keep the protocol and the @ symbol, mask the credentials
            if "https?://" in pattern.pattern:
                text = pattern.sub(r'\1***:***\2', text)
            else:
                text = pattern.sub(r'[REDACTED]', text)
                
        return text

    @classmethod
    def register_dynamic_secret(cls, secret: str):
        """
        Dynamically register a secret to be sanitized.
        Useful for environment variables that don't match standard patterns.
        """
        if not secret or len(secret) < 8:
            return
            
        # Escape the secret and add a pattern
        escaped = re.escape(secret)
        cls.PATTERNS.append(re.compile(f'({escaped})'))
