"""
Drop Tail (FIFO with tail drop) — the simplest queue management policy.

How it works:
─────────────
  - Router maintains a FIFO queue of fixed size N.
  - Packets arriving when queue is full are DROPPED (from the tail).
  - Packets arriving when space is available are ACCEPTED.
  - That's it. No intelligence, no randomness.

Problems with Drop Tail:
────────────────────────
1. TCP Global Synchronization
   All TCP flows detect loss at the same time (when queue fills up).
   All halve their cwnd simultaneously → link goes idle → all ramp up
   together again → fill queue → all drop again. Sawtooth in unison.

2. Lock-Out
   Bursty flows can fill the queue and starve other flows.

3. Full Queue Bias
   Drop Tail implicitly signals congestion only AFTER the queue is full.
   By then, latency is already high (bufferbloat).

Why it's still used:
────────────────────
  Simplicity. Zero per-packet computation. Works fine for low-traffic links.
  Most home routers use Drop Tail.

Compare with RED:
────────────────
  RED drops proactively before the queue fills, avoiding global sync.
  This is the key tradeoff you'll explain in your interview.

Note: The actual drop logic lives in network.py (Router._drop_tail_drop).
This file provides a standalone explainer class used in benchmarks
to clearly label which policy is active.
"""


class DropTail:
    """
    Drop Tail policy descriptor.

    This is a thin wrapper used by the benchmark runner to:
      1. Label results correctly in CSV/plots
      2. Configure the Router with drop_policy='drop_tail'
      3. Provide metadata for comparison reports

    The real implementation is in Router._drop_tail_drop().
    """

    name = "drop_tail"
    display_name = "Drop Tail"
    description = "Accept until full, then drop all arrivals"
    color = "#E24B4A"  # Red — used in benchmark plots

    @staticmethod
    def configure_router(router):
        """
        Apply Drop Tail settings to a Router instance.

        Args:
            router: sim.network.Router instance
        """
        router.drop_policy = "drop_tail"
        return router

    @staticmethod
    def explain() -> str:
        return (
            "Drop Tail: Packets are queued FIFO. "
            "When the buffer is full, every new arriving packet is dropped. "
            "Simple but causes TCP global synchronization."
        )

    @staticmethod
    def expected_behavior() -> dict:
        """
        Expected characteristics for benchmark validation.
        Used in benchmarks/run_all.py to add annotations to plots.
        """
        return {
            "loss_pattern": "bursty",          # Loss comes in bursts
            "queue_pattern": "sawtooth",        # Queue fills and empties cyclically
            "sync_risk": "high",                # TCP flows sync their drops
            "latency_impact": "high",           # Full queue = high standing latency
            "suitable_for": "low-traffic links",
        }