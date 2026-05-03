# Server Overhaul — Operator Runbook

Operational reference for the DaemonCraft server overhaul (epic DC-124). Companion to `plans/DC-124.md` and the verbatim plan in `~/REPOS/vault/projects/DaemonCraft/overhaul-plan.md`.

This file is updated as each phase lands. Treat it as the single source of truth for "what versions are pinned, how do I upgrade them, how do I restore from backup".

---

## Pinned versions

### Server image (DC-125)

```
itzg/minecraft-server@sha256:629762aaf864e109a35e00b11d701cfc6b2bddca4331944aefde0a352ebb9fd4
```

Captured 2026-05-03 from `docker image inspect itzg/minecraft-server:latest --format '{{index .RepoDigests 0}}'` on a known-good running container.

**Upgrade procedure:**

1. On a scratch host (or laptop), pull the new tag and start a clean container with the same env. Smoke test: server boots healthy, Geyser loads, agent bot connects.
2. Capture the new digest: `docker image inspect itzg/minecraft-server:latest --format '{{index .RepoDigests 0}}'`
3. Open a PR that updates only the digest line in `docker-compose.yml`. PR description: what version changed, what was smoke-tested.
4. After merge, `docker compose pull && docker compose up -d` on production. Watch logs for 5 min.
5. **Never switch back to `:latest`** — that defeats the pin and makes incidents un-bisectable.

### Plugins (auto-installed via itzg)

| Plugin | Source | Version pin | Owner ticket |
|---|---|---|---|
| Geyser-Spigot | Modrinth `geyser` | `2.9.5-b1130` (`R7DKgZlt`) — pin once `feat/bedrock-geyser-support` merges upstream | DC-125 follow-up |

The Geyser pin lands as a follow-up because the `MODRINTH_PROJECTS: "geyser"` line is on the `feat/bedrock-geyser-support` branch (PR #2 to nicoechaniz). Once that merges, a small follow-up PR replaces `"geyser"` with `"geyser:R7DKgZlt"`.

### Plugins (manually installed)

Currently in `server/data/plugins/` (not auto-installed; survive the gitignored `server/data/` boundary because the plugin jars and configs are managed manually):

| Plugin | Loaded version | Source |
|---|---|---|
| Denizen | _capture from running server, see below_ | manual |
| spark | _capture from running server, see below_ | manual |

To capture loaded versions:
```
docker exec daemoncraft-minecraft mc-send-to-console "version Denizen"
docker exec daemoncraft-minecraft mc-send-to-console "version spark"
```

(These versions land in this table as part of DC-126 when LuckPerms / CoreProtect / SkinsRestorer / DecentHolograms / TAB are added — they all get one inventory pass.)

---

## Cast model configuration (DC-125)

All casts use **MiniMax-M2.7** via `provider: minimax` and `base_url: https://api.minimax.io/anthropic`. The `agents/casts/rolemaster.yaml` file was previously misconfigured with `kimi-k2.6` / `kimi-coding`; corrected in DC-125 to match the runtime.

If you add a new cast, copy the model/provider/base_url block from `companion.yaml` as the canonical reference.

---

## Difficulty (DC-125)

Server-wide default: **easy**. Permits hostile mob spawns (needed for rolemaster narrative tension) while keeping kid-friendly damage scaling.

Pamplinas (rolemaster cast) can issue `/difficulty peaceful` for specific scenes via `mc_command`; the server-wide default reverts on next restart.

**Gotcha**: existing worlds store difficulty in `level.dat` (NBT) which overrides `server.properties`. Changing the env var alone does nothing for an already-generated world. Apply once via console:
```
docker exec daemoncraft-minecraft rcon-cli difficulty easy
```
This persists into `level.dat`. New worlds pick up the env value at generation.

---

## Backup + restore (DC-126 — pending)

Procedure lands here when DC-126 ships the `mc-backup` sidecar.

---

## CoreProtect rollback (DC-126 — pending)

Procedure lands here when CoreProtect installs.

---

## LuckPerms group definitions (DC-126 — pending)

Group hierarchy and permission grammar land here.

---

## Whitelist / invite-code procedure (DC-131 — pending)

Onboarding runbook lands here.

---

## Daily metrics report (DC-132 — pending)

Aggregation script and read-the-output guide land here.
