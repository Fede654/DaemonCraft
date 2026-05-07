import test from 'node:test';
import assert from 'node:assert/strict';
import {
  angleDiffDegrees,
  normalizeDegrees,
  yawPitchToDir,
  bearingFromDelta,
  classifySector,
  makeBlockMemoryKey,
  canSee,
  raycastFirstSolid,
  canDetectEntity,
  scanVisibleBlocks,
  detectHazardsFromVisibleBlocks,
  inferSource,
  summarizeVisibleBlocks,
  summarizeSceneText,
  renderScene,
} from '../../lib/perception/core.js';

// ═══════════════════════════════════════════════════════════════════
// Math utilities
// ═══════════════════════════════════════════════════════════════════

test('angleDiffDegrees wraps across 360 cleanly', () => {
  assert.equal(angleDiffDegrees(10, 350), 20);
  assert.equal(angleDiffDegrees(350, 10), -20);
  assert.equal(angleDiffDegrees(0, 180), -180);
  assert.equal(angleDiffDegrees(180, 0), -180);
});

test('normalizeDegrees keeps angles in [0,360)', () => {
  assert.equal(normalizeDegrees(-10), 350);
  assert.equal(normalizeDegrees(370), 10);
  assert.equal(normalizeDegrees(0), 0);
});

test('yawPitchToDir produces unit-ish vectors', () => {
  const dir = yawPitchToDir(0, 0);
  assert.ok(Math.abs(dir.x) < 0.001);
  assert.ok(Math.abs(dir.z + 1) < 0.001);
});

test('bearingFromDelta returns cardinal labels', () => {
  assert.equal(bearingFromDelta(0, -10), 'north');
  assert.equal(bearingFromDelta(10, 0), 'east');
  assert.equal(bearingFromDelta(-10, 0), 'west');
  assert.equal(bearingFromDelta(0, 10), 'south');
});

test('classifySector buckets relative angles', () => {
  assert.equal(classifySector(-50), 'left');
  assert.equal(classifySector(0), 'center');
  assert.equal(classifySector(50), 'right');
});

test('makeBlockMemoryKey is stable and rounded', () => {
  assert.equal(makeBlockMemoryKey({ x: 10.4, y: 64.6, z: -2.2 }, 'oak_log'), 'oak_log@10,65,-2');
});

// ═══════════════════════════════════════════════════════════════════
// LOS & raycasting
// ═══════════════════════════════════════════════════════════════════

function makeFlatEnv(wallX = null) {
  return {
    blockAt: ({ x, y, z }) => {
      if (y < 0) return { name: 'bedrock', boundingBox: 'block' };
      if (wallX !== null && x === wallX) return { name: 'stone', boundingBox: 'block' };
      return { name: 'air', boundingBox: 'empty' };
    },
  };
}

test('canSee returns true when unobstructed', () => {
  const env = makeFlatEnv();
  assert.equal(canSee({ x: 0, y: 2, z: 0 }, { x: 5, y: 2, z: 0 }, env), true);
});

test('canSee returns false when wall blocks path', () => {
  const env = makeFlatEnv(3);
  assert.equal(canSee({ x: 0, y: 2, z: 0 }, { x: 5, y: 2, z: 0 }, env), false);
});

test('canSee returns true for very close targets', () => {
  const env = makeFlatEnv(3);
  assert.equal(canSee({ x: 0, y: 2, z: 0 }, { x: 0.5, y: 2, z: 0 }, env), true);
});

test('raycastFirstSolid hits a wall', () => {
  const env = makeFlatEnv(3);
  const hit = raycastFirstSolid({ x: 0, y: 2, z: 0 }, { x: 1, y: 0, z: 0 }, env, 10, 0.5);
  assert.ok(hit);
  assert.equal(hit.block.name, 'stone');
  assert.ok(hit.distance >= 2.5 && hit.distance <= 3.5);
});

test('raycastFirstSolid returns null in open air', () => {
  const env = makeFlatEnv();
  const hit = raycastFirstSolid({ x: 0, y: 2, z: 0 }, { x: 1, y: 0, z: 0 }, env, 10, 0.5);
  assert.equal(hit, null);
});

// ═══════════════════════════════════════════════════════════════════
// Entity detection
// ═══════════════════════════════════════════════════════════════════

test('canDetectEntity passes everything when fairPlay=false', () => {
  const env = makeFlatEnv();
  const observer = { x: 0, y: 2, z: 0 };
  const target = { x: 50, y: 2, z: 0 };
  assert.equal(canDetectEntity({ observer, target, env, rules: { fairPlay: false } }), true);
});

test('canDetectEntity detects melee range regardless of LOS', () => {
  const env = makeFlatEnv(1); // wall at x=1
  const observer = { x: 0, y: 2, z: 0 };
  const target = { x: 0.5, y: 2, z: 0 };
  assert.equal(canDetectEntity({ observer, target, env, rules: { fairPlay: true } }), true);
});

test('canDetectEntity rejects beyond losEntityRange', () => {
  const env = makeFlatEnv();
  const observer = { x: 0, y: 2, z: 0 };
  const target = { x: 60, y: 2, z: 0, height: 1.8 };
  assert.equal(canDetectEntity({ observer, target, env, rules: { fairPlay: true, losEntityRange: 48 } }), false);
});

