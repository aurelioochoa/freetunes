"""Charge-rate estimator.

iOS exposes no time-to-full API (no cycle count, no wattage, no ETA), so
time-until-full is *estimated* from battery-% samples collected on each
/devices poll. The UI must always label it approximate ("~").
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field


@dataclass
class ChargeEstimator:
    window_seconds: float = 1800.0
    min_span_seconds: float = 120.0
    _samples: dict[str, deque] = field(default_factory=dict, repr=False)

    def record(self, udid: str, pct: int, charging: bool,
               now: float) -> int | None:
        """Feed one poll sample. Returns ETA minutes, 0 if full, else None."""
        history = self._samples.setdefault(udid, deque())
        if pct >= 100:
            history.clear()
            return 0
        if not charging or pct < 0:
            history.clear()
            return None
        history.append((now, pct))
        while history and now - history[0][0] > self.window_seconds:
            history.popleft()
        if len(history) < 2:
            return None
        span_min = (history[-1][0] - history[0][0]) / 60.0
        if span_min * 60.0 < self.min_span_seconds:
            return None
        rate = (history[-1][1] - history[0][1]) / span_min  # % per minute
        if rate <= 0:
            return None
        return math.ceil((100 - history[-1][1]) / rate)
