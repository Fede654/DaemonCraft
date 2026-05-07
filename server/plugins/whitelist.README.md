# Whitelist seeding (DC-131 / DC-DEP-6)

`ENFORCE_WHITELIST=true` (set in `docker-compose.yml`) means every connection
needs an explicit entry in `server/data/whitelist.json`. That file is
gitignored (it contains live UUID ↔ username mappings), so a fresh clone or
a fresh `docker compose up` boots with an **empty** whitelist — and nobody
can connect.

## Auto-generation (DC-DEP-6)

Hermes profiles are now managed automatically:

```bash
# Regenerate whitelist from cast YAMLs + deterministic offline UUIDs
python scripts/generate-whitelist.py

# Dry-run to preview changes
python scripts/generate-whitelist.py --dry-run
```

The script:
1. Reads every agent name from `agents/casts/*.yaml`
2. Generates deterministic offline UUIDs using the Minecraft standard:
   `UUID.nameUUIDFromBytes("OfflinePlayer:<username>".getBytes(UTF-8))`
3. Merges them with existing human players already in `server/data/whitelist.json`
4. Writes the updated whitelist

Human players are **preserved** automatically — any entry whose name does not
match a known cast agent is kept intact. To drop humans and output Hermes-only:

```bash
python scripts/generate-whitelist.py --no-preserve
```

### Verified deterministic UUIDs

| Username      | Deterministic UUID                     |
|---------------|----------------------------------------|
| Pamplinas     | `19dc6d96-3c66-3cad-b88c-3a2fc4dd506f` |
| Hermes-Clio   | `c32daea6-3ed7-3d07-98cc-3e60b244937b` |
| TestBotMC     | `a5cd5255-a003-38f1-8c19-d69be43a202a` |

Run `python scripts/generate-whitelist.py --verify <username>` to check a
single name.

## Skin assignment pipeline

Skins are assigned via `scripts/assign-skins.py` using `config/hermes-skins.yaml`:

```bash
# Assign all skins defined in the config
python scripts/assign-skins.py

# Assign only one agent
python scripts/assign-skins.py --only Pamplinas

# Preview without writing
python scripts/assign-skins.py --dry-run
```

Supported sources:
- `mojang:<username>` — fetch signed skin data from Mojang
- `url:<image-url>` — generate skin via MineSkin API
- `local:<.playerskin>` — copy an existing SkinsRestorer skin file
- `default` — remove override, let SkinsRestorer handle it naturally

Skin files are written to:
`server/data/plugins/SkinsRestorer/skins/<offline-uuid>.playerskin`

## ⚠️ Pre-merge checklist for the maintainer

If you currently have human players connected (e.g. `Siqui`,
`NicoElViejoGamer`, your own admin account, any Bedrock players via Geyser),
**add them to the whitelist before the next server restart that picks up
this change**. Otherwise they'll be locked out and see "You are not
whitelisted on this server!" on next reconnect.

```bash
# For each currently-known player:
docker exec -u 1000 daemoncraft-minecraft mc-send-to-console "whitelist add <username>"

# Verify:
docker exec -u 1000 daemoncraft-minecraft mc-send-to-console "whitelist list"
```

## Bedrock / Geyser players

Bedrock usernames carry a `.` prefix when bridged through Geyser
(e.g. `.iNicoElViejoGamer`). If you whitelist by Java username only, the
Bedrock connection still fails. Either:

- Whitelist with the prefixed name explicitly, or
- Install Floodgate (currently NOT installed; tracked as DC-131 open
  question — would let Bedrock players auto-resolve to a stable UUID).

## Seed file

`whitelist.example.json` is a stub showing the format the server expects.
Real entries land in `server/data/whitelist.json` (gitignored). The server
auto-fetches the canonical Mojang UUID for online accounts; for offline-mode
servers like ours, the UUID is generated deterministically from the username
(`OfflinePlayer:<name>`).

## Removing a player

See `docs/privacy.md` — the full parent-deletion runbook (whitelist remove,
CoreProtect rollback, LuckPerms clear, usercache cleanup) lives there.
