"""
receiver.py - TCP Receiver

Pulls forwarded packets from the router buffer and tracks:
  - Which packets arrived (for reorder detection)
  - Out-of-order arrivals (for duplicate ACK generation)
  - Receive window statistics
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional, Set

from sim.network import Router, Packet


@dataclass
class ReceiverState:
    """Mutable state tracked by the receiver."""
    received_seqs: Set[int] = field(default_factory=set)   # All arrived seq nums
    out_of_order: List[int] = field(default_factory=list)  # Packets buffered OOO
    expected_seq: int = 0                                   # Next expected seq num
    total_received: int = 0
    total_bytes: int = 0

    # Logs for visualization
    arrival_log: List[tuple] = field(default_factory=list)  # (time, seq_num)
    dup_ack_log: List[tuple] = field(default_factory=list)  # (time, seq_num)


class Receiver:
    """
    Simulates a TCP receiver.

    Dequeues packets from the router buffer and generates ACKs.
    In this simulation, ACKs are returned directly (no separate ACK channel).

    Usage:
        Called by the Sender internally via router.dequeue().
        Can also be used standalone to inspect what arrived.
    """

    def __init__(self, router: Router):
        self.router = router
        self.state = ReceiverState()
        self._start_time = time.time()

    #  Public API                                                          

    def receive(self) -> Optional[int]:
        """
        Pull one packet from the router and process it.
        Returns the ACK number (next expected seq), or None if buffer empty.
        """
        packet = self.router.dequeue()
        if packet is None:
            return None

        return self._process(packet)

    def receive_all(self) -> List[int]:
        """Drain the entire router buffer and return all ACK numbers."""
        acks = []
        while True:
            ack = self.receive()
            if ack is None:
                break
            acks.append(ack)
        return acks

    def reset(self):
        """Reset receiver state for a fresh run."""
        self.state = ReceiverState()
        self._start_time = time.time()

    # ------------------------------------------------------------------ #
    #  Internals                                                           #
    # ------------------------------------------------------------------ #

    def _process(self, packet: Packet) -> int:
        """
        Handle an arriving packet:
          - In-order → advance expected_seq, return cumulative ACK
          - Out-of-order → buffer it, return duplicate ACK (expected_seq unchanged)
        """
        now = self._now()
        seq = packet.seq_num

        self.state.received_seqs.add(seq)
        self.state.total_received += 1
        self.state.total_bytes += packet.size
        self.state.arrival_log.append((now, seq))

        if seq == self.state.expected_seq:
            # In-order: advance and flush any buffered OOO packets
            self.state.expected_seq += 1
            self._flush_out_of_order()
        elif seq > self.state.expected_seq:
            # Gap detected → buffer this packet, send dup ACK
            self.state.out_of_order.append(seq)
            self.state.out_of_order.sort()
            self.state.dup_ack_log.append((now, self.state.expected_seq))
        # seq < expected_seq → duplicate/retransmit, ignore silently

        return self.state.expected_seq  # Cumulative ACK

    def _flush_out_of_order(self):
        """
        After an in-order packet arrives, check if buffered OOO packets
        can now be delivered in sequence.
        """
        while self.state.out_of_order:
            next_expected = self.state.expected_seq
            if self.state.out_of_order[0] == next_expected:
                self.state.out_of_order.pop(0)
                self.state.expected_seq += 1
            else:
                break

    def _now(self) -> float:
        return time.time() - self._start_time

    #  Display                                                             

    def summary(self) -> str:
        s = self.state
        dup_acks = len(s.dup_ack_log)
        return (
            f"\n{'='*45}\n"
            f"  Receiver Summary\n"
            f"{'='*45}\n"
            f"  Total received : {s.total_received}\n"
            f"  Total bytes    : {s.total_bytes:,} B\n"
            f"  Duplicate ACKs : {dup_acks}\n"
            f"  Out-of-order   : {len(s.out_of_order)} buffered\n"
            f"  Next expected  : seq {s.expected_seq}\n"
            f"{'='*45}\n"
        )