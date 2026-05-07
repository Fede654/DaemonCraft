# Telegram <-> Minecraft Chat Bridge (MVP)

A standalone, stdlib-only Python service that forwards text messages
bidirectionally between a Minecraft server (via the HermesCraft bot HTTP API)
and a Telegram chat.

## Features

- **Bidirectional text forwarding** — MC chat → Telegram, Telegram → MC
- **Zero external dependencies** — runs on Python 3.8+ with only the standard library
- **Optional PyYAML support** — falls back to an inline minimal YAML parser
- **Deduplication & filtering** — ignores bot echo, configurable ignore-lists
- **Configurable formatting** — custom templates for both directions
- **Systemd ready** — includes service unit file

## Quick Start

### 1. Create a Telegram Bot

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Run `/newbot` and follow the prompts
3. Copy the bot token (looks like `123456789:ABCdef...`)
4. Add the bot to the group chat you want to bridge
5. Send a message in the group, then visit:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Look for `"chat":{"id":-1001234567890,...}` — that number is your `chat_id`.

### 2. Configure the Bridge

```bash
cp config/telegram-bridge.yaml.example config/telegram-bridge.yaml
nano config/telegram-bridge.yaml
```

Fill in at least:

```yaml
telegram:
  bot_token: "YOUR_BOT_TOKEN"
  chat_id: "-100YOUR_CHAT_ID"
```

### 3. Run the Bridge

```bash
# Ensure the HermesCraft bot API is running (default port 3001)
python3 scripts/telegram-bridge.py
```

For verbose debug output:

```bash
python3 scripts/telegram-bridge.py -v
```

### 4. Install as Systemd Service

```bash
sudo cp systemd/daemoncraft-telegram-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now daemoncraft-telegram-bridge
sudo journalctl -u daemoncraft-telegram-bridge -f
```

## Architecture

```
+-----------+      GET /chat      +------------------+      Telegram Bot API      +-----------+
| Minecraft | <------------------ | telegram-bridge  | <------------------------> | Telegram  |
|  Server   |     POST /chat/send |     .py          |      getUpdates/sendMessage|   Chat    |
+-----------+                     +------------------+                            +-----------+
```

- **MC → TG**: polls `GET /chat?count=50` every 2 s, skips `self: true` messages,
  forwards new entries to Telegram via `sendMessage`.
- **TG → MC**: polls `getUpdates` every 2 s, skips bot messages, forwards new
  text messages to Minecraft via `POST /chat/send`.

## Configuration Reference

| Key | Default | Description |
|-----|---------|-------------|
| `telegram.bot_token` | *required* | Telegram Bot API token |
| `telegram.chat_id` | *required* | Target chat ID (group or user) |
| `minecraft.api_url` | `http://localhost:3001` | HermesCraft bot HTTP API |
| `minecraft.bot_username` | `HermesBot` | MC bot username (auto-filtered) |
| `minecraft.poll_interval` | `2.0` | Poll interval in seconds |
| `bridge.mc_to_tg_format` | `[{world}] <{sender}> {message}` | MC → TG message template |
| `bridge.tg_to_mc_format` | `[TG] {sender}: {message}` | TG → MC message template |
| `bridge.ignore_mc_users` | `HermesBot` | Comma-separated MC usernames to skip |
| `bridge.ignore_tg_users` | *(empty)* | Comma-separated Telegram usernames to skip |
| `bridge.ignore_tg_bots` | `true` | Drop messages from Telegram bots |
| `bridge.require_prefix` | *(empty)* | Only forward messages starting with this prefix |
| `bridge.max_length` | `1000` | Truncate forwarded messages to this length |
| `bridge.dedup_window` | `200` | In-memory dedup window size for MC messages |

## Message Flow Examples

**Player in Minecraft:**
```
<Steve> Hello from the overworld!
```
**Appears in Telegram:**
```
[overworld] <Steve> Hello from the overworld!
```

**User in Telegram:**
```
@alice: Hey everyone!
```
**Appears in Minecraft:**
```
[TG] alice: Hey everyone!
```

## Known Limitations (MVP)

- Text only — no media, commands, or rich formatting
- One Telegram chat per bridge instance
- MC messages are polled via HTTP (not WebSocket) to keep dependencies at zero
- Telegram `getUpdates` long-polling is used; webhooks are not supported yet
- No persistent message history — deduplication is in-memory only

## Troubleshooting

**"MC health check failed"**
- Ensure the HermesCraft bot server is running (`node agents/bot/server.js`)
- Check that `minecraft.api_url` matches the bot's HTTP port (default 3001)

**"TG bot check failed"**
- Verify the token with: `curl https://api.telegram.org/bot<TOKEN>/getMe`
- Ensure the bot is added to the target group chat

**Messages are not forwarding**
- Run with `-v` for DEBUG logs
- Check `ignore_mc_users` and `ignore_tg_users` filters
- Verify `chat_id` is correct (groups start with `-100`)
