/**
 * Minecraft Perception Adapter
 *
 * Wraps the environment-agnostic perception core around a Mineflayer bot.
 * Used by server.js to produce the /scene payload.
 */

import { Vec3 } from 'vec3';
import {
  canSee,
  canDetectEntity,
  raycastFirstSolid,
  scanVisibleBlocks,
  detectHazardsFromVisibleBlocks,
  renderScene,
  inferSource,
  bearingFromDelta,
  angleDiffDegrees,
  classifySector,
  makeBlockMemoryKey,
  yawPitchToDir,
} from '../core.js';

const DEFAULT_RULES = {
  fairPlay: false,
  losEntityRange: 48,
  sneakDetectRange: 8,
  soundMineRadius: 16,
  soundSprintRadius: 8,
  soundWalkRadius: 4,
  soundSneakRadius: 1,
  blockScanRange: 16,
};

/**
 * @param {import('mineflayer').Bot} bot
 * @param {object} [options]
 * @param {object} [options.rules] — fair-play constants
 * @param {number} [options.maxSoundEvents=20]
 * @param {number} [options.soundTtlMs=30000]
 * @returns {object}
 */
export function createMinecraftPerceptionAdapter(bot, options = {}) {
  const rules = { ...DEFAULT_RULES, ...options.rules };
  const maxSoundEvents = options.maxSoundEvents ?? 20;
  const soundTtlMs = options.soundTtlMs ?? 30000;

  let soundEvents = [];
  let observedBlocks = new Map();

  // Internal: build an env object from the live bot.
  function makeEnv() {
    return {
      blockAt: ({ x, y, z }) => bot.blockAt(new Vec3(x, y, z)),
    };
  }

  function observerState() {
    const pos = bot.entity.position;
    return {
      x: pos.x,
      y: pos.y,
      z: pos.z,
      yaw: bot.entity.yaw,
      pitch: bot.entity.pitch,
      height: bot.entity.height,
    };
  }

  function fmt(n) {
    return Math.round(n * 10) / 10;
  }

  function posObj(v) {
    return { x: v.x, y: v.y, z: v.z };
  }

  function eyePosition() {
    const pos = bot.entity.position;
    return { x: pos.x, y: pos.y + (bot.entity.height || 1.62) * 0.85, z: pos.z };
  }

  return {
    // ───────────────────────────────────────────────────────────────────
    // Configuration
    // ───────────────────────────────────────────────────────────────────

    getRules() {
      return { ...rules };
    },

    setRules(partial) {
      Object.assign(rules, partial);
    },

    // ───────────────────────────────────────────────────────────────────
    // LOS helpers
    // ───────────────────────────────────────────────────────────────────

    hasLineOfSight(from, to) {
      return canSee(from, to, makeEnv());
    },

    raycastFirstSolid(origin, direction, maxDistance, step) {
      return raycastFirstSolid(origin, direction, makeEnv(), maxDistance, step);
    },

    // ───────────────────────────────────────────────────────────────────
    // Entity scanning
    // ───────────────────────────────────────────────────────────────────

    canDetectEntity(entity) {
      const obs = observerState();
      const target = {
        x: entity.position.x,
        y: entity.position.y,
        z: entity.position.z,
        height: entity.height,
        metadata: entity.metadata,
        crouching: entity.crouching,
        pose: entity.pose,
      };
      return canDetectEntity({ observer: obs, target, env: makeEnv(), rules });
    },

    scanEntities({ range = rules.blockScanRange, maxCount = 8 } = {}) {
      const pos = bot.entity.position;
      const raw = Object.values(bot.entities || {})
        .filter((e) => e !== bot.entity && e.position.distanceTo(pos) <= Math.min(range + 8, 24))
        .sort((a, c) => a.position.distanceTo(pos) - c.position.distanceTo(pos));

      const visible = rules.fairPlay
        ? raw.filter((e) => this.canDetectEntity(e))
        : raw;

      return visible.slice(0, maxCount).map((entity) => {
        const dist = entity.position.distanceTo(pos);
        return {
          type: entity.username || entity.name || entity.displayName || 'unknown',
          distance: fmt(dist),
          bearing: bearingFromDelta(entity.position.x - pos.x, entity.position.z - pos.z),
          kind: entity.type || (entity.username ? 'player' : 'mob'),
          health: entity.health ?? undefined,
        };
      });
    },

    // ───────────────────────────────────────────────────────────────────
    // Block scanning
    // ───────────────────────────────────────────────────────────────────

    scanBlocks(opts = {}) {
      const obs = observerState();
      const scanOpts = rules.fairPlay
        ? { observer: obs, env: makeEnv(), range: opts.range ?? rules.blockScanRange }
        : {
            observer: obs,
            env: makeEnv(),
            range: Math.min(opts.range ?? rules.blockScanRange, 24),
            horizontalFov: 140,
            verticalFov: 50,
            horizontalRays: 9,
            verticalRays: 4,
          };
      const hits = scanVisibleBlocks(scanOpts);
      // Persist to observed-block memory
      for (const entry of hits) {
        observedBlocks.set(makeBlockMemoryKey(entry.position, entry.name), {
          ...entry,
          lastSeen: Date.now(),
        });
      }
      if (observedBlocks.size > 200) {
        const oldest = [...observedBlocks.entries()]
          .sort((a, b) => a[1].lastSeen - b[1].lastSeen)
          .slice(0, observedBlocks.size - 200);
        oldest.forEach(([key]) => observedBlocks.delete(key));
      }
      return hits;
    },

    findVisibleBlocksByName(blockName, { range = rules.blockScanRange, count = 10 } = {}) {
      const needle = String(blockName || '').toLowerCase();
      return this.scanBlocks({ range }).filter((entry) => entry.name.toLowerCase() === needle).slice(0, count);
    },

    // ───────────────────────────────────────────────────────────────────
    // Sound model
    // ───────────────────────────────────────────────────────────────────

    addSoundEvent(type, position, radius) {
      const pos = bot.entity.position;
      const dist = pos.distanceTo(position);
      if (dist > radius) return;
      const dx = position.x - pos.x;
      const dz = position.z - pos.z;
      const angle = Math.atan2(dz, dx) * 180 / Math.PI;
      let dir;
      if (angle > -22.5 && angle <= 22.5) dir = 'east';
      else if (angle > 22.5 && angle <= 67.5) dir = 'southeast';
      else if (angle > 67.5 && angle <= 112.5) dir = 'south';
      else if (angle > 112.5 && angle <= 157.5) dir = 'southwest';
      else if (angle > 157.5 || angle <= -157.5) dir = 'west';
      else if (angle > -157.5 && angle <= -112.5) dir = 'northwest';
      else if (angle > -112.5 && angle <= -67.5) dir = 'north';
      else dir = 'northeast';

      soundEvents.push({
        time: Date.now(),
        type,
        direction: dir,
        distance: fmt(dist),
        approximate: true,
      });
      soundEvents = soundEvents.filter((e) => Date.now() - e.time < soundTtlMs).slice(-maxSoundEvents);
    },

    getSoundEvents() {
      return soundEvents.slice();
    },

    inferSoundSource(soundEvent) {
      return inferSource(soundEvent, soundEvents);
    },

    clearSoundEvents() {
      soundEvents = [];
    },

    // ───────────────────────────────────────────────────────────────────
    // Memory
    // ───────────────────────────────────────────────────────────────────

    getMemoryHints(limit = 4) {
      return [...observedBlocks.values()]
        .sort((a, b) => b.lastSeen - a.lastSeen)
        .slice(0, limit)
        .map((entry) => `${entry.name} ${entry.bearing} ${entry.distance}m (${Math.round((Date.now() - entry.lastSeen) / 1000)}s ago)`);
    },

    getObservedBlocks() {
      return new Map(observedBlocks);
    },

    // ───────────────────────────────────────────────────────────────────
    // Scene composition
    // ───────────────────────────────────────────────────────────────────

    buildScene({ range = rules.blockScanRange } = {}) {
      const visibleBlocks = this.scanBlocks({ range });
      const visibleEntities = this.scanEntities({ range });
      const lookingAtBlock = bot.blockAtCursor?.(5);
      const hazards = detectHazardsFromVisibleBlocks(visibleBlocks);
      const sounds = soundEvents.slice(-5);
      const memoryHints = this.getMemoryHints();

      const { summary, structured } = renderScene(
        {
          lookingAt: lookingAtBlock
            ? { name: lookingAtBlock.name, position: posObj(lookingAtBlock.position) }
            : null,
          visibleBlocks,
          visibleEntities,
          hazards,
          sounds,
          memoryHints,
          fairPlay: rules.fairPlay,
          range,
        },
        { observedBlocks: [...observedBlocks.values()], soundHistory: soundEvents }
      );

      return {
        summary,
        ...structured,
      };
    },
  };
}
