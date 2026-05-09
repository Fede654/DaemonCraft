"""Tool-call cycle breaker for the agent loop.

Maintains a ring buffer of the last N tool-call signatures (SHA256 over
canonicalized name+args) and reports when the same signature dominates
the recent window — an indicator that the agent is stuck looping.

Inspired by OpenFang's recovery layer (see
`Alter-infra:wiki/openfang.md`); ported as a tiny stdlib-only module.

Configurable thresholds (defaulting to 4 of last 6):
    n      — minimum number of identical sigs in `window` to trigger
    window — sliding window size to inspect
    action — what to do on detection: 'log' | 'pause' | 'chat'

`pause` and `chat` are advisory — the agent loop reads `triggered` and
decides; this module never directly drives the agent.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _canonicalize(args: Any) -> str:
    """Stable JSON for any args structure. Booleans/None stay distinct."""
    try:
        if isinstance(args, str):
            # tool_calls' arguments are usually a JSON string already;
            # try to re-serialize for consistent ordering.
            try:
                args = json.loads(args)
            except Exception:
                return args
        return json.dumps(args, sort_keys=True, default=str)
    except Exception:
        return repr(args)


def signature(name: str, args: Any) -> str:
    """SHA256 of name + canonical args. Stable across turns."""
    payload = f"{name}|{_canonicalize(args)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


@dataclass
class CycleResult:
    triggered: bool
    sig: Optional[str]
    count: int
    window: int
    action: str


@dataclass
class CycleDetector:
    """Ring-buffer cycle detector.

    Each `record(name, args)` appends one signature; `evaluate()` (or the
    return of `record`) reports whether the threshold is hit.
    """
    n: int = 4
    window: int = 6
    action: str = "log"
    _buf: Deque[str] = field(default_factory=deque)
    _last_triggered_sig: Optional[str] = None

    def __post_init__(self) -> None:
        self._buf = deque(maxlen=max(self.window, self.n))

    def record(self, name: str, args: Any) -> CycleResult:
        sig = signature(name, args)
        self._buf.append(sig)
        return self.evaluate()

    def evaluate(self) -> CycleResult:
        if len(self._buf) < self.n:
            return CycleResult(False, None, 0, len(self._buf), self.action)
        # Count occurrences of each sig in the current buffer
        counts: Dict[str, int] = {}
        for s in self._buf:
            counts[s] = counts.get(s, 0) + 1
        # Pick the most common
        top_sig, top_count = max(counts.items(), key=lambda kv: kv[1])
        if top_count >= self.n:
            # Avoid re-triggering on the SAME cycle indefinitely — once
            # we've fired for a sig, suppress until a different sig
            # rises to top.
            if top_sig == self._last_triggered_sig:
                return CycleResult(False, top_sig, top_count, len(self._buf), self.action)
            self._last_triggered_sig = top_sig
            return CycleResult(True, top_sig, top_count, len(self._buf), self.action)
        # Different top now — clear the suppression so future cycles can
        # trigger.
        if self._last_triggered_sig and self._last_triggered_sig != top_sig:
            self._last_triggered_sig = None
        return CycleResult(False, top_sig, top_count, len(self._buf), self.action)

    def reset(self) -> None:
        self._buf.clear()
        self._last_triggered_sig = None
