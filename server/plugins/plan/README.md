# Plan plugin — local-only webserver bind

Plan (Player Analytics) ships with `Webserver.Internal_IP: 0.0.0.0` by default.
On a host-network container that exposes the dashboard publicly on
`<host-ip>:8804` — including any auth bypass it has at the time. We bind to
`127.0.0.1` so the dashboard is reachable only from the host (or via SSH
tunnel for remote admin).

## Apply on a fresh server

The full `config.yml` lives under the gitignored `server/data/` tree. After
the plugin generates its config on first boot, apply the bind override:

```bash
docker exec daemoncraft-minecraft sed -i \
  's|Internal_IP: 0.0.0.0|Internal_IP: 127.0.0.1|' \
  /data/plugins/Plan/config.yml
docker exec -u 1000 daemoncraft-minecraft mc-send-to-console "plan reload"
```

Verify:

```bash
# Should respond (302 → /server)
curl -sI http://127.0.0.1:8804/ | head -1
# Should be unreachable from any other interface
curl -sI --max-time 3 http://<host-public-ip>:8804/ | head -1   # expect timeout / no route
```

## Why not ship the whole config.yml?

Plan's `config.yml` is ~3 KB of timezone, theme, extension, retention, and
proxy knobs that have nothing to do with security and change between Plan
versions. Tracking the whole file means rebasing it every Plan bump.
Tracking just the one critical setting (this README) keeps the security
contract stable across Plan versions.

If the Plan team ever changes the default to `127.0.0.1`, this whole step
becomes a no-op — the override still works, and the README documents why
the line is there.

## Future

If we ever need more Plan settings tracked (theme branding, server name,
retention), prefer a thin overlay file pattern (small YAML with just the
overrides, applied via a script at boot) over committing the whole
generated config.
