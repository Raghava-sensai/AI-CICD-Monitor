from flask import Blueprint, jsonify

templates_bp = Blueprint("templates", __name__)

TEMPLATES = {
    "python": {
        "name": "Python (Flask/FastAPI/Django)",
        "content": "project_name=my-python-app\nssl=true\n\n## Build Command\n```bash\npython3 -m venv venv\nsource venv/bin/activate\npip install -r requirements.txt\n```\n\n## Start Command\n```bash\nsource venv/bin/activate\npython app.py\n```"
    },
    "node": {
        "name": "Node.js (Express/Next.js)",
        "content": "project_name=my-node-app\nssl=true\n\n## Build Command\n```bash\nnpm install\n```\n\n## Start Command\n```bash\nnpm run prod\n```"
    },
    "go": {
        "name": "Golang",
        "content": "project_name=my-go-app\nssl=true\n\n## Build Command\n```bash\ngo build -o main .\n```\n\n## Start Command\n```bash\n./main\n```"
    },
    "static": {
        "name": "Static HTML/React (Serve with Python)",
        "content": "project_name=my-static-site\nssl=true\n\n## Start Command\n```bash\npython3 -m http.server $PORT\n```"
    }
}

@templates_bp.route("/", methods=["GET"])
def get_templates():
    """Return available language templates for deployment.txt."""
    return jsonify(TEMPLATES), 200

@templates_bp.route("/<string:language>", methods=["GET"])
def get_template(language: str):
    """Return a specific template by language ID."""
    template = TEMPLATES.get(language.lower())
    if not template:
        return jsonify({"error": "Template not found"}), 404
    return jsonify(template), 200
