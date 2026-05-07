#!/usr/bin/env python3
"""
generate-whitelist.py — Deterministic offline UUID whitelist generator for Hermes profiles.

Reads agent names from cast YAML files, generates deterministic offline UUIDs
(Minecraft standard: UUID v3 from "OfflinePlayer:<username>"), and produces
a merged whitelist.json that preserves existing human players.

Usage:
    python scripts/generate-whitelist.py
    python scripts/generate-whitelist.py --dry-run
    python scripts/generate-whitelist.py --output server/data/whitelist.json
    python scripts/generate-whitelist.py --casts-dir agents/casts

The script auto-detects the repository root by looking for .git / agents / server.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path


def offline_uuid(username: str) -> str:
    """Return the deterministic offline-mode UUID for a Minecraft username.

    This replicates the exact algorithm Minecraft uses:
      UUID.nameUUIDFromBytes("OfflinePlayer:<username>".getBytes(UTF_8))

    Verified against existing whitelist entries:
      Hermes-Clio  -> c32daea6-3ed7-3d07-98cc-3e60b244937b
      Pamplinas    -> 19dc6d96-3c66-3cad-b88c-3a2fc4dd506f
      TestBotMC    -> a5cd5255-a003-38f1-8c19-d69be43a202a
    """
    data = f"OfflinePlayer:{username}".encode("utf-8")
    md5 = hashlib.md5(data).digest()
    # Java's nameUUIDFromBytes sets version=3 and variant=RFC-4122,
    # which is exactly what uuid.UUID(bytes=..., version=3) does.
    return str(uuid.UUID(bytes=md5[:16], version=3))


def find_repo_root() -> Path:
    """Walk upward until we find a directory that looks like the daemoncraft repo."""
    cwd = Path.cwd().resolve()
    for path in [cwd, *cwd.parents]:
        if (path / ".git").exists() and (path / "agents").exists():
            return path
    # Fallback: assume we are inside the repo already.
    return cwd


def load_casts(casts_dir: Path) -> list[dict]:
    """Load all cast YAMLs and return a list of agent dicts."""
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML is required: pip install pyyaml") from exc

    agents: list[dict] = []
    for cast_file in sorted(casts_dir.glob("*.yaml")):
        try:
            config = yaml.safe_load(cast_file.read_text()) or {}
        except Exception as e:
            print(f"[warn] Failed to load {cast_file}: {e}", file=sys.stderr)
            continue

        cast_name = config.get("name", cast_file.stem)
        for agent in config.get("agents", []):
            name = agent.get("name", "")
            if not name:
                continue
            agents.append(
                {
                    "name": name,
                    "cast": cast_name,
                    "template": agent.get("template", ""),
                }
            )
    return agents


def load_existing_whitelist(path: Path) -> list[dict]:
    """Load existing whitelist.json if it exists."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return data
    except json.JSONDecodeError as e:
        print(f"[warn] Corrupt whitelist.json ({e}), starting fresh", file=sys.stderr)
    return []


def is_hermes_profile(name: str, known_names: set[str]) -> bool:
    """Check if a whitelist entry name matches a known Hermes profile."""
    return name in known_names


def merge_whitelist(
    existing: list[dict],
    hermes_agents: list[dict],
    preserve_unknown: bool = True,
) -> list[dict]:
    """Merge Hermes agents into whitelist, optionally preserving unknown players."""
    known_names = {a["name"] for a in hermes_agents}
    known_lower = {n.lower() for n in known_names}

    # Start with Hermes entries (deterministic, always regenerated)
    entries: dict[str, dict] = {}
    for agent in hermes_agents:
        username = agent["name"]
        entries[username.lower()] = {
            "uuid": offline_uuid(username),
            "name": username,
        }

    if preserve_unknown:
        for entry in existing:
            name = entry.get("name", "")
            if not name:
                continue
            # Skip entries that look like Hermes profiles (we regenerate those)
            if name.lower() in known_lower:
                continue
            # Skip zero-UUID placeholder entries
            if entry.get("uuid") == "00000000-0000-0000-0000-000000000000":
                continue
            # Preserve unknown / human players
            entries[name.lower()] = entry

    return list(entries.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic whitelist.json for Hermes profiles"
    )
    parser.add_argument(
        "--casts-dir",
        type=Path,
        help="Directory containing cast YAML files (default: agents/casts)",
    )
    parser.add_argument(
        "--whitelist",
        type=Path,
        help="Path to existing whitelist.json (default: server/data/whitelist.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (default: same as --whitelist)",
    )
    parser.add_argument(
        "--no-preserve",
        action="store_true",
        help="Do not preserve unknown/human players; output Hermes-only",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resulting JSON but do not write it",
    )
    parser.add_argument(
        "--verify",
        metavar="USERNAME",
        help="Print the deterministic offline UUID for a single username and exit",
    )
    args = parser.parse_args(argv)

    if args.verify:
        print(offline_uuid(args.verify))
        return 0

    repo_root = find_repo_root()
    casts_dir = args.casts_dir or repo_root / "agents" / "casts"
    whitelist_path = args.whitelist or repo_root / "server" / "data" / "whitelist.json"
    output_path = args.output or whitelist_path

    if not casts_dir.exists():
        print(f"[error] Casts directory not found: {casts_dir}", file=sys.stderr)
        return 1

    agents = load_casts(casts_dir)
    if not agents:
        print("[warn] No agents found in cast files.", file=sys.stderr)

    existing = load_existing_whitelist(whitelist_path)
    merged = merge_whitelist(
        existing, agents, preserve_unknown=not args.no_preserve
    )

    # Sort: Hermes profiles first (by cast order), then humans alphabetically
    known_order = {a["name"].lower(): i for i, a in enumerate(agents)}

    def sort_key(entry: dict) -> tuple:
        name_lower = entry.get("name", "").lower()
        is_hermes = name_lower in known_order
        return (0 if is_hermes else 1, known_order.get(name_lower, name_lower))

    merged.sort(key=sort_key)

    payload = json.dumps(merged, indent=2) + "\n"

    if args.dry_run:
        print(payload)
        print(f"\n# Would write {len(merged)} entries to {output_path}")
        print(f"# Hermes profiles: {len([e for e in merged if e.get('name','').lower() in known_order])}")
        print(f"# Preserved humans: {len([e for e in merged if e.get('name','').lower() not in known_order])}")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload)
    print(f"Wrote {len(merged)} entries to {output_path}")
    print(f"  Hermes profiles : {len([e for e in merged if e.get('name','').lower() in known_order])}")
    print(f"  Preserved humans: {len([e for e in merged if e.get('name','').lower() not in known_order])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
