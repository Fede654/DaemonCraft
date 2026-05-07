/**
 * Perception Core — Environment-agnostic perception primitives
 *
 * DC-DEP-3 / HRM-119: Extracted from server.js + perception.js
 * No Mineflayer dependencies. Pure functions only.
 */

// ═══════════════════════════════════════════════════════════════════
// Math utilities
// ═══════════════════════════════════════════════════════════════════

export function angleDiffDegrees(a, b) {
  let diff = ((a - b + 540) % 360) - 180;
  if (diff < -180) diff += 360;
  return diff;
}

export function normalizeDegrees(angle) {
  return ((angle % 360) + 360) % 360;
}

export function yawPitchToDir(yaw, pitch = 0) {
  const cy = Math.cos(yaw);
  const sy = Math.sin(yaw);
  const cp = Math.cos(pitch);
  const sp = Math.sin(pitch);
  return {
    x: -sy * cp,
    y: sp,
    z: -cy * cp,
  };
}

export function bearingFromDelta(dx, dz) {
  const angle = normalizeDegrees((Math.atan2(dx, -dz) * 180) / Math.PI);
  if (angle >= 337.5 || angle < 22.5) return 'north';
  if (angle < 67.5) return 'northeast';
  if (angle < 112.5) return 'east';
  if (angle < 157.5) return 'southeast';
  if (angle < 202.5) return 'south';
  if (angle < 247.5) return 'southwest';
  if (angle < 292.5) return 'west';
  return 'northwest';
}

export function classifySector(relativeAngle) {
  if (relativeAngle < -35) return 'left';
  if (relativeAngle > 35) return 'right';
  return 'center';
}

// ═══════════════════════════════════════════════════════════════════
// Memory key
// ═══════════════════════════════════════════════════════════════════

export function makeBlockMemoryKey(position, name) {
  return `${name}@${Math.round(position.x)},${Math.round(position.y)},${Math.round(position.z)}`;
}

// ═══════════════════════════════════════════════════════════════════
// LOS (Line of Sight) — environment-agnostic
// ═══════════════════════════════════════════════════════════════════

/**
 * Check whether `observer` has unobstructed line-of-sight to `target`.
 *
 * @param {{x:number,y:number,z:number}} observer — world position (eyes)
 * @param {{x:number,y:number,z:number}} target   — world position
 * @param {{blockAt:({x:number,y:number,z:number})=>{boundingBox?:string,name?:string}|null|null}} env
 * @returns {boolean}
 */
export function canSee(observer, target, env) {
  const dx = target.x - observer.x;
  const dy = target.y - observer.y;
  const dz = target.z - observer.z;
  const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);
  if (dist < 1) return true;
  const steps = Math.ceil(dist * 2); // check every 0.5 blocks
  for (let i = 1; i < steps; i++) {
    const t = i / steps;
    const x = observer.x + dx * t;
    const y = observer.y + dy * t;
    const z = observer.z + dz * t;
    const block = env.blockAt({ x: Math.floor(x), y: Math.floor(y), z: Math.floor(z) });
    if (block && block.boundingBox === 'block') return false;
  }
  return true;
}

// ═══════════════════════════════════════════════════════════════════
// Raycasting — environment-agnostic
// ═══════════════════════════════════════════════════════════════════

/**
 * Cast a ray from `origin` along `direction` until a solid block is hit.
 *
 * @param {{x:number,y:number,z:number}} origin
 * @param {{x:number,y:number,z:number}} direction — unit vector
 * @param {{blockAt:({x:number,y:number,z:number})=>{boundingBox?:string,name?:string}|null|null}} env
 * @param {number} [maxDistance=16]
 * @param {number} [step=0.75]
 * @returns {{block:{name:string,position:{x:number,y:number,z:number}},distance:number}|null}
 */