test('canDetectEntity rejects sneaking beyond sneakDetectRange', () => {
  const env = makeFlatEnv();
  const observer = { x: 0, y: 2, z: 0 };
  const target = { x: 12, y: 2, z: 0, height: 1.8, pose: 'sneaking' };
  assert.equal(canDetectEntity({ observer, target, env, rules: { fairPlay: true, sneakDetectRange: 8 } }), false);
});

// ═══════════════════════════════════════════════════════════════════
// Block scanning
// ═══════════════════════════════════════════════════════════════════

test('scanVisibleBlocks finds a wall straight ahead', () => {
  const env = {
    blockAt: ({ x, y, z }) => {
      if (y < 0) return { name: 'bedrock', boundingBox: 'block' };
      if (z === 5) return { name: 'stone', boundingBox: 'block' };
      return { name: 'air', boundingBox: 'empty' };
    },
  };
  const observer = { x: 0, y: 2, z: 0, yaw: 0, pitch: 0, height: 1.62 };
  const hits = scanVisibleBlocks({ observer, env, range: 10, horizontalRays: 1, verticalRays: 1 });
  assert.equal(hits.length, 1);
  assert.equal(hits[0].name, 'stone');
  assert.ok(hits[0].distance >= 4 && hits[0].distance <= 6);
});

test('scanVisibleBlocks returns empty in open void', () => {
  const env = makeFlatEnv();
  const observer = { x: 0, y: 2, z: 0, yaw: 0, pitch: 0, height: 1.62 };
  const hits = scanVisibleBlocks({ observer, env, range: 5, horizontalRays: 3, verticalRays: 1 });
  assert.equal(hits.length, 0);
});

// ═══════════════════════════════════════════════════════════════════
// Hazards & sounds
// ═══════════════════════════════════════════════════════════════════

test('detectHazardsFromVisibleBlocks extracts lava and fire', () => {
  const blocks = [
    { name: 'lava', sector: 'right', distance: 3 },
    { name: 'stone', sector: 'center', distance: 2 },
    { name: 'fire', sector: 'left', distance: 1 },
  ];
  const hazards = detectHazardsFromVisibleBlocks(blocks);
  assert.equal(hazards.length, 2);
  assert.ok(hazards.some((h) => h.startsWith('lava')));
  assert.ok(hazards.some((h) => h.startsWith('fire')));
});

test('inferSource returns confidence for known sound type', () => {
  const result = inferSource({ type: 'mining', direction: 'east', distance: 8 }, []);
  assert.equal(result.type, 'mining');
  assert.ok(result.confidence > 0.5);
  assert.match(result.description, /mining/i);
});

test('inferSource boosts confidence with similar history', () => {
  const history = [
    { type: 'mining', direction: 'east', distance: 8, time: 1000 },
    { type: 'mining', direction: 'east', distance: 9, time: 2000 },
  ];
  const result = inferSource({ type: 'mining', direction: 'east', distance: 8, time: 3000 }, history);
  assert.ok(result.confidence > 0.7);
});

// ═══════════════════════════════════════════════════════════════════
// Summarization
// ═══════════════════════════════════════════════════════════════════

test('summarizeVisibleBlocks groups repeated block hits', () => {
  const summary = summarizeVisibleBlocks([
    { name: 'oak_log', distance: 4.2, sector: 'left' },
    { name: 'oak_log', distance: 6.1, sector: 'center' },
    { name: 'water', distance: 3.9, sector: 'right' },
  ]);

  assert.deepEqual(summary[0], {
    name: 'water',
    count: 1,
    nearest_distance: 3.9,
    sectors: ['right'],
  });

  assert.deepEqual(summary[1], {
    name: 'oak_log',
    count: 2,
    nearest_distance: 4.2,
    sectors: ['left', 'center'],
  });
});

test('summarizeSceneText mentions uncertainty and notable cues', () => {
  const text = summarizeSceneText({
    lookingAt: { name: 'oak_log' },
    visibleBlocks: [{ name: 'oak_log', distance: 4.2, sector: 'left' }],
    visibleEntities: [{ type: 'Alex', distance: 6, bearing: 'north' }],
    hazards: ['lava right 5m'],
    sounds: [{ type: 'mining', direction: 'east', distance: '8m' }],
    memoryHints: ['furnace behind you 6m'],
  });

  assert.match(text, /Looking at oak_log/);
  assert.match(text, /Visible entities: Alex 6m north/);
  assert.match(text, /Hazards: lava right 5m/);
  assert.match(text, /Unknown areas remain hidden/);
});

test('renderScene returns both summary and structured payload', () => {
  const result = renderScene({
    lookingAt: { name: 'stone', position: { x: 0, y: 64, z: 0 } },
    visibleBlocks: [{ name: 'stone', distance: 2, sector: 'center', bearing: 'north', position: { x: 0, y: 64, z: -2 } }],
    visibleEntities: [],
    hazards: [],
    sounds: [],
    memoryHints: [],
    fairPlay: true,
    range: 16,
  });

  assert.ok(typeof result.summary === 'string');
  assert.ok(result.structured);
  assert.equal(result.structured.fair_play, true);
  assert.equal(result.structured.range, 16);
  assert.equal(result.structured.visible_blocks.length, 1);
});
