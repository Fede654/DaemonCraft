"""Body factory.

Picks an adapter based on the `kind` argument or the `MC_BODY` env var.
Defaults to `hermescraft` for backwards compatibility — existing casts
that don't declare a body get the same adapter as before.

Usage from agent_loop:

    from body import make_body
    body = make_body(os.getenv("MC_BODY"), os.getenv("MC_API_URL"), os.getenv("MC_USERNAME"))
    body.start_event_listener(on_chat_event)
"""

from __future__ import annotations

import os
from typing import Optional

from .contract import Body
from .hermescraft import HermescraftBody
from .mindcraft import MindcraftBody

_KINDS = {
    "hermescraft": HermescraftBody,
    "mindcraft": MindcraftBody,
}


def make_body(
    kind: Optional[str],
    api_url: str,
    username: str,
) -> Body:
    """Construct a Body adapter.

    `kind` of None or empty string defaults to MC_BODY env or
    "hermescraft". Unknown kinds raise ValueError.
    """
    name = (kind or os.getenv("MC_BODY", "")).strip().lower() or "hermescraft"
    cls = _KINDS.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown body kind: {name!r}. Known: {sorted(_KINDS)}"
        )
    return cls(api_url=api_url, username=username)


__all__ = ["Body", "HermescraftBody", "MindcraftBody", "make_body"]
