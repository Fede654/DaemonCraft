# DaemonCraft

Distributed AI-native Minecraft metaverse with persistent AI agents ("Daemons").

## Overview

DaemonCraft is a scalable ecosystem where persistent AI companions live inside a rich industrial and exploration world built on the **Phi-Craft** modpack. The game supports both **Java Edition** and **Bedrock Edition** clients from day one.

## Repository Structure

- `server/` — Minecraft Forge server configuration and data
- `bots/` — Mineflayer-based Daemon AI agents (Node.js)
- `agent-bridge/` — Python trigger bridge for agent orchestration
- `scripts/telegram-bridge.py` — Standalone Telegram <-> Minecraft chat bridge (see `docs/telegram-bridge.md`)
- `docker/` — Docker configurations and overrides
- `docs/` — Architecture docs, runbooks, and design records
  - [`docs/privacy.md`](docs/privacy.md) — what we log, retention, and parent-deletion runbook

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
