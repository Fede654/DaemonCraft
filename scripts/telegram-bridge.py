#!/usr/bin/env python3
"""
DaemonCraft Telegram <-> Minecraft Chat Bridge (MVP)

A standalone, stdlib-only Python service that forwards text messages
bidirectionally between a Minecraft server (via the HermesCraft bot HTTP API)
and a Telegram chat.

Requires: Python 3.8+ (no external packages)
Optional: PyYAML (falls back to minimal inline parser)

Usage:
    python3 scripts/telegram-bridge.py
    python3 scripts/telegram-bridge.py --config config/telegram-bridge.yaml
"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Minimal YAML parser (safe subset for flat-ish nested configs)
# ---------------------------------------------------------------------------

class MinimalYamlParser:
    """Parse a tiny subset of YAML: nested maps, scalars, lists."""

    @staticmethod
    def parse(text: str) -> Any:
        lines = text.splitlines()
        stack: List[Tuple[int, Any]] = [(0, {})]
        in_flow = False
        for raw_line in lines:
            line = raw_line.rstrip()
            if not line or line.strip().startswith("#"):
                continue
            stripped = line.lstrip()
            indent = len(line) - len(stripped)
            if stripped.startswith("-"):
                # List item
                while len(stack) > 1 and indent < stack[-1][0]:
                    stack.pop()
                if not isinstance(stack[-1][1], list):
                    # Replace current dict with list? Only at root edge cases.
                    pass
                _, current = stack[-1]
                val = stripped[1:].strip()
                if val == "":
                    child: Any = {}
                    current.append(child)
                    stack.append((indent + 2, child))
                else:
                    current.append(MinimalYamlParser._scalar(val))
                continue
            key, val = MinimalYamlParser._split_key_val(stripped)
            if key is None:
                continue
            while len(stack) > 1 and indent < stack[-1][0]:
                stack.pop()
            _, current = stack[-1]
            if val == "":
                child = {}
                current[key] = child
                stack.append((indent + 2, child))
            else:
                current[key] = MinimalYamlParser._scalar(val)
        return stack[0][1]

    @staticmethod
    def _split_key_val(s: str) -> Tuple[Optional[str], str]:
        # Split on first colon outside quotes
        in_quote = None
        for i, ch in enumerate(s):
            if ch in ('"', "'") and (i == 0 or s[i - 1] != "\\"):
                in_quote = ch if in_quote != ch else None
            if ch == ":" and in_quote is None:
                return s[:i].strip(), s[i + 1:].strip()
        return None, s

    @staticmethod
    def _scalar(val: str) -> Any:
        val = val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]
        lower = val.lower()
        if lower in ("true", "yes", "on"):
            return True
        if lower in ("false", "no", "off"):
            return False
        if lower in ("null", "~", ""):
            return None
        try:
            if "." in val:
                return float(val)
            return int(val)
        except ValueError:
            return val


def load_config(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    text = p.read_text(encoding="utf-8")
    ext = p.suffix.lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            return yaml.safe_load(text)
        except Exception:
            return MinimalYamlParser.parse(text)
    if ext == ".json":
        return json.loads(text)
    # Try YAML first, then JSON
    try:
        return MinimalYamlParser.parse(text)
    except Exception:
        return json.loads(text)


# ---------------------------------------------------------------------------
# HTTP helpers (stdlib only)
# ---------------------------------------------------------------------------

def http_get_json(url: str, timeout: float = 10.0) -> Any:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post_json(url: str, payload: Dict[str, Any], timeout: float = 10.0) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Bridge core
# ---------------------------------------------------------------------------

class TelegramMinecraftBridge:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.log = logging.getLogger("tg-mc-bridge")

        # Telegram
        tg = config.get("telegram", {})
        self.tg_token = tg.get("bot_token", os.getenv("TELEGRAM_BOT_TOKEN", ""))
        self.tg_chat_id = str(tg.get("chat_id", os.getenv("TELEGRAM_CHAT_ID", "")))
        self.tg_api_base = tg.get("api_base", "https://api.telegram.org").rstrip("/")

        # Minecraft
        mc = config.get("minecraft", {})
        self.mc_api_url = mc.get("api_url", "http://localhost:3001").rstrip("/")
        self.mc_poll_interval = float(mc.get("poll_interval", 2.0))
        self.mc_bot_username = mc.get("bot_username", "HermesBot")

        # Bridge behaviour
        bridge = config.get("bridge", {})
        self.mc_to_tg_format = bridge.get("mc_to_tg_format", "[{world}] <{sender}> {message}")
        self.tg_to_mc_format = bridge.get("tg_to_mc_format", "[TG] {sender}: {message}")
        self.ignore_mc_users: Set[str] = set(
            u.strip().lower()
            for u in str(bridge.get("ignore_mc_users", self.mc_bot_username)).split(",")
            if u.strip()
        )
        self.ignore_tg_users: Set[str] = set(
            u.strip().lower()
            for u in str(bridge.get("ignore_tg_users", "")).split(",")
            if u.strip()
        )
        self.ignore_tg_bots = bool(bridge.get("ignore_tg_bots", True))
        self.require_prefix = str(bridge.get("require_prefix", "")).strip()
        self.max_length = int(bridge.get("max_length", 1000))
        self.dedup_window = int(bridge.get("dedup_window", 200))

        # Runtime state
        self._shutdown = threading.Event()
        self._last_mc_time = 0
        self._seen_mc: deque = deque(maxlen=self.dedup_window)
        self._last_tg_update_id: Optional[int] = None
        self._tg_lock = threading.Lock()
        self._mc_lock = threading.Lock()

    # ── Telegram helpers ──────────────────────────────────────────────

    def _tg_api(self, method: str, payload: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.tg_api_base}/bot{self.tg_token}/{method}"
        if payload is None:
            return http_get_json(url)
        return http_post_json(url, payload)

    def _tg_get_updates(self) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {"limit": 100, "timeout": min(int(self.mc_poll_interval), 30)}
        with self._tg_lock:
            if self._last_tg_update_id is not None:
                payload["offset"] = self._last_tg_update_id + 1
        try:
            resp = self._tg_api("getUpdates", payload)
            if not resp.get("ok"):
                self.log.warning("Telegram getUpdates error: %s", resp)
                return []
            return resp.get("result", [])
        except Exception as e:
            self.log.warning("Telegram poll failed: %s", e)
            return []

    def _tg_send_message(self, text: str) -> bool:
        if not text:
            return True
        payload = {
            "chat_id": self.tg_chat_id,
            "text": text[:self.max_length],
            "disable_notification": False,
        }
        try:
            resp = self._tg_api("sendMessage", payload)
            if not resp.get("ok"):
                self.log.warning("Telegram sendMessage error: %s", resp)
                return False
            return True
        except Exception as e:
            self.log.error("Failed to send Telegram message: %s", e)
            return False

    # ── Minecraft helpers ─────────────────────────────────────────────

    def _mc_get_chat(self, count: int = 50) -> List[Dict[str, Any]]:
        url = f"{self.mc_api_url}/chat?count={count}"
        try:
            resp = http_get_json(url)
            if not resp.get("ok"):
                self.log.warning("MC chat endpoint error: %s", resp)
                return []
            data = resp.get("data", {})
            return data.get("messages", []) if isinstance(data, dict) else []
        except Exception as e:
            self.log.warning("MC poll failed: %s", e)
            return []

    def _mc_send_chat(self, text: str) -> bool:
        if not text:
            return True
        url = f"{self.mc_api_url}/chat/send"
        payload = {"message": text[:self.max_length]}
        try:
            resp = http_post_json(url, payload)
            if not resp.get("ok"):
                self.log.warning("MC send error: %s", resp)
                return False
            self.log.debug("MC send ok: %s", resp)
            return True
        except Exception as e:
            self.log.error("Failed to send MC message: %s", e)
            return False

    # ── Directional forwarding ────────────────────────────────────────

    def _should_forward_mc(self, msg: Dict[str, Any]) -> bool:
        sender = str(msg.get("from", "")).strip()
        message = str(msg.get("message", "")).strip()
        is_self = bool(msg.get("self", False))
        if not sender or not message:
            return False
        if is_self:
            return False
        if sender.lower() in self.ignore_mc_users:
            return False
        if self.require_prefix and not message.startswith(self.require_prefix):
            return False
        return True

    def _should_forward_tg(self, msg: Dict[str, Any]) -> bool:
        chat = msg.get("chat", {})
        if str(chat.get("id", "")) != self.tg_chat_id:
            return False
        text = msg.get("text", "")
        if not text:
            return False
        from_user = msg.get("from", {})
        username = str(from_user.get("username", "") or from_user.get("first_name", "Unknown")).strip()
        if not username:
            return False
        if self.ignore_tg_bots and from_user.get("is_bot", False):
            return False
        if username.lower() in self.ignore_tg_users:
            return False
        if self.require_prefix and not text.startswith(self.require_prefix):
            return False
        return True

    def _format_mc_to_tg(self, msg: Dict[str, Any]) -> str:
        world = str(msg.get("world", "MC"))
        sender = str(msg.get("from", "Unknown"))
        message = str(msg.get("message", ""))
        return self.mc_to_tg_format.format(world=world, sender=sender, message=message)

    def _format_tg_to_mc(self, msg: Dict[str, Any]) -> str:
        from_user = msg.get("from", {})
        username = str(from_user.get("username", "") or from_user.get("first_name", "Unknown")).strip()
        text = str(msg.get("text", ""))
        return self.tg_to_mc_format.format(sender=username, message=text)

    # ── Poll loops ────────────────────────────────────────────────────

    def poll_minecraft(self):
        """Background thread: poll MC chat and forward to Telegram."""
        while not self._shutdown.is_set():
            try:
                messages = self._mc_get_chat(count=50)
                new_msgs: List[Dict[str, Any]] = []
                with self._mc_lock:
                    for msg in messages:
                        t = int(msg.get("time", 0))
                        sender = str(msg.get("from", ""))
                        body = str(msg.get("message", ""))
                        key = (t, sender, body)
                        if t > self._last_mc_time and key not in self._seen_mc:
                            new_msgs.append(msg)
                            self._seen_mc.append(key)
                    if new_msgs:
                        self._last_mc_time = max(int(m.get("time", 0)) for m in new_msgs)
                    # deque maxlen handles eviction automatically

                for msg in sorted(new_msgs, key=lambda m: int(m.get("time", 0))):
                    if self._should_forward_mc(msg):
                        text = self._format_mc_to_tg(msg)
                        self.log.info("MC -> TG | %s", text.replace("\n", " "))
                        self._tg_send_message(text)
            except Exception as e:
                self.log.exception("MC poll loop error: %s", e)
            self._shutdown.wait(self.mc_poll_interval)

    def poll_telegram(self):
        """Background thread: poll Telegram and forward to Minecraft."""
        while not self._shutdown.is_set():
            try:
                updates = self._tg_get_updates()
                for upd in updates:
                    update_id = upd.get("update_id")
                    if update_id is not None:
                        with self._tg_lock:
                            if self._last_tg_update_id is None or update_id > self._last_tg_update_id:
                                self._last_tg_update_id = update_id
                    msg = upd.get("message")
                    if not msg:
                        continue
                    if self._should_forward_tg(msg):
                        text = self._format_tg_to_mc(msg)
                        self.log.info("TG -> MC | %s", text.replace("\n", " "))
                        self._mc_send_chat(text)
            except Exception as e:
                self.log.exception("TG poll loop error: %s", e)
            self._shutdown.wait(self.mc_poll_interval)

    # ── Lifecycle ─────────────────────────────────────────────────────

    def start(self):
        self.log.info("=" * 50)
        self.log.info("DaemonCraft Telegram <-> Minecraft Bridge")
        self.log.info("MC API: %s", self.mc_api_url)
        self.log.info("TG Chat: %s", self.tg_chat_id)
        self.log.info("=" * 50)

        # Quick connectivity checks
        try:
            health = http_get_json(f"{self.mc_api_url}/health")
            self.log.info("MC health: %s", health)
        except Exception as e:
            self.log.warning("MC health check failed (will retry): %s", e)

        try:
            me = self._tg_api("getMe")
            self.log.info("TG bot: @%s", me.get("result", {}).get("username", "?"))
        except Exception as e:
            self.log.warning("TG bot check failed (will retry): %s", e)

        self._threads = [
            threading.Thread(target=self.poll_minecraft, name="mc-poller", daemon=True),
            threading.Thread(target=self.poll_telegram, name="tg-poller", daemon=True),
        ]
        for t in self._threads:
            t.start()

    def stop(self):
        self.log.info("Shutting down...")
        self._shutdown.set()
        for t in self._threads:
            t.join(timeout=5.0)
        self.log.info("Stopped.")

    def run(self):
        self.start()
        try:
            while not self._shutdown.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="DaemonCraft Telegram <-> Minecraft Chat Bridge")
    parser.add_argument("--config", "-c", default="config/telegram-bridge.yaml", help="Path to config file")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable DEBUG logging")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        config = load_config(args.config)
    except FileNotFoundError:
        logging.error("Config file not found: %s", args.config)
        logging.error("Copy config/telegram-bridge.yaml.example to %s and edit it.", args.config)
        sys.exit(1)
    except Exception as e:
        logging.error("Failed to load config: %s", e)
        sys.exit(1)

    bridge = TelegramMinecraftBridge(config)

    def _sig_handler(signum, frame):
        bridge.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    bridge.run()


if __name__ == "__main__":
    main()
