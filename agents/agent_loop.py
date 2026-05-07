#!/usr/bin/env python3
"""
TEST HARNESS ONLY — NOT A RUNTIME

DC-DEP-9: agent_loop.py is now a test harness for the body protocol.
The Hermes gateway adapter is the canonical runtime.

Provides:
- Single-turn test runner (run_test_turn) for one-shot agent turns
- HTTP helpers for direct bot server communication (body protocol testing)
- Mock body utilities for CI testing
- Human Design context generation helpers
- Metrics emission helpers

Usage:
    python agent_loop.py --profile stevie --mock-body
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# Ensure Hermes is on path
HERMES_DIR = Path.home() / ".hermes" / "hermes-agent"
if str(HERMES_DIR) not in sys.path:
    sys.path.insert(0, str(HERMES_DIR))

MC_API_URL = os.getenv("MC_API_URL", "http://localhost:3001")
BOT_USERNAME = os.getenv("MC_USERNAME", "Steve").lower()

# DC-132 metrics — append-only JSONL per cast per UTC day.
_METRICS_DIR_DEFAULT = Path.home() / ".hermes" / "metrics"
METRICS_CAST = os.getenv("MC_METRICS_CAST", "")
METRICS_DIR = Path(os.getenv("MC_METRICS_DIR", str(_METRICS_DIR_DEFAULT)))


def _emit_metric(kind: str, **fields) -> None:
    """Append a JSON line to ~/.hermes/metrics/<cast>/<date>.jsonl. Best-effort.

    Uses a single os.write() with O_APPEND so writes shorter than PIPE_BUF
    (typically 4 KB on Linux) are POSIX-atomic — even with concurrent writers
    or a process kill mid-write, you can't get a half-written line. The
    report script tolerates truncated lines anyway, but this prevents them
    in the first place.
    """
    if not METRICS_CAST:
        return
    try:
        import datetime as _dt

        now = _dt.datetime.utcnow()
        cast_dir = METRICS_DIR / METRICS_CAST
        cast_dir.mkdir(parents=True, exist_ok=True)
        path = cast_dir / f"{now.date().isoformat()}.jsonl"
        record = {
            "ts": now.isoformat(timespec="seconds") + "Z",
            "cast": METRICS_CAST,
            "agent": BOT_USERNAME.capitalize(),
            "kind": kind,
            **fields,
        }
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode("utf-8")
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line)
        finally:
            os.close(fd)
    except Exception:
        # Metrics must never break the test harness.
        pass


# ═══════════════════════════════════════════════════════════════════════════════
# Human Design Integration (DC-144)
# ═══════════════════════════════════════════════════════════════════════════════


def _init_hd_injector(agent_id: str):
    """Initialize HD context injector. Returns (injector, chart_exists) or (None, False)."""
    try:
        from human_design import HDChartStorage, TransitEngine, HDContextInjector

        storage = HDChartStorage(cast_name="rolemaster")
        transits = TransitEngine()
        injector = HDContextInjector(storage, transits)
        chart = storage.load(agent_id)
        return injector, chart is not None
    except Exception as e:
        print(f"[test] HD not available: {e}", flush=True)
        return None, False


def _generate_hd_context(injector, agent_id: str, is_first: bool) -> str:
    """Generate HD context block for this turn."""
    if injector is None:
        return ""
    try:
        from human_design import HDChartStorage, TransitEngine, HDContextInjector

        storage = HDChartStorage(cast_name="rolemaster")
        transits = TransitEngine()
        injector = HDContextInjector(storage, transits)
        minimal_soul = "[[hd-context]]\n"
        injected = injector.inject(minimal_soul, agent_id, is_first_turn=is_first)
        start = injected.find("[[hd-context]]")
        end = injected.find("[[/hd-context]]")
        if start != -1 and end != -1:
            return injected[start + len("[[hd-context]]") : end].strip()
        return ""
    except Exception as e:
        print(f"[test] HD context generation failed: {e}", flush=True)
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _post_json(path: str, payload: dict) -> bool:
    """POST JSON to the bot server. Returns True on success."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{MC_API_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status < 300
    except Exception as e:
        print(f"[test] POST {path} failed: {e}", flush=True)
        return False


