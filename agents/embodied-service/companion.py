#!/usr/bin/env python3
"""
Companion mode — bot listens for chat addressed to it, plans & acts.

Phase 2 minimal of the "play alongside" experience. Polls the bot's
`/commands` endpoint for messages directed at the bot (format:
"HermesBot: <msg>" or "HermesBot, <msg>" — already detected by the
bot's WS handler), then for each:

  1. Builds an embodied_plan intent from the chat message
  2. Calls embodied service POST /intent (Gemma-Andy plans + executes)
  3. Sends a chat reply back to the world summarizing what's being done

Run:
  python companion.py

Stop with Ctrl-C.

Environment overrides:
  BOT_API_URL          default http://localhost:3001
  EMBODIED_SERVICE_URL default http://localhost:7790
  POLL_INTERVAL        default 1.0 (seconds between /commands polls)
  COMPANION_USERNAME   default HermesBot — only respond when addressed
                       as this name (case-insensitive prefix match)
"""
from __future__ import annotations
import os, sys, time, json, signal, requests
from datetime import datetime

BOT_API = os.getenv("BOT_API_URL", "http://localhost:3001")
SERVICE_API = os.getenv("EMBODIED_SERVICE_URL", "http://localhost:7790")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "1.0"))
USERNAME = os.getenv("COMPANION_USERNAME", "HermesBot")
# permissive: responde a todo chat de no-bot cuando hay 1 sola persona en el mundo
# strict: solo responde si el mensaje empieza con un alias del bot
COMPANION_MODE = os.getenv("COMPANION_MODE", "permissive")


_running = True
_seen_command_ids: set[str] = set()
_seen_chat_ts: int = 0  # millisecond timestamp; only process messages newer than this
_intent_in_flight: bool = False  # mutex: only one embodied_plan call at a time
_pending_messages: list[dict] = []  # queue messages while another intent is in flight


def _fuzzy_addresses_me(message: str, my_name: str) -> bool:
    """Looser than the bot's strict matcher — catches typos like 'HermeBot'.

    True when the message starts with any of:
      - the full bot name (case-insensitive)
      - 'hermes', 'hermesbot', 'hermsbot', 'hermebot', 'hermbot'
      - 'bot' (canonical alias)
      - 'herm' followed by anything other than a letter (e.g. 'herm: ' or 'herm,')
    """
    if not message:
        return False
    lower = message.strip().lower()
    name = (my_name or "").lower()
    if name and lower.startswith(name):
        return True
    common_prefixes = (
        "hermesbot", "hermes-bot", "hermes_bot",
        "hermsbot", "hermebot", "hermbot",
        "hermes", "hermes,", "hermes:", "hermes ",
        "bot,", "bot:", "bot ",
    )
    if lower.startswith(common_prefixes):
        return True
    # Fallback: 'herm' + non-letter punctuation/whitespace within first 6 chars
    if lower.startswith("herm") and len(lower) > 4 and not lower[4].isalpha():
        return True
    return False


def _strip_my_prefix(message: str) -> str:
    """Remove the addressing prefix so we send only the actual content."""
    s = message.strip()
    lower = s.lower()
    # Drop the longest matching prefix
    candidates = [
        USERNAME.lower(),
        "hermesbot", "hermes-bot", "hermes_bot",
        "hermsbot", "hermebot", "hermbot",
        "hermes", "bot",
    ]
    for cand in sorted(candidates, key=len, reverse=True):
        if lower.startswith(cand):
            s = s[len(cand):]
            break
    # Trim leftover punctuation/whitespace
    return s.lstrip(",.:;! ").strip() or message


def _stop(*_):
    global _running
    _running = False
    print("\n[companion] stopping...")


signal.signal(signal.SIGINT, _stop)
signal.signal(signal.SIGTERM, _stop)


def now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{now()}] {msg}", flush=True)


def get_pending_commands():
    """Return the bot's pending command queue (chat addressed to bot,
    according to the bot's strict matcher — useful when /commands fires)."""
    try:
        r = requests.get(f"{BOT_API}/commands", timeout=3).json()
        return r.get("data", {}).get("commands", []) or []
    except Exception as e:
        log(f"[!] /commands fetch failed: {e}")
        return []


