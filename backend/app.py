"""
AI-CICD-Monitor - Main Flask Application Entry Point
"""

import os
import yaml
from flask import Flask, jsonify, make_response, render_template
from flask_cors import CORS

from routes.webhook import webhook_bp
from routes.deployment import deployment_bp
from routes.monitor import monitor_bp
from utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# HTML Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>AI-CICD-Monitor</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet"/>
  <style>
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :root{
      --bg:#0d0f1a;--surface:#13162a;--surface2:#1a1e35;--surface3:#20253e;
      --border:rgba(255,255,255,.07);--border2:rgba(255,255,255,.12);
      --accent:#6c63ff;--accent2:#00d4aa;--accent3:#ff6b6b;--accent4:#ffa94d;
      --text:#e8eaf0;--muted:#7a7f99;
      --get:#00d4aa;--post:#6c63ff;--radius:14px;
    }
    body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}
    body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
      background:radial-gradient(ellipse 80% 50% at 20% -10%,rgba(108,99,255,.15) 0%,transparent 60%),
                 radial-gradient(ellipse 60% 40% at 80% 110%,rgba(0,212,170,.1) 0%,transparent 60%)}
    .wrap{position:relative;z-index:1;max-width:1200px;margin:0 auto;padding:0 24px 80px}

    /* ── Header ── */
    header{padding:48px 0 36px;display:flex;align-items:center;gap:18px;flex-wrap:wrap}
    .logo{width:50px;height:50px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:14px;display:grid;place-items:center;font-size:24px;box-shadow:0 8px 28px rgba(108,99,255,.4);flex-shrink:0}
    .title-block h1{font-size:1.9rem;font-weight:800;letter-spacing:-.5px}
    .title-block h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
    .title-block p{color:var(--muted);font-size:.9rem;margin-top:3px}
    .badge{margin-left:auto;display:flex;align-items:center;gap:8px;background:rgba(0,212,170,.1);border:1px solid rgba(0,212,170,.3);color:var(--accent2);padding:6px 14px;border-radius:999px;font-size:.8rem;font-weight:600}
    .dot{width:8px;height:8px;background:var(--accent2);border-radius:50%;animation:pulse 2s infinite}
    @keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.4;transform:scale(1.5)}}

    /* ── Tab Nav ── */
    .tabs{display:flex;gap:4px;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:4px;margin-bottom:28px;width:fit-content}
    .tab{padding:8px 20px;border-radius:9px;cursor:pointer;font-size:.85rem;font-weight:500;color:var(--muted);border:none;background:none;transition:all .2s}
    .tab.active{background:var(--surface2);color:var(--text);box-shadow:0 2px 8px rgba(0,0,0,.3)}
    .tab-panel{display:none}.tab-panel.active{display:block}

    /* ── Stats ── */
    .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:14px;margin-bottom:28px}
    .stat{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px;transition:transform .2s,box-shadow .2s}
    .stat:hover{transform:translateY(-2px);box-shadow:0 10px 30px rgba(0,0,0,.4)}
    .stat .lbl{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:6px}
    .stat .val{font-size:1.7rem;font-weight:700}
    .stat .sub{font-size:.72rem;color:var(--muted);margin-top:3px}
    .purple{color:var(--accent)}.green{color:var(--accent2)}.red{color:var(--accent3)}.orange{color:var(--accent4)}

    /* ── Section heading ── */
    .sh{font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:14px;display:flex;align-items:center;gap:10px}
    .sh::after{content:'';flex:1;height:1px;background:var(--border)}

    /* ── Endpoint cards ── */
    .groups{display:grid;gap:20px}
    .group{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
    .gh{padding:14px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}
    .gi{font-size:16px}.gn{font-weight:700}.gd{font-size:.8rem;color:var(--muted);margin-left:auto}
    .ep{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--border);transition:background .15s;cursor:pointer}
    .ep:last-child{border-bottom:none}
    .ep:hover{background:rgba(255,255,255,.03)}
    .method{font-family:'JetBrains Mono',monospace;font-size:.7rem;font-weight:700;padding:3px 9px;border-radius:5px;min-width:48px;text-align:center;flex-shrink:0}
    .method.GET{background:rgba(0,212,170,.15);color:var(--get)}
    .method.POST{background:rgba(108,99,255,.2);color:var(--post)}
    .path{font-family:'JetBrains Mono',monospace;font-size:.82rem;flex:1}
    .desc{font-size:.78rem;color:var(--muted)}
    .try-btn{font-size:.72rem;color:var(--accent);border:1px solid rgba(108,99,255,.35);padding:3px 10px;border-radius:6px;background:none;cursor:pointer;transition:all .15s;white-space:nowrap;text-decoration:none}
    .try-btn:hover{background:rgba(108,99,255,.2);color:#fff}

    /* ── Tester Panel ── */
    .tester{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
    .tester-top{padding:16px 20px;background:var(--surface2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap}
    .tester-top select,.tester-top input{background:var(--surface3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:6px 12px;font-family:'Inter',sans-serif;font-size:.85rem;outline:none}
    .tester-top select{width:130px}
    .tester-top input{flex:1;min-width:200px}
    .send-btn{background:linear-gradient(135deg,var(--accent),#8f88ff);border:none;color:#fff;padding:7px 20px;border-radius:8px;font-weight:600;font-size:.85rem;cursor:pointer;transition:opacity .2s;white-space:nowrap}
    .send-btn:hover{opacity:.85}
    .tester-body{display:grid;grid-template-columns:1fr 1fr;gap:0}
    @media(max-width:700px){.tester-body{grid-template-columns:1fr}}
    .tester-section{padding:16px 20px;border-right:1px solid var(--border)}
    .tester-section:last-child{border-right:none}
    .tester-section label{font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;display:block;margin-bottom:8px}
    .tester-section textarea{width:100%;background:var(--surface3);border:1px solid var(--border2);color:var(--text);border-radius:8px;padding:10px;font-family:'JetBrains Mono',monospace;font-size:.78rem;resize:vertical;min-height:160px;outline:none;line-height:1.6}
    .status-bar{padding:8px 20px;background:var(--surface2);border-top:1px solid var(--border);font-family:'JetBrains Mono',monospace;font-size:.75rem;color:var(--muted);display:flex;gap:16px}
    .status-ok{color:var(--accent2)}.status-err{color:var(--accent3)}.status-loading{color:var(--accent4)}

    /* ── Quick tests ── */
    .qtest-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}
    .qtest{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px 18px;cursor:pointer;transition:all .2s}
    .qtest:hover{border-color:rgba(108,99,255,.4);transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.3)}
    .qtest h4{font-size:.88rem;font-weight:600;margin-bottom:4px;display:flex;align-items:center;gap:8px}
    .qtest p{font-size:.78rem;color:var(--muted);line-height:1.5}
    .qtest .tag{font-size:.65rem;font-weight:700;padding:2px 7px;border-radius:4px}
    .tag-get{background:rgba(0,212,170,.15);color:var(--get)}
    .tag-post{background:rgba(108,99,255,.2);color:var(--post)}

    /* ── Upload panel ── */
    .upload-box{border:2px dashed var(--border2);border-radius:var(--radius);padding:40px 24px;text-align:center;transition:all .2s;cursor:pointer;background:var(--surface)}
    .upload-box:hover,.upload-box.drag{border-color:var(--accent);background:rgba(108,99,255,.06)}
    .upload-box .icon{font-size:40px;margin-bottom:12px}
    .upload-box h3{font-size:1rem;font-weight:600;margin-bottom:6px}
    .upload-box p{font-size:.83rem;color:var(--muted)}
    #fileInput{display:none}
    .upload-steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px;margin-top:24px}
    .step{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;display:flex;gap:12px;align-items:flex-start}
    .step-num{width:28px;height:28px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:50%;display:grid;place-items:center;font-weight:700;font-size:.82rem;flex-shrink:0}
    .step-text h4{font-size:.85rem;font-weight:600;margin-bottom:3px}
    .step-text p{font-size:.78rem;color:var(--muted);line-height:1.5}
    .gh-steps{margin-top:24px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
    .gh-steps-header{padding:14px 20px;background:var(--surface2);border-bottom:1px solid var(--border);font-weight:700;display:flex;align-items:center;gap:8px}
    .gh-steps pre{padding:18px 20px;font-family:'JetBrains Mono',monospace;font-size:.8rem;color:#a8b4d8;line-height:1.9;overflow-x:auto}
    .cmd-c{color:#4a5270}.cmd-v{color:#f9826c}.cmd-g{color:var(--accent2)}

    /* ── Log viewer ── */
    .log-box{background:var(--surface3);border:1px solid var(--border);border-radius:10px;padding:16px;font-family:'JetBrains Mono',monospace;font-size:.78rem;color:#a8b4d8;line-height:1.8;max-height:300px;overflow-y:auto;white-space:pre-wrap;word-break:break-all}

    footer{margin-top:60px;padding-top:20px;border-top:1px solid var(--border);color:var(--muted);font-size:.8rem;display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px}
    footer a{color:var(--accent);text-decoration:none}
    @media(max-width:600px){.gd,.desc{display:none}.badge{margin-left:0}}
  </style>
</head>
<body>
<div class="wrap">

  <!-- Header -->
  <header>
    <div class="logo">&#x1F680;</div>
    <div class="title-block">
      <h1>AI-CICD-<span>Monitor</span></h1>
      <p>Automated deployment &amp; AI-powered pipeline diagnostics</p>
    </div>
    <div class="badge"><span class="dot"></span>v1.0.0 &nbsp;RUNNING</div>
  </header>

  <!-- Tabs -->
  <div class="tabs">
    <button class="tab active" onclick="switchTab('overview')">📊 Overview</button>
    <button class="tab" onclick="switchTab('tester')">🧪 API Tester</button>
    <button class="tab" onclick="switchTab('quicktest')">⚡ Quick Tests</button>
    <button class="tab" onclick="switchTab('projectupload')">📦 Upload Project</button>
    <button class="tab" onclick="switchTab('upload')">📤 Upload to GitHub</button>
</div>

  <!-- ═══ TAB 1: Overview ═══ -->
  <div id="tab-overview" class="tab-panel active">
    <div class="stats">
      <div class="stat"><div class="lbl">CPU Usage</div><div class="val purple" id="cpu">&#8212;</div><div class="sub">Live</div></div>
      <div class="stat"><div class="lbl">Memory</div><div class="val green" id="mem">&#8212;</div><div class="sub">Live</div></div>
      <div class="stat"><div class="lbl">Disk</div><div class="val red" id="disk">&#8212;</div><div class="sub">Live</div></div>
      <div class="stat"><div class="lbl">Deployments</div><div class="val purple" id="dep-count">&#8212;</div><div class="sub">Total</div></div>
      <div class="stat"><div class="lbl">Projects</div><div class="val orange" id="proj-count">&#8212;</div><div class="sub">Monitored</div></div>
    </div>
    
    <div class="sh">Top Issues (Global)</div>
    <div class="stats" id="top-issues-container" style="margin-bottom: 28px;">
      <!-- Populated dynamically -->
    </div>

    <div class="sh">All API Endpoints</div>
    <div class="groups">
      <div class="group">
        <div class="gh"><span class="gi">&#x1F517;</span><span class="gn">Webhook</span><span class="gd">GitHub event receiver</span></div>
        <div class="ep" onclick="loadTester('GET','/api/webhook/ping','')">
          <span class="method GET">GET</span><span class="path">/api/webhook/ping</span><span class="desc">Health check</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('POST','/api/webhook/github','{\"repository\":{\"full_name\":\"user/repo\"},\"ref\":\"refs/heads/main\",\"after\":\"abc123\",\"pusher\":{\"name\":\"dev\"}}','X-GitHub-Event: push')">
          <span class="method POST">POST</span><span class="path">/api/webhook/github</span><span class="desc">Receive push / PR / workflow</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
      </div>

      <div class="group">
        <div class="gh"><span class="gi">&#x1F6A2;</span><span class="gn">Deployment</span><span class="gd">Trigger, track &amp; rollback</span></div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/','')">
          <span class="method GET">GET</span><span class="path">/api/deployment/</span><span class="desc">List all deployments</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('POST','/api/deployment/trigger','{\"repo\":\"your-org/your-repo\",\"branch\":\"main\"}')">
          <span class="method POST">POST</span><span class="path">/api/deployment/trigger</span><span class="desc">Manually trigger deployment</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/&lt;id&gt;','')">
          <span class="method GET">GET</span><span class="path">/api/deployment/&lt;id&gt;</span><span class="desc">Get deployment details</span>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/&lt;id&gt;/analysis','')">
          <span class="method GET">GET</span><span class="path">/api/deployment/&lt;id&gt;/analysis</span><span class="desc">Cached analysis</span>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/&lt;id&gt;/startup','')">
          <span class="method GET">GET</span><span class="path">/api/deployment/&lt;id&gt;/startup</span><span class="desc">Startup error snapshot</span>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/global','')" >
          <span class="method GET">GET</span><span class="path">/api/deployment/global</span><span class="desc">Global state &amp; counters</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/deployment/rollbacks','')">
          <span class="method GET">GET</span><span class="path">/api/deployment/rollbacks</span><span class="desc">Rollback history</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('POST','/api/deployment/&lt;id&gt;/rollback','{\"reason\":\"Manual rollback\"}')">
          <span class="method POST">POST</span><span class="path">/api/deployment/&lt;id&gt;/rollback</span><span class="desc">Roll back + reason</span>
        </div>
      </div>

      <div class="group">
        <div class="gh"><span class="gi">&#x1F4E1;</span><span class="gn">Monitor</span><span class="gd">Health, analysis &amp; AI diagnostics</span></div>
        <div class="ep" onclick="loadTester('GET','/api/monitor/health','')">
          <span class="method GET">GET</span><span class="path">/api/monitor/health</span><span class="desc">CPU / memory / disk</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/monitor/projects','')">
          <span class="method GET">GET</span><span class="path">/api/monitor/projects</span><span class="desc">List monitored projects</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('POST','/api/monitor/pipeline/analyze','{\"logs\":\"Step 1 OK\\nModuleNotFoundError: No module named flask\\nBuild FAILED in 5.2s\"}')">
          <span class="method POST">POST</span><span class="path">/api/monitor/pipeline/analyze</span><span class="desc">Analyze build logs</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('POST','/api/monitor/errors/explain','{\"error\":\"npm ERR! Cannot find module express\",\"context\":{\"language\":\"javascript\"}}')">
          <span class="method POST">POST</span><span class="path">/api/monitor/errors/explain</span><span class="desc">AI fix suggestions</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
        <div class="ep" onclick="loadTester('GET','/api/monitor/reports','')">
          <span class="method GET">GET</span><span class="path">/api/monitor/reports</span><span class="desc">Health reports</span>
          <button class="try-btn">Try &#x2197;</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ TAB 2: API Tester ═══ -->
  <div id="tab-tester" class="tab-panel">
    <div class="sh">Interactive API Tester</div>
    <div class="tester">
      <div class="tester-top">
        <select id="t-method">
          <option>GET</option>
          <option>POST</option>
          <option>PUT</option>
          <option>DELETE</option>
        </select>
        <input id="t-url" type="text" placeholder="e.g. /api/monitor/health" value="/api/monitor/health"/>
        <button class="send-btn" onclick="sendRequest()">&#x25B6;&nbsp; Send</button>
      </div>
      <div class="tester-body">
        <div class="tester-section">
          <label>Request Body (JSON)</label>
          <textarea id="t-body" placeholder='{"key": "value"}'></textarea>
        </div>
        <div class="tester-section">
          <label>Response</label>
          <textarea id="t-response" readonly placeholder="Response will appear here..."></textarea>
        </div>
      </div>
      <div class="status-bar">
        <span id="t-status">Ready</span>
        <span id="t-time"></span>
        <span id="t-size"></span>
      </div>
    </div>
  </div>

  <!-- ═══ TAB 3: Quick Tests ═══ -->
  <div id="tab-quicktest" class="tab-panel">
    <div class="sh">One-Click Tests — click any card to run it instantly</div>
    <div class="qtest-grid">
      <div class="qtest" onclick="runQuick('GET','/api/webhook/ping','')">
        <h4><span class="tag tag-get">GET</span> Webhook Ping</h4>
        <p>Check that the webhook service is alive and responding.</p>
      </div>
      <div class="qtest" onclick="runQuick('GET','/api/monitor/health','')">
        <h4><span class="tag tag-get">GET</span> System Health</h4>
        <p>Get live CPU, memory and disk usage from the server.</p>
      </div>
      <div class="qtest" onclick="runQuick('GET','/api/deployment/','')">
        <h4><span class="tag tag-get">GET</span> List Deployments</h4>
        <p>See all deployments tracked by the monitor.</p>
      </div>
      <div class="qtest" onclick="runQuick('GET','/api/monitor/projects','')">
        <h4><span class="tag tag-get">GET</span> List Projects</h4>
        <p>List all GitHub repositories being monitored.</p>
      </div>
      <div class="qtest" onclick="runQuick('GET','/api/monitor/reports','')">
        <h4><span class="tag tag-get">GET</span> Health Reports</h4>
        <p>Retrieve all auto-generated monitoring reports.</p>
      </div>
      <div class="qtest" onclick="runQuick('POST','/api/monitor/pipeline/analyze',JSON.stringify({logs:'Step 1 OK\nModuleNotFoundError: No module named flask\nnpm ERR! missing package\nBuild FAILED in 12.4s'}))">
        <h4><span class="tag tag-post">POST</span> Analyze Pipeline Log</h4>
        <p>Parse a sample failing build log — detects errors, severity &amp; recommendations.</p>
      </div>
      <div class="qtest" onclick="runQuick('POST','/api/monitor/errors/explain',JSON.stringify({error:'ModuleNotFoundError: No module named flask',context:{language:'python'}}))">
        <h4><span class="tag tag-post">POST</span> AI Fix (Python Error)</h4>
        <p>Ask AI to explain and suggest a fix for a missing Python module error.</p>
      </div>
      <div class="qtest" onclick="runQuick('POST','/api/monitor/errors/explain',JSON.stringify({error:'npm ERR! Cannot find module express',context:{language:'javascript'}}))">
        <h4><span class="tag tag-post">POST</span> AI Fix (Node Error)</h4>
        <p>Ask AI to explain and suggest a fix for a missing Node.js module error.</p>
      </div>
      <div class="qtest" onclick="runQuick('POST','/api/webhook/github',JSON.stringify({repository:{full_name:'testuser/demo-app'},ref:'refs/heads/main',after:'abc1234',pusher:{name:'developer'}}), 'X-GitHub-Event: push')">
        <h4><span class="tag tag-post">POST</span> Simulate GitHub Push</h4>
        <p>Send a fake push event to the webhook — triggers deploy logic for main branch.</p>
      </div>
      <div class="qtest" onclick="runQuick('POST','/api/deployment/trigger',JSON.stringify({repo:'testuser/demo-app',branch:'main'}))">
        <h4><span class="tag tag-post">POST</span> Trigger Deployment</h4>
        <p>Manually start a deployment for a repository on the main branch.</p>
      </div>
    </div>

    <!-- Live result -->
    <div style="margin-top:24px">
      <div class="sh">Last Test Result</div>
      <div class="log-box" id="quick-result">Click any card above to run a test...</div>
    </div>
  </div>
<!-- ═══ TAB 4: Upload Project ═══ -->
<div id="tab-projectupload" class="tab-panel">

  <div class="sh">Upload ZIP Project</div>

  <div class="upload-box">
      <div class="icon">📦</div>

      <h3>Select Project ZIP</h3>

      <p>
          Upload any Python, Node.js, Java, Go,
          PHP, Rust, C/C++ or TypeScript project.
      </p>

      <br>

      <input type="file" id="zipFile">

      <br><br>

      <button class="send-btn"
              onclick="uploadProject()">
          Upload & Analyze
      </button>
  </div>

  <div style="margin-top:20px">

      <div class="sh">Upload Result</div>

      <div class="log-box"
           id="upload-result">

          No upload yet...

      </div>

  </div>

</div>
  <!-- ═══ TAB 4: Upload to GitHub ═══ -->
  <div id="tab-upload" class="tab-panel">
    <div class="sh">Upload AI-CICD-Monitor to GitHub</div>

    <div class="upload-steps">
      <div class="step">
        <div class="step-num">1</div>
        <div class="step-text">
          <h4>Create GitHub Repo</h4>
          <p>Go to <a href="https://github.com/new" target="_blank" style="color:var(--accent)">github.com/new</a>, name it <strong>AI-CICD-Monitor</strong>, keep it public, click Create.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">2</div>
        <div class="step-text">
          <h4>Open Terminal</h4>
          <p>Press <strong>Win + R</strong> → type <strong>powershell</strong> → Enter. Or open VS Code terminal.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">3</div>
        <div class="step-text">
          <h4>Run These Commands</h4>
          <p>Copy the commands below, replace YOUR_USERNAME with your GitHub username.</p>
        </div>
      </div>
      <div class="step">
        <div class="step-num">4</div>
        <div class="step-text">
          <h4>Done!</h4>
          <p>Your project is live at <strong>github.com/YOUR_USERNAME/AI-CICD-Monitor</strong></p>
        </div>
      </div>
    </div>

    <div class="gh-steps" style="margin-top:24px">
      <div class="gh-steps-header">&#x1F4CB; Commands to run in PowerShell</div>
      <pre><span class="cmd-c"># Navigate to your project folder</span>
<span class="cmd-g">cd C:\Users\ragha\AI-CICD-Monitor</span>

<span class="cmd-c"># Connect to your GitHub repo (replace YOUR_USERNAME)</span>
<span class="cmd-g">git remote add origin https://github.com/YOUR_USERNAME/AI-CICD-Monitor.git</span>

<span class="cmd-c"># Rename branch to main (already done, just in case)</span>
<span class="cmd-g">git branch -M main</span>

<span class="cmd-c"># Push all files to GitHub</span>
<span class="cmd-g">git push -u origin main</span>

<span class="cmd-c"># Enter your GitHub username and password/token when prompted</span>
<span class="cmd-c"># (Use a Personal Access Token as password: github.com/settings/tokens)</span></pre>
    </div>

    <div class="gh-steps" style="margin-top:16px">
      <div class="gh-steps-header">&#x1F511; How to get a GitHub Personal Access Token</div>
      <pre><span class="cmd-c">1. Go to: https://github.com/settings/tokens</span>
<span class="cmd-c">2. Click "Generate new token (classic)"</span>
<span class="cmd-c">3. Give it a name: "AI-CICD-Monitor"</span>
<span class="cmd-c">4. Check these scopes: repo, workflow</span>
<span class="cmd-c">5. Click "Generate token" and COPY it</span>
<span class="cmd-c">6. Use that token as your password in the git push step above</span></pre>
    </div>

    <div class="gh-steps" style="margin-top:16px">
      <div class="gh-steps-header">&#x1F3F7;&#xFE0F; What files will be uploaded to GitHub</div>
      <pre><span class="cmd-g">AI-CICD-Monitor/</span>
<span class="cmd-c">├── README.md             ← Project documentation</span>
<span class="cmd-c">├── requirements.txt      ← Python dependencies</span>
<span class="cmd-c">├── config.yaml           ← All settings</span>
<span class="cmd-c">├── .gitignore            ← Excluded files (logs, __pycache__)</span>
<span class="cmd-c">└── backend/</span>
<span class="cmd-c">    ├── app.py            ← Main Flask app + this dashboard</span>
<span class="cmd-c">    ├── routes/           ← webhook, deployment, monitor</span>
<span class="cmd-c">    ├── services/         ← github, ssl, port, AI solver...</span>
<span class="cmd-c">    ├── workers/          ← deployment &amp; monitor workers</span>
<span class="cmd-c">    ├── models/           ← project, deployment, errors</span>
<span class="cmd-c">    └── utils/            ← logger, shell, parser</span>

<span class="cmd-c">NOT uploaded (in .gitignore):</span>
<span class="cmd-v">  logs/*.log, __pycache__/, .env, certs/, deployment_storage/*/</span></pre>
    </div>
  </div>

  <footer>
    <span>AI-CICD-Monitor &copy; 2026</span>
    <a href="https://github.com/your-org/AI-CICD-Monitor" target="_blank">GitHub &#x2192;</a>
  </footer>
</div>

<script>
// ── Tab switching ──────────────────────────────────────────────────────────
function switchTab(name) {
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  event.target.classList.add('active');
}

// ── Live stats (Overview tab) ─────────────────────────────────────────────
async function loadStats() {
  try {
    const [h, d, p] = await Promise.all([
      fetch('/api/monitor/health').then(r=>r.json()),
      fetch('/api/deployment/').then(r=>r.json()),
      fetch('/api/monitor/projects').then(r=>r.json()),
    ]);
    document.getElementById('cpu').textContent   = h.cpu_percent   != null ? h.cpu_percent.toFixed(1)+'%'   : 'N/A';
    document.getElementById('mem').textContent   = h.memory_percent != null ? h.memory_percent.toFixed(1)+'%' : 'N/A';
    document.getElementById('disk').textContent  = h.disk_percent   != null ? h.disk_percent.toFixed(1)+'%'  : 'N/A';
    document.getElementById('dep-count').textContent  = Array.isArray(d.deployments) ? d.deployments.length : 0;
    document.getElementById('proj-count').textContent = Array.isArray(p.projects)    ? p.projects.length    : 0;
    
    // Top Issues
    try {
      const t = await fetch('/api/monitor/issues/top').then(r=>r.json());
      const c = document.getElementById('top-issues-container');
      if (t.issues && t.issues.length > 0) {
        c.innerHTML = t.issues.map(i => `<div class="stat"><div class="lbl">${i.error_id}</div><div class="val red">${i.count}</div><div class="sub">Occurrences</div></div>`).join('');
      } else {
        c.innerHTML = '<div class="stat"><div class="lbl">All Good</div><div class="val green">0</div><div class="sub">No issues yet</div></div>';
      }
    } catch(e) {}
  } catch(e) { console.warn('Stats error', e); }
}
loadStats();
setInterval(loadStats, 8000);

// ── Load endpoint into Tester tab ─────────────────────────────────────────
function loadTester(method, url, body, headers) {
  switchTab('tester');
  document.querySelectorAll('.tab').forEach((t,i) => { if(i===1) t.classList.add('active'); else t.classList.remove('active'); });
  document.getElementById('t-method').value = method;
  document.getElementById('t-url').value    = url.replace(/&lt;/g,'<').replace(/&gt;/g,'>');
  document.getElementById('t-body').value   = body ? JSON.stringify(JSON.parse(body), null, 2) : '';
}

// ── Send API request (Tester tab) ─────────────────────────────────────────
async function sendRequest() {
  const method   = document.getElementById('t-method').value;
  const url      = document.getElementById('t-url').value.trim();
  const bodyText = document.getElementById('t-body').value.trim();
  const resEl    = document.getElementById('t-response');
  const stEl     = document.getElementById('t-status');
  const tmEl     = document.getElementById('t-time');
  const szEl     = document.getElementById('t-size');

  stEl.className = 'status-loading';
  stEl.textContent = 'Sending...';
  resEl.value = '';

  const t0 = Date.now();
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (bodyText && method !== 'GET') opts.body = bodyText;

    const r = await fetch(url, opts);
    const ms = Date.now() - t0;
    const text = await r.text();

    let pretty = text;
    try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch(_) {}

    resEl.value = pretty;
    stEl.className = r.ok ? 'status-ok' : 'status-err';
    stEl.textContent = `${r.status} ${r.statusText}`;
    tmEl.textContent = `${ms}ms`;
    szEl.textContent = `${new Blob([text]).size} bytes`;
  } catch(e) {
    resEl.value = 'Error: ' + e.message;
    stEl.className = 'status-err';
    stEl.textContent = 'Request failed';
    tmEl.textContent = '';
  }
}

async function uploadProject() {

    const file =
        document.getElementById("zipFile").files[0];

    if (!file) {

        alert("Please choose a ZIP file.");

        return;
    }

    const output =
        document.getElementById("upload-result");

    output.textContent =
        "Uploading project...";

    const formData = new FormData();

    formData.append(
        "file",
        file
    );

    formData.append(
        "name",
        file.name
    );

    try {

        const response =
            await fetch(
                "/api/deployment/upload",
                {
                    method: "POST",
                    body: formData
                }
            );

        const data =
            await response.json();

       output.textContent =
    JSON.stringify(data, null, 2);

if (data.deployment_id) {

    trackDeployment(
        data.deployment_id
    );
}
async function trackDeployment(id) {

    const output =
        document.getElementById(
            "upload-result"
        );

    const timer =
        setInterval(
            async () => {

                try {

                    const response =
                        await fetch(
                            `/api/deployment/${id}/pipeline`
                        );

                    const data =
                        await response.json();

                    output.textContent =
                        JSON.stringify(
                            data,
                            null,
                            2
                        );

                    const failed =
                        data.stages?.some(
                            s =>
                                s.status ===
                                "failed"
                        );

                    const finished =
                        data.stages?.every(
                            s =>
                                s.status ===
                                "success"
                        );

                    if (
                        failed ||
                        finished
                    ) {

                        clearInterval(
                            timer
                        );
                    }

                } catch {}

            },
            3000
        );
}

    } catch (err) {

        output.textContent =
            "Upload failed:\n\n" +
            err.message;
    }
}
// ── Quick test runner ──────────────────────────────────────────────────────
async function runQuick(method, url, body, extraHeader) {
  const el = document.getElementById('quick-result');
  el.textContent = `\u25B6 ${method} ${url}\n\nSending...`;
  const t0 = Date.now();
  try {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (extraHeader) { const [k,v] = extraHeader.split(': '); opts.headers[k] = v; }
    if (body && method !== 'GET') opts.body = body;

    const r   = await fetch(url, opts);
    const ms  = Date.now() - t0;
    const txt = await r.text();
    let pretty = txt;
    try { pretty = JSON.stringify(JSON.parse(txt), null, 2); } catch(_){}

    el.textContent = `\u25BA ${method} ${url}\n\u23F1  ${ms}ms  |  HTTP ${r.status} ${r.statusText}\n${'─'.repeat(50)}\n${pretty}`;
  } catch(e) {
    el.textContent = `\u274C Error: ${e.message}`;
  }
}
</script>
</body>
</html>"""


def load_config(path: str = "config.yaml") -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", path)
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def create_app(config: dict = None) -> Flask:
    app = Flask(__name__)
    CORS(app)

    if config is None:
        config = load_config()

    app.config.update(config)

    app.register_blueprint(webhook_bp, url_prefix="/api/webhook")
    app.register_blueprint(deployment_bp, url_prefix="/api/deployment")
    app.register_blueprint(monitor_bp, url_prefix="/api/monitor")

    @app.route("/")
    def index():
        resp = make_response(DASHBOARD_HTML)
        resp.headers["Content-Type"] = "text/html; charset=utf-8"
        return resp

    @app.route("/api")
    def api_index():
        return (
            jsonify(
                {
                    "name": "AI-CICD-Monitor",
                    "version": "1.0.0",
                    "status": "running",
                    "routes": {
                        "webhook": "/api/webhook",
                        "deployment": "/api/deployment",
                        "monitor": "/api/monitor",
                    },
                }
            ),
            200,
        )

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not Found", "hint": "Visit / for the dashboard"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method Not Allowed", "message": str(e)}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

    logger.info("AI-CICD-Monitor backend started.")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
