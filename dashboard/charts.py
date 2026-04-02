"""
Chart data builders for the Flask dashboard.

Each function reads simulation state / CSV logs and returns
JSON-serialisable dicts that the frontend (Chart.js) consumes.

Chart types:
  1. cwnd_chart_data()       — congestion window over time (line chart)
  2. queue_chart_data()      — queue occupancy over time (area chart)
  3. throughput_chart_data() — throughput over time (line chart)
  4. heatmap_data()          — link congestion heatmap (grid)
  5. summary_table_data()    — benchmark summary rows from CSV
"""

import os
import csv
from typing import List, Dict, Any

# 🔥 Scenario mapping (frontend → backend)
SCENARIO_MAP = {
    "high": "high_congestion",
    "low": "low_congestion",
    "bursty": "bursty"
}

# Colour palette
SERIES_COLORS = {
    "slow_start_aimd__drop_tail": "#E24B4A",
    "slow_start_aimd__red":       "#EF9F27",
    "cubic__drop_tail":           "#378ADD",
    "cubic__red":                 "#1D9E75",
}

SERIES_LABELS = {
    "slow_start_aimd__drop_tail": "AIMD + Drop Tail",
    "slow_start_aimd__red":       "AIMD + RED",
    "cubic__drop_tail":           "Cubic + Drop Tail",
    "cubic__red":                 "Cubic + RED",
}

# ─────────────────────────────────────────────────────────────
# 🔥 AUTO RUN BENCHMARKS
# ─────────────────────────────────────────────────────────────

def ensure_benchmarks_exist():
    """
    Ensures benchmark CSV files exist.
    If not, automatically runs benchmarks.
    """
    from benchmarks.run_all import main as run_bench

    path = os.path.join(
        os.path.dirname(__file__), "..", "benchmarks", "results", "summary.csv"
    )

    if not os.path.exists(path):
        print("⚡ Running benchmarks automatically...")
        run_bench()

# ─────────────────────────────────────────────────────────────

def _read_csv(path: str) -> List[Dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def _results_dir() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "benchmarks", "results")

def _downsample(rows: list, max_points: int = 200) -> list:
    """Reduce number of data points so charts don't lag."""
    if len(rows) <= max_points:
        return rows
    step = max(1, len(rows) // max_points)
    return rows[::step]

# ─────────────────────────────────────────────────────────────
# 📊 CHARTS
# ─────────────────────────────────────────────────────────────

def cwnd_chart_data(scenario: str = "high") -> Dict[str, Any]:
    ensure_benchmarks_exist()

    scenario_real = SCENARIO_MAP.get(scenario, scenario)
    results_dir = _results_dir()
    datasets = []

    for tag, label in SERIES_LABELS.items():
        algo, policy = tag.split("__")

        path = os.path.join(
            results_dir,
            f"{scenario_real}__{algo}__{policy}.csv"
        )

        rows = _downsample(_read_csv(path))
        if not rows:
            continue

        datasets.append({
            "label": label,
            "data": [
                {"x": round(float(r["time_s"]) * 1000, 2), "y": round(float(r["cwnd"]), 2)}
                for r in rows
            ],
            "borderColor": SERIES_COLORS[tag],
            "backgroundColor": SERIES_COLORS[tag] + "22",
            "borderWidth": 2,
            "pointRadius": 0,
            "fill": False,
            "tension": 0.3,
        })

    return {
        "type": "line",
        "data": {"datasets": datasets},
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"Congestion Window (cwnd) over Time — {scenario} scenario"
                }
            },
            "scales": {
                "x": {"title": {"display": True, "text": "Time (ms)"}},
                "y": {"title": {"display": True, "text": "cwnd (packets)"}}
            }
        }
    }

# ─────────────────────────────────────────────────────────────

