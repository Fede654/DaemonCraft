"""Cycle breaker unit tests — pure stdlib, no live state."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make agents/ importable from tests/
sys.path.insert(0, str(Path(__file__).parent.parent / "agents"))

from safety import CycleDetector, signature  # noqa: E402


class TestSignature:
    def test_same_name_same_args_same_sig(self):
        a = signature("!goToPlayer", {"name": "fede", "distance": 3})
        b = signature("!goToPlayer", {"name": "fede", "distance": 3})
        assert a == b

    def test_arg_order_does_not_matter(self):
        a = signature("!x", {"a": 1, "b": 2})
        b = signature("!x", {"b": 2, "a": 1})
        assert a == b

    def test_string_args_get_parsed(self):
        # tool_calls.arguments is usually a JSON string; sig should
        # match the dict equivalent.
        a = signature("!x", '{"a":1,"b":2}')
        b = signature("!x", {"a": 1, "b": 2})
        assert a == b

    def test_diff_name_diff_sig(self):
        a = signature("!goToPlayer", {"name": "fede"})
        b = signature("!followPlayer", {"name": "fede"})
        assert a != b

    def test_diff_args_diff_sig(self):
        a = signature("!goToPlayer", {"name": "fede"})
        b = signature("!goToPlayer", {"name": "alice"})
        assert a != b


class TestCycleDetector:
    def test_below_threshold_no_trigger(self):
        d = CycleDetector(n=4, window=6)
        for _ in range(3):
            r = d.record("!stop", {})
            assert r.triggered is False

    def test_threshold_trigger(self):
        d = CycleDetector(n=4, window=6)
        for _ in range(3):
            r = d.record("!stop", {})
            assert r.triggered is False
        r = d.record("!stop", {})
        assert r.triggered is True
        assert r.count == 4

    def test_no_double_trigger_for_same_cycle(self):
        d = CycleDetector(n=3, window=6)
        # Records 1 and 2 are below threshold
        for _ in range(2):
            r = d.record("!stop", {})
            assert r.triggered is False
        # Record 3 trips the threshold
        r = d.record("!stop", {})
        assert r.triggered is True
        # Records 4+ for the same sig must NOT re-trigger
        for _ in range(5):
            r = d.record("!stop", {})
            assert r.triggered is False

    def test_different_cycle_re_triggers(self):
        d = CycleDetector(n=3, window=6)
        # First cycle: 3 records of !stop trip on the 3rd
        for _ in range(2):
            d.record("!stop", {})
        r = d.record("!stop", {})
        assert r.triggered is True
        # Roll the buffer with non-cycling sigs so !stop gets evicted
        d.record("!inventory", {})
        d.record("!status", {})
        d.record("!look", {})
        # Build up a NEW cycle on a different sig — fires on the 3rd
        d.record("!goToPlayer", {"name": "fede"})
        d.record("!goToPlayer", {"name": "fede"})
        r = d.record("!goToPlayer", {"name": "fede"})
        assert r.triggered is True

    def test_window_smaller_than_n_uses_n_as_cap(self):
        d = CycleDetector(n=5, window=3)
        for _ in range(4):
            d.record("!stop", {})
        r = d.record("!stop", {})
        assert r.triggered is True

    def test_reset_clears_state(self):
        d = CycleDetector(n=3, window=6)
        for _ in range(3):
            d.record("!stop", {})
        d.record("!stop", {})  # triggers
        d.reset()
        # Buffer empty; no trigger until 3 again
        for _ in range(2):
            r = d.record("!stop", {})
            assert r.triggered is False
        r = d.record("!stop", {})
        assert r.triggered is True

    def test_alternating_does_not_trigger(self):
        d = CycleDetector(n=4, window=6)
        for _ in range(6):
            r = d.record("!a" if _ % 2 == 0 else "!b", {})
            assert r.triggered is False, "alternating shouldn't trigger threshold of 4"

    def test_arg_difference_breaks_cycle(self):
        d = CycleDetector(n=3, window=6)
        # Same name, different args each time — none repeated enough
        for i in range(6):
            r = d.record("!goToCoordinates", {"x": i, "y": 64, "z": 0})
            assert r.triggered is False
