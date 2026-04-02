"""
benchmarks/run_all.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Benchmark runner — compares all algorithm combinations across 3 traffic scenarios.

Scenarios:
  1. low_congestion   — large queue, low packet count (normal traffic)
  2. high_congestion  — small queue, high packet count (bottleneck link)
  3. bursty           — medium queue, alternating burst/idle windows

Output:
  benchmarks/results/<scenario>_<algo>_<policy>.csv   — per-run time series
  benchmarks/results/summary.csv                       — aggregate comparison table

Run from project root:
  python -m benchmarks.run_all
"""

import os
import csv
import time
from dataclasses import dataclass
from typing import List

# ── project imports ──────────────────────────────────────────────────────────
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.network import Router
from sim.sender import Sender
from sim.receiver import Receiver


# ── output directory ─────────────────────────────────────────────────────────
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── scenario definitions ──────────────────────────────────────────────────────
@dataclass
class Scenario:
    name: str
    bandwidth_kbps: int
    delay_ms: float
    queue_size: int
    num_packets: int
    description: str


SCENARIOS: List[Scenario] = [
    Scenario(
        name="low_congestion",
        bandwidth_kbps=2000,
        delay_ms=30,
        queue_size=50,
        num_packets=200,
        description="Normal traffic — large buffer, plenty of bandwidth",
    ),
    Scenario(
        name="high_congestion",
        bandwidth_kbps=500,
        delay_ms=80,
        queue_size=10,
        num_packets=300,
        description="Bottleneck link — small buffer, limited bandwidth",
    ),
    Scenario(
        name="bursty",
        bandwidth_kbps=1000,
        delay_ms=50,
        queue_size=20,
        num_packets=250,
        description="Bursty traffic — medium settings, simulates real internet load",
    ),
]

