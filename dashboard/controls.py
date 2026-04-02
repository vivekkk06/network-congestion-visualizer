"""
Handles the "Live Simulation" panel.

When the user adjusts sliders and clicks "Run Simulation", the frontend
POSTs parameters here. This module:
  1. Validates the incoming parameters
  2. Runs a fresh simulation with those params
  3. Returns cwnd_log, queue_log, loss_rate etc. as JSON
     so the dashboard can update its live charts immediately
     (without needing to re-run benchmarks/run_all.py).
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sim.network import Router
from sim.sender import Sender


# ─────────────────────────────────────────────────────────────────────────────
#  Parameter schema
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SimParams:
    """
    All user-configurable parameters exposed as dashboard sliders.
    Validated and clamped before running the simulation.
    """
    algorithm:     str   = "slow_start_aimd"   # "slow_start_aimd" | "cubic"
    drop_policy:   str   = "drop_tail"          # "drop_tail" | "red"
    bandwidth_kbps: int  = 1000                 # 100 – 5000 kbps
    delay_ms:      float = 50.0                 # 5 – 500 ms
    queue_size:    int   = 20                   # 5 – 100 packets
    num_packets:   int   = 200                  # 50 – 500

    # Slider bounds (used by frontend to build range inputs)
    BOUNDS: dict = field(default_factory=lambda: {
        "bandwidth_kbps": (100,  5000, 100),    # (min, max, step)
        "delay_ms":       (5,    500,  5),
        "queue_size":     (5,    100,  1),
        "num_packets":    (50,   500,  50),
    })

    ALGO_OPTIONS = [
        {"value": "slow_start_aimd", "label": "Slow Start + AIMD"},
        {"value": "cubic",           "label": "TCP Cubic"},
    ]
    DROP_OPTIONS = [
        {"value": "drop_tail", "label": "Drop Tail"},
        {"value": "red",       "label": "RED (Random Early Detection)"},
    ]

    @classmethod
    def from_dict(cls, d: dict) -> "SimParams":
        """Parse and clamp incoming JSON from the frontend."""
        p = cls()
        if d.get("algorithm") in ("slow_start_aimd", "cubic"):
            p.algorithm = d["algorithm"]
        if d.get("drop_policy") in ("drop_tail", "red"):
            p.drop_policy = d["drop_policy"]
        p.bandwidth_kbps = _clamp(int(d.get("bandwidth_kbps", 1000)), 100, 5000)
        p.delay_ms       = _clamp(float(d.get("delay_ms", 50)),       5,   500)
        p.queue_size     = _clamp(int(d.get("queue_size", 20)),        5,   100)
        p.num_packets    = _clamp(int(d.get("num_packets", 200)),      50,  500)
        return p

    def to_frontend_config(self) -> dict:
        """Return slider config the HTML page uses to build controls."""
        return {
            "current": {
                "algorithm":      self.algorithm,
                "drop_policy":    self.drop_policy,
                "bandwidth_kbps": self.bandwidth_kbps,
                "delay_ms":       self.delay_ms,
                "queue_size":     self.queue_size,
                "num_packets":    self.num_packets,
            },
            "bounds":        self.BOUNDS,
            "algo_options":  self.ALGO_OPTIONS,
            "drop_options":  self.DROP_OPTIONS,
        }


# ─────────────────────────────────────────────────────────────────────────────
#  Live simulation runner
# ─────────────────────────────────────────────────────────────────────────────

def run_live(params: SimParams) -> dict:
    """
    Run a fresh simulation with user-supplied params.
    Returns a JSON-serialisable dict with chart data + summary stats.

    Called by app.py POST /api/run
    """
    router = Router(
        bandwidth_kbps=params.bandwidth_kbps,
        delay_ms=params.delay_ms,
        queue_size=params.queue_size,
        drop_policy=params.drop_policy,
    )
    sender = Sender(router, algorithm=params.algorithm)
    state  = sender.run(num_packets=params.num_packets, verbose=False)

    # Downsample logs so the browser doesn't choke
    cwnd_log  = _downsample(state.cwnd_log,          200)
    queue_log = _downsample(router.stats.queue_log,  200)
    tp_log    = _downsample(router.stats.throughput_log, 200)
    loss_log  = state.loss_log[:500]

    peak_cwnd = max((v for _, v in state.cwnd_log), default=0)
    avg_rtt   = (
        sum(r for _, r in state.rtt_log) / len(state.rtt_log)
        if state.rtt_log else 0
    )

    return {
        "ok": True,
        "params": {
            "algorithm":      params.algorithm,
            "drop_policy":    params.drop_policy,
            "bandwidth_kbps": params.bandwidth_kbps,
            "delay_ms":       params.delay_ms,
            "queue_size":     params.queue_size,
            "num_packets":    params.num_packets,
        },
        "stats": {
            "loss_rate_pct":     round(router.stats.loss_rate, 2),
            "delivery_rate_pct": round(router.stats.delivery_rate, 2),
            "peak_cwnd":         round(peak_cwnd, 2),
            "avg_rtt_ms":        round(avg_rtt, 2),
            "packets_sent":      router.stats.packets_sent,
            "packets_dropped":   router.stats.packets_dropped,
        },
        "cwnd_log":  [{"x": round(t, 3), "y": round(v, 2)} for t, v in cwnd_log],
        "queue_log": [{"x": round(t, 3), "y": v}           for t, v in queue_log],
        "tp_log":    [{"x": round(t, 3), "y": round(v, 1)} for t, v in tp_log],
        "loss_events": [round(t, 3) for t, _ in loss_log],
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(value, lo, hi):
    return max(lo, min(hi, value))


def _downsample(log: list, max_pts: int) -> list:
    if len(log) <= max_pts:
        return log
    step = max(1, len(log) // max_pts)
    return log[::step]