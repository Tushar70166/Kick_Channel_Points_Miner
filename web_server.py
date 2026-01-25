import threading
import json
import asyncio
from flask import Flask, render_template_string, jsonify
from loguru import logger
from datetime import datetime

# Хранилище ссылок на данные
shared_context = {
    "streamers": [],
    "points": {},
    "last_update": {},
    "status": "Initializing"
}

app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kick Miner Dashboard</title>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
    <!-- Bootstrap 5 & Icons -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css">
    
    <style>
        :root {
            --kick-green: #53fc18;
            --bg-dark: #0b0e11;
            --card-bg: #191c21;
            --border-color: #2a2e35;
        }
        body {
            background-color: var(--bg-dark);
            color: #e0e0e0;
            font-family: 'Inter', sans-serif;
            min-height: 100vh;
        }
        .navbar {
            background: rgba(11, 14, 17, 0.95) !important;
            backdrop-filter: blur(10px);
            border-bottom: 1px solid var(--border-color);
        }
        .brand-logo {
            font-family: 'JetBrains Mono', monospace;
            font-weight: 700;
            letter-spacing: -0.5px;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 16px rgba(0,0,0,0.4);
        }
        .stat-card-title {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #8b949e;
        }
        .stat-value {
            font-size: 2.5rem;
            font-weight: 700;
        }
        .table {
            --bs-table-bg: transparent;
            --bs-table-color: #e0e0e0;
            border-color: var(--border-color);
        }
        .table thead th {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #8b949e;
            border-bottom-width: 1px;
            padding-bottom: 15px;
        }
        .table tbody tr {
            transition: background-color 0.2s;
        }
        .table tbody tr:hover {
            background-color: rgba(255,255,255,0.03);
        }
        .streamer-link {
            color: #fff;
            text-decoration: none;
            font-weight: 600;
            display: flex;
            align-items: center;
        }
        .streamer-link:hover {
            color: var(--kick-green);
        }
        .avatar-placeholder {
            width: 32px;
            height: 32px;
            background: #2a2e35;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin-right: 12px;
            font-size: 0.8rem;
            color: var(--kick-green);
        }
        .badge-points {
            background: rgba(83, 252, 24, 0.1);
            color: var(--kick-green);
            border: 1px solid rgba(83, 252, 24, 0.2);
            font-family: 'JetBrains Mono', monospace;
            padding: 6px 12px;
            border-radius: 6px;
        }
        .status-dot {
            width: 8px;
            height: 8px;
            background-color: var(--kick-green);
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
            box-shadow: 0 0 8px var(--kick-green);
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(1.1); }
            100% { opacity: 1; transform: scale(1); }
        }
    </style>
