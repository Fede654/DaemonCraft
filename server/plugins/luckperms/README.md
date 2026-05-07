# LuckPerms group definitions

`groups.json` is the authoritative group config exported from the live server via `lp export`.

## Groups

| Group | Inherits | Purpose |
|---|---|---|
| `default` | — | All players; basic chat commands only |
| `pamplina-team` | `default` | Narrative operator scope (mirrors `mc_command` capability) |
| `op` | `pamplina-team` | Full server ops; human admin only |

## Applying to a fresh server

```bash
# 1. Copy groups.json into the LuckPerms plugin data dir
cp server/plugins/luckperms/groups.json \
   server/data/plugins/LuckPerms/groups-import.json
# 2. Import via rcon
docker exec daemoncraft-minecraft rcon-cli "lp import groups-import.json"
```

## Adding a new player to a group

```bash
docker exec daemoncraft-minecraft rcon-cli "lp user <username> parent add pamplina-team"
```

## Updating group definitions

Make changes in-game or via rcon, then re-export:
```bash
docker exec daemoncraft-minecraft rcon-cli "lp export groups-export.yml"
# decode the gzip+json, overwrite groups.json, commit
python3 -c "import gzip,json; open('server/plugins/luckperms/groups.json','w').write(
  json.dumps(json.loads(gzip.open('server/data/plugins/LuckPerms/groups-export.yml.json.gz').read()),indent=2))"
```