def _get_json(path: str) -> dict:
    """GET JSON from the bot server. Returns {} on failure."""
    try:
        with urllib.request.urlopen(f"{MC_API_URL}{path}", timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def send_heartbeat_context(
    status: dict,
    nearby: dict,
    inventory: dict,
    plan: dict,
    events: list,
    hd_context: str = "",
) -> bool:
    """Send a perception snapshot to the gateway via the bot server."""
    payload = {
        "status": status,
        "nearby": nearby,
        "inventory": inventory,
        "plan": plan,
        "events": events,
    }
    if hd_context:
        payload["hd_context"] = hd_context
    return _post_json("/heartbeat/context", payload)


def send_agent_heartbeat(next_turn_in: float | None = None, turn_in_progress: bool = False):
    """Send legacy heartbeat to bot server for dashboard display."""
    _post_json(
        "/agent/heartbeat",
        {"nextTurnIn": next_turn_in, "turnInProgress": turn_in_progress},
    )


def fetch_plan() -> dict:
    """Fetch the bot's current plan from the bot server."""
    try:
        data = _get_json("/plan")
        return data.get("data", {})
    except Exception:
        return {}


def fetch_bot_status() -> dict:
    """Fetch bot status (health, position, food, etc.)."""
    try:
        data = _get_json("/status")
        return data.get("data", {})
    except Exception:
        return {}


def fetch_bot_nearby() -> dict:
    """Fetch nearby entities and blocks."""
    try:
        data = _get_json("/nearby")
        return data.get("data", {})
    except Exception:
        return {}


def fetch_bot_inventory() -> dict:
    """Fetch bot inventory."""
    try:
        data = _get_json("/inventory")
        return data.get("data", {})
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
# Mock body utilities for CI testing
# ═══════════════════════════════════════════════════════════════════════════════


class MockBodyAdapter:
    """Mock body adapter for CI testing without a live bot server."""

    def __init__(self):
        self.status = {
            "health": 20,
            "food": 20,
            "position": {"x": 0, "y": 64, "z": 0},
            "gamemode": "creative",
        }
        self.nearby = {"entities": [], "blocks": []}
        self.inventory = {"items": [{"name": "diamond_pickaxe", "count": 1}]}
        self.plan = {"current": "explore", "objective": "find diamonds"}
        self.events: list[dict] = []
        self._chat_log: list[str] = []
        self._command_log: list[str] = []

    def fetch_status(self) -> dict:
        return self.status

    def fetch_nearby(self) -> dict:
        return self.nearby

    def fetch_inventory(self) -> dict:
        return self.inventory

    def fetch_plan(self) -> dict:
        return self.plan

    def send_chat(self, message: str) -> bool:
        self._chat_log.append(message)
        self.events.append({"type": "chat", "message": message})
        return True

    def send_command(self, command: str) -> bool:
        self._command_log.append(command)
        self.events.append({"type": "command", "command": command})
        return True

    def get_chat_log(self) -> list[str]:
        return self._chat_log[:]

    def get_command_log(self) -> list[str]:
        return self._command_log[:]

    def reset(self):
        self.events.clear()
        self._chat_log.clear()
        self._command_log.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# Single-turn test runner
# ═══════════════════════════════════════════════════════════════════════════════


def run_test_turn(
    profile_name: str = "test",
    interval: int = 30,
    use_mock_body: bool = False,
) -> dict:
    """Run a single agent turn for testing.

    Gathers bot state, optionally generates HD context, and sends a
    heartbeat perception snapshot.  Returns the gathered state dict.
    """
    print(f"[test] Single turn started: {profile_name}")
    print(f"[test] MC_API_URL: {MC_API_URL}")

    agent_id = BOT_USERNAME.lower()
    hd_injector, hd_ready = _init_hd_injector(agent_id)
    if hd_ready:
        print(f"[test] HD chart loaded for {agent_id}", flush=True)
    else:
        print(f"[test] HD not active for {agent_id}", flush=True)

    if use_mock_body:
        body = MockBodyAdapter()
        status = body.fetch_status()
        nearby = body.fetch_nearby()
        inventory = body.fetch_inventory()
        plan = body.fetch_plan()
        events = body.events
    else:
        status = fetch_bot_status()
        nearby = fetch_bot_nearby()
        inventory = fetch_bot_inventory()
        plan = fetch_plan()
        events = []

    hd_context = _generate_hd_context(hd_injector, agent_id, is_first=True)
    if hd_context:
        print(f"[test] HD context generated ({len(hd_context)} chars)", flush=True)

    ok = send_heartbeat_context(status, nearby, inventory, plan, events, hd_context)
    if ok:
        print(
            f"[test] Heartbeat sent (status={bool(status)}, nearby={bool(nearby)}, "
            f"plan={bool(plan)}, hd={bool(hd_context)})",
            flush=True,
        )
        _emit_metric("heartbeat", triggered=False, hd_active=bool(hd_context))
    else:
        print("[test] Heartbeat send failed", flush=True)

    result = {
        "status": status,
        "nearby": nearby,
        "inventory": inventory,
        "plan": plan,
        "events": events,
        "hd_context": hd_context,
        "heartbeat_sent": ok,
        "hd_ready": hd_ready,
    }

    print(f"[test] Turn complete. heartbeat_sent={ok}, hd_ready={hd_ready}")
    return result


def main():
    parser = argparse.ArgumentParser(description="DaemonCraft agent loop test harness")
    parser.add_argument("--profile", default="test", help="Hermes profile name")
    parser.add_argument("--prompt", default="Begin.", help="Unused legacy arg")
    parser.add_argument("--interval", type=int, default=30, help="Unused legacy arg")
    parser.add_argument("--mock-body", action="store_true", help="Use mock body adapter")
    args = parser.parse_args()

    run_test_turn(args.profile, args.interval, use_mock_body=args.mock_body)


if __name__ == "__main__":
    main()
