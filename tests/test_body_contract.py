"""Body protocol contract tests — no live server needed.

Validates the factory dispatch, capability flags, and method shapes that
agent_loop relies on. Live integration testing happens via Phase 3/4/5
session artifacts in Alter-infra:inference/andy/experiments/.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make agents/body importable from tests/
AGENTS_DIR = Path(__file__).parent.parent / "agents"
sys.path.insert(0, str(AGENTS_DIR))

from body import Body, HermescraftBody, MindcraftBody, make_body


class TestFactory:
    def test_default_is_hermescraft(self):
        b = make_body(None, "http://localhost:3001", "Steve")
        assert isinstance(b, HermescraftBody)
        assert b.kind == "hermescraft"

    def test_explicit_hermescraft(self):
        b = make_body("hermescraft", "http://localhost:3001", "Steve")
        assert isinstance(b, HermescraftBody)

    def test_explicit_mindcraft(self):
        b = make_body("mindcraft", "http://localhost:8090", "andy")
        assert isinstance(b, MindcraftBody)
        assert b.kind == "mindcraft"

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown body kind"):
            make_body("foo", "http://localhost", "x")

    def test_url_is_normalized(self):
        b = make_body("hermescraft", "http://localhost:3001/", "Steve")
        # Trailing slash stripped — adapters concat paths with `/foo`.
        assert b.api_url == "http://localhost:3001"

    def test_env_var_used_when_kind_blank(self, monkeypatch):
        monkeypatch.setenv("MC_BODY", "mindcraft")
        b = make_body("", "http://localhost:8090", "andy")
        assert b.kind == "mindcraft"


class TestCapabilities:
    def test_hermescraft_caps(self):
        b = HermescraftBody("http://localhost:3001", "Steve")
        # bot/server.js has /screenshot via puppeteer + /tellraw impersonation
        assert b.supports_screenshot is True
        assert b.supports_impersonation is True
        # but no /set_goal or /act preempt
        assert b.supports_set_goal is False
        assert b.supports_act is False

    def test_mindcraft_caps(self):
        b = MindcraftBody("http://localhost:8090", "andy")
        # sidecar Phase 4 has set_goal + act
        assert b.supports_set_goal is True
        assert b.supports_act is True
        # but no screenshot or impersonation yet
        assert b.supports_screenshot is False
        assert b.supports_impersonation is False


class TestUnsupportedMethods:
    """Methods that aren't supported on a given adapter must return a
    structured error (never raise) so callers can branch via supports_*
    or by inspecting the result dict."""

    def test_hermescraft_set_goal_returns_error(self):
        b = HermescraftBody("http://localhost:3001", "Steve")
        r = b.set_goal("foo")
        assert r["ok"] is False
        assert "set_goal" in r["error"].lower()

    def test_hermescraft_act_returns_error(self):
        b = HermescraftBody("http://localhost:3001", "Steve")
        r = b.act("!stop")
        assert r["ok"] is False
        assert "act" in r["error"].lower()


class TestProtocolConformance:
    """Both adapters must satisfy the Body Protocol at runtime."""

    @pytest.mark.parametrize("kind", ["hermescraft", "mindcraft"])
    def test_isinstance_of_body(self, kind):
        b = make_body(kind, "http://localhost:1234", "x")
        assert isinstance(b, Body), (
            f"{kind} adapter does not satisfy Body protocol"
        )


class TestEmptyMessageRejection:
    """Both adapters reject empty/None chat messages without hitting the
    network."""

    @pytest.mark.parametrize("kind", ["hermescraft", "mindcraft"])
    @pytest.mark.parametrize("text", ["", "   ", None, 123, []])
    def test_rejects_empty_chat(self, kind, text):
        b = make_body(kind, "http://localhost:1234", "x")
        r = b.chat(text)  # type: ignore[arg-type]
        assert r["ok"] is False
        assert "message" in r["error"].lower()
