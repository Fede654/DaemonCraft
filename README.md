# DaemonCraft

Distributed AI-native Minecraft metaverse with persistent AI agents ("Daemons").

## Overview

DaemonCraft is a scalable ecosystem where persistent AI companions live inside a rich industrial and exploration world built on the **Phi-Craft** modpack. The game supports both **Java Edition** and **Bedrock Edition** clients from day one.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Hermes Gateway (gateway/platforms/daemoncraft.py)                    │
│  — Canonical runtime for embodied AI agents                           │
│  — Multi-platform routing (Minecraft ↔ Telegram ↔ Discord ↔ CLI)       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Body Protocol (gateway/platforms/daemoncraft_body.py)                │
│  — Swappable body adapters: Hermescraft (Mineflayer) | Mindcraft        │
│  — Async HTTP/WS contract between gateway and bot server                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Bot Server (agents/bot/server.js)                                     │
│  — Mineflayer bot + Perception Primitive + Quest Engine                 │
│  — Emits PerceptionSnapshot on every heartbeat                          │
└─────────────────────────────────────────────────────────────────────┘
```

## Repository Structure

- `server/` — Minecraft Forge server configuration and data
- `agents/` — AI agent casts, SOUL prompts, and test harness
  - `agents/bot/` — Mineflayer bot server with Perception Primitive
  - `agents/casts/` — YAML cast definitions (companion, architect, etc.)
  - `agents/SOUL-*.md` — Role-playing system prompts
- `scripts/` — Operational scripts
  - `scripts/generate-whitelist.py` — Auto-whitelist from cast definitions
  - `scripts/assign-skins.py` — Skin assignment via SkinsRestorer
  - `scripts/telegram-bridge.py` — Telegram ↔ Minecraft chat bridge
- `docs/` — Architecture docs, runbooks, and design records
  - [`docs/privacy.md`](docs/privacy.md) — what we log, retention, and parent-deletion runbook
  - [`docs/telegram-bridge.md`](docs/telegram-bridge.md) — bridge setup and operation
- `config/` — Configuration templates
- `systemd/` — systemd unit files for background services
- `docker/` — Docker configurations and overrides

## Quick Start

```bash
./start-dev.sh
```

## Development

This project uses:
- **Lattice** for task tracking (see `.lattice/`)
- **Git feature branches** — never commit directly to `main`
- **TDD** where applicable
- **Wiki** at `~/wiki` for design docs and research

## Phase 0

Current milestone: Development Server Setup
See `PROJECT.md` for the full Phase 0 specification.

## Related Repositories

- [`hermes-agent`](https://github.com/nousresearch/hermes-agent) — The Hermes gateway runtime (platform adapter: `gateway/platforms/daemoncraft.py`)
- [`vault`](~/REPOS/vault) — Design docs, ADRs, and research notes (ADR-004 covers multi-agent orchestration)
