"""Mindcraft sidecar body adapter — Phase-4 commander layer.

Mindcraft branch `altermundi/sidecar-phase1` exposes:
* GET  /health, /perceive, /plan
* POST /chat[/send], /set_goal, /act, /agent/log, /agent/heartbeat
* WS   /events, /ws

Phase 4 commander methods (set_goal, act) are first-class here. The
sidecar emits `action_result` WS events with `{label, ok, interrupted,
timedout, duration_ms, goal}` — exposed verbatim through the event
listener.

Repo pin: kolbytn/mindcraft @ 8acbd90 base + altermundi/sidecar-phase1
HEAD `7a4d99c` (Phase 4 close, 2026-04-29).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ._base import _WsThread, _get, _post, http_to_ws


class MindcraftBody:
    """Adapter for the Mindcraft sidecar (port 8090 by default)."""

    api_url: str
    username: str

    # Capabilities
    supports_screenshot: bool = False  # not yet wired in sidecar
    supports_impersonation: bool = False  # `as_` ignored by sidecar.chat()
    supports_set_goal: bool = True
    supports_act: bool = True
    kind: str = "mindcraft"

    def __init__(self, api_url: str, username: str):
        self.api_url = api_url.rstrip("/")
        self.username = username
        self._ws: Optional[_WsThread] = None

    # ── HTTP ────────────────────────────────────────────────────────────

    def chat(self, text: str, *, as_: Optional[str] = None) -> dict:
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "error": "message required"}
        # Sidecar accepts {message|text|line}; pick `message` for explicitness.
        # `as_` is silently ignored (no /tellraw impersonation in sidecar).
        body = {"message": text}
        result = _post(f"{self.api_url}/chat/send", body)
        return result or {"ok": False, "error": "request failed"}

    def get_plan(self) -> dict:
        # Sidecar returns {plan: null|..., goal: text|null} at the root
        # (no `data` wrapper). agent_loop's fetch_plan does
        # `data.get("data", {})` so it'll fall back to {} — meaning no
        # plan injection. That's correct: we don't have a structured
        # plan, just a goal string. Hermes can read /plan directly if
        # it wants the goal.
        result = _get(f"{self.api_url}/plan")
        if not isinstance(result, dict):
            return {}
        # Synthesize a goal-only plan so format_plan can show it if the
        # caller wants. agent_loop currently asks for `data` (DaemonCraft
        # bot shape), so return both keys for compatibility.
        goal = result.get("goal")
        if goal:
            return {"data": {"goal": goal, "tasks": []}, "plan": result.get("plan"), "goal": goal}
        return result

    def perceive(self) -> dict:
        result = _get(f"{self.api_url}/perceive")
        return result or {}

    def log_turn(self, turn: dict) -> None:
        _post(f"{self.api_url}/agent/log", turn, timeout=5.0)

    def heartbeat(
        self,
        *,
        next_turn_in: Optional[float] = None,
        turn_in_progress: bool = False,
    ) -> None:
        _post(
            f"{self.api_url}/agent/heartbeat",
            {"nextTurnIn": next_turn_in, "turnInProgress": turn_in_progress},
            timeout=2.0,
        )

    def set_goal(self, text: str, priority: int = 5) -> dict:
        result = _post(f"{self.api_url}/set_goal", {"text": text, "priority": priority})
        return result or {"ok": False, "error": "request failed"}

    def act(self, command: str) -> dict:
        result = _post(f"{self.api_url}/act", {"command": command})
        return result or {"ok": False, "error": "request failed"}

    # ── Events ──────────────────────────────────────────────────────────

    def start_event_listener(
        self,
        on_message: Callable[[dict], None],
        *,
        on_open: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[Optional[int], Optional[str]], None]] = None,
    ) -> None:
        ws_url = http_to_ws(self.api_url) + "/ws"
        self._ws = _WsThread(lambda: ws_url, on_message, on_open, on_close)
        self._ws.start()
