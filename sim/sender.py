"""
sender.py - TCP Sender with pluggable congestion control algorithms

The sender maintains a congestion window (cwnd) and decides:
  - How many packets to send at once
  - How to grow/shrink cwnd based on ACKs and losses
  - Which algorithm controls this behavior

Data flow:
  Sender → Router (enqueue) → Receiver (dequeue + ACK) → Sender (update cwnd)
"""

import time
from dataclasses import dataclass, field
from typing import List

from sim.network import Router, Packet


@dataclass
class SenderState:
    """All changeable state the sender tracks during a session."""
    cwnd: float = 1.0          # Congestion window (in packets)
    ssthresh: float = 64.0     # Slow start threshold(intital we take it as 64, but it can be changed by the algorithm)
    seq_num: int = 0           # Next sequence number to send
    acked: int = 0             # Highest ACK received
    duplicate_acks: int = 0    # Count of duplicate ACKs (for fast retransmit)

    # Logs for visualization
    cwnd_log: List[tuple] = field(default_factory=list)
    rtt_log: List[tuple] = field(default_factory=list)
    loss_log: List[tuple] = field(default_factory=list)


class Sender:

    ALGORITHMS = ['slow_start_aimd', 'cubic']

    def __init__(self, router: Router, algorithm: str = 'slow_start_aimd', max_cwnd: float = 128.0):
        if algorithm not in self.ALGORITHMS:
            raise ValueError(f"Unknown algorithm '{algorithm}'")

        self.router = router
        self.algorithm = algorithm
        self.max_cwnd = max_cwnd
        self.state = SenderState()
        self._start_time = time.time()

        self._algo = self._load_algorithm(algorithm)


    #  Public API                                                         

    def run(self, num_packets: int = 300, verbose: bool = False) -> SenderState:
        """
        Send `num_packets` packets through the router.
        This is the main simulation loop.
        """
        self.state = SenderState()
        self._start_time = time.time()

        packets_sent = 0

        while packets_sent < num_packets:

            # Send up to cwnd packets in one window
            window = max(1, int(self.state.cwnd))
            window = min(window, num_packets - packets_sent)

            sent_packets = []
            acked_this_round = 0
            loss_this_round = False

            # -------------------- SEND PHASE -------------------- #
            for _ in range(window):
                pkt = Packet(seq_num=self.state.seq_num, size=1000)
                self.state.seq_num += 1

                accepted = self.router.enqueue(pkt)

                if accepted:
                    sent_packets.append(pkt)
                    packets_sent += 1
                else:
                    # Packet dropped at router (queue full)
                    loss_this_round = True
                    packets_sent += 1

            # -------------------- RECEIVE / ACK PHASE -------------------- #
            for _ in range(len(sent_packets)):
                rtt_start = time.time()

                forwarded = self.router.dequeue()

                rtt_ms = (time.time() - rtt_start) * 1000 + self.router.delay_ms * 2

                if forwarded:
                    acked_this_round += 1
                    self.state.acked += 1
                    self.state.rtt_log.append((self._now(), rtt_ms))
                else:
                    loss_this_round = True

            # -------------------- CONGESTION CONTROL -------------------- #
            self._algo.on_window_complete(
                state=self.state,
                acked=acked_this_round,
                lost=loss_this_round,
                max_cwnd=self.max_cwnd,
            )

            # -------------------- LOGGING -------------------- #
            self.state.cwnd_log.append((self._now(), self.state.cwnd))

            if loss_this_round:
                self.state.loss_log.append((self._now(), 'loss'))

            if verbose:
                print(
                    f"t={self._now():.2f}s | cwnd={self.state.cwnd:.2f} | "
                    f"sent={packets_sent}/{num_packets} | "
                    f"loss={'YES' if loss_this_round else 'no'}"
                )

        return self.state

    # ------------------------------------------------------------------ #

    def reset(self):
        self.state = SenderState()
        self._start_time = time.time()
        self._algo = self._load_algorithm(self.algorithm)

    def _now(self) -> float:
        return time.time() - self._start_time

    def _load_algorithm(self, name: str):
        if name == 'slow_start_aimd':
            from sim.algorithms.slow_start import SlowStartAIMD
            return SlowStartAIMD()
        elif name == 'cubic':
            from sim.algorithms.cubic import TCPCubic
            return TCPCubic()

    # ------------------------------------------------------------------ #

    def summary(self) -> str:
        s = self.state
        peak_cwnd = max((v for _, v in s.cwnd_log), default=0)

        avg_rtt = (
            sum(r for _, r in s.rtt_log) / len(s.rtt_log)
            if s.rtt_log else 0
        )

        return (
            f"\n{'='*45}\n"
            f"  Sender Summary [{self.algorithm.upper()}]\n"
            f"{'='*45}\n"
            f"  Packets sent  : {s.seq_num}\n"
            f"  Packets acked : {s.acked}\n"
            f"  Loss events   : {len(s.loss_log)}\n"
            f"  Peak cwnd     : {peak_cwnd:.2f}\n"
            f"  Avg RTT       : {avg_rtt:.2f} ms\n"
            f"{'='*45}\n"
        )