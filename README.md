# 🚀 AI-CICD-Monitor

> **Automated CI/CD deployment monitor with AI-powered error analysis.**  
> Listen to GitHub webhooks → auto-deploy projects → monitor health → diagnose failures using AI.

---

## 📋 Table of Contents

- [Features](#-features)
- [Architecture](#-architecture)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Environment Variables](#-environment-variables)
- [How It Works](#-how-it-works)
- [Testing](#-testing)
- [Roadmap](#-roadmap)

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔗 **GitHub Webhooks** | Listens for `push`, `pull_request`, and `workflow_run` events |
| 🚢 **Auto Deploy** | Clones repo, installs deps, starts app automatically on push to `main` |
| 🌐 **Port Manager** | Allocates free TCP ports per deployment (range 8100–9000) |
| 🔒 **SSL Manager** | Provisions TLS via Let's Encrypt or self-signed certs |
| 🧠 **AI Error Solver** | Uses Gemini / GPT-4 / rule-based fallback to suggest fixes |
| 🔍 **Pipeline Analyzer** | Parses build logs — errors, warnings, test summary, duration |
| 📡 **Monitor Worker** | Background health polling with periodic JSON reports |
| 🗂️ **Language Detector** | Auto-detects Python, Node, Go, Ruby, Java, Rust, and more |

---

## 🗂 Architecture

```
AI-CICD-Monitor/
│
├── backend/
│   ├── app.py                  ← Flask app factory + all routes registered
│   │
│   ├── routes/
│   │   ├── webhook.py          ← POST /api/webhook/github
│   │   ├── deployment.py       ← CRUD + trigger + rollback
│   │   └── monitor.py          ← Health, pipeline analysis, AI solver
│   │
│   ├── services/
│   │   ├── github_service.py   ← GitHub API client
│   │   ├── deployment_service.py
│   │   ├── port_manager.py     ← Allocates TCP ports
│   │   ├── ssl_manager.py      ← Let's Encrypt / self-signed TLS
│   │   ├── pipeline_analyzer.py
│   │   ├── ai_error_solver.py  ← Gemini / OpenAI / rule-based
│   │   └── language_detector.py
│   │
│   ├── workers/
│   │   ├── deployment_worker.py  ← Async thread: clone → install → run
│   │   └── monitor_worker.py     ← Health polling + report generation
│   │
│   ├── models/
│   │   ├── project.py
│   │   ├── deployment.py       ← DeploymentStatus enum
│   │   └── errors.py           ← PipelineError, ErrorReport
│   │
│   └── utils/
│       ├── logger.py           ← Rotating file logger
│       ├── shell.py            ← Safe subprocess wrapper
│       └── parser.py           ← Log + YAML parsing helpers
│
├── deployment_storage/         ← Cloned repos land here
├── logs/                       ← App + per-deployment logs
├── reports/                    ← Periodic JSON health reports
├── requirements.txt
└── config.yaml
```

---

## ⚡ Quick Start

### 1. Clone & enter the project

```bash
git clone https://github.com/your-org/AI-CICD-Monitor.git
cd AI-CICD-Monitor
```

### 2. Install dependencies

```bash
pip install flask flask-cors requests PyYAML psutil
# Full install (includes AI backends, celery, testing tools):
pip install -r requirements.txt
```

### 3. (Optional) Set environment variables

```bash
# GitHub integration
set GITHUB_TOKEN=REPLACE_WITH_GITHUB_PAT
set GITHUB_WEBHOOK_SECRET=your_secret

# AI Error Solver (pick one)
set GEMINI_API_KEY=AIza...
set OPENAI_API_KEY=sk-...
```

### 4. Start the server

```bash
cd backend
python -m flask --app app.py run --host 0.0.0.0 --port 5000 --debug
```

### 5. Visit in your browser

```
http://127.0.0.1:5000/
```
You'll see the full API index with all available endpoints.

---

## ⚙️ Configuration

All settings live in [`config.yaml`](config.yaml) at the project root.

```yaml
server:
  host: "0.0.0.0"
  port: 5000
  debug: false

github:
  webhook_secret: ""          # or set GITHUB_WEBHOOK_SECRET env var
  auto_deploy_branches:
    - main
    - master
    - production

deployment:
  port_range:
    start: 8100
    end: 9000
  timeout_seconds: 600
  max_concurrent: 5

ssl:
  enabled: false
  provider: "letsencrypt"     # or "self_signed"

ai:
  backend: "auto"             # auto | gemini | openai | rule_based
```

---

## 📡 API Reference

### Root

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API index — all endpoints listed |

### Webhook

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/webhook/ping` | Health check |
| `POST` | `/api/webhook/github` | Receive GitHub events |

**Example — simulate a push event:**
```bash
curl -X POST http://localhost:5000/api/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: push" \
  -d '{"repository":{"full_name":"user/repo"},"ref":"refs/heads/main","after":"abc123","pusher":{"name":"dev"}}'
```

---

### Deployment

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/deployment/` | List all deployments |
| `POST` | `/api/deployment/trigger` | Manually trigger a deployment |
| `GET` | `/api/deployment/<id>` | Get deployment details |
| `GET` | `/api/deployment/<id>/status` | Live status |
| `POST` | `/api/deployment/<id>/rollback` | Roll back |

**Example — trigger a deployment:**
```bash
curl -X POST http://localhost:5000/api/deployment/trigger \
  -H "Content-Type: application/json" \
  -d '{"repo": "your-org/your-repo", "branch": "main"}'
```

---

### Monitor

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/monitor/health` | CPU, memory, disk metrics |
| `GET` | `/api/monitor/projects` | All monitored projects |
| `GET` | `/api/monitor/projects/<id>` | Single project |
| `POST` | `/api/monitor/pipeline/analyze` | Analyze build logs |
| `POST` | `/api/monitor/errors/solve` | AI fix suggestions |
| `GET` | `/api/monitor/reports` | List JSON reports |

**Example — analyze a build log:**
```bash
curl -X POST http://localhost:5000/api/monitor/pipeline/analyze \
  -H "Content-Type: application/json" \
  -d '{"logs": "ModuleNotFoundError: No module named flask\nBuild FAILED in 5.2s"}'
```

**Example — get an AI fix suggestion:**
```bash
curl -X POST http://localhost:5000/api/monitor/errors/solve \
  -H "Content-Type: application/json" \
  -d '{"error": "npm ERR! Cannot find module express", "context": {"language": "javascript"}}'
```

---

## 🔐 Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | No | GitHub personal access token (for API calls) |
| `GITHUB_WEBHOOK_SECRET` | No | HMAC secret for webhook signature validation |
| `GEMINI_API_KEY` | No | Google Gemini API key for AI error solving |
| `OPENAI_API_KEY` | No | OpenAI API key (fallback if no Gemini key) |

> **Note:** If neither AI key is set, the system falls back to rule-based error suggestions automatically.

---

## 🔄 How It Works

```
GitHub Push Event
      │
      ▼
POST /api/webhook/github
      │
      ├─ Verify HMAC signature
      ├─ Parse event (repo, branch, sha)
      └─ Is branch in auto_deploy_branches?
              │
              YES → DeploymentService.trigger_deployment()
                        │
                        ├─ Allocate port (PortManager)
                        ├─ Create Deployment record
                        └─ DeploymentWorker.start() [background thread]
                                  │
                                  ├─ git clone repo
                                  ├─ Detect language (LanguageDetector)
                                  ├─ pip install / npm install
                                  ├─ Start application on allocated port
                                  └─ Update deployment status → SUCCESS / FAILED
                                              │
                                        FAILED → PipelineAnalyzer + AIErrorSolver
                                                 → Fix suggestion stored in error log
```

---

## 🧪 Testing

Run all endpoint tests with the built-in test script:

```bash
python -c "
import requests, json

BASE = 'http://127.0.0.1:5000/api'

tests = [
    ('GET',  f'{BASE[:-3]}/',                    None),
    ('GET',  f'{BASE}/webhook/ping',             None),
    ('GET',  f'{BASE}/monitor/health',           None),
    ('GET',  f'{BASE}/deployment/',              None),
    ('POST', f'{BASE}/monitor/pipeline/analyze', {'logs': 'FAILED\nModuleNotFoundError'}),
    ('POST', f'{BASE}/monitor/errors/solve',     {'error': 'npm ERR! missing package'}),
]

for method, url, body in tests:
    r = getattr(requests, method.lower())(url, json=body, timeout=5)
    print(f'[{r.status_code}] {method} {url}')
"
```

---

## 🗺 Roadmap

- [ ] **Database persistence** — SQLite/PostgreSQL instead of in-memory store
- [ ] **WebSocket dashboard** — Real-time deployment log streaming
- [ ] **Docker support** — Run each deployment in an isolated container
- [ ] **Slack / Discord notifications** — Alert on deploy success/failure
- [ ] **Multi-user auth** — JWT-based authentication
- [ ] **Frontend UI** — React dashboard for visual monitoring
- [ ] **Celery + Redis** — Production-grade async task queue
- [ ] **GitHub Actions integration** — Trigger from workflow events

---

## 📄 License

MIT © 2026 AI-CICD-Monitor Contributors
