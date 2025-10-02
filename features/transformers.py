from __future__ import annotations

import math
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Optional


class RingBins:
    """Fixed-size ring buffer of time-binned values for a rolling window.

    Efficient O(delta) advance when time moves forward and O(k) query where k is number of bins in the requested window.
    """

    def __init__(self, window_seconds: int, bin_size: int) -> None:
        assert window_seconds > 0 and bin_size > 0, "window and bin must be >0"
        self.window_seconds = window_seconds
        self.bin_size = bin_size
        self.n_bins = int(math.ceil(window_seconds / bin_size))
        self.values = [0.0] * self.n_bins
        self.last_bin_index: Optional[int] = None

    def _bin_index(self, now: float) -> int:
        return int(now // self.bin_size)

    def _advance(self, now_bin: int) -> None:
        if self.last_bin_index is None:
            self.last_bin_index = now_bin
            return
        delta = now_bin - self.last_bin_index
        if delta <= 0:
            return
        if delta >= self.n_bins:
            # time jumped past entire window; clear all
            for i in range(self.n_bins):
                self.values[i] = 0.0
        else:
            # zero-out bins between last and now
            for i in range(1, delta + 1):
                idx = (self.last_bin_index + i) % self.n_bins
                self.values[idx] = 0.0
        self.last_bin_index = now_bin

    def add(self, value: float, now: Optional[float] = None) -> None:
        t = now if now is not None else time.time()
        now_bin = self._bin_index(t)
        self._advance(now_bin)
        idx = now_bin % self.n_bins
        self.values[idx] += float(value)

    def sum(self, window_seconds: Optional[int] = None, now: Optional[float] = None) -> float:
        if self.last_bin_index is None:
            return 0.0
        t = now if now is not None else time.time()
        now_bin = self._bin_index(t)
        self._advance(now_bin)
        span = self.window_seconds if window_seconds is None else min(self.window_seconds, window_seconds)
        # Include the lower boundary by adding one bin
        k = int(math.floor(span / self.bin_size)) + 1
        total = 0.0
        for j in range(k):
            idx = (now_bin - j) % self.n_bins
            total += self.values[idx]
        return total


@dataclass
class EntityStats:
    # Transactions (store timestamps; derive counts for windows)
    _tx_times: Deque[float] = field(default_factory=deque)
    # Amount aggregations
    amt_1h: RingBins = field(default_factory=lambda: RingBins(3600, 60))
    amt_sum_24h: RingBins = field(default_factory=lambda: RingBins(86400, 3600))
    amt_cnt_24h: RingBins = field(default_factory=lambda: RingBins(86400, 3600))
    # SMS
    sms_total_1h: RingBins = field(default_factory=lambda: RingBins(3600, 60))
    sms_links_1h: RingBins = field(default_factory=lambda: RingBins(3600, 60))
    # Email
    email_total_24h: RingBins = field(default_factory=lambda: RingBins(86400, 3600))
    email_spoof_24h: RingBins = field(default_factory=lambda: RingBins(86400, 3600))
    # Unique merchants (24h TTL)
    merchant_last_seen: Dict[str, float] = field(default_factory=dict)
    # Switch events (24h TTL)
    device_switch_events: Deque[float] = field(default_factory=deque)
    geo_switch_events: Deque[float] = field(default_factory=deque)
    # Last seen states
    last_device_id: Optional[str] = None
    last_country: Optional[str] = None

    def record_payment(self, amount: float, merchant_id: str | None, country: str | None, device_id: str | None, now: Optional[float] = None) -> None:
        t = now if now is not None else time.time()
        # tx counts: append time and evict beyond 1h
        self._tx_times.append(t)
        cutoff_1h = t - 3600
        while self._tx_times and self._tx_times[0] < cutoff_1h:
            self._tx_times.popleft()
        # amount
        self.amt_1h.add(amount, t)
        self.amt_sum_24h.add(amount, t)
        self.amt_cnt_24h.add(1.0, t)
        # unique merchants with TTL
        if merchant_id:
            self.merchant_last_seen[merchant_id] = t
        self._gc_merchants(t)
        # device switches
        if device_id is not None:
            if self.last_device_id is not None and device_id != self.last_device_id:
                self.device_switch_events.append(t)
            self.last_device_id = device_id
            self._gc_switches(self.device_switch_events, t)
        # geo switches (by country)
        if country is not None:
            if self.last_country is not None and country != self.last_country:
                self.geo_switch_events.append(t)
            self.last_country = country
            self._gc_switches(self.geo_switch_events, t)

    def record_sms(self, has_link: bool, country: str | None, device_id: str | None, now: Optional[float] = None) -> None:
        t = now if now is not None else time.time()
        self.sms_total_1h.add(1.0, t)
        if has_link:
            self.sms_links_1h.add(1.0, t)
        # switches by device/geo
        if device_id is not None:
            if self.last_device_id is not None and device_id != self.last_device_id:
                self.device_switch_events.append(t)
            self.last_device_id = device_id
            self._gc_switches(self.device_switch_events, t)
        if country is not None:
            if self.last_country is not None and country != self.last_country:
                self.geo_switch_events.append(t)
            self.last_country = country
            self._gc_switches(self.geo_switch_events, t)

    def record_email(self, spoof_flag: bool, country: str | None, device_id: str | None, now: Optional[float] = None) -> None:
        t = now if now is not None else time.time()
        self.email_total_24h.add(1.0, t)
        if spoof_flag:
            self.email_spoof_24h.add(1.0, t)
        # switches
        if device_id is not None:
            if self.last_device_id is not None and device_id != self.last_device_id:
                self.device_switch_events.append(t)
            self.last_device_id = device_id
            self._gc_switches(self.device_switch_events, t)
        if country is not None:
            if self.last_country is not None and country != self.last_country:
                self.geo_switch_events.append(t)
            self.last_country = country
            self._gc_switches(self.geo_switch_events, t)

    def _gc_merchants(self, now: float) -> None:
        cutoff = now - 86400
        stale = [m for m, ts in self.merchant_last_seen.items() if ts < cutoff]
        for m in stale:
            self.merchant_last_seen.pop(m, None)

    @staticmethod
    def _gc_switches(dq: Deque[float], now: float) -> None:
        cutoff = now - 86400
        while dq and dq[0] < cutoff:
            dq.popleft()

    # Readouts
    def txn_count_1m(self) -> float:
        now = time.time()
        cutoff = now - 60
        return float(sum(1 for ts in self._tx_times if ts >= cutoff))

    def txn_count_5m(self) -> float:
        now = time.time()
        cutoff = now - 300
        return float(sum(1 for ts in self._tx_times if ts >= cutoff))

    def txn_count_1h(self) -> float:
        return float(len(self._tx_times))

    def count_in_window(self, window_seconds: int, now: Optional[float] = None) -> float:
        now = now if now is not None else time.time()
        cutoff = now - float(window_seconds)
        return float(sum(1 for ts in self._tx_times if ts >= cutoff))

    def sum_amount_1h(self) -> float:
        return self.amt_1h.sum(3600)

    def avg_amount_24h(self) -> float:
        cnt = self.amt_cnt_24h.sum(86400)
        if cnt <= 0:
            return 0.0
        return self.amt_sum_24h.sum(86400) / max(cnt, 1.0)

    def unique_merchants_24h(self) -> float:
        self._gc_merchants(time.time())
        return float(len(self.merchant_last_seen))

    def geo_switch_24h(self) -> float:
        self._gc_switches(self.geo_switch_events, time.time())
        return float(len(self.geo_switch_events))

    def device_switch_24h(self) -> float:
        self._gc_switches(self.device_switch_events, time.time())
        return float(len(self.device_switch_events))

    def sms_link_ratio_1h(self) -> float:
        total = self.sms_total_1h.sum(3600)
        if total <= 0:
            return 0.0
        return self.sms_links_1h.sum(3600) / total

    def email_spoof_score_24h(self) -> float:
        total = self.email_total_24h.sum(86400)
        if total <= 0:
            return 0.0
        return self.email_spoof_24h.sum(86400) / total


class StatsManager:
    """Holds stats per user and per device."""

    def __init__(self) -> None:
        self.user: Dict[str, EntityStats] = defaultdict(EntityStats)
        self.device: Dict[str, EntityStats] = defaultdict(EntityStats)

    def get_user(self, user_id: str) -> EntityStats:
        return self.user[user_id]

    def get_device(self, device_id: str) -> EntityStats:
        return self.device[device_id]


# Global manager (in-memory). Optionally can be backed by Redis later.
STATS = StatsManager()
