"""
AI-CICD-Monitor - Main Flask Application Entry Point
"""

import os
import yaml
from flask import Flask, jsonify, make_response
from flask_cors import CORS

from routes.webhook import webhook_bp
from routes.deployment import deployment_bp
from routes.monitor import monitor_bp
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# HTML Dashboard (served at GET /)
# ---------------------------------------------------------------------------
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI-CICD-Monitor</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{
      --bg:#0d0f1a;--surface:#13162a;--surface2:#1a1e35;
      --border:rgba(255,255,255,.07);
      --accent:#6c63ff;--accent2:#00d4aa;--accent3:#ff6b6b;
      --text:#e8eaf0;--muted:#7a7f99;
      --get:#00d4aa;--post:#6c63ff;--radius:14px;
    }
    body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
    body::before{
      content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
      background:
        radial-gradient(ellipse 80% 50% at 20% -10%,rgba(108,99,255,.18) 0%,transparent 60%),
        radial-gradient(ellipse 60% 40% at 80% 110%,rgba(0,212,170,.12) 0%,transparent 60%);
    }
    .wrap{position:relative;z-index:1;max-width:1100px;margin:0 auto;padding:0 24px 80px}

    /* Header */
    header{padding:52px 0 40px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
    .logo{width:52px;height:52px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:14px;display:grid;place-items:center;font-size:26px;box-shadow:0 8px 32px rgba(108,99,255,.45);flex-shrink:0}
    .title-block h1{font-size:2rem;font-weight:800;letter-spacing:-.5px}
    .title-block h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .title-block p{color:var(--muted);font-size:.95rem;margin-top:4px}
    .badge{margin-left:auto;display:flex;align-items:center;gap:8px;background:rgba(0,212,170,.12);border:1px solid rgba(0,212,170,.3);color:var(--accent2);padding:6px 14px;border-radius:999px;font-size:.82rem;font-weight:600}
    .badge::before{content:'';width:8px;height:8px;background:var(--accent2);border-radius:50%;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(1.4)}}

    /* Stats */
    .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;margin-bottom:40px}
    .stat-card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px 22px;transition:transform .2s,box-shadow .2s}
    .stat-card:hover{transform:translateY(-3px);box-shadow:0 12px 36px rgba(0,0,0,.4)}
    .stat-card .label{font-size:.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
    .stat-card .value{font-size:1.8rem;font-weight:700}
    .stat-card .sub{font-size:.78rem;color:var(--muted);margin-top:4px}
    .c-purple{color:var(--accent)}.c-green{color:var(--accent2)}.c-red{color:var(--accent3)}

    /* Section title */
    .section-title{font-size:.78rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:16px;display:flex;align-items:center;gap:10px}
    .section-title::after{content:'';flex:1;height:1px;background:var(--border)}

    /* Endpoint groups */
    .groups{display:grid;gap:24px}
    .group{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
    .group-header{padding:16px 22px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:12px}
    .group-icon{font-size:18px}
    .group-name{font-weight:700;font-size:1rem}
    .group-desc{font-size:.82rem;color:var(--muted);margin-left:auto}
    .endpoint{display:flex;align-items:center;gap:16px;padding:14px 22px;border-bottom:1px solid var(--border);transition:background .15s}
    .endpoint:last-child{border-bottom:none}
    .endpoint:hover{background:rgba(255,255,255,.03)}
    .method{font-family:'JetBrains Mono',monospace;font-size:.72rem;font-weight:700;padding:4px 10px;border-radius:6px;min-width:52px;text-align:center;flex-shrink:0}
    .method.GET{background:rgba(0,212,170,.15);color:var(--get)}
    .method.POST{background:rgba(108,99,255,.2);color:var(--post)}
    .ep-path{font-family:'JetBrains Mono',monospace;font-size:.85rem;color:var(--text);flex:1}
    .ep-desc{font-size:.82rem;color:var(--muted);text-align:right}
    .ep-link{text-decoration:none;font-size:.75rem;color:var(--accent);border:1px solid rgba(108,99,255,.35);padding:3px 10px;border-radius:6px;transition:background .15s,color .15s;white-space:nowrap}
    .ep-link:hover{background:rgba(108,99,255,.2);color:#fff}

    /* Quick-start */
    .quickstart{margin-top:40px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
    .quickstart-header{padding:16px 22px;background:var(--surface2);border-bottom:1px solid var(--border);font-weight:700;display:flex;align-items:center;gap:10px}
    .quickstart pre{padding:20px 22px;font-family:'JetBrains Mono',monospace;font-size:.82rem;color:#a8b4d8;line-height:1.8;overflow-x:auto}
    .cmd-comment{color:#4a5270}.cmd-val{color:#f9826c}

    /* Footer */
    footer{margin-top:60px;padding-top:24px;border-top:1px solid var(--border);color:var(--muted);font-size:.82rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
    footer a{color:var(--accent);text-decoration:none}
    footer a:hover{text-decoration:underline}
    @media(max-width:640px){.ep-desc{display:none}.badge{margin-left:0}header{padding-top:32px}}
  </style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="logo">&#x1F680;</div>
    <div class="title-block">
      <h1>AI-CICD-<span>Monitor</span></h1>
      <p>Automated deployment &amp; AI-powered pipeline diagnostics</p>
    </div>
    <div class="badge">v1.0.0 &nbsp; RUNNING</div>
  </header>

  <div class="stats">
    <div class="stat-card">
      <div class="label">CPU Usage</div>
      <div class="value c-purple" id="cpu">&#8212;</div>
      <div class="sub">Live metric</div>
    </div>
    <div class="stat-card">
      <div class="label">Memory</div>
      <div class="value c-green" id="mem">&#8212;</div>
      <div class="sub">Live metric</div>
    </div>
    <div class="stat-card">
      <div class="label">Disk</div>
      <div class="value c-red" id="disk">&#8212;</div>
      <div class="sub">Live metric</div>
    </div>
    <div class="stat-card">
      <div class="label">Deployments</div>
      <div class="value c-purple" id="deps">&#8212;</div>
      <div class="sub">Total tracked</div>
    </div>
  </div>

  <div class="section-title">API Endpoints</div>
  <div class="groups">

    <div class="group">
      <div class="group-header">
        <span class="group-icon">&#x1F517;</span>
        <span class="group-name">Webhook</span>
        <span class="group-desc">GitHub event receiver</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/webhook/ping</span>
        <span class="ep-desc">Health check</span>
        <a href="/api/webhook/ping" target="_blank" class="ep-link">Try &#x2197;</a>
      </div>
      <div class="endpoint">
        <span class="method POST">POST</span>
        <span class="ep-path">/api/webhook/github</span>
        <span class="ep-desc">Receive push / PR / workflow events</span>
      </div>
    </div>

    <div class="group">
      <div class="group-header">
        <span class="group-icon">&#x1F6A2;</span>
        <span class="group-name">Deployment</span>
        <span class="group-desc">Trigger, track &amp; rollback</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/deployment/</span>
        <span class="ep-desc">List all deployments</span>
        <a href="/api/deployment/" target="_blank" class="ep-link">Try &#x2197;</a>
      </div>
      <div class="endpoint">
        <span class="method POST">POST</span>
        <span class="ep-path">/api/deployment/trigger</span>
        <span class="ep-desc">Manually trigger a deployment</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/deployment/&lt;id&gt;</span>
        <span class="ep-desc">Get deployment details</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/deployment/&lt;id&gt;/status</span>
        <span class="ep-desc">Live deployment status</span>
      </div>
      <div class="endpoint">
        <span class="method POST">POST</span>
        <span class="ep-path">/api/deployment/&lt;id&gt;/rollback</span>
        <span class="ep-desc">Roll back to previous version</span>
      </div>
    </div>

    <div class="group">
      <div class="group-header">
        <span class="group-icon">&#x1F4E1;</span>
        <span class="group-name">Monitor</span>
        <span class="group-desc">Health, analysis &amp; AI diagnostics</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/monitor/health</span>
        <span class="ep-desc">CPU / memory / disk metrics</span>
        <a href="/api/monitor/health" target="_blank" class="ep-link">Try &#x2197;</a>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/monitor/projects</span>
        <span class="ep-desc">List monitored projects</span>
        <a href="/api/monitor/projects" target="_blank" class="ep-link">Try &#x2197;</a>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/monitor/projects/&lt;id&gt;</span>
        <span class="ep-desc">Single project details</span>
      </div>
      <div class="endpoint">
        <span class="method POST">POST</span>
        <span class="ep-path">/api/monitor/pipeline/analyze</span>
        <span class="ep-desc">Parse build logs for errors</span>
      </div>
      <div class="endpoint">
        <span class="method POST">POST</span>
        <span class="ep-path">/api/monitor/errors/solve</span>
        <span class="ep-desc">AI-powered fix suggestions</span>
      </div>
      <div class="endpoint">
        <span class="method GET">GET</span>
        <span class="ep-path">/api/monitor/reports</span>
        <span class="ep-desc">List health reports</span>
        <a href="/api/monitor/reports" target="_blank" class="ep-link">Try &#x2197;</a>
      </div>
    </div>
  </div>

  <div class="quickstart">
    <div class="quickstart-header">&#x26A1; Quick Test (copy &amp; paste into terminal)</div>
    <pre><span class="cmd-comment"># Analyze a failing build log</span>
curl -X POST http://localhost:5000/api/monitor/pipeline/analyze \
  -H <span class="cmd-val">"Content-Type: application/json"</span> \
  -d <span class="cmd-val">'{"logs":"ModuleNotFoundError: No module named flask\\nBuild FAILED in 5.2s"}'</span>

<span class="cmd-comment"># Get an AI fix suggestion</span>
curl -X POST http://localhost:5000/api/monitor/errors/solve \
  -H <span class="cmd-val">"Content-Type: application/json"</span> \
  -d <span class="cmd-val">'{"error":"npm ERR! Cannot find module express"}'</span>

<span class="cmd-comment"># Trigger a deployment</span>
curl -X POST http://localhost:5000/api/deployment/trigger \
  -H <span class="cmd-val">"Content-Type: application/json"</span> \
  -d <span class="cmd-val">'{"repo":"your-org/your-repo","branch":"main"}'</span></pre>
  </div>

  <footer>
    <span>AI-CICD-Monitor &copy; 2026</span>
    <span><a href="https://github.com/your-org/AI-CICD-Monitor" target="_blank">GitHub &#x2192;</a></span>
  </footer>
</div>

<script>
async function loadStats() {
  try {
    const [health, deps] = await Promise.all([
      fetch('/api/monitor/health').then(r => r.json()),
      fetch('/api/deployment/').then(r => r.json())
    ]);
    document.getElementById('cpu').textContent  = health.cpu_percent   != null ? health.cpu_percent.toFixed(1)   + '%' : 'N/A';
    document.getElementById('mem').textContent  = health.memory_percent != null ? health.memory_percent.toFixed(1) + '%' : 'N/A';
    document.getElementById('disk').textContent = health.disk_percent   != null ? health.disk_percent.toFixed(1)  + '%' : 'N/A';
    document.getElementById('deps').textContent = Array.isArray(deps.deployments) ? deps.deployments.length : 0;
  } catch(e) { console.warn('Stats fetch failed', e); }
}
loadStats();
setInterval(loadStats, 10000);
</script>
</body>
</html>"""


def load_config(path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    config_path = os.path.join(os.path.dirname(__file__), "..", path)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_app(config: dict = None) -> Flask:
    """Application factory."""
    app = Flask(__name__)
    CORS(app)

    if config is None:
        config = load_config()

    app.config.update(config)

    # Register blueprints
    app.register_blueprint(webhook_bp, url_prefix="/api/webhook")
    app.register_blueprint(deployment_bp, url_prefix="/api/deployment")
    app.register_blueprint(monitor_bp, url_prefix="/api/monitor")

    # ── HTML Dashboard ────────────────────────────────────────────────
    @app.route("/")
    def index():
        """Serve the HTML dashboard to browsers."""
        resp = make_response(DASHBOARD_HTML)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    # ── JSON API index (for scripts / curl) ───────────────────────────
    @app.route("/api")
    def api_index():
        """Machine-readable API index."""
        return jsonify({
            "name": "AI-CICD-Monitor",
            "version": "1.0.0",
            "status": "running",
            "routes": {
                "webhook":    "/api/webhook",
                "deployment": "/api/deployment",
                "monitor":    "/api/monitor",
            }
        }), 200

    # ── Error Handlers ────────────────────────────────────────────────
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "error": "Not Found",
            "message": "The requested endpoint does not exist.",
            "hint": "Visit http://localhost:5000/ for the dashboard."
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({
            "error": "Method Not Allowed",
            "message": str(e),
        }), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({
            "error": "Internal Server Error",
            "message": "Something went wrong. Check logs/ for details."
        }), 500

    logger.info("AI-CICD-Monitor backend started.")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
