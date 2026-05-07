#!/usr/bin/env python3
"""Aggregate one day of agent JSONL metrics into a one-page summary.

Reads ~/.hermes/metrics/<cast>/<YYYY-MM-DD>.jsonl (append-only, line-delimited
JSON), aggregates four metric families, and prints a readable report.

JSONL schema (one event per line):

    {
      "ts": "2026-05-03T08:21:00Z",      # ISO8601 UTC
      "cast": "rolemaster",              # agents/casts/<cast>.yaml
      "agent": "Pamplinas",
      "kind": "turn" | "tool" | "heartbeat",
      # turn:       tokens_in, tokens_out, latency_ms
      # tool:       tool, ok (bool)
      # heartbeat:  (no extra fields — count alone)
    }

Emitters: agent_loop.py (heartbeats, latency) and gateway/platforms/daemoncraft.py
(turns + tool calls). Wiring those is tracked as the open item in plans/DC-132.md.

Usage:
    scripts/agent-metrics-report.py            # today, all casts
    scripts/agent-metrics-report.py 2026-05-02
    scripts/agent-metrics-report.py 2026-05-02 --cast rolemaster
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

METRICS_ROOT = Path.home() / ".hermes" / "metrics"


def _read_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _aggregate(events):
    by_agent_turns = defaultdict(lambda: {"count": 0, "tokens_in": 0, "tokens_out": 0, "latency_ms": []})
    by_agent_tools = defaultdict(Counter)
    by_agent_heartbeats = Counter()
    tool_failures = Counter()
    for e in events:
        agent = e.get("agent", "?")
        kind = e.get("kind")
        if kind == "turn":
            t = by_agent_turns[agent]
            t["count"] += 1
            t["tokens_in"] += int(e.get("tokens_in", 0) or 0)
            t["tokens_out"] += int(e.get("tokens_out", 0) or 0)
            lat = e.get("latency_ms")
            if isinstance(lat, (int, float)):
                t["latency_ms"].append(lat)
        elif kind == "tool":
            tool = e.get("tool", "?")
            by_agent_tools[agent][tool] += 1
            if e.get("ok") is False:
                tool_failures[(agent, tool)] += 1
        elif kind == "heartbeat":
            by_agent_heartbeats[agent] += 1
    return by_agent_turns, by_agent_tools, by_agent_heartbeats, tool_failures


def _fmt_latency(samples):
    if not samples:
        return "—"
    s = sorted(samples)
    n = len(s)
    p50 = s[n // 2]
    p95 = s[min(n - 1, int(n * 0.95))]
    return f"p50={p50:.0f}ms p95={p95:.0f}ms (n={n})"


def report(date: dt.date, cast_filter: str | None) -> int:
    if not METRICS_ROOT.exists():
        print(f"No metrics dir at {METRICS_ROOT} — nothing to report.")
        print("Emission hooks (agent_loop.py + gateway/platforms/daemoncraft.py) are pending.")
        return 1

    cast_dirs = [d for d in METRICS_ROOT.iterdir() if d.is_dir()]
    if cast_filter:
        cast_dirs = [d for d in cast_dirs if d.name == cast_filter]
    if not cast_dirs:
        print(f"No cast metrics for filter={cast_filter!r} under {METRICS_ROOT}")
        return 1

    print(f"=== Agent metrics — {date.isoformat()} ===\n")
    total_files = 0
    for cast_dir in sorted(cast_dirs):
        path = cast_dir / f"{date.isoformat()}.jsonl"
        events = list(_read_jsonl(path))
        if not events:
            print(f"[{cast_dir.name}] no events ({path})\n")
            continue
        total_files += 1
        turns, tools, hbs, failures = _aggregate(events)
        print(f"[{cast_dir.name}] {len(events)} events from {path.name}")

        for agent in sorted(set(list(turns.keys()) + list(tools.keys()) + list(hbs.keys()))):
            t = turns.get(agent, {})
            print(f"  {agent}:")
            if t.get("count"):
                print(f"    turns:      {t['count']}  tokens_in={t['tokens_in']:,}  tokens_out={t['tokens_out']:,}")
                print(f"    latency:    {_fmt_latency(t['latency_ms'])}")
            if hbs.get(agent):
                # rate per minute over a 24h day
                print(f"    heartbeats: {hbs[agent]}  (avg {hbs[agent] / 1440:.2f}/min)")
            agent_tools = tools.get(agent)
            if agent_tools:
                top = ", ".join(f"{name}={n}" for name, n in agent_tools.most_common(5))
                print(f"    tools:      {top}")
            agent_failures = {tn: c for (a, tn), c in failures.items() if a == agent}
            if agent_failures:
                fails = ", ".join(f"{tn}={c}" for tn, c in sorted(agent_failures.items(), key=lambda x: -x[1]))
                print(f"    failures:   {fails}")
        print()
    return 0 if total_files else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("date", nargs="?", help="YYYY-MM-DD, default today (UTC)")
    parser.add_argument("--cast", help="filter to one cast (default: all)")
    args = parser.parse_args()

    if args.date:
        try:
            date = dt.date.fromisoformat(args.date)
        except ValueError:
            print(f"Bad date: {args.date!r} (want YYYY-MM-DD)", file=sys.stderr)
            sys.exit(2)
    else:
        date = dt.datetime.utcnow().date()

    sys.exit(report(date, args.cast))


if __name__ == "__main__":
    main()
