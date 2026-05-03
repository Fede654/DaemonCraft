# ChatFilter — Spanish Wordlist

The ChatFilter plugin (Modrinth `chatfilter-zepsizola`) installs with an
EN-only sample. `wordFilters-es.yml` here is a tight ES floor: common
strong-profanity (soft-block / replace with `****`) plus a smaller
zero-tolerance group-slur list (hard-block).

## Install

ChatFilter doesn't (yet) support an `include:` directive, so the entries
need to live in the plugin's main `wordFilters.yml`. The recommended path
is the installer script:

```bash
scripts/install-chatfilter-es.sh
```

It detects whether the entries are already merged (idempotent — uses an
`AddedBy: DC-131` sentinel), appends them if not, and restarts minecraft
so ChatFilter rebuilds its filter set. Re-running on an already-installed
server is a no-op.

If you'd rather do it by hand, the script is short and the manual paths
below are equivalent.

**A) Append** — add the `ChatFilter:` children to the plugin's existing file,
then **restart the server** (see gotcha below):

```bash
docker cp server/plugins/chatfilter/wordFilters-es.yml \
  daemoncraft-minecraft:/data/plugins/ChatFilter/wordFilters-es.yml.staging
docker exec -u 1000 daemoncraft-minecraft python3 -c "
src = open('/data/plugins/ChatFilter/wordFilters-es.yml.staging').read()
body = src.split('ChatFilter:\n', 1)[1]   # strip the leading header
with open('/data/plugins/ChatFilter/wordFilters.yml', 'a') as f:
    f.write('\n' + body)
"
docker exec -u 1000 daemoncraft-minecraft rm /data/plugins/ChatFilter/wordFilters-es.yml.staging
docker compose restart minecraft
```

**B) Replace** — starting fresh, no EN samples needed:

```bash
cp server/plugins/chatfilter/wordFilters-es.yml \
  server/data/plugins/ChatFilter/wordFilters.yml
docker compose restart minecraft
```

**Gotcha:** `chatfilter reload` reloads `config.yml` and the locale
properties, but **NOT** `wordFilters.yml` — the filter set is built once
at plugin enable. A full server restart is required to pick up new entries.
Verified against ChatFilter 2.0.15 (zepsizola): `chatfilter reload` says
"Config reloaded!" but the new entries don't fire; after `docker compose
restart minecraft` the boot log shows the bumped filter count and the
entries fire on the next chat message.

`server/data/` is gitignored, so the live file isn't tracked here. This
directory holds the canonical authored source.

## Tuning

- The strong-profanity list uses `\w*` after the root to catch conjugations
  (`putada`, `mierdoso`) but `\b` on the left to avoid catching innocuous
  prefixes (`disputa`, `inmiscuirse`).
- Group slurs are deliberately narrow — false positives here would be much
  worse than missed catches. Widen only after an incident review surfaces
  a specific gap.
- Soft-block uses `Replace: true` + `Cancel: false` so the message still
  reaches chat with the offending word as `****`. Hard-block uses `Cancel:
  true` so the line never appears.

## Future

If repeated offenders need automated escalation (mute, kick), add a
LiteBans hook in `Action:` blocks. Out of scope today.
