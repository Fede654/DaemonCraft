"""Hermescraft body adapter — DaemonCraft's own bot/server.js.

This is the default body for backwards compatibility. All existing casts
(companion, landfolk, civilization, rolemaster) work unchanged with this
adapter.

The bot HTTP API is rich (see agents/bot/server.js):
* GET  /health, /status, /inventory, /nearby, /map, /look, /scene,
       /screenshot, /social, /chat, /overhear, /deaths, /plan
* POST /agent/log, /agent/heartbeat, /chat/send (with optional `as`),
       /task/<action>, /task/cancel, /action/<action>, /connect

The Body protocol exposes only the surface agent_loop currently uses;
adapter-specific extensions (nearby, scene, screenshot, social, etc.)
remain available as additional methods callers can use after a
`supports_*` check.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ._base import _WsThread, _get, _post, http_to_ws


class HermescraftBody:
    """Adapter for DaemonCraft's own bot/server.js (port 3001 by default)."""

    api_url: str
    username: str

    # Capabilities
    supports_screenshot: bool = True  # /screenshot via puppeteer is real
    supports_impersonation: bool = True  # /chat/send accepts `as` field
    supports_set_goal: bool = False  # bot/server.js has no /set_goal
    supports_act: bool = False  # bot/server.js has no /act preempt
    kind: str = "hermescraft"

    def __init__(self, api_url: str, username: str):
        self.api_url = api_url.rstrip("/")
        self.username = username
        self._ws: Optional[_WsThread] = None

    # ── HTTP ────────────────────────────────────────────────────────────

    def chat(self, text: str, *, as_: Optional[str] = None) -> dict:
        if not isinstance(text, str) or not text.strip():
            return {"ok": False, "error": "message required"}
        body: dict = {"message": text}
        if as_:
            body["as"] = as_
        result = _post(f"{self.api_url}/chat/send", body)
        return result or {"ok": False, "error": "request failed"}

    def get_plan(self) -> dict:
        # bot/server.js wraps payload as {ok, data: {goal, tasks}}.
        # agent_loop's fetch_plan reads .get("data", {}) so we return as-is.
        result = _get(f"{self.api_url}/plan")
        return result or {}

    def perceive(self) -> dict:
        # bot/server.js exposes /status (full state) and /scene (narrative).
        # Use /status as the equivalent of Mindcraft's /perceive.
        result = _get(f"{self.api_url}/status")
        if result and isinstance(result, dict):
            return result.get("data", result)
        return {}

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
        return {"ok": False, "error": "hermescraft does not support set_goal"}

    def act(self, command: str) -> dict:
        return {"ok": False, "error": "hermescraft does not support act"}

    # ── Adapter-specific extras (callers gate via supports_* or kind) ───

    def screenshot(self, width: int = 1280, height: int = 720) -> dict:
        # /screenshot is GET with query params on hermescraft.
        url = f"{self.api_url}/screenshot?width={width}&height={height}"
        result = _get(url, timeout=15.0)
        return result or {"ok": False, "error": "request failed"}

    def task(self, action: str, body: Optional[dict] = None) -> dict:
        """Async task dispatch. Returns {ok, task_id, status} immediately."""
        result = _post(f"{self.api_url}/task/{action}", body or {})
        return result or {"ok": False, "error": "request failed"}

    def cancel_task(self) -> dict:
        result = _post(f"{self.api_url}/task/cancel", {})
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
