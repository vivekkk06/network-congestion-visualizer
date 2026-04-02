"""
dashboard/app.py
━━━━━━━━━━━━━━━━
Flask dashboard server for Network Congestion Visualizer.

Run:
    python -m dashboard.app          (from project root)
    OR
    python main.py --dashboard

Routes:
    GET  /                   → Main dashboard HTML page
    GET  /api/chart/<type>   → JSON for cwnd / queue / throughput / heatmap charts
    GET  /api/summary        → JSON benchmark summary table rows
    GET  /api/controls       → JSON slider/dropdown config for frontend
    POST /api/run            → Run live simulation, return chart data as JSON
"""

import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, request, jsonify, Response

from dashboard.charts   import (cwnd_chart_data, queue_chart_data,
                                 throughput_chart_data, heatmap_data,
                                 summary_table_data)
from dashboard.controls import SimParams, run_live

app = Flask(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  HTML page (served inline — no template folder needed)
# ─────────────────────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Network Congestion Visualizer</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:       #0f1117;
    --surface:  #1a1d27;
    --border:   #2a2d3a;
    --text:     #e2e4ef;
    --muted:    #8b8fa8;
    --accent:   #378ADD;
    --red:      #E24B4A;
    --amber:    #EF9F27;
    --teal:     #1D9E75;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif;
         font-size: 14px; line-height: 1.6; }

  /* ── Layout ── */
  .header { padding: 20px 32px; border-bottom: 1px solid var(--border);
             display: flex; align-items: center; gap: 16px; }
  .header h1 { font-size: 18px; font-weight: 600; }
  .header .sub { color: var(--muted); font-size: 13px; }
  .main { display: grid; grid-template-columns: 280px 1fr; min-height: calc(100vh - 61px); }

  /* ── Sidebar ── */
  .sidebar { background: var(--surface); border-right: 1px solid var(--border);
             padding: 24px 20px; overflow-y: auto; }
  .sidebar h2 { font-size: 12px; font-weight: 600; color: var(--muted);
                text-transform: uppercase; letter-spacing: .08em; margin-bottom: 16px; }
  .ctrl-group { margin-bottom: 20px; }
  .ctrl-group label { display: block; font-size: 12px; color: var(--muted);
                      margin-bottom: 6px; }
  .ctrl-group select, .ctrl-group input[type=range] { width: 100%; }
  select { background: var(--bg); color: var(--text); border: 1px solid var(--border);
           border-radius: 6px; padding: 7px 10px; font-size: 13px; }
  .slider-row { display: flex; align-items: center; gap: 10px; }
  .slider-row input { flex: 1; accent-color: var(--accent); }
  .slider-val { min-width: 52px; text-align: right; font-size: 13px;
                color: var(--text); font-variant-numeric: tabular-nums; }
  .run-btn { width: 100%; margin-top: 8px; padding: 10px; background: var(--accent);
             color: #fff; border: none; border-radius: 8px; font-size: 14px;
             font-weight: 600; cursor: pointer; transition: opacity .15s; }
  .run-btn:hover { opacity: .85; }
  .run-btn:disabled { opacity: .4; cursor: not-allowed; }

  /* ── Stats bar ── */
  .stats-bar { display: flex; gap: 12px; flex-wrap: wrap; padding: 0 0 4px; }
  .stat-card { background: var(--surface); border: 1px solid var(--border);
               border-radius: 8px; padding: 10px 16px; min-width: 130px; flex: 1; }
  .stat-card .val { font-size: 22px; font-weight: 700; }
  .stat-card .lbl { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .stat-card.loss .val { color: var(--red); }
  .stat-card.cwnd .val { color: var(--accent); }
  .stat-card.rtt  .val { color: var(--amber); }
  .stat-card.drop .val { color: var(--teal); }

  /* ── Content area ── */
  .content { padding: 24px 28px; display: flex; flex-direction: column; gap: 28px; overflow-y: auto; }
  .section-title { font-size: 11px; font-weight: 600; color: var(--muted);
                   text-transform: uppercase; letter-spacing: .08em; margin-bottom: 14px; }

  /* ── Tabs ── */
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; }
  .tab  { padding: 6px 16px; border-radius: 6px; border: 1px solid var(--border);
          background: transparent; color: var(--muted); font-size: 13px;
          cursor: pointer; transition: all .15s; }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  /* ── Scenario selector ── */
  .scenario-bar { display: flex; gap: 8px; margin-bottom: 18px; }
  .scen-btn { padding: 6px 18px; border-radius: 6px; border: 1px solid var(--border);
              background: transparent; color: var(--muted); font-size: 13px;
              cursor: pointer; transition: all .15s; }
  .scen-btn.active { background: var(--surface); color: var(--text);
                     border-color: var(--accent); }

  /* ── Chart cards ── */
  .chart-card { background: var(--surface); border: 1px solid var(--border);
                border-radius: 10px; padding: 20px; }
  .chart-card h3 { font-size: 13px; font-weight: 600; margin-bottom: 16px; }
  .chart-wrap { position: relative; height: 240px; }

  /* ── Heatmap ── */
  .heatmap-grid { display: grid; gap: 3px; margin-top: 8px; }
  .heatmap-cell { border-radius: 3px; height: 28px; transition: opacity .3s; }
  .heatmap-labels-x { display: flex; gap: 3px; margin-top: 6px; }
  .heatmap-labels-x span { flex: 1; font-size: 10px; color: var(--muted);
                            text-align: center; overflow: hidden; white-space: nowrap; }

  /* ── Summary table ── */
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  thead th { color: var(--muted); font-weight: 500; text-align: left;
             padding: 6px 12px; border-bottom: 1px solid var(--border); }
  tbody td { padding: 8px 12px; border-bottom: 1px solid var(--border)22; }
  tbody tr:hover td { background: var(--border)44; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: 11px; font-weight: 500; }
  .badge.red  { background: #E24B4A22; color: var(--red); }
  .badge.teal { background: #1D9E7522; color: var(--teal); }
  .badge.blue { background: #378ADD22; color: var(--accent); }
  .badge.amber{ background: #EF9F2722; color: var(--amber); }

  /* ── Mode toggle ── */
  .mode-toggle { display: flex; gap: 4px; margin-bottom: 16px; }
  .mode-btn { padding: 5px 14px; border-radius: 6px; border: 1px solid var(--border);
              background: transparent; color: var(--muted); font-size: 12px;
              cursor: pointer; }
  .mode-btn.active { background: var(--surface); color: var(--text); border-color: var(--accent); }

  /* loading spinner */
  .spinner { display: none; width: 16px; height: 16px; border: 2px solid #ffffff44;
             border-top-color: #fff; border-radius: 50%;
             animation: spin .6s linear infinite; margin: auto; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Network Congestion Visualizer</h1>
    <div class="sub">Slow Start · AIMD · TCP Cubic · Drop Tail · RED</div>
  </div>
</div>

<div class="main">

  <!-- ── Sidebar ── -->
  <aside class="sidebar">
    <h2>Live Simulation</h2>

    <div class="ctrl-group">
      <label>Algorithm</label>
      <select id="ctl-algo">
        <option value="slow_start_aimd">Slow Start + AIMD</option>
        <option value="cubic">TCP Cubic</option>
      </select>
    </div>

    <div class="ctrl-group">
      <label>Drop Policy</label>
      <select id="ctl-policy">
        <option value="drop_tail">Drop Tail</option>
        <option value="red">RED (Random Early Detection)</option>
      </select>
    </div>

    <div class="ctrl-group">
      <label>Bandwidth</label>
      <div class="slider-row">
        <input type="range" id="ctl-bw" min="100" max="5000" step="100" value="1000"
               oninput="syncVal('ctl-bw','val-bw',v=>v+' kbps')">
        <span class="slider-val" id="val-bw">1000 kbps</span>
      </div>
    </div>

    <div class="ctrl-group">
      <label>Propagation Delay</label>
      <div class="slider-row">
        <input type="range" id="ctl-delay" min="5" max="500" step="5" value="50"
               oninput="syncVal('ctl-delay','val-delay',v=>v+' ms')">
        <span class="slider-val" id="val-delay">50 ms</span>
      </div>
    </div>

    <div class="ctrl-group">
      <label>Queue Size (packets)</label>
      <div class="slider-row">
        <input type="range" id="ctl-queue" min="5" max="100" step="1" value="20"
               oninput="syncVal('ctl-queue','val-queue',v=>v+' pkts')">
        <span class="slider-val" id="val-queue">20 pkts</span>
      </div>
    </div>

    <div class="ctrl-group">
      <label>Packets to send</label>
      <div class="slider-row">
        <input type="range" id="ctl-pkts" min="50" max="500" step="50" value="200"
               oninput="syncVal('ctl-pkts','val-pkts',v=>v)">
        <span class="slider-val" id="val-pkts">200</span>
      </div>
    </div>

    <button class="run-btn" id="run-btn" onclick="runLive()">
      ▶ Run Simulation
    </button>
    <div class="spinner" id="spinner" style="margin-top:12px;"></div>
  </aside>

  <!-- ── Main content ── -->
  <div class="content">

    <!-- Stats bar -->
    <div class="stats-bar" id="stats-bar">
      <div class="stat-card loss"><div class="val" id="stat-loss">—</div><div class="lbl">Loss Rate</div></div>
      <div class="stat-card cwnd"><div class="val" id="stat-cwnd">—</div><div class="lbl">Peak cwnd</div></div>
      <div class="stat-card rtt" ><div class="val" id="stat-rtt" >—</div><div class="lbl">Avg RTT</div></div>
      <div class="stat-card drop"><div class="val" id="stat-drop">—</div><div class="lbl">Pkts Dropped</div></div>
    </div>

    <!-- Mode toggle: Live vs Benchmark -->
    <div>
      <div class="mode-toggle">
        <button class="mode-btn active" id="mode-live" onclick="setMode('live')">Live Run</button>
        <button class="mode-btn"        id="mode-bench" onclick="setMode('bench')">Benchmark Comparison</button>
      </div>

      <!-- LIVE mode charts -->
      <div id="panel-live">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
          <div class="chart-card">
            <h3>Congestion Window (cwnd)</h3>
            <div class="chart-wrap"><canvas id="live-cwnd"></canvas></div>
          </div>
          <div class="chart-card">
            <h3>Queue Occupancy</h3>
            <div class="chart-wrap"><canvas id="live-queue"></canvas></div>
          </div>
        </div>
        <div style="margin-top:16px;" class="chart-card">
          <h3>Throughput (kbps)</h3>
          <div class="chart-wrap"><canvas id="live-tp"></canvas></div>
        </div>
      </div>

      <!-- BENCHMARK mode -->
      <div id="panel-bench" style="display:none;">
        <p class="section-title">Scenario</p>
        <div class="scenario-bar">
          <button class="scen-btn active" onclick="loadBench('high',this)">High Congestion</button>
          <button class="scen-btn"        onclick="loadBench('low',this)">Low Congestion</button>
          <button class="scen-btn"        onclick="loadBench('bursty',this)">Bursty Traffic</button>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px;">
          <div class="chart-card">
            <h3>cwnd comparison</h3>
            <div class="chart-wrap"><canvas id="bench-cwnd"></canvas></div>
          </div>
          <div class="chart-card">
            <h3>Queue occupancy</h3>
            <div class="chart-wrap"><canvas id="bench-queue"></canvas></div>
          </div>
        </div>

        <div class="chart-card" style="margin-bottom:16px;">
          <h3>Throughput comparison</h3>
          <div class="chart-wrap"><canvas id="bench-tp"></canvas></div>
        </div>

        <!-- Heatmap -->
        <div class="chart-card" style="margin-bottom:16px;">
          <h3>Congestion Heatmap (queue fill intensity)</h3>
          <div id="heatmap-container"></div>
        </div>

        <!-- Summary table -->
        <div class="chart-card">
          <h3>Benchmark Summary</h3>
          <div id="summary-table"></div>
        </div>
      </div>
    </div>

  </div>
</div>

<script>
// ── Globals ──────────────────────────────────────────────────────────────────
const CHART_OPTS = (title, yLabel) => ({
  responsive: true, maintainAspectRatio: false, animation: false,
  parsing: false,
  plugins: { legend: { position: 'top', labels: { color:'#8b8fa8', boxWidth:12, font:{size:11} } },
             title: { display: false } },
  scales: {
    x: { type:'linear', grid:{color:'#2a2d3a'}, ticks:{color:'#8b8fa8',maxTicksLimit:8},
         title:{display:true, text:'Time (s)', color:'#8b8fa8'} },
    y: { grid:{color:'#2a2d3a'}, ticks:{color:'#8b8fa8'},
         title:{display:true, text:yLabel, color:'#8b8fa8'} }
  }
});

let charts = {};
let currentMode = 'live';
let currentScenario = 'high';

// ── Slider sync ──────────────────────────────────────────────────────────────
function syncVal(inputId, spanId, fmt) {
  document.getElementById(spanId).textContent = fmt(document.getElementById(inputId).value);
}

// ── Mode switch ──────────────────────────────────────────────────────────────
function setMode(mode) {
  currentMode = mode;
  document.getElementById('panel-live').style.display  = mode === 'live'  ? '' : 'none';
  document.getElementById('panel-bench').style.display = mode === 'bench' ? '' : 'none';
  document.getElementById('mode-live').classList.toggle('active',  mode === 'live');
  document.getElementById('mode-bench').classList.toggle('active', mode === 'bench');
  if (mode === 'bench') loadBench(currentScenario, null);
}

// ── Chart helpers ─────────────────────────────────────────────────────────────
function makeChart(id, yLabel) {
  if (charts[id]) { charts[id].destroy(); }
  charts[id] = new Chart(document.getElementById(id), {
    type: 'line',
    data: { datasets: [] },
    options: CHART_OPTS('', yLabel),
  });
  return charts[id];
}

function applyChartData(chart, cfg) {
  chart.data.datasets = cfg.data.datasets;
  Object.assign(chart.options, cfg.options);
  chart.update('none');
}

// ── Live simulation ───────────────────────────────────────────────────────────
function runLive() {
  const btn = document.getElementById('run-btn');
  const spinner = document.getElementById('spinner');
  btn.disabled = true;
  spinner.style.display = 'block';

  const payload = {
    algorithm:      document.getElementById('ctl-algo').value,
    drop_policy:    document.getElementById('ctl-policy').value,
    bandwidth_kbps: +document.getElementById('ctl-bw').value,
    delay_ms:       +document.getElementById('ctl-delay').value,
    queue_size:     +document.getElementById('ctl-queue').value,
    num_packets:    +document.getElementById('ctl-pkts').value,
  };

  fetch('/api/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  })
  .then(r => r.json())
  .then(data => {
    if (!data.ok) { alert('Simulation error: ' + (data.error||'unknown')); return; }

    // Update stats bar
    document.getElementById('stat-loss').textContent = data.stats.loss_rate_pct + '%';
    document.getElementById('stat-cwnd').textContent = data.stats.peak_cwnd;
    document.getElementById('stat-rtt').textContent  = data.stats.avg_rtt_ms + ' ms';
    document.getElementById('stat-drop').textContent = data.stats.packets_dropped;

    const COLOR = '#378ADD';
    const ds = (label, d, color) => ({
      label, data: d, borderColor: color, backgroundColor: color+'22',
      borderWidth: 2, pointRadius: 0, fill: false, tension: 0.3,
    });

    // cwnd chart
    const cwndChart = makeChart('live-cwnd', 'cwnd (packets)');
    cwndChart.data.datasets = [ds('cwnd', data.cwnd_log, COLOR)];

    // Add loss event vertical lines as scatter points
    if (data.loss_events.length) {
      cwndChart.data.datasets.push({
        label: 'Loss event', type: 'scatter',
        data: data.loss_events.map(t => ({x:t, y:0})),
        backgroundColor: '#E24B4A', pointRadius: 4, pointStyle: 'triangle',
      });
    }
    cwndChart.update('none');

    const qChart = makeChart('live-queue', 'Queue (packets)');
    qChart.data.datasets = [ds('queue size', data.queue_log, '#EF9F27')];
    qChart.update('none');

    const tpChart = makeChart('live-tp', 'Throughput (kbps)');
    tpChart.data.datasets = [ds('throughput', data.tp_log, '#1D9E75')];
    tpChart.update('none');
  })
  .catch(e => alert('Error: ' + e))
  .finally(() => { btn.disabled = false; spinner.style.display = 'none'; });
}

// ── Benchmark mode ────────────────────────────────────────────────────────────
function loadBench(scenario, btn) {
  currentScenario = scenario;
  document.querySelectorAll('.scen-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  // Load all 3 charts in parallel
  Promise.all([
    fetch(`/api/chart/cwnd?scenario=${scenario}`).then(r=>r.json()),
    fetch(`/api/chart/queue?scenario=${scenario}`).then(r=>r.json()),
    fetch(`/api/chart/throughput?scenario=${scenario}`).then(r=>r.json()),
    fetch(`/api/chart/heatmap?scenario=${scenario}`).then(r=>r.json()),
    fetch('/api/summary').then(r=>r.json()),
  ]).then(([cwnd, queue, tp, hm, summary]) => {
    // Charts
    makeChart('bench-cwnd',  'cwnd (packets)');
    makeChart('bench-queue', 'Queue (packets)');
    makeChart('bench-tp',    'Throughput (Mbps)');
    applyChartData(charts['bench-cwnd'],  cwnd);
    applyChartData(charts['bench-queue'], queue);
    applyChartData(charts['bench-tp'],    tp);

    // Heatmap
    renderHeatmap(hm);

    // Summary table
    renderTable(summary, scenario);
  });
}

function renderHeatmap(hm) {
  const container = document.getElementById('heatmap-container');
  if (!hm.values || !hm.values.length) {
    container.innerHTML = '<p style="color:var(--muted);padding:16px;">Run benchmarks first: python -m benchmarks.run_all</p>';
    return;
  }
  const nRows = hm.n_rows, nCols = hm.n_cols;

  let html = `<div style="display:flex;gap:8px;align-items:flex-start;margin-top:8px;">`;

  // Row labels
  html += `<div style="display:flex;flex-direction:column;gap:3px;padding-top:0;">`;
  hm.labels_x.forEach(l => {
    html += `<div style="height:28px;line-height:28px;font-size:10px;color:var(--muted);
                         white-space:nowrap;padding-right:8px;">${l}</div>`;
  });
  html += `</div>`;

  // Grid
  html += `<div style="flex:1;display:flex;flex-direction:column;gap:3px;">`;
  for (let r = 0; r < nRows; r++) {
    html += `<div style="display:flex;gap:3px;">`;
    for (let c = 0; c < nCols; c++) {
      const v = hm.values[r * nCols + c];
      const alpha = Math.round(v * 255).toString(16).padStart(2,'0');
      html += `<div style="flex:1;height:28px;border-radius:3px;background:#E24B4A${alpha};
                           title='intensity ${Math.round(v*100)}%'"></div>`;
    }
    html += `</div>`;
  }
  html += `</div></div>`;

  // Time axis labels
  html += `<div style="display:flex;gap:3px;margin-top:4px;padding-left:0;">`;
  hm.labels_y.forEach(l => {
    html += `<div style="flex:1;font-size:10px;color:var(--muted);text-align:center;">${l}</div>`;
  });
  html += `</div>`;

  container.innerHTML = html;
}

function renderTable(rows, scenario) {
  const container = document.getElementById('summary-table');
  if (!rows || !rows.length) {
    container.innerHTML = '<p style="color:var(--muted);padding:16px;">Run benchmarks/run_all.py first.</p>';
    return;
  }

  const filtered = rows.filter(r => r.scenario === scenario);
  if (!filtered.length) {
    container.innerHTML = '<p style="color:var(--muted);padding:16px;">No data for this scenario yet.</p>';
    return;
  }

  const ALGO_BADGE = {
    'slow_start_aimd': 'badge red',
    'cubic':           'badge blue',
  };
  const DROP_BADGE = {
    'drop_tail': 'badge amber',
    'red':       'badge teal',
  };

  let html = `<table><thead><tr>
    <th>Algorithm</th><th>Drop Policy</th>
    <th>Peak cwnd</th><th>Loss %</th><th>Avg RTT</th><th>Pkts Dropped</th>
  </tr></thead><tbody>`;

  filtered.forEach(r => {
    html += `<tr>
      <td><span class="${ALGO_BADGE[r.algorithm]||'badge'}">${r.algorithm}</span></td>
      <td><span class="${DROP_BADGE[r.drop_policy]||'badge'}">${r.drop_policy}</span></td>
      <td>${r.peak_cwnd}</td>
      <td>${r.loss_rate_pct}%</td>
      <td>${r.avg_rtt_ms} ms</td>
      <td>${r.packets_dropped}</td>
    </tr>`;
  });

  html += '</tbody></table>';
  container.innerHTML = html;
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  // Pre-initialise empty live charts
  makeChart('live-cwnd',  'cwnd (packets)');
  makeChart('live-queue', 'Queue size');
  makeChart('live-tp',    'Throughput (kbps)');
});
</script>
</body>
</html>
"""


# ─────────────────────────────────────────────────────────────────────────────
#  Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


@app.route("/api/chart/<chart_type>")
def chart(chart_type: str):
    scenario = request.args.get("scenario", "high")
    try:
        if chart_type == "cwnd":
            data = cwnd_chart_data(scenario)
        elif chart_type == "queue":
            data = queue_chart_data(scenario)
        elif chart_type == "throughput":
            data = throughput_chart_data(scenario)
        elif chart_type == "heatmap":
            data = heatmap_data(scenario)
        else:
            return jsonify({"error": f"Unknown chart type: {chart_type}"}), 400
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/summary")
def summary():
    try:
        return jsonify(summary_table_data())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/controls")
def controls():
    return jsonify(SimParams().to_frontend_config())


@app.route("/api/run", methods=["POST"])
def run():
    try:
        body   = request.get_json(force=True) or {}
        params = SimParams.from_dict(body)
        result = run_live(params)
        return jsonify(result)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def start(host: str = "127.0.0.1", port: int = 8050, debug: bool = False):
    print(f"\n  Dashboard running →  http://{host}:{port}\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    start(debug=True)