def get_recent_chat(since_ts: int = 0):
    """Poll the bot's chat log directly. Catches messages with typos
    that the bot's strict mention-matcher would skip."""
    try:
        r = requests.get(f"{BOT_API}/chat?limit=30", timeout=3).json()
        msgs = r.get("data", {}).get("messages", []) or []
        return [m for m in msgs if m.get("time", 0) > since_ts]
    except Exception as e:
        log(f"[!] /chat fetch failed: {e}")
        return []


def mark_command_done(idx: int):
    """Tell the bot this command has been processed (drains the queue)."""
    try:
        requests.post(
            f"{BOT_API}/action/complete_command",
            json={"index": idx},
            timeout=3,
        )
    except Exception as e:
        log(f"[!] complete_command({idx}) failed: {e}")


def speak(message: str, target: str | None = None) -> None:
    """Send chat from the bot to the world (broadcast or whisper)."""
    try:
        body = {"message": message[:240]}
        if target:
            body["target"] = target
        requests.post(f"{BOT_API}/chat/send", json=body, timeout=5)
    except Exception as e:
        log(f"[!] chat/send failed: {e}")


def cancel_bot_task() -> None:
    """Tell the bot to drop any in-flight pathfinder/mining/etc. Used when
    a new intent arrives and we want a clean slate (no stale tasks
    competing with the new plan)."""
    try:
        requests.post(f"{BOT_API}/action/stop", json={}, timeout=3)
        requests.post(f"{BOT_API}/task/cancel", json={}, timeout=3)
    except Exception as e:
        log(f"[!] cancel_bot_task failed: {e}")


def classify_intent(message: str) -> str:
    """Cheap classifier — labels the chat into broad buckets so we can
    constrain allowed_tools and keep the model from over-planning.
    Returns one of: 'navigate', 'gather', 'build', 'craft', 'combat',
    'social', 'unknown'."""
    msg = (message or "").lower()
    if any(k in msg for k in ["come here", "ven aca", "ven acá", "veni", "vení", "ven", "follow me", "follow", "sigue", "seguime", "sígueme", "mové", "mover", "go to", "anda a"]):
        return "navigate"
    if any(k in msg for k in ["dame", "trae", "give me", "bring", "pickup", "agarra", "necesito"]):
        return "gather"
    if any(k in msg for k in ["build", "construy", "construí", "construir", "place", "pon ", "pone", "poné", "ponelo", "armemos", "hagamos una", "hagamos un",
                              "torre", "casa", "wall", "muro", "techo", "piso", "top of", "cima", "encima"]):
        return "build"
    if any(k in msg for k in ["craft", "armar", "fabri"]) or msg.strip() == "haz":
        return "craft"
    if any(k in msg for k in ["attack", "kill", "fight", "ataca", "matá", "mata"]):
        return "combat"
    if msg.strip() in ("hola", "hello", "hey", "hi", "buenas", "qué onda", "que onda"):
        return "social"
    if msg.strip().endswith("?") and any(q in msg for q in ["qué", "que ", "what", "where", "donde", "cuál"]):
        return "social"
    return "unknown"


def allowed_tools_for(category: str) -> list[str] | None:
    """Restricted tool palette per intent category. Keeps the model from
    pulling in mine/craft/toss when the user just said 'come here'."""
    SIGNALS = ["ask_clarification", "raise_guardian_event", "report_execution_error"]
    if category == "navigate":
        return ["scan_nearby", "goto", "follow", "stop_movement"] + SIGNALS
    if category == "gather":
        return ["scan_nearby", "goto", "mine_block", "mine_blocks", "collect_drops", "pickup_item", "toss_item"] + SIGNALS
    if category == "build":
        return ["scan_nearby", "goto", "place_block", "fill_volume"] + SIGNALS
    if category == "craft":
        return ["scan_nearby", "goto", "get_inventory", "view_craftable", "craft_item", "smelt_item"] + SIGNALS
    if category == "combat":
        return ["scan_nearby", "find_entities", "attack_entity", "raise_shield", "flee_from", "move_away"] + SIGNALS
    if category == "social":
        return ["scan_nearby"] + SIGNALS  # mostly chat-ish; let the model ask_clarification
    # unknown — return None so caller uses defaults
    return None


