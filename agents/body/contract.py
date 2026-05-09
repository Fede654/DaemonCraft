"""Body protocol — the narrow contract between agent_loop and a Minecraft body.

Two adapters live here:

* `hermescraft` — DaemonCraft's own `agents/bot/server.js` (default; backwards
  compatible with all existing casts).
* `mindcraft`  — the Mindcraft sidecar at `mindcraft.altermundi/sidecar-phase1`
  (Phase 4 commander layer; supports `set_goal`/`act` and the
  `route_chat_to_sidecar_only` chat gate).

The protocol is deliberately narrow: it exposes only the surface
agent_loop touches today plus the Phase-4 commander methods. Anything
adapter-specific (DaemonCraft's `/scene`, `/look`, `/screenshot`,
`/social`, etc., or Mindcraft's `action_result` events) is accessed via
adapter-specific methods or capability flags.

Sync API: agent_loop runs sync (urllib + thread for WS); the body
mirrors that pattern.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol, runtime_checkable


@runtime_checkable
class Body(Protocol):
    """Minimal contract between agent_loop and a Minecraft body.

    Adapters set the capability flags below; callers respect them with
    explicit checks (`if body.supports_set_goal: ...`) rather than blind
    dispatch.
    """

    # ── Identity ────────────────────────────────────────────────────────
    api_url: str
    """Base HTTP URL of the body (e.g. http://localhost:3001 or 8090)."""

    username: str
    """In-game username this body controls (for self-echo filtering)."""

    # ── Capability flags ────────────────────────────────────────────────
    supports_screenshot: bool
    supports_impersonation: bool
    """`chat(text, as_=...)` honors the `as_` arg (DaemonCraft /tellraw)."""

    supports_set_goal: bool
    supports_act: bool
    """Phase-4 commander methods (Mindcraft sidecar v2)."""

    # ── HTTP ────────────────────────────────────────────────────────────
    def chat(self, text: str, *, as_: Optional[str] = None) -> dict:
        """Send chat to the game. Adapters that don't support impersonation
        (`as_`) ignore it. Returns {ok, ...}."""
        ...

    def get_plan(self) -> dict:
        """Fetch the body's current plan/goal. Returns adapter-shaped dict;
        agent_loop's `format_plan` consumes the inner shape directly."""
        ...

    def perceive(self) -> dict:
        """Snapshot of bot + nearby world."""
        ...

    def log_turn(self, turn: dict) -> None:
        """Best-effort POST of turn data for dashboard rendering. Mindcraft
        sidecar accepts a no-op stub. Never raises."""
        ...

    def heartbeat(
        self,
        *,
        next_turn_in: Optional[float] = None,
        turn_in_progress: bool = False,
    ) -> None:
        """Best-effort countdown POST. Mindcraft sidecar accepts a no-op
        stub. Never raises."""
        ...

    def set_goal(self, text: str, priority: int = 5) -> dict:
        """Set the body's autonomous goal (Phase-4 commander). Only valid
        when `supports_set_goal=True`."""
        ...

    def act(self, command: str) -> dict:
        """Direct command emission with action-manager preempt (Phase-4
        commander). Only valid when `supports_act=True`."""
        ...

    # ── Events ──────────────────────────────────────────────────────────
    def start_event_listener(
        self,
        on_message: Callable[[dict], None],
        *,
        on_open: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[Optional[int], Optional[str]], None]] = None,
    ) -> None:
        """Spawn a daemon thread that connects to the body's WS and calls
        `on_message(event_dict)` for each incoming event. The body owns
        reconnection — agent_loop just supplies the callback."""
        ...