def queue_chart_data(scenario: str = "high") -> Dict[str, Any]:
    ensure_benchmarks_exist()

    scenario_real = SCENARIO_MAP.get(scenario, scenario)
    results_dir = _results_dir()
    datasets = []

    for tag, label in SERIES_LABELS.items():
        algo, policy = tag.split("__")

        path = os.path.join(
            results_dir,
            f"{scenario_real}__{algo}__{policy}.csv"
        )

        rows = _downsample(_read_csv(path))
        if not rows:
            continue

        datasets.append({
            "label": label,
            "data": [
                {"x": round(float(r["time_s"]) * 1000, 2), "y": int(r["queue_size"])}
                for r in rows
            ],
            "borderColor": SERIES_COLORS[tag],
            "backgroundColor": SERIES_COLORS[tag] + "33",
            "borderWidth": 2,
            "pointRadius": 0,
            "fill": True,
            "tension": 0.2,
        })

    return {
        "type": "line",
        "data": {"datasets": datasets},
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"Queue Occupancy — {scenario} scenario"
                }
            },
            "scales": {
                "x": {"title": {"display": True, "text": "Time (ms)"}},
                "y": {"title": {"display": True, "text": "Packets in queue"}}
            }
        }
    }

# ─────────────────────────────────────────────────────────────

def throughput_chart_data(scenario: str = "high") -> Dict[str, Any]:
    ensure_benchmarks_exist()

    scenario_real = SCENARIO_MAP.get(scenario, scenario)
    results_dir = _results_dir()
    datasets = []

    for tag, label in SERIES_LABELS.items():
        algo, policy = tag.split("__")

        path = os.path.join(
            results_dir,
            f"{scenario_real}__{algo}__{policy}.csv"
        )

        rows = _downsample(_read_csv(path))
        if not rows:
            continue

        datasets.append({
            "label": f"{label}",
            "data": [
                {
                    "x": round(float(r["time_s"]) * 1000, 2),     # ms
                    "y": round(float(r["throughput_kbps"]) / 1000, 2)  # Mbps
                }
                for r in rows
            ],
            "borderColor": SERIES_COLORS[tag],
            "backgroundColor": SERIES_COLORS[tag] + "22",
            "borderWidth": 2,
            "pointRadius": 0,
            "fill": False,
            "tension": 0.3,
        })

    return {
        "type": "line",
        "data": {"datasets": datasets},
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"Throughput over Time — {scenario} scenario"
                }
            },
            "scales": {
                "x": {"title": {"display": True, "text": "Time (ms)"}},
                "y": {"title": {"display": True, "text": "Throughput (Mbps)"}, "min": 0}
            }
        }
    }

# ─────────────────────────────────────────────────────────────

def heatmap_data(scenario: str = "high") -> Dict[str, Any]:
    ensure_benchmarks_exist()

    scenario_real = SCENARIO_MAP.get(scenario, scenario)
    results_dir = _results_dir()

    combos = list(SERIES_LABELS.keys())
    BUCKETS = 10

    grid = []
    labels_x = list(SERIES_LABELS.values())
    labels_y = [f"t{i+1}" for i in range(BUCKETS)]

    for tag in combos:
        algo, policy = tag.split("__")

        path = os.path.join(
            results_dir,
            f"{scenario_real}__{algo}__{policy}.csv"
        )

        rows = _read_csv(path)
        if not rows:
            grid.extend([0.0] * BUCKETS)
            continue

        times = [float(r["time_s"]) for r in rows]
        queues = [float(r["queue_size"]) for r in rows]

        if not times:
            grid.extend([0.0] * BUCKETS)
            continue

        t_min, t_max = min(times), max(times)
        bucket_size = (t_max - t_min) / BUCKETS if t_max > t_min else 1

        buckets = [[] for _ in range(BUCKETS)]
        for t, q in zip(times, queues):
            idx = min(int((t - t_min) / bucket_size), BUCKETS - 1)
            buckets[idx].append(q)

        MAX_Q = 50
        for b in buckets:
            val = (sum(b) / len(b) / MAX_Q) if b else 0
            grid.append(min(val, 1.0))

    return {
        "labels_x": labels_x,
        "labels_y": labels_y,
        "values": grid,
        "n_cols": BUCKETS,
        "n_rows": len(combos),
    }

# ─────────────────────────────────────────────────────────────

def summary_table_data() -> List[Dict]:
    ensure_benchmarks_exist()

    path = os.path.join(
        os.path.dirname(__file__), "..", "benchmarks", "results", "summary.csv"
    )
    return _read_csv(path)