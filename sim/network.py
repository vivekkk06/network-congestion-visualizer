"""
network.py - Core network simulation engine
Simulates a router with configurable bandwidth, delay, and queue (buffer).
Packets flow from sender → router → receiver.
"""

import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Packet:
    """Represents a single network packet."""
    seq_num: int            # Sequence number
    size: int = 1000        # Bytes (default 1KB)
    timestamp: float = 0.0  # Time it was sent

    def __repr__(self):
        return f"Packet(seq={self.seq_num})"


@dataclass
class NetworkStats:
    """Tracks live network statistics."""
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0
    total_bytes: int = 0
    timestamps: list = field(default_factory=list)
    throughput_log: list = field(default_factory=list)   # (time, throughput_kbps)
    queue_log: list = field(default_factory=list)        # (time, queue_size)
    drop_log: list = field(default_factory=list)         # (time, was_dropped)

    @property
    def loss_rate(self) -> float:
        total = self.packets_sent
        return (self.packets_dropped / total * 100) if total > 0 else 0.0

    @property
    def delivery_rate(self) -> float:
        total = self.packets_sent
        return (self.packets_received / total * 100) if total > 0 else 0.0


class Router:
    """
    Simulates a network router/bottleneck link.

    Attributes:
        bandwidth_kbps  : Link capacity in kilobits per second
        delay_ms        : One-way propagation delay in milliseconds
        queue_size      : Max packets the buffer can hold (tail-drop by default)
        drop_policy     : 'drop_tail' or 'red' (Random Early Detection)
    """

    def __init__(
        self,
        bandwidth_kbps: int = 1000,
        delay_ms: float = 50.0,
        queue_size: int = 20,
        drop_policy: str = "drop_tail",
    ):
        self.bandwidth_kbps = bandwidth_kbps
        self.delay_ms = delay_ms
        self.queue_size = queue_size
        self.drop_policy = drop_policy.lower()

        self.buffer: deque = deque()
        self.stats = NetworkStats()
        self._start_time = time.time()

        # RED parameters (used only when drop_policy == 'red')
        self.red_min_threshold = queue_size * 0.3   # Start dropping at 30% full
        self.red_max_threshold = queue_size * 0.8   # Drop all at 80% full
        self.red_max_drop_prob = 0.5                 # Max drop probability

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    def enqueue(self, packet: Packet) -> bool:
        """
        Try to place a packet into the router buffer.
        Returns True if accepted, False if dropped.
        """
        self.stats.packets_sent += 1
        packet.timestamp = self._now()

        dropped = self._should_drop(packet)

        if dropped:
            self.stats.packets_dropped += 1
            self.stats.drop_log.append((self._now(), True))
            return False

        self.buffer.append(packet)
        self.stats.drop_log.append((self._now(), False))
        self._log_queue()
        return True

    def dequeue(self) -> Optional[Packet]:
        """
        Pull the next packet off the buffer (simulates forwarding).
        Returns None if buffer is empty.
        """
        if not self.buffer:
            return None

        packet = self.buffer.popleft()
        self.stats.packets_received += 1
        self.stats.total_bytes += packet.size

        # Log throughput every packet
        elapsed = self._now()
        throughput = (self.stats.total_bytes * 8) / max(elapsed, 0.001)  # bits/sec
        self.stats.throughput_log.append((elapsed, throughput / 1000))   # kbps
        self._log_queue()
        return packet

    def transmit_delay(self, packet: Packet) -> float:
        """
        Calculate total delay for a packet:
          serialization delay + propagation delay
        """
        serialization_ms = (packet.size * 8) / self.bandwidth_kbps  # ms
        return serialization_ms + self.delay_ms

    def reset(self):
        """Clear buffer and reset stats (call between benchmark runs)."""
        self.buffer.clear()
        self.stats = NetworkStats()
        self._start_time = time.time()

    @property
    def queue_utilization(self) -> float:
        """Returns current buffer fill as a fraction 0.0–1.0."""
        return len(self.buffer) / self.queue_size

    @property
    def current_queue_size(self) -> int:
        return len(self.buffer)

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _should_drop(self, packet: Packet) -> bool:
        """Route to the correct drop policy."""
        if self.drop_policy == "red":
            return self._red_drop()
        return self._drop_tail_drop()

    def _drop_tail_drop(self) -> bool:
        """
        Drop Tail: Accept until full, then drop everything.
        Simple but causes TCP synchronization issues.
        """
        return len(self.buffer) >= self.queue_size

    def _red_drop(self) -> bool:
        """
        Random Early Detection (RED):
        - Below min_threshold → never drop
        - Between min and max → drop with linearly increasing probability
        - Above max_threshold → always drop
        Prevents global synchronization by dropping proactively.
        """
        q = len(self.buffer)

        if q < self.red_min_threshold:
            return False

        if q >= self.red_max_threshold:
            return True

        # Linear interpolation of drop probability
        ratio = (q - self.red_min_threshold) / (
            self.red_max_threshold - self.red_min_threshold
        )
        drop_prob = ratio * self.red_max_drop_prob
        return random.random() < drop_prob

    def _now(self) -> float:
        return time.time() - self._start_time

    def _log_queue(self):
        self.stats.queue_log.append((self._now(), len(self.buffer)))

    # ------------------------------------------------------------------ #
    #  Display                                                             #
    # ------------------------------------------------------------------ #

    def summary(self) -> str:
        s = self.stats
        return (
            f"\n{'='*45}\n"
            f"  Router Summary [{self.drop_policy.upper()}]\n"
            f"{'='*45}\n"
            f"  Packets sent    : {s.packets_sent}\n"
            f"  Packets received: {s.packets_received}\n"
            f"  Packets dropped : {s.packets_dropped}\n"
            f"  Loss rate       : {s.loss_rate:.2f}%\n"
            f"  Delivery rate   : {s.delivery_rate:.2f}%\n"
            f"{'='*45}\n"
        )