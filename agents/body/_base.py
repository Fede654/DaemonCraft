"""Shared HTTP/WS plumbing for body adapters.

Both adapters do the same urllib + websocket-client dance. Centralizing it
here keeps each adapter focused on its own endpoint differences.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Any, Callable, Optional


def _post(url: str, body: dict, timeout: float = 5.0) -> Optional[dict]:
    """Best-effort POST. Returns parsed JSON on 2xx, None on failure.

    Never raises — agent_loop assumes these calls fail silently when the
    body isn't reachable (consistent with the original urllib calls in
    agent_loop.py).
    """
    payload = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
        return json.loads(raw)
    except Exception:
        return None


def _get(url: str, timeout: float = 5.0) -> Optional[dict]:
    """Best-effort GET. Returns parsed JSON on 2xx, None on failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8") or "{}"
        return json.loads(raw)
    except Exception:
        return None


class _WsThread:
    """Manages a websocket-client thread that reconnects with backoff.

    Constructor takes a `make_url()` callable so the adapter can pick the
    right path (/events vs /ws) without subclassing.
    """

    def __init__(
        self,
        make_url: Callable[[], str],
        on_message: Callable[[dict], None],
        on_open: Optional[Callable[[], None]] = None,
        on_close: Optional[Callable[[Optional[int], Optional[str]], None]] = None,
    ):
        self._make_url = make_url
        self._on_message = on_message
        self._on_open = on_open
        self._on_close = on_close
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        # Lazy import keeps the body module importable on systems that
        # haven't installed websocket-client yet.
        import websocket

        def _on_msg(ws, message: str) -> None:
            try:
                ev = json.loads(message)
            except Exception:
                return
            try:
                self._on_message(ev)
            except Exception as exc:
                print(f"[body.ws] on_message handler error: {exc}", flush=True)

        def _on_open(ws) -> None:
            print(f"[body.ws] connected: {self._make_url()}", flush=True)
            if self._on_open:
                try:
                    self._on_open()
                except Exception:
                    pass

        def _on_close(ws, code, msg) -> None:
            print(f"[body.ws] disconnected: {code} {msg}", flush=True)
            if self._on_close:
                try:
                    self._on_close(code, msg)
                except Exception:
                    pass

        while not self._stop.is_set():
            url = self._make_url()
            try:
                ws_app = websocket.WebSocketApp(
                    url,
                    on_message=_on_msg,
                    on_open=_on_open,
                    on_close=_on_close,
                )
                ws_app.run_forever(ping_interval=30, ping_timeout=10)
            except Exception as e:
                print(f"[body.ws] connection error: {e}; retrying in 5s", flush=True)
            if self._stop.is_set():
                break
            time.sleep(5)


def http_to_ws(url: str) -> str:
    """Convert http://host:port to ws://host:port (preserving scheme map)."""
    return url.replace("http://", "ws://").replace("https://", "wss://")
