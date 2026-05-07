# DaemonCraft — Agent Orchestration Architecture

> Companion to ADR-004: Multi-Agent Orchestration (Task Plane vs Runtime Plane).
> This document is the operational reference for the DaemonCraft repo specifically.

---

## 1. Two-Plane Architecture

DaemonCraft agents run on a **split-plane** model:

| Concern | System | Where in this repo |
|---------|--------|-------------------|
| **Task plane** | Lattice (event-sourced) | Not in repo — tracked in `~/.hermes/org/.lattice` |
| **Runtime plane** | Gateway adapter + local SQLite | `agent-bridge/`, `agents/bot/server.js` |

### 1.1 Task Plane (Lattice)

Human-visible coordination. One Lattice epic per cast or deployment phase:
- **Epic**: representa una misión multi-agent (ej: “Civilization mode — Round 3”).
- **Subtasks**: cada agente embodied es un subtask `subtask_of` el epic.
- **Supervisor task**: un coordinator profile que monitorea y reasigna.

**Eventos Lattice válidos**:
- Epic created / in_progress / blocked / done
- Agent assigned / reassigned
- Mission state change (planned → in_progress → review → done)
- Supervisor heartbeat (cada 5 min)
- Recovery (agente muerto y respawneado después de threshold)

**NO van a Lattice**:
- Spawn / act / die / respawn individuales
- Percepciones por tick
- Chat lines (salvo que bloqueen una misión)

### 1.2 Runtime Plane (Gateway Adapter)

El gateway adapter es el **runtime canónico**. `agents/agent_loop.py` está deprecado (DC-DEP-9); solo se conserva como test harness.

**Componentes runtime**:
- `agent-bridge/bridge.py` — Flask HTTP control plane. Recibe triggers externos y los forwarda al Mineflayer Bot API.
- `agents/bot/server.js` — Mineflayer HTTP API + dashboard WebSocket. Consume percepciones del mundo Minecraft y las expone al gateway.
- `agents/hermescraft/minecraft_tools.py` — Hermes toolset que habla con el gateway adapter (ahora el Body Protocol canónico).

**Store local**:
- SQLite en `~/.hermes/gateway/runtime/<cast_id>.db` (no commiteado en repo).
  - `perception_log`: snapshots del Body Protocol (ventana 24h).
  - `action_log`: tool calls emitidas por gateway hacia bodies (ventana 7d).
  - `chat_log`: chat persistente (auditoría social).
  - `state_log`: checkpoints periódicos del mundo.

---

## 2. Supervisor-Agent Pattern

### 2.1 Cast Lifecycle

```
Humano crea Epic en Lattice
        ↓
Supervisor (agent:coordinator) lee el epic
        ↓
Por cada bot en cast YAML → crea subtask + spawnea session gateway
        ↓
Cada agente = profile YAML + gateway session + body (Mineflayer bot)
        ↓
Supervisor pollea Lattice status cada 5 min
        ↓
Si blocked > threshold → reassign o escalate a needs_human
```

### 2.2 Files Involved

- `agents/casts/*.yaml` — definición del cast (qué bots, qué profiles, qué feature flags).
- `agents/SOUL-*.md` — reglas de comportamiento por modo (base, civilization, landfolk, rolemaster).
- `agents/daemoncraft.py` — launcher manual (start/stop/restart/update). **Legacy** — el supervisor lo reemplaza en modo swarm.

### 2.3 Migration Path

| Fase | Estado | Qué corre |
|------|--------|-----------|
| P0 (ahora) | Manual | `daemoncraft.py start civilization` — 1 humano lanza 1 cast |
| P1 (HRM-91) | Background swarm | Cron-driven profiles en CT201, sin supervisor autónomo |
| P2 (HRM-88) | Supervisor-autónomo | Supervisor spawn/reassign sin humano en el loop |

---

## 3. Trust / Isolation Model

### 3.1 Profile Boundaries