export function raycastFirstSolid(origin, direction, env, maxDistance = 16, step = 0.75) {
  for (let distance = step; distance <= maxDistance; distance += step) {
    const sample = {
      x: origin.x + direction.x * distance,
      y: origin.y + direction.y * distance,
      z: origin.z + direction.z * distance,
    };
    const block = env.blockAt({ x: Math.floor(sample.x), y: Math.floor(sample.y), z: Math.floor(sample.z) });
    if (block && block.boundingBox === 'block' && block.name !== 'air' && block.name !== 'cave_air') {
      // Ensure position is present (test-fake adapters may omit it)
      if (!block.position) {
        block.position = { x: Math.floor(sample.x), y: Math.floor(sample.y), z: Math.floor(sample.z) };
      }
      return { block, distance };
    }
  }
  return null;
}

// ═══════════════════════════════════════════════════════════════════
// Entity detection — environment-agnostic
// ═══════════════════════════════════════════════════════════════════

/**
 * Determine whether an entity can be detected under fair-play rules.
 *
 * @param {object} params
 * @param {{x:number,y:number,z:number,yaw?:number,pitch?:number,height?:number}} params.observer
 * @param {{x:number,y:number,z:number,height?:number,metadata?:any,crouching?:boolean,pose?:string}} params.target
 * @param {{blockAt:Function}} params.env
 * @param {{fairPlay?:boolean,losEntityRange?:number,sneakDetectRange?:number}} [params.rules]
 * @returns {boolean}
 */
export function canDetectEntity({ observer, target, env, rules = {} }) {
  const {
    fairPlay = true,
    losEntityRange = 48,
    sneakDetectRange = 8,
  } = rules;

  if (!fairPlay) return true;

  const dx = target.x - observer.x;
  const dy = target.y - observer.y;
  const dz = target.z - observer.z;
  const dist = Math.sqrt(dx * dx + dy * dy + dz * dz);

  // Always detect within 3 blocks (melee / audible range)
  if (dist < 3) return true;

  // Sneaking entities: much shorter detection range
  const isSneaking = target.metadata?.[6] === 5 || target.crouching || target.pose === 'sneaking';
  if (isSneaking && dist > sneakDetectRange) return false;

  // Beyond max range: invisible
  if (dist > losEntityRange) return false;

  // LOS check: raycast from observer eyes to entity center
  const eyeHeight = (observer.height || 1.62) * 0.85;
  const eyePos = { x: observer.x, y: observer.y + eyeHeight, z: observer.z };
  const targetCenter = {
    x: target.x,
    y: target.y + (target.height || 1.8) * 0.5,
    z: target.z,
  };

  return canSee(eyePos, targetCenter, env);
}

// ═══════════════════════════════════════════════════════════════════
// Block scanning — environment-agnostic
// ═══════════════════════════════════════════════════════════════════

/**
 * Scan for visible blocks using a ray-grid from the observer's viewpoint.
 *
 * @param {object} params
 * @param {{x:number,y:number,z:number,yaw?:number,pitch?:number,height?:number}} params.observer
 * @param {{blockAt:Function}} params.env
 * @param {number} [params.range=16]
 * @param {number} [params.horizontalFov=100]
 * @param {number} [params.verticalFov=36]
 * @param {number} [params.horizontalRays=7]
 * @param {number} [params.verticalRays=3]
 * @returns {Array<{name:string,position:{x:number,y:number,z:number},distance:number,bearing:string,sector:string}>}
 */
