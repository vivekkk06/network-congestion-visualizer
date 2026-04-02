"""
TCP Classic: Slow Start + AIMD + Fast Retransmit / Fast Recovery

How it works :
1. SLOW START (cwnd < ssthresh)
   cwnd doubles every RTT (exponential growth).
   "Slow" because it starts at 1 — not because it grows slowly.

2. CONGESTION AVOIDANCE / AIMD (cwnd >= ssthresh)
   - Additive Increase: cwnd += 1 per RTT  (linear growth)
   - Multiplicative Decrease: on loss, cwnd halved  (fast halving)

3. FAST RETRANSMIT + FAST RECOVERY
   - 3 duplicate ACKs → assume one packet lost (not full congestion)
   - ssthresh = cwnd / 2
   - cwnd = ssthresh (skip slow start, stay in CA)
   - On timeout (severe loss): ssthresh = cwnd/2, cwnd = 1 (restart)

"""


class SlowStartAIMD:
    """
    Implements Slow Start + AIMD + Fast Retransmit.

    Called by Sender.run() after each transmission window.
    Mutates SenderState in place.
    """

    def __init__(self):
        self._dup_ack_count = 0   # Track dup ACKs internally
        self._in_fast_recovery = False

    def on_window_complete(self, state, acked: int, lost: bool, max_cwnd: float):
        """
        Called once per transmission window with results.

        Args:
            state    : SenderState (cwnd, ssthresh, etc.)
            acked    : Number of packets successfully ACKed this window
            lost     : True if any packet was dropped this window
            max_cwnd : Hard cap on cwnd
        """
        if lost:
            self._handle_loss(state)
        else:
            self._handle_ack(state, acked, max_cwnd)

    #  Loss handler                                                        

    def _handle_loss(self, state):
        """
        On packet loss:
          - Check if 3 dup ACKs (fast retransmit) or timeout.
          - Both halve ssthresh, but differ in cwnd reset.
        """
        self._dup_ack_count += 1

        if self._dup_ack_count >= 3:
            # Fast Retransmit: partial loss signal
            # ssthresh = cwnd / 2, cwnd = ssthresh (stay in CA)
            state.ssthresh = max(state.cwnd / 2, 2.0)
            state.cwnd = state.ssthresh
            self._dup_ack_count = 0
            self._in_fast_recovery = True
        else:
            # Timeout (severe congestion): reset cwnd to 1
            state.ssthresh = max(state.cwnd / 2, 2.0)
            state.cwnd = 1.0
            self._in_fast_recovery = False
            self._dup_ack_count = 0

    
    #  ACK handler                                                        

    def _handle_ack(self, state, acked: int, max_cwnd: float):
        """
        On successful ACK(s):
          - Slow Start phase: exponential growth (double cwnd)
          - Congestion Avoidance: linear growth (+1 per RTT)
        """
        self._dup_ack_count = 0
        self._in_fast_recovery = False

        if state.cwnd < state.ssthresh:
            # ── SLOW START ──────────────────────────────────────
            # Each ACK increases cwnd by 1 → cwnd doubles per RTT
            state.cwnd += acked
        else:
            # ── CONGESTION AVOIDANCE (AIMD) ──────────────────────
            # cwnd increases by 1 per full window (not per ACK)
            # Formula: cwnd += 1/cwnd per ACK → +1 per RTT
            if state.cwnd > 0:
                state.cwnd += acked / state.cwnd

        # Clamp to maximum allowed window
        state.cwnd = min(state.cwnd, max_cwnd)