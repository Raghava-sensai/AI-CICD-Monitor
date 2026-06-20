from functools import wraps
from flask import request, jsonify
from services.github_service import GithubService
from utils.sanitizer import SecretSanitizer
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Simple in-memory cache to avoid rate-limiting if the user spams requests
_token_cache = {}

def require_github_token(f):
    """
    Flask decorator that enforces GitHub Token authentication.
    - Checks X-GitHub-Token header or json 'github_token'.
    - Validates token against GitHub.
    - Injects 'github_token' into the decorated function kwargs.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get("X-GitHub-Token")
        
        # Fallback to checking the form or JSON payload
        if not token:
            if request.is_json:
                data = request.get_json(silent=True) or {}
                token = data.get("github_token")
            else:
                token = request.form.get("github_token")
                
        if token:
            # Register the token to be sanitized in logs
            SecretSanitizer.register_dynamic_secret(token)
                
            # Check cache
            if token in _token_cache:
                validation = _token_cache[token]
            else:
                validation = GithubService.validate_token(token)
                if validation["valid"]:
                    _token_cache[token] = validation
                    
            if not validation["valid"]:
                logger.warning("Rejected request due to invalid GitHub PAT.")
                return jsonify({"error": f"Unauthorized: {validation.get('error', 'Invalid GitHub Token')}"}), 401
                
            logger.info(f"Authenticated as {validation['username']} ({validation['account_type']})")
            
        kwargs['github_token'] = token if token else None
        
        return f(*args, **kwargs)
        
    return decorated_function
