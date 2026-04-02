"""
RED — Random Early Detection (Floyd & Jacobson, 1993)

The core insight:
─────────────────
Instead of waiting for the queue to be completely full (like Drop Tail),
RED monitors the *average queue length* and starts dropping packets
probabilistically BEFORE the queue overflows.

This serves as an early congestion signal to TCP senders, letting them
back off individually before the whole link collapses.

The RED algorithm:
──────────────────
1. Compute exponentially weighted moving average of queue length:
     avg_q = (1 - w_q) × avg_q + w_q × current_q
   (w_q is a small weight, typically 0.002)

2. When a new packet arrives:
   ┌─────────────────────────────────────────────────────────┐
   │  avg_q < min_th  → ACCEPT (no congestion)               │
   │  avg_q > max_th  → DROP (severe congestion)             │
   │  min_th ≤ avg_q ≤ max_th → DROP with probability p:    │
   │    p = max_p × (avg_q − min_th) / (max_th − min_th)    │
   └─────────────────────────────────────────────────────────┘

Key advantages over Drop Tail:
───────────────────────────────
  ✓ No global synchronization — flows get independent random signals
  ✓ Lower average queue → lower latency (avoids bufferbloat)
  ✓ Higher throughput under heavy load
  ✗ Requires parameter tuning (min_th, max_th, max_p, w_q)
  ✗ Slightly more CPU per packet

Typical parameters (RFC 2309):
───────────────────────────────
  min_th  = 5–20 packets
  max_th  = 3× min_th
  max_p   = 0.02–0.1
  w_q     = 0.002

Interview insight: RED was the dominant AQM for 20 years. It's been
largely succeeded by CoDel (Controlled Delay) and FQ-CoDel, which
are delay-based rather than queue-length-based. But RED remains the
textbook AQM algorithm.
"""

import random


class RED:
    """
    Random Early Detection active queue management.

    Used by the Router when drop_policy='red'.
    Can also be instantiated standalone for custom integration.

    The actual drop decision in benchmarks is handled by
    Router._red_drop(), which uses the router's configured thresholds.
    This class provides the full weighted-average variant used
    when you want more precise RED behavior.
    """

    name = "red"
    display_name = "RED"
    description = "Probabilistic early drop based on avg queue length"
    color = "#1D9E75"  # Teal — used in benchmark plots

    def __init__(
        self,
        min_threshold: float = 5.0,
        max_threshold: float = 15.0,
        max_drop_prob: float = 0.1,
        w_q: float = 0.002,
        queue_size: int = 20,
    ):
        """
        Args:
            min_threshold  : avg queue length below which no drops occur
            max_threshold  : avg queue length above which all packets drop
            max_drop_prob  : maximum drop probability in the linear zone
            w_q            : weight for EWMA queue length smoothing
            queue_size     : physical queue capacity (hard limit)
        """
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold
        self.max_drop_prob = max_drop_prob
        self.w_q = w_q
        self.queue_size = queue_size

        # Internal state
        self._avg_queue = 0.0         # EWMA of queue length
        self._count = 0               # Packets since last drop
        self._q_time = 0.0            # Time queue became empty (for idle adjustment)

        # Logs for visualization
        self.avg_queue_log = []       # [(step, avg_q)]
        self.drop_prob_log = []       # [(step, drop_prob)]
        self._step = 0

    # ------------------------------------------------------------------ #
    #  Main decision method                                                #
    # ------------------------------------------------------------------ #

    def should_drop(self, current_queue_length: int) -> bool:
        """
        Decide whether to drop an arriving packet.

        Args:
            current_queue_length: Number of packets currently in queue

        Returns:
            True → drop this packet
            False → accept this packet
        """
        self._step += 1

        # Step 1: Update EWMA of queue length
        self._avg_queue = (
            (1 - self.w_q) * self._avg_queue + self.w_q * current_queue_length
        )
        self.avg_queue_log.append((self._step, self._avg_queue))

        # Step 2: Hard limit — physical queue full
        if current_queue_length >= self.queue_size:
            self.drop_prob_log.append((self._step, 1.0))
            return True

        # Step 3: Below min threshold → no drop
        if self._avg_queue < self.min_threshold:
            self._count = 0
            self.drop_prob_log.append((self._step, 0.0))
            return False

        # Step 4: Above max threshold → always drop
        if self._avg_queue >= self.max_threshold:
            self._count = 0
            self.drop_prob_log.append((self._step, 1.0))
            return True

        # Step 5: Linear zone — probabilistic drop
        p = self._compute_drop_probability()
        self.drop_prob_log.append((self._step, p))

        if random.random() < p:
            self._count = 0
            return True

        self._count += 1
        return False

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _compute_drop_probability(self) -> float:
        """
        Linearly interpolate drop probability between min_th and max_th.

        p_b = max_p × (avg_q − min_th) / (max_th − min_th)

        The "count" adjustment makes drops more uniform over time:
        p = p_b / (1 − count × p_b)
        """
        p_b = (
            self.max_drop_prob
            * (self._avg_queue - self.min_threshold)
            / (self.max_threshold - self.min_threshold)
        )
        # Avoid division by zero
        denominator = 1 - self._count * p_b
        if denominator <= 0:
            return 1.0
        p = p_b / denominator
        return min(p, 1.0)

    # ------------------------------------------------------------------ #
    #  Router integration                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def configure_router(router):
        """
        Apply RED settings to a Router instance.

        Args:
            router: sim.network.Router instance
        """
        router.drop_policy = "red"
        return router

    @staticmethod
    def explain() -> str:
        return (
            "RED: Monitors average queue length. "
            "Drops packets probabilistically before the queue fills, "
            "giving early congestion signals to individual TCP flows. "
            "Prevents global synchronization that plagues Drop Tail."
        )

    @staticmethod
    def expected_behavior() -> dict:
        return {
            "loss_pattern": "distributed",      # Drops spread across flows
            "queue_pattern": "stable",           # Queue stays below max_th
            "sync_risk": "low",                  # Random drops = no sync
            "latency_impact": "low",             # Shorter avg queue = less delay
            "suitable_for": "high-traffic links with multiple flows",
        }

    def reset(self):
        """Reset internal state for a fresh benchmark run."""
        self._avg_queue = 0.0
        self._count = 0
        self._step = 0
        self.avg_queue_log.clear()
        self.drop_prob_log.clear()