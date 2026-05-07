#!/usr/bin/env python3
"""
assign-skins.py — Skin assignment pipeline for Hermes profiles via SkinsRestorer.

Maps agent names (from cast YAMLs + skin config) to skin sources and writes
<offline-uuid>.playerskin files into the SkinsRestorer skins directory.

Supported sources:
  mojang:<username>   — Fetch skin from Mojang API (value + signature).
  url:<image-url>     — Generate skin via MineSkin API.
  local:<path>        — Copy an existing .playerskin file, rewriting UUID/name.
  default             — Remove any existing override; let SkinsRestorer handle it.

Usage:
    python scripts/assign-skins.py
    python scripts/assign-skins.py --dry-run
    python scripts/assign-skins.py --skin-config config/hermes-skins.yaml
    python scripts/assign-skins.py --skin-config config/hermes-skins.yaml --only Pamplinas

Requires:
    PyYAML  (pip install pyyaml)
    Python >=3.9
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


def offline_uuid(username: str) -> str:
    """Deterministic offline-mode UUID (Minecraft standard)."""
    data = f"OfflinePlayer:{username}".encode("utf-8")
    md5 = hashlib.md5(data).digest()
    return str(uuid.UUID(bytes=md5[:16], version=3))


def find_repo_root() -> Path:
    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        if (path / ".git").exists() and (path / "agents").exists():
            return path
    return cwd


def load_skin_config(path: Path) -> dict[str, dict]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc
    data = yaml.safe_load(path.read_text()) or {}
    # Top-level keys that are not metadata are usernames
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def fetch_mojang_skin(username: str) -> dict | None:
    """Fetch skin value + signature from Mojang for a premium username."""
    # 1. Resolve username -> UUID
    profile_url = f"https://api.mojang.com/users/profiles/minecraft/{username}"
    try:
        with urllib_request.urlopen(profile_url, timeout=10) as resp:
            profile = json.loads(resp.read().decode("utf-8"))
    except urllib_error.HTTPError as e:
        if e.code == 404:
            print(f"  [warn] Mojang profile not found for '{username}'", file=sys.stderr)
        else:
            print(f"  [warn] Mojang API error {e.code} for '{username}'", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [warn] Failed to reach Mojang API: {e}", file=sys.stderr)
        return None

    mojang_uuid = profile.get("id")
    if not mojang_uuid:
        return None

    # 2. Fetch signed texture data
    session_url = (
        f"https://sessionserver.mojang.com/session/minecraft/profile/{mojang_uuid}"
        f"?unsigned=false"
    )
    try:
        with urllib_request.urlopen(session_url, timeout=10) as resp:
            session = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [warn] Failed to fetch session for '{username}': {e}", file=sys.stderr)
        return None

    properties = session.get("properties", [])
    textures = next(
        (p for p in properties if p.get("name") == "textures"), None
    )
    if not textures:
        print(f"  [warn] No textures property for '{username}'", file=sys.stderr)
        return None

    return {
        "value": textures.get("value", ""),
        "signature": textures.get("signature", ""),
    }


def fetch_mineskin_skin(image_url: str, api_key: str = "") -> dict | None:
    """Upload a skin image URL via MineSkin and return value + signature."""
    payload: dict = {"url": image_url, "name": "hermes_generated"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib_request.Request(
        "https://api.mineskin.org/generate/url",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [warn] MineSkin API failed: {e}", file=sys.stderr)
        return None

    data = result.get("data", {})
    texture = data.get("texture", {})
    return {
        "value": texture.get("value", ""),
        "signature": texture.get("signature", ""),
    }


def build_playerskin_json(agent_name: str, offline_uuid_str: str, skin_data: dict) -> dict:
    """Assemble the .playerskin JSON payload."""
    return {
        "uniqueId": offline_uuid_str,
        "lastKnownName": agent_name,
        "value": skin_data["value"],
        "signature": skin_data["signature"],
        "timestamp": int(time.time()),
        "dataVersion": 1,
    }


def load_local_playerskin(path: Path) -> dict | None:
    """Load and validate an existing .playerskin file."""
    try:
        data = json.loads(path.read_text())
        if {"uniqueId", "value", "signature"} <= data.keys():
            return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [warn] Failed to load local skin {path}: {e}", file=sys.stderr)
    return None


def assign_skin(
    agent_name: str,
    source: str,
    skins_dir: Path,
    dry_run: bool,
    mineskin_api_key: str = "",
) -> bool:
    """Assign a skin to a single agent. Returns True on success."""
    offline = offline_uuid(agent_name)
    target_file = skins_dir / f"{offline}.playerskin"

    if source.lower() == "default":
        if dry_run:
            print(f"  [dry-run] Would remove {target_file} (default skin)")
        else:
            if target_file.exists():
                target_file.unlink()
                print(f"  Removed {target_file.name} → default skin")
            else:
                print(f"  No override for {agent_name} (already default)")
        return True

    skin_data: dict | None = None

    if source.startswith("mojang:"):
        mojang_name = source.split(":", 1)[1]
        print(f"  Fetching Mojang skin for '{mojang_name}'...")
        skin_data = fetch_mojang_skin(mojang_name)

    elif source.startswith("url:"):
        url = source.split(":", 1)[1]
        print(f"  Generating MineSkin from URL...")
        skin_data = fetch_mineskin_skin(url, api_key=mineskin_api_key)

    elif source.startswith("local:"):
        local_path = Path(source.split(":", 1)[1]).expanduser()
        print(f"  Loading local skin {local_path}...")
        existing = load_local_playerskin(local_path)
        if existing:
            skin_data = {
                "value": existing["value"],
                "signature": existing["signature"],
            }
    else:
        print(f"  [error] Unknown source format: {source}", file=sys.stderr)
        return False

    if not skin_data:
        return False

    payload = build_playerskin_json(agent_name, offline, skin_data)
    json_str = json.dumps(payload, indent=2) + "\n"

    if dry_run:
        print(f"  [dry-run] Would write {target_file.name}")
        print(f"    uniqueId={offline}, lastKnownName={agent_name}")
        return True

    skins_dir.mkdir(parents=True, exist_ok=True)
    target_file.write_text(json_str)
    print(f"  Wrote {target_file.name}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Assign skins to Hermes profiles via SkinsRestorer"
    )
    parser.add_argument(
        "--skin-config",
        type=Path,
        help="Path to skin mapping YAML (default: config/hermes-skins.yaml)",
    )
    parser.add_argument(
        "--skins-dir",
        type=Path,
        help="SkinsRestorer skins directory (default: server/data/plugins/SkinsRestorer/skins)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without writing files",
    )
    parser.add_argument(
        "--only",
        metavar="AGENT",
        help="Process only a single agent name",
    )
    parser.add_argument(
        "--mineskin-api-key",
        default="",
        help="MineSkin API key (optional, for url skins)",
    )
    args = parser.parse_args(argv)

    repo_root = find_repo_root()
    skin_config_path = args.skin_config or repo_root / "config" / "hermes-skins.yaml"
    skins_dir = args.skins_dir or (
        repo_root / "server" / "data" / "plugins" / "SkinsRestorer" / "skins"
    )

    if not skin_config_path.exists():
        print(f"[error] Skin config not found: {skin_config_path}", file=sys.stderr)
        return 1

    mappings = load_skin_config(skin_config_path)
    if not mappings:
        print("[warn] No skin mappings found in config.", file=sys.stderr)
        return 0

    if args.only:
        if args.only not in mappings:
            print(
                f"[error] Agent '{args.only}' not found in skin config.",
                file=sys.stderr,
            )
            return 1
        mappings = {args.only: mappings[args.only]}

    ok = 0
    failed = 0
    skipped = 0

    for agent_name, cfg in sorted(mappings.items()):
        source = cfg.get("source", "default")
        notes = cfg.get("notes", "")
        print(f"\n{agent_name} → {source}" + (f"  ({notes})" if notes else ""))
        if assign_skin(
            agent_name,
            source,
            skins_dir,
            dry_run=args.dry_run,
            mineskin_api_key=args.mineskin_api_key,
        ):
            ok += 1
        else:
            if source == "default":
                skipped += 1
            else:
                failed += 1

    print(f"\nDone.  OK={ok}  Failed={failed}  Skipped={skipped}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
