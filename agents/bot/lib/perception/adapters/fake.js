/**
 * Fake (Test) Perception Adapter
 *
 * Deterministic, in-memory adapter for unit-testing perception scenarios
 * without a Mineflayer bot. Uses a simple 3-D grid of block names.
 */

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
} from '../core.js';

const DEFAULT_RULES = {
  fairPlay: true,
  losEntityRange: 48,
  sneakDetectRange: 8,
  soundMineRadius: 16,
  soundSprintRadius: 8,
  soundWalkRadius: 4,
  soundSneakRadius: 1,
  blockScanRange: 16,
};

/**
 * @param {object} [options]
 * @param {Map<string,{name:string,boundingBox?:string}>} [options.grid] — key="x,y,z"
 * @param {object} [options.rules]
 * @returns {object}
 */
export function createFakePerceptionAdapter(options = {}) {
  const grid = options.grid ?? new Map();
  const rules = { ...DEFAULT_RULES, ...options.rules };

  let soundEvents = [];
  let observedBlocks = new Map();

  // Internal env backed by the grid
  function makeEnv() {
    return {
      blockAt: ({ x, y, z }) => {
        const key = `${x},${y},${z}`;
        if (grid.has(key)) return grid.get(key);
        // Default to air / void
        return { name: 'air', boundingBox: 'empty' };
      },
    };
  }

  function fmt(n) {
    return Math.round(n * 10) / 10;
  }

  return {
    // ───────────────────────────────────────────────────────────────────
    // Grid manipulation (test helpers)
    // ───────────────────────────────────────────────────────────────────

    setBlock(x, y, z, name, boundingBox = 'block') {
      grid.set(`${x},${y},${z}`, { name, boundingBox });
    },

    removeBlock(x, y, z) {
      grid.delete(`${x},${y},${z}`);
    },

    clearGrid() {
      grid.clear();
    },

    getGrid() {
      return new Map(grid);
    },

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

    canDetectEntity(observer, target) {
      return canDetectEntity({ observer, target, env: makeEnv(), rules });
    },

    scanEntities(observer, entities, { range = rules.blockScanRange, maxCount = 8 } = {}) {
      const raw = entities
        .filter((e) => {
          const dx = e.x - observer.x;
          const dy = e.y - observer.y;
          const dz = e.z - observer.z;
          return Math.sqrt(dx * dx + dy * dy + dz * dz) <= Math.min(range + 8, 24);
        })
        .sort((a, c) => {
          const da = Math.sqrt((a.x - observer.x) ** 2 + (a.y - observer.y) ** 2 + (a.z - observer.z) ** 2);
          const dc = Math.sqrt((c.x - observer.x) ** 2 + (c.y - observer.y) ** 2 + (c.z - observer.z) ** 2);
          return da - dc;
        });

      const visible = rules.fairPlay
        ? raw.filter((e) => this.canDetectEntity(observer, e))
        : raw;

      return visible.slice(0, maxCount).map((entity) => {
        const dx = entity.x - observer.x;
        const dy = entity.y - observer.y;
        const dz = entity.z - observer.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
        return {
          type: entity.username || entity.name || 'unknown',
          distance: fmt(dist),
          bearing: bearingFromDelta(dx, dz),
          kind: entity.kind || (entity.username ? 'player' : 'mob'),
          health: entity.health ?? undefined,
        };
      });
    },

    // ───────────────────────────────────────────────────────────────────
    // Block scanning
    // ───────────────────────────────────────────────────────────────────

    scanBlocks(observer, opts = {}) {
      const scanOpts = rules.fairPlay
        ? { observer, env: makeEnv(), range: opts.range ?? rules.blockScanRange }
        : {
            observer,
            env: makeEnv(),
            range: Math.min(opts.range ?? rules.blockScanRange, 24),
            horizontalFov: 140,
            verticalFov: 50,
            horizontalRays: 9,
            verticalRays: 4,
          };
      const hits = scanVisibleBlocks(scanOpts);
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

    findVisibleBlocksByName(observer, blockName, { range = rules.blockScanRange, count = 10 } = {}) {
      const needle = String(blockName || '').toLowerCase();
      return this.scanBlocks(observer, { range }).filter((entry) => entry.name.toLowerCase() === needle).slice(0, count);
    },

    // ───────────────────────────────────────────────────────────────────
    // Sound model
    // ───────────────────────────────────────────────────────────────────

    addSoundEvent(type, observerPosition, sourcePosition, radius) {
      const dx = sourcePosition.x - observerPosition.x;
      const dy = sourcePosition.y - observerPosition.y;
      const dz = sourcePosition.z - observerPosition.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
      if (dist > radius) return;
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
      soundEvents = soundEvents.filter((e) => Date.now() - e.time < 30000).slice(-20);
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

    buildScene(observer, { range = rules.blockScanRange, lookingAt = null, entities = [] } = {}) {
      const visibleBlocks = this.scanBlocks(observer, { range });
      const visibleEntities = this.scanEntities(observer, entities, { range });
      const hazards = detectHazardsFromVisibleBlocks(visibleBlocks);
      const sounds = soundEvents.slice(-5);
      const memoryHints = this.getMemoryHints();

      const { summary, structured } = renderScene(
        {
          lookingAt,
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
