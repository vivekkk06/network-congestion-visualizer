"""
TCP Cubic — Default congestion control in Linux since kernel 2.6.19

Why Cubic exists:
Classic AIMD grows cwnd linearly (+1 per RTT). On high-bandwidth,
long-delay links (e.g. 10Gbps transcontinental), it takes thousands
of RTTs to fill the pipe after a loss. Cubic fixes this.

The cubic growth function:

After a loss event, Cubic records W_max (cwnd at loss point) and the
time of the last loss T_last_loss.

cwnd(t) = C × (t − K)³ + W_max

Where:
  t         = time since last loss event
  K         = ∛(W_max × β / C)   — time to reach W_max again
  C         = 0.4  (scaling constant)
  β         = 0.7  (multiplicative decrease factor, gentler than AIMD's 0.5)

Key properties:
  - Far below W_max → grows FAST (cubic curve is steep)
  - Near W_max → grows SLOWLY (flat part of curve), probes carefully
  - Above W_max → grows FAST again (exploring new bandwidth)

Interview insight: Cubic is "self-clocking" — it doesn't depend on RTT
for its growth rate. Two Cubic flows with different RTTs converge to
fair bandwidth sharing, unlike AIMD which biases short-RTT flows.

Reference: Ha, S., Rhee, I., Xu, L. (2008). CUBIC: A New TCP-Friendly
           High-Speed TCP Variant. ACM SIGOPS.
"""

import math
import time


class TCPCubic:
    """
    TCP Cubic congestion control.

    Called by Sender.run() after each transmission window.
    Mutates SenderState in place.
    """

    # Cubic constants (from Linux kernel implementation)
    C = 0.4       # Cubic scaling factor
    BETA = 0.7    # Multiplicative decrease (gentler than AIMD's 0.5)

    def __init__(self):
        self._w_max = 10.0         # cwnd at last loss event
        self._t_last_loss = 0.0   # Wall-clock time of last loss
        self._k = 0.0              # Time to reach W_max from current cwnd
        self._origin_point = 0.0  # cwnd at start of current epoch
        self._in_slow_start = True
        self._ssthresh = 64.0
        self._start_time = time.time()

    def on_window_complete(self, state, acked: int, lost: bool, max_cwnd: float):
        """
        Called once per transmission window.

        Args:
            state    : SenderState (cwnd, ssthresh modified in place)
            acked    : Packets successfully acknowledged this window
            lost     : True if any drop occurred
            max_cwnd : Hard ceiling on cwnd
        """
        if lost:
            self._handle_loss(state)
        else:
            self._handle_ack(state, acked, max_cwnd)

    # ------------------------------------------------------------------ #
    #  Loss handler                                                        #
    # ------------------------------------------------------------------ #

    def _handle_loss(self, state):
        """
        On loss:
          - Record W_max = current cwnd
          - Reduce cwnd by factor β (0.7, gentler than AIMD's 0.5)
          - Recompute K (time to reach W_max from new cwnd)
        """
        self._w_max = state.cwnd
        self._t_last_loss = self._now()
        self._in_slow_start = False

        # Multiplicative decrease (β = 0.7)
        state.cwnd = max(state.cwnd * self.BETA, 2.0)
        state.ssthresh = max(state.cwnd, 2.0)

        # K = cubic_root( W_max * (1-β) / C )
        # This is the time interval until cwnd = W_max again
        self._k = math.pow((self._w_max * (1 - self.BETA)) / self.C, 1 / 3)
        self._origin_point = state.cwnd

    # ------------------------------------------------------------------ #
    #  ACK handler                                                         #
    # ------------------------------------------------------------------ #

    def _handle_ack(self, state, acked: int, max_cwnd: float):
        """
        On successful ACKs, grow cwnd using the cubic function.

        Two modes:
          1. Slow start (before first loss): exponential like classic TCP
          2. Cubic mode (after first loss): W_cubic(t) = C(t-K)³ + W_max
        """
        if self._in_slow_start:
            # Exponential growth until first loss (same as classic Slow Start)
            state.cwnd += acked
            state.cwnd = min(state.cwnd, max_cwnd)
            return

        # Time elapsed since last loss event
        t = self._now() - self._t_last_loss

        # W_cubic(t) = C × (t − K)³ + W_max
        w_cubic = self.C * math.pow(t - self._k, 3) + self._w_max

        # TCP-Friendly (Reno-equivalent) window for fairness
        # Ensures Cubic never starves AIMD flows
        w_reno_friendly = self._w_max * self.BETA + (3 * (1 - self.BETA) / (1 + self.BETA)) * (t / 1.0)

        # Use whichever is larger
        target = max(w_cubic, w_reno_friendly)
        target = min(target, max_cwnd)
        target = max(target, 1.0)

        # Move cwnd toward target (don't jump instantly — increment per ACK)
        if state.cwnd < target:
            state.cwnd += (target - state.cwnd) / state.cwnd
        else:
            state.cwnd = target  # At or above target: hold steady

    #  Internal                                                            

    def _now(self) -> float:
        return time.time() - self._start_time