export function scanVisibleBlocks({
  observer,
  env,
  range = 16,
  horizontalFov = 100,
  verticalFov = 36,
  horizontalRays = 7,
  verticalRays = 3,
}) {
  const origin = {
    x: observer.x,
    y: observer.y + (observer.height || 1.62) * 0.85,
    z: observer.z,
  };
  const hits = [];
  const seen = new Set();
  const baseYawDeg = observer.yaw !== undefined ? (observer.yaw * 180) / Math.PI : 0;
  const basePitchDeg = observer.pitch !== undefined ? (observer.pitch * 180) / Math.PI : 0;

  for (let yi = 0; yi < verticalRays; yi++) {
    const pitchOffset = verticalRays === 1 ? 0 : -verticalFov / 2 + (verticalFov * yi) / (verticalRays - 1);
    for (let xi = 0; xi < horizontalRays; xi++) {
      const yawOffset = horizontalRays === 1 ? 0 : -horizontalFov / 2 + (horizontalFov * xi) / (horizontalRays - 1);
      const yaw = ((baseYawDeg + yawOffset) * Math.PI) / 180;
      const pitch = ((basePitchDeg + pitchOffset) * Math.PI) / 180;
      const hit = raycastFirstSolid(origin, yawPitchToDir(yaw, pitch), env, range);
      if (!hit) continue;
      const key = `${hit.block.name}@${hit.block.position.x},${hit.block.position.y},${hit.block.position.z}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const dx = hit.block.position.x - observer.x;
      const dz = hit.block.position.z - observer.z;
      const bearing = bearingFromDelta(dx, dz);
      const relativeAngle = angleDiffDegrees(baseYawDeg, (Math.atan2(dx, -dz) * 180) / Math.PI);
      const sector = classifySector(relativeAngle);
      hits.push({
        name: hit.block.name,
        position: { x: hit.block.position.x, y: hit.block.position.y, z: hit.block.position.z },
        distance: Math.round(hit.distance * 10) / 10,
        bearing,
        sector,
      });
    }
  }

  return hits.sort((a, b) => a.distance - b.distance);
}

// ═══════════════════════════════════════════════════════════════════
// Hazard detection
// ═══════════════════════════════════════════════════════════════════

const HAZARD_BLOCK_NAMES = new Set(['lava', 'flowing_lava', 'fire', 'campfire']);

/**
 * Extract hazard descriptions from visible block hits.
 *
 * @param {Array<{name:string,sector:string,distance:number}>} blocks
 * @returns {string[]}
 */
export function detectHazardsFromVisibleBlocks(blocks) {
  return blocks
    .filter((block) => HAZARD_BLOCK_NAMES.has(block.name))
    .slice(0, 5)
    .map((block) => `${block.name} ${block.sector} ${block.distance}m`);
}

// ═══════════════════════════════════════════════════════════════════
// Sound inference
// ═══════════════════════════════════════════════════════════════════

const SOUND_TYPE_WEIGHTS = {
  mining: 1.0,
  sprinting: 0.8,
  walking: 0.4,
  combat: 0.9,
  explosion: 1.0,
};

/**
 * Infer a probable source description from a sound event + history.
 *
 * @param {{type:string,direction?:string,distance?:number,approximate?:boolean,time?:number}} soundEvent
 * @param {Array} history — prior sound events
 * @returns {{type:string,confidence:number,description:string,possibleSources?:string[]}}
 */
export function inferSource(soundEvent, history = []) {
  const weight = SOUND_TYPE_WEIGHTS[soundEvent.type] || 0.5;
  const similar = history.filter(
    (e) =>
      e.type === soundEvent.type &&
      e.direction === soundEvent.direction &&
      soundEvent.time != null &&
      e.time != null &&
      Math.abs(e.time - soundEvent.time) < 5000
  );
  const confidence = Math.min(0.3 + weight * 0.5 + similar.length * 0.1, 0.95);

  const descriptions = {
    mining: 'Someone is mining nearby',
    sprinting: 'Something is sprinting',
    walking: 'Footsteps nearby',
    combat: 'Combat sounds',
    explosion: 'An explosion occurred',
  };

  return {
    type: soundEvent.type,
    confidence,
    description: descriptions[soundEvent.type] || `Unknown sound: ${soundEvent.type}`,
    possibleSources: similar.length > 0 ? ['player', 'mob'] : undefined,
  };
}

// ═══════════════════════════════════════════════════════════════════
// Summarization (moved from legacy perception.js)
// ═══════════════════════════════════════════════════════════════════

export function summarizeVisibleBlocks(blocks, limit = 8) {
  const grouped = new Map();
  for (const block of blocks) {
    const current = grouped.get(block.name) || { name: block.name, count: 0, nearestDistance: Infinity, sectors: new Set() };
    current.count += 1;
    current.nearestDistance = Math.min(current.nearestDistance, block.distance);
    current.sectors.add(block.sectors || block.sector);
    grouped.set(block.name, current);
  }

  return [...grouped.values()]
    .sort((a, b) => a.nearestDistance - b.nearestDistance)
    .slice(0, limit)
    .map((entry) => ({
      name: entry.name,
      count: entry.count,
      nearest_distance: Math.round(entry.nearestDistance * 10) / 10,
      sectors: [...entry.sectors],
    }));
}

export function summarizeSceneText({ lookingAt, visibleBlocks = [], visibleEntities = [], hazards = [], sounds = [], memoryHints = [] }) {
  const parts = [];

  if (lookingAt?.name) {
    parts.push(`Looking at ${lookingAt.name}.`);
  }

  const blockSummary = summarizeVisibleBlocks(visibleBlocks, 6);
  if (blockSummary.length > 0) {
    const blocksText = blockSummary
      .map((entry) => `${entry.name} ${entry.nearest_distance}m ${entry.sectors.join('/')}`)
      .join(', ');
    parts.push(`Visible blocks: ${blocksText}.`);
  } else {
    parts.push('No notable visible blocks in view.');
  }

  if (visibleEntities.length > 0) {
    const entText = visibleEntities
      .slice(0, 5)
      .map((entity) => `${entity.type} ${entity.distance}m ${entity.bearing}`)
      .join(', ');
    parts.push(`Visible entities: ${entText}.`);
  }

  if (hazards.length > 0) {
    parts.push(`Hazards: ${hazards.slice(0, 5).join(', ')}.`);
  }

  if (sounds.length > 0) {
    const soundText = sounds.slice(-3).map((sound) => `${sound.type} ${sound.direction} ${sound.distance}`).join(', ');
    parts.push(`Recent sounds: ${soundText}.`);
  }

  if (memoryHints.length > 0) {
    parts.push(`Remembered nearby: ${memoryHints.slice(0, 4).join(', ')}.`);
  }

  parts.push('Unknown areas remain hidden behind terrain and outside the current view cone.');
  return parts.join(' ');
}

// ═══════════════════════════════════════════════════════════════════
// Scene rendering — top-level primitive
// ═══════════════════════════════════════════════════════════════════

/**
 * Render a structured scene + text summary from a perception buffer.
 *
 * @param {object} perceptionBuffer
 * @param {object} [memory]
 * @param {Array} [memory.observedBlocks] — {name,position,distance,bearing,lastSeen}
 * @param {Array} [memory.soundHistory]
 * @returns {{summary:string,structured:object}}
 */
export function renderScene(perceptionBuffer, memory = {}) {
  const {
    lookingAt = null,
    visibleBlocks = [],
    visibleEntities = [],
    hazards = [],
    sounds = [],
    memoryHints = [],
    fairPlay = false,
    range = 16,
  } = perceptionBuffer;

  const summary = summarizeSceneText({
    lookingAt,
    visibleBlocks,
    visibleEntities,
    hazards,
    sounds,
    memoryHints,
  });

  const structured = {
    summary,
    visible_blocks: summarizeVisibleBlocks(visibleBlocks),
    visible_block_hits: visibleBlocks,
    visible_entities: visibleEntities,
    hazards,
    looking_at: lookingAt,
    sounds,
    memory_hints: memoryHints,
    fair_play: fairPlay,
    range,
  };

  return { summary, structured };
}