# ── algorithm + drop-policy combinations to test ─────────────────────────────
COMBINATIONS = [
    ("slow_start_aimd", "drop_tail"),
    ("slow_start_aimd", "red"),
    ("cubic",           "drop_tail"),
    ("cubic",           "red"),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def run_single(scenario: Scenario, algorithm: str, drop_policy: str) -> dict:
    """
    Run one simulation and return aggregated metrics + time series data.
    """
    router = Router(
        bandwidth_kbps=scenario.bandwidth_kbps,
        delay_ms=scenario.delay_ms,
        queue_size=scenario.queue_size,
        drop_policy=drop_policy,
    )
    sender = Sender(router, algorithm=algorithm)

    t_start = time.time()
    state = sender.run(num_packets=scenario.num_packets, verbose=False)
    elapsed = time.time() - t_start

    stats = router.stats
    peak_cwnd = max((v for _, v in state.cwnd_log), default=0)
    avg_cwnd  = (
        sum(v for _, v in state.cwnd_log) / len(state.cwnd_log)
        if state.cwnd_log else 0
    )
    avg_rtt = (
        sum(r for _, r in state.rtt_log) / len(state.rtt_log)
        if state.rtt_log else 0
    )
    avg_throughput = (
        sum(t for _, t in stats.throughput_log) / len(stats.throughput_log)
        if stats.throughput_log else 0
    )

    return {
        # identity
        "scenario":     scenario.name,
        "algorithm":    algorithm,
        "drop_policy":  drop_policy,
        # aggregate metrics
        "packets_sent":     stats.packets_sent,
        "packets_received": stats.packets_received,
        "packets_dropped":  stats.packets_dropped,
        "loss_rate_pct":    round(stats.loss_rate, 3),
        "delivery_rate_pct":round(stats.delivery_rate, 3),
        "peak_cwnd":        round(peak_cwnd, 3),
        "avg_cwnd":         round(avg_cwnd, 3),
        "avg_rtt_ms":       round(avg_rtt, 3),
        "avg_throughput_kbps": round(avg_throughput, 3),
        "loss_events":      len(state.loss_log),
        "sim_time_sec":     round(elapsed, 4),
        # raw time series (for per-run CSVs)
        "_cwnd_log":        state.cwnd_log,
        "_queue_log":       stats.queue_log,
        "_throughput_log":  stats.throughput_log,
        "_drop_log":        stats.drop_log,
    }


def save_timeseries(result: dict, scenario_name: str, algorithm: str, drop_policy: str):
    """
    Save per-run time series to a CSV file.
    Columns: time, cwnd, queue_size, throughput_kbps, dropped
    """
    fname = f"{scenario_name}__{algorithm}__{drop_policy}.csv"
    fpath = os.path.join(RESULTS_DIR, fname)

    # Align all logs to the same length (pad shorter ones)
    cwnd_log       = result["_cwnd_log"]
    queue_log      = result["_queue_log"]
    throughput_log = result["_throughput_log"]
    drop_log       = result["_drop_log"]

    max_len = max(len(cwnd_log), len(queue_log), len(throughput_log), len(drop_log))

    def safe_get(log, i, default):
        return log[i] if i < len(log) else (None, default)

    with open(fpath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time_s", "cwnd", "queue_size", "throughput_kbps", "dropped"])
        for i in range(max_len):
            t_c,  cwnd   = safe_get(cwnd_log,       i, 0)
            t_q,  qsize  = safe_get(queue_log,       i, 0)
            t_tp, tp     = safe_get(throughput_log,  i, 0)
            t_d,  drop   = safe_get(drop_log,        i, False)

            t = t_c or t_q or t_tp or t_d or i
            writer.writerow([
                round(t, 4),
                round(cwnd, 4),
                int(qsize),
                round(tp, 4),
                1 if drop else 0,
            ])

    return fpath


def save_summary(all_results: list):
    """
    Save aggregate comparison table to summary.csv.
    This is the file that gets plotted as the comparison bar chart.
    """
    fpath = os.path.join(RESULTS_DIR, "summary.csv")
    fields = [
        "scenario", "algorithm", "drop_policy",
        "packets_sent", "packets_received", "packets_dropped",
        "loss_rate_pct", "delivery_rate_pct",
        "peak_cwnd", "avg_cwnd", "avg_rtt_ms",
        "avg_throughput_kbps", "loss_events", "sim_time_sec",
    ]
    with open(fpath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in all_results:
            writer.writerow({k: r[k] for k in fields})

    return fpath


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  Network Congestion Control — Benchmark Suite")
    print("=" * 60)

    all_results = []
    total = len(SCENARIOS) * len(COMBINATIONS)
    run_num = 0

    for scenario in SCENARIOS:
        print(f"\n[Scenario] {scenario.name}")
        print(f"  {scenario.description}")
        print(f"  bandwidth={scenario.bandwidth_kbps}kbps  delay={scenario.delay_ms}ms  "
              f"queue={scenario.queue_size}  packets={scenario.num_packets}")
        print()

        for algo, policy in COMBINATIONS:
            run_num += 1
            label = f"{algo} + {policy}"
            print(f"  [{run_num}/{total}] {label} ...", end=" ", flush=True)

            result = run_single(scenario, algo, policy)
            all_results.append(result)

            ts_path = save_timeseries(result, scenario.name, algo, policy)

            print(
                f"loss={result['loss_rate_pct']:.1f}%  "
                f"peak_cwnd={result['peak_cwnd']:.1f}  "
                f"throughput={result['avg_throughput_kbps']:.1f}kbps  "
                f"→ {os.path.basename(ts_path)}"
            )

    summary_path = save_summary(all_results)

    print("\n" + "=" * 60)
    print(f"  Done! {total} runs completed.")
    print(f"  Results saved to: {RESULTS_DIR}/")
    print(f"  Summary table  : {summary_path}")
    print("=" * 60)

    # Print quick comparison table
    print("\n  Quick comparison (high_congestion scenario):\n")
    print(f"  {'Algorithm':<20} {'Policy':<12} {'Loss%':>6} {'PeakCwnd':>9} {'Thrpt(kbps)':>12}")
    print(f"  {'-'*20} {'-'*12} {'-'*6} {'-'*9} {'-'*12}")
    for r in all_results:
        if r["scenario"] == "high_congestion":
            print(
                f"  {r['algorithm']:<20} {r['drop_policy']:<12} "
                f"{r['loss_rate_pct']:>6.1f} "
                f"{r['peak_cwnd']:>9.1f} "
                f"{r['avg_throughput_kbps']:>12.1f}"
            )
    print()


if __name__ == "__main__":
    main()