Cada agente corre con un profile YAML que restringe su toolset:
- `altercraft-clio`: solo `altercraft` + `memory` tools.
- `altercraft-atlas`: podría tener `altercraft` + `terminal` (si necesita ejecutar comandos RCON).
- Ningún embodied profile tiene acceso a `git`, `telegram`, `discord` tools a menos que el cast lo declare explícitemente.

> **Esto es configuración, no enforcement.** Un prompt injection puede saltarlo. Sandbox OS es future work.

### 3.2 Shared-World Namespace

- Todos los bots en un mundo comparten namespace Minecraft (usernames, posiciones, chat).
- No hay autenticación técnica bot-a-bot: Bot A puede enviar chat que Bot B interpreta como mensaje de jugador.
- **Mitigación**: el gateway adapter filtra chat originado por bots del mismo cast para evitar cascadas de echo (ver AUDIT_MULTIAGENT_GAPS.md §3.2).

### 3.3 Feature Flags per Cast

Cada cast YAML declara flags que restringen capacidades peligrosas:

```yaml
cast:
  name: civilization
  feature_flags:
    GATEWAY_HANDLES_QUEST_EVENTS: true
    GATEWAY_HANDLES_CHAT: true
    ALLOW_OPERATOR_COMMANDS: false   # bloquea /ban, /give, /kill, /tp
```

- `ALLOW_OPERATOR_COMMANDS: false` es el default para todos los casts multibot.
- Solo `rolemaster` (single-bot, human-supervised) puede tenerlo en `true`.

### 3.4 Future: Signed Souls

El plan Craftium (archivado en `~/REPOS/vault/raw/daemoncraft-plan-may2026.md`) propone:
- Clave Ed25519 por daemon.
- Commits firmados en repo git-backed.
- `soul-canonical-state` invariant.

Este ADR asume identidad **declarativa** (profile YAML) en el corto plazo. La identidad criptográfica es dependencia de HRM-26 (persistent memory), aún en backlog.

---

## 4. Operational Checklist

### Agregar un nuevo cast

1. Crear `agents/casts/<nombre>.yaml` con bot list + profiles + feature_flags.
2. Crear/modificar `agents/SOUL-<nombre>.md` si el modo necesita reglas nuevas.
3. Crear Lattice epic (si es trabajo trackeable) o usar `daemoncraft.py start` (si es dev/test).
4. Verificar que `ALLOW_OPERATOR_COMMANDS` está en `false` si hay >1 bot.
5. Asegurar que el gateway adapter tenga el cast config en su registry (`BOT_REGISTRY` env).

### Debuggear un agente caído

1. **Task plane**: `lattice show <task-id>` → ¿está `blocked` o `needs_human`?
2. **Runtime plane**: revisar `~/.hermes/gateway/runtime/<cast_id>.db` → `action_log` y `chat_log`.
3. **Gateway logs**: `journalctl -u hermes-gateway` (si corre como systemd) o stdout del gateway.
4. **Body logs**: `agents/bot/logs/<bot_name>.log` (Mineflayer debug).

### Escalar a modo supervisor

1. Asegurar que el supervisor profile (`agent:coordinator`) tiene toolset `mcp_lattice` + `delegate_task`.
2. El supervisor debe correr en un proceso watchdoggeado (systemd `Restart=on-failure`).
3. Configurar `MemoryHigh` / `MemoryMax` en systemd unit para evitar OOM del host.

---

## 5. References

- ADR-004 (canonical): `~/REPOS/vault/adrs/ADR-004-multi-agent-orchestration.md`
- AUDIT_MULTIAGENT_GAPS: `./AUDIT_MULTIAGENT_GAPS.md`
- HRM-88 (LV-SWARM Epic): `~/REPOS/LaVanguardIA/plans/HERMES-SWARM-PLAN.md`
- HRM-25 (original spike): `~/.hermes/org/` — Lattice task T002.6
- HRM-123 (DC-DEP-7): `~/.hermes/org/` — Lattice task cerrada con este ADR.
- DC-109 (feature flags): `./plans/DC-109.md`
- DC-DEP-9 (agent_loop deprecation): `~/.hermes/org/` — HRM-125
