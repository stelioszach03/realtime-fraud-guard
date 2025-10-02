from __future__ import annotations

import bisect
import math
import time
from typing import List, Optional


class RollingWindowPctl:
    """Approximate rolling percentile over a fixed time window using time/value bins.

    - Time is bucketed into fixed-size bins (e.g., 1s); we maintain a ring buffer of counts for each time bin.
    - Values (latency in seconds) are bucketed by predefined edges (histogram); we keep aggregate counts per value bin.
    - Updates are O(1) amortized per event, plus O(B) per time-bin advance (B = number of value bins).
    - Query (current percentile) is O(B).
    """

    def __init__(
        self,
        pctl: float = 95.0,
        window_seconds: int = 300,
        time_bin_size: int = 1,
        value_bin_edges: Optional[List[float]] = None,
    ) -> None:
        self.pctl = pctl
        self.window_seconds = window_seconds
        self.time_bin_size = time_bin_size
        self.n_time_bins = int(math.ceil(window_seconds / time_bin_size))
        # Default latency buckets in seconds (similar to Prometheus hist buckets)
        if value_bin_edges is None:
            value_bin_edges = [
                0.005,
                0.01,
                0.025,
                0.05,
                0.1,
                0.25,
                0.5,
                1.0,
                2.0,
                5.0,
            ]
        self.value_edges = list(sorted(value_bin_edges))
        self.n_value_bins = len(self.value_edges) + 1  # last is +Inf

        # Ring buffer: time_bins x value_bins counts
        self._time_bins = [[0] * self.n_value_bins for _ in range(self.n_time_bins)]
        self._agg = [0] * self.n_value_bins
        self._last_time_index: Optional[int] = None

    def _now_index(self, now: Optional[float] = None) -> int:
        t = now if now is not None else time.time()
        return int(t // self.time_bin_size)

    def _advance(self, now_index: int) -> None:
        if self._last_time_index is None:
            self._last_time_index = now_index
            return
        delta = now_index - self._last_time_index
        if delta <= 0:
            return
        if delta >= self.n_time_bins:
            # full reset
            for i in range(self.n_time_bins):
                row = self._time_bins[i]
                for j in range(self.n_value_bins):
                    if row[j]:
                        self._agg[j] -= row[j]
                        row[j] = 0
        else:
            for step in range(1, delta + 1):
                idx = (self._last_time_index + step) % self.n_time_bins
                row = self._time_bins[idx]
                if any(row):
                    for j in range(self.n_value_bins):
                        if row[j]:
                            self._agg[j] -= row[j]
                            row[j] = 0
        self._last_time_index = now_index

    def _value_bin(self, seconds: float) -> int:
        # returns index in [0, n_value_bins-1]
        pos = bisect.bisect_right(self.value_edges, seconds)
        return pos

    def observe_seconds(self, seconds: float, now: Optional[float] = None) -> None:
        now_idx = self._now_index(now)
        self._advance(now_idx)
        bin_idx = self._value_bin(seconds)
        tslot = now_idx % self.n_time_bins
        self._time_bins[tslot][bin_idx] += 1
        self._agg[bin_idx] += 1

    def observe_ms(self, ms: float, now: Optional[float] = None) -> None:
        self.observe_seconds(ms / 1000.0, now)

    def total_count(self) -> int:
        return sum(self._agg)

    def current_seconds(self) -> float:
        total = self.total_count()
        if total <= 0:
            return 0.0
        target = math.ceil((self.pctl / 100.0) * total)
        cum = 0
        for i, c in enumerate(self._agg):
            cum += c
            if cum >= target:
                # return upper edge of this bucket (or +Inf -> use last edge)
                if i < len(self.value_edges):
                    return float(self.value_edges[i])
                return float(self.value_edges[-1])
        return float(self.value_edges[-1])


# Global p95 tracker over 5 minutes
P95 = RollingWindowPctl(pctl=95.0, window_seconds=300, time_bin_size=1)