def plan_and_act(intent: str, who: str, allowed_tools: list[str] | None = None,
                 deadline_seconds: int = 60, previous_error: dict | None = None) -> dict:
    """Call the embodied service with a chat-derived intent."""
    payload = {
        "intent": intent,
        "deadline_seconds": deadline_seconds,
    }
    if allowed_tools is not None:
        payload["allowed_tools"] = allowed_tools
    if previous_error is not None:
        payload["previous_error"] = previous_error
    try:
        r = requests.post(f"{SERVICE_API}/intent", json=payload, timeout=deadline_seconds + 30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log(f"[!] embodied service call failed for {who!r}: {e}")
        return {"ok": False, "error": str(e)}


def _human_action_summary(tool_name: str, args: dict) -> str:
    """Translate a canonical tool_call into a short human phrase."""
    a = args or {}
    if tool_name == "scan_nearby":
        bs = a.get("blocks") or []
        if bs: return f"escaneando por {', '.join(bs[:3])}"
        return "mirando alrededor"
    if tool_name == "goto":
        t = a.get("target")
        if isinstance(t, list) and len(t) == 3: return f"yendo a {t[0]},{t[1]},{t[2]}"
        return f"yendo a {t}"
    if tool_name in ("mine_block", "mine_blocks"):
        return f"minando {a.get('quantity', 1)} {a.get('block', '?')}"
    if tool_name == "collect_drops":
        return "juntando drops"
    if tool_name == "follow":
        return f"siguiendo a {a.get('target', '?')}"
    if tool_name == "place_block":
        return f"poniendo {a.get('block', '?')}"
    if tool_name == "consume_food":
        return f"comiendo {a.get('food', 'algo')}"
    if tool_name == "craft_item":
        return f"crafteando {a.get('quantity', 1)} {a.get('item', '?')}"
    if tool_name == "remember_here":
        return f"marcando este lugar como '{a.get('name', '?')}'"
    if tool_name == "stop_movement":
        return "parando"
    if tool_name == "raise_shield":
        return "levantando shield"
    if tool_name == "attack_entity":
        return f"atacando {a.get('target', '?')}"
    if tool_name == "flee_from":
        return f"huyendo de {a.get('threat', '?')}"
    return tool_name


def summarize_for_chat(out: dict) -> str | None:
    """Build a short chat reply from an embodied_plan response."""
    plan = out.get("plan") or {}
    tool_calls = plan.get("tool_calls", [])

    # If a clarification was emitted, ask it directly
    for tc in tool_calls:
        if tc.get("name") == "ask_clarification":
            q = (tc.get("arguments") or {}).get("question")
            if q:
                return q

    # If a guardian event fired, surface its reason
    for tc in tool_calls:
        if tc.get("name") == "raise_guardian_event":
            args = tc.get("arguments") or {}
            cat = args.get("category", "")
            if cat == "out_of_scope":
                # Conversational / chat — not a body request. Echo a friendly ack.
                return None  # let the caller fall through to None / no reply
            return f"no puedo con eso ({cat})"

    # Build a human summary from the actual tool_calls (not the body_plan
    # text which the model fills with jargon).
    exec_results = out.get("execution_results") or []
    soft_fails = [r for r in exec_results if r.get("error_type") == "bot_soft_failure"]

    if soft_fails:
        first = soft_fails[0]
        return f"no pude — {first.get('details', '?')[:140]}"

    # Filter signal tools out of the action narration
    action_calls = [t for t in tool_calls
                    if t.get("name") not in ("ask_clarification", "raise_guardian_event", "report_execution_error")]
    if action_calls:
        phrases = [_human_action_summary(t["name"], t.get("arguments", {})) for t in action_calls]
        return " → ".join(phrases)[:200]

    if not exec_results:
        return None
    return f"hecho ({len(exec_results)} acciones)"


def build_intent(username: str, message: str, category: str) -> str:
    """Convert raw chat into a body-orchestration intent.

    Per the integration guide (raw/gemma-andy/gemma-andy-integration-guide.md
    + ollama-usage.md), `high_level_command` should be the natural user
    request, byte-similar to training distribution. Examples from the
    guide: "Help the player gather wood before night.", "Build it over
    there.", "Trae un poco de madera para construir una mesa.".

    Earlier versions of this function templated the message with meta-
    instructions ("This is a NAVIGATION command. Emit ONLY..."). The
    model treated those as the user request and got confused. The
    classifier still drives allowed_tools and deadline; it does NOT
    re-write the user's message.
    """
    return message.strip() or message


def process_command(idx: int, cmd: dict) -> None:
    """Path A — the bot's strict-matched queue. Defers to the same
    classification + mutex flow as Path B, then drains the queue index
    so the bot doesn't replay this command on the next poll."""
    who = cmd.get("from") or "?"
    raw = cmd.get("command") or ""
    if not raw.strip():
        mark_command_done(idx)
        return
    # Reuse the unified path. Build a synthetic chat-message dict with
    # the same shape Path B receives.
    msg = {
        "from": who,
        "message": raw,
        "self": False,
        "time": cmd.get("time"),
    }
    try:
        # prefilter=False — bot's strict matcher already verified address
        # and stripped the prefix; running the fuzzy matcher on the
        # already-stripped body produces false negatives ("veni aca,
        # buscame" doesn't start with "hermes" anymore).
        process_chat_message(msg, prefilter=False)
    finally:
        mark_command_done(idx)


def _count_human_players() -> int:
    """How many non-bot players are visible right now?"""
    try:
        r = requests.get(f"{BOT_API}/nearby?radius=128", timeout=3).json()
        ents = (r.get("data") or {}).get("entities", []) or []
        return sum(1 for e in ents if e.get("kind") == "player" or e.get("type") == "player")
    except Exception:
        return 0


def process_chat_message(msg: dict, *, prefilter: bool = True) -> None:
    """Process a chat-derived message through the embodied flow.

    `prefilter=False` skips the address-detection step. Used by Path A
    (`process_command`) where the bot's strict matcher already verified
    the user spoke to us — and stripped the prefix — so fuzzy matching
    on the body would produce false negatives.
    """
    global _intent_in_flight

    # Real bot field is `from`, NOT `username`. Skip self-messages.
    if msg.get("self"):
        return
    who = msg.get("from") or msg.get("username") or "?"
    raw = msg.get("message") or ""
    if who.lower() == USERNAME.lower():
        return  # ignore our own messages

    if prefilter:
        addresses_me = _fuzzy_addresses_me(raw, USERNAME)
        if not addresses_me:
            if COMPANION_MODE != "permissive":
                return
            if _count_human_players() != 1:
                return  # multi-player → require explicit address
        body = _strip_my_prefix(raw) if addresses_me else raw
    else:
        # Path A: the bot already addressed-detected and stripped the
        # prefix; trust that, treat raw as the body verbatim.
        body = raw

    # Mutex — if an intent is already in flight, drop or cancel-and-replace.
    # Behavior: NEW intent wins. Cancel bot's current task, then proceed.
    # This matches user expectation: latest command supersedes previous.
    if _intent_in_flight:
        log(f"<{who}> {raw}  [INTERRUPT — canceling previous task]")
        cancel_bot_task()
        speak("ok, cambio de plan")
        # Wait briefly for cancel to settle. Don't block the thread for long;
        # the bot's ensureBot/task system handles re-entry.
        time.sleep(0.5)
    else:
        log(f"<{who}> {raw}")

    category = classify_intent(body)
    log(f"  category: {category}")
    intent = build_intent(who, body, category)
    allowed = allowed_tools_for(category)

    # Variable deadline by category — gather/build legitimately need more time
    deadline = {
        "navigate": 30,
        "social": 20,
        "craft": 45,
        "gather": 90,
        "build": 60,
        "combat": 30,
    }.get(category, 60)

    _intent_in_flight = True
    try:
        out = plan_and_act(intent, who, allowed_tools=allowed, deadline_seconds=deadline)
        # Auto-recover on actionable failures (one-shot retry per chat).
        # Surfaces real bot feedback as previous_error so the model can
        # pick a different material / target / approach.
        retry = _maybe_build_retry(out, who, body, category)
        if retry is not None:
            log(f"  ↻ retry with previous_error: {retry['previous_error']['details'][:100]}")
            out2 = plan_and_act(
                retry["intent"], who,
                allowed_tools=retry.get("allowed_tools", allowed),
                deadline_seconds=deadline,
                previous_error=retry.get("previous_error"),
            )
            # Merge: prefer retry result for narration but keep both
            # execution_results visible in logs.
            for r in out2.get("execution_results", []):
                marker = "✓" if r.get("ok") else "✗"
                det = (r.get("details") or r.get("error_type") or "")[:120]
                log(f"    [retry] {marker} {r['tool']}: {det}")
            out = out2
    finally:
        _intent_in_flight = False

    plan = out.get("plan") or {}
    risk = plan.get("operational_risk", "?")
    tools = [t["name"] for t in plan.get("tool_calls", [])]
    mits = [m["regression"] for m in (out.get("mitigations") or [])]
    log(f"  → ok={out.get('ok')} risk={risk} tools={tools} mitigations={mits or '—'}")
    for r in out.get("execution_results", []):
        marker = "✓" if r.get("ok") else "✗"
        det = (r.get("details") or r.get("error_type") or "")[:120]
        log(f"    {marker} {r['tool']}: {det}")
    reply = summarize_for_chat(out)
    if reply:
        log(f"  → speak: {reply}")
        speak(reply)


def _maybe_build_retry(out: dict, who: str, body: str, category: str) -> dict | None:
    """If the plan failed in a way that's recoverable with model replan,
    build a follow-up intent payload. Returns None when no retry should
    fire (success, signal-only plan, or non-actionable failure)."""
    if out.get("ok"):
        return None
    exec_results = out.get("execution_results") or []
    # Find the first failed action (not a signal) with a useful details msg.
    failed = None
    for r in exec_results:
        if r.get("ok"):
            continue
        et = r.get("error_type") or ""
        if et in ("bot_action_failed", "bot_soft_failure"):
            failed = r
            break
    if not failed:
        return None
    details = (failed.get("details") or "")[:300]
    if not details:
        return None

    prev_err = {
        "tool": failed.get("tool"),
        "error_type": failed.get("error_type"),
        "details": details,
    }
    # Keep the intent natural — the model was trained on integration
    # guide example #4 with a clean high_level_command + structured
    # previous_error. Earlier verbose retry texts overrode that signal
    # and the model interpreted the essay as new constraints.
    return {
        "intent": body,  # the original user request, verbatim
        "previous_error": prev_err,
        "allowed_tools": allowed_tools_for(category),
    }


def main():
    global _seen_chat_ts
    # Initialize timestamp filter — only consider messages from now forward
    _seen_chat_ts = int(time.time() * 1000)

    # Clean slate: kill any leftover pathfinder goal or task from a
    # previous companion session. Without this, bot can resume a stale
    # goto from a crashed run and look "runaway" to the user.
    cancel_bot_task()
    log(f"companion online — polling {BOT_API}/chat every {POLL_INTERVAL}s")
    log(f"embodied service at {SERVICE_API}")
    log(f"will respond to messages addressing me as: HermesBot, Hermes, bot, or typos like HermeBot/Hermsbot")
    log("Ctrl-C to stop.")

    while _running:
        # Path A — the bot's strict-matched queue (cleanest for proper addressing)
        cmds = get_pending_commands()
        for idx, cmd in enumerate(cmds):
            if not _running:
                break
            if cmd.get("status") and cmd["status"] != "pending":
                continue
            cid = f"{cmd.get('time')}:{cmd.get('from')}:{cmd.get('command')}"
            if cid in _seen_command_ids:
                continue
            _seen_command_ids.add(cid)
            # mark this chat ts as seen so we don't double-process via Path B
            ts = cmd.get("time") or 0
            if ts > _seen_chat_ts:
                _seen_chat_ts = ts
            try:
                process_command(idx, cmd)
            except Exception as e:
                log(f"[!] process_command exception: {e}")
                mark_command_done(idx)

        # Path B — fuzzy-matched chat poll (catches typos / loose addressing
        # that the bot's strict matcher missed)
        msgs = get_recent_chat(since_ts=_seen_chat_ts)
        for m in msgs:
            if not _running:
                break
            ts = m.get("time") or 0
            if ts <= _seen_chat_ts:
                continue
            _seen_chat_ts = ts
            try:
                process_chat_message(m)
            except Exception as e:
                log(f"[!] process_chat_message exception: {e}")

        time.sleep(POLL_INTERVAL)

    log("companion offline.")


if __name__ == "__main__":
    main()