</head>
<body>
    <nav class="navbar navbar-expand-lg sticky-top mb-5">
        <div class="container">
            <a class="navbar-brand brand-logo text-white" href="#">
                <span style="color: var(--kick-green)">KICK</span>MINER
            </a>
            <div class="d-flex align-items-center">
                <span class="badge bg-dark border border-secondary me-3" id="ws-status">
                    <i class="bi bi-activity"></i> Connected
                </span>
                <a href="#" onclick="fetchStats()" class="btn btn-sm btn-outline-secondary">
                    <i class="bi bi-arrow-clockwise"></i>
                </a>
            </div>
        </div>
    </nav>

    <div class="container">
        <!-- Stats Overview -->
        <div class="row g-4 mb-5">
            <div class="col-md-4">
                <div class="card h-100 p-4">
                    <div class="d-flex justify-content-between mb-3">
                        <div class="stat-card-title">Active Channels</div>
                        <i class="bi bi-broadcast text-secondary"></i>
                    </div>
                    <div class="stat-value text-white" id="count-streamers">0</div>
                    <small class="text-success"><i class="bi bi-check-circle-fill"></i> Monitoring active</small>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card h-100 p-4">
                    <div class="d-flex justify-content-between mb-3">
                        <div class="stat-card-title">Total Points Farmed</div>
                        <i class="bi bi-gem text-secondary"></i>
                    </div>
                    <div class="stat-value" style="color: var(--kick-green)" id="total-points">0</div>
                    <small class="text-muted">Accumulated across all channels</small>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card h-100 p-4">
                    <div class="d-flex justify-content-between mb-3">
                        <div class="stat-card-title">Session Uptime</div>
                        <i class="bi bi-clock-history text-secondary"></i>
                    </div>
                    <div class="stat-value text-info" id="uptime">00:00:00</div>
                    <small class="text-muted">Since miner started</small>
                </div>
            </div>
        </div>

        <!-- Main Table -->
        <div class="card">
            <div class="card-body p-0">
                <div class="table-responsive">
                    <table class="table mb-0 align-middle">
                        <thead>
                            <tr>
                                <th class="ps-4">Streamer</th>
                                <th>Balance</th>
                                <th>Last Check</th>
                                <th class="text-end pe-4">Status</th>
                            </tr>
                        </thead>
                        <tbody id="streamer-rows">
                            <!-- JS Injection -->
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
        
        <footer class="text-center text-muted mt-5 mb-3 small">
            <p>Kick Channel Points Miner • <span id="last-sync">Syncing...</span></p>
        </footer>
    </div>

    <script>
        const startTime = Date.now(); 

        function formatNumber(num) {
            return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");
        }

        function updateUptime() {
            const diff = Math.floor((Date.now() - startTime) / 1000);
            const h = Math.floor(diff / 3600).toString().padStart(2, '0');
            const m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
            const s = (diff % 60).toString().padStart(2, '0');
            document.getElementById('uptime').innerText = `${h}:${m}:${s}`;
        }

        async function fetchStats() {
            try {
                const res = await fetch('/api/data');
                const data = await res.json();
                
                document.getElementById('count-streamers').innerText = data.streamers.length;
                
                let total = 0;
                let rowsHtml = '';
                
                data.streamers.forEach(name => {
                    const pts = data.points[name] || 0;
                    const last = data.last_update[name] || 'Pending...';
                    total += pts;
                    
                    const initial = name.charAt(0).toUpperCase();
                    
                    rowsHtml += `
                        <tr>
                            <td class="ps-4">
                                <a href="https://kick.com/${name}" target="_blank" class="streamer-link">
                                    <div class="avatar-placeholder">${initial}</div>
                                    ${name}
                                </a>
                            </td>
                            <td><span class="badge-points">${formatNumber(pts)}</span></td>
                            <td class="text-muted small" style="font-family: monospace">${last}</td>
                            <td class="text-end pe-4">
                                <div class="d-flex align-items-center justify-content-end">
                                    <span class="status-dot"></span>
                                    <span class="small text-white">Online</span>
                                </div>
                            </td>
                        </tr>
                    `;
                });
                
                document.getElementById('streamer-rows').innerHTML = rowsHtml;
                document.getElementById('total-points').innerText = formatNumber(total);
                
                const now = new Date();
                document.getElementById('last-sync').innerText = 'Last sync: ' + now.toLocaleTimeString();
                
            } catch (err) {
                console.error(err);
                document.getElementById('ws-status').className = 'badge bg-danger me-3';
                document.getElementById('ws-status').innerText = 'Disconnected';
            }
        }

        setInterval(fetchStats, 3000);
        setInterval(updateUptime, 1000);
        fetchStats();
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/data')
def get_data():
    clean_last_update = {}
    for k, v in shared_context["last_update"].items():
        if isinstance(v, datetime):
            clean_last_update[k] = v.strftime("%H:%M:%S")
        else:
            clean_last_update[k] = str(v)

    return jsonify({
        "streamers": shared_context["streamers"],
        "points": shared_context["points"],
        "last_update": clean_last_update,
        "status": shared_context["status"]
    })

def start_server(streamers_list, port=5000):
    shared_context["streamers"] = streamers_list
    shared_context["status"] = "Active"
    
    def run():
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        logger.info(f"🌍 Web Dashboard available at http://localhost:{port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    t = threading.Thread(target=run, daemon=True)
    t.start()

def update_streamer_info(name, points, last_update_time):
    shared_context["points"][name] = points
    shared_context["last_update"][name] = last_update_time
