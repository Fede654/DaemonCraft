# Perception Primitive JSON Contract

> DC-DEP-3 / HRM-119 — Gateway consumption schema
>
> The bot server produces a **perception snapshot** on every heartbeat.
> The Hermes gateway (Python) consumes this JSON directly — no Mineflayer
> dependencies on the gateway side.

## Top-level schema (`PerceptionSnapshot`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "PerceptionSnapshot",
  "type": "object",
  "required": ["summary", "visible_blocks", "visible_entities", "hazards", "fair_play", "range"],
  "properties": {
    "summary": { "type": "string", "description": "Human-readable scene description." },
    "visible_blocks": {
      "type": "array",
      "items": { "$ref": "#/$defs/VisibleBlockSummary" }
    },
    "visible_block_hits": {
      "type": "array",
      "items": { "$ref": "#/$defs/BlockHit" }
    },
    "visible_entities": {
      "type": "array",
      "items": { "$ref": "#/$defs/VisibleEntity" }
    },
    "hazards": {
      "type": "array",
      "items": { "type": "string" }
    },
    "looking_at": {
      "oneOf": [
        { "$ref": "#/$defs/LookingAt" },
        { "type": "null" }
      ]
    },
    "sounds": {
      "type": "array",
      "items": { "$ref": "#/$defs/SoundEvent" }
    },
    "memory_hints": {
      "type": "array",
      "items": { "type": "string" }
    },
    "fair_play": { "type": "boolean", "description": "Whether LOS / range filtering was applied." },
    "range": { "type": "number", "description": "Scan radius in blocks." }
  },
  "$defs": {
    "VisibleBlockSummary": {
      "type": "object",
      "required": ["name", "count", "nearest_distance", "sectors"],
      "properties": {
        "name": { "type": "string" },
        "count": { "type": "integer", "minimum": 1 },
        "nearest_distance": { "type": "number" },
        "sectors": {
          "type": "array",
          "items": { "enum": ["left", "center", "right"] }
        }
      }
    },
    "BlockHit": {
      "type": "object",
      "required": ["name", "position", "distance", "bearing", "sector"],
      "properties": {
        "name": { "type": "string" },
        "position": { "$ref": "#/$defs/Vec3" },
        "distance": { "type": "number" },
        "bearing": { "type": "string" },
        "sector": { "enum": ["left", "center", "right"] }
      }
    },
    "VisibleEntity": {
      "type": "object",
      "required": ["type", "distance", "bearing", "kind"],
      "properties": {
        "type": { "type": "string", "description": "username, mob name, or 'unknown'" },
        "distance": { "type": "number" },
        "bearing": { "type": "string" },
        "kind": { "enum": ["player", "mob", "object", "other"] },
        "health": { "type": "number" }
      }
    },
    "LookingAt": {
      "type": "object",
      "required": ["name", "position"],
      "properties": {
        "name": { "type": "string" },
        "position": { "$ref": "#/$defs/Vec3" }
      }
    },
    "SoundEvent": {
      "type": "object",
      "required": ["time", "type", "direction", "distance", "approximate"],
      "properties": {
        "time": { "type": "integer", "description": "Unix epoch ms" },
        "type": { "enum": ["mining", "sprinting", "walking", "combat", "explosion"] },
        "direction": { "type": "string" },
        "distance": { "type": "number" },
        "approximate": { "type": "boolean" }
      }
    },
    "Vec3": {
      "type": "object",
      "required": ["x", "y", "z"],
      "properties": {
        "x": { "type": "number" },
        "y": { "type": "number" },
        "z": { "type": "number" }
      }
    }
  }
}
```

## Example snapshot

```json
{
  "summary": "Looking at oak_log. Visible blocks: oak_log 4.2m left, stone 2.1m center. Visible entities: Alex 6m north. Hazards: lava right 5m. Unknown areas remain hidden behind terrain and outside the current view cone.",
  "visible_blocks": [
    { "name": "oak_log", "count": 2, "nearest_distance": 4.2, "sectors": ["left", "center"] }
  ],
  "visible_block_hits": [
    { "name": "oak_log", "position": { "x": 10, "y": 64, "z": 5 }, "distance": 4.2, "bearing": "northeast", "sector": "left" }
  ],
  "visible_entities": [
    { "type": "Alex", "distance": 6, "bearing": "north", "kind": "player" }
  ],
  "hazards": ["lava right 5m"],
  "looking_at": { "name": "oak_log", "position": { "x": 10, "y": 64, "z": 5 } },
  "sounds": [
    { "time": 1715600000000, "type": "mining", "direction": "east", "distance": 8, "approximate": true }
  ],
  "memory_hints": ["furnace behind you 6m (120s ago)"],
  "fair_play": true,
  "range": 16
}
```

## Gateway consumption notes

1. **The gateway never calls Mineflayer APIs.** It receives the snapshot via
   `POST /heartbeat/context` (see `agent_loop.py`).
2. **All distances are in blocks** and rounded to one decimal place.
3. **Bearings** are cardinal/inter-cardinal strings (`north`, `northeast`, ...).
4. **Sectors** are relative to the bot's facing direction: `left`, `center`, `right`.
5. **Sound events** are ephemeral (30 s TTL, max 20 stored). The gateway should
   treat them as "heard within the last 30 seconds".
6. **If `fair_play` is `true`**, the gateway can trust that entities/blocks were
   filtered by LOS and range. If `false`, the bot is in god-mode perception.

## Adapter wiring

| Layer | File | Role |
|-------|------|------|
| Core | `lib/perception/core.js` | Pure functions, no env deps |
| Minecraft adapter | `lib/perception/adapters/minecraft.js` | Reads live `bot.*` APIs |
| Fake adapter | `lib/perception/adapters/fake.js` | Deterministic in-memory grid |
| Legacy shim | `lib/perception.js` | Re-exports core for old imports |
