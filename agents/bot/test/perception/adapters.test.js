import test from 'node:test';
import assert from 'node:assert/strict';
import { createMinecraftPerceptionAdapter } from '../../lib/perception/adapters/minecraft.js';
import { createFakePerceptionAdapter } from '../../lib/perception/adapters/fake.js';

// ═══════════════════════════════════════════════════════════════════
// Shared scenario data
// ═══════════════════════════════════════════════════════════════════

function buildSimpleGrid() {
  const adapter = createFakePerceptionAdapter();
  // Floor at y=63, wall at z=5
  for (let x = -4; x <= 4; x++) {
    adapter.setBlock(x, 63, 5, 'stone');
  }
  // A tree
  adapter.setBlock(2, 64, 3, 'oak_log');
  adapter.setBlock(2, 65, 3, 'oak_log');
  // Lava hazard
  adapter.setBlock(-2, 64, 4, 'lava');
  return adapter;
}

const SHARED_OBSERVER = { x: 0, y: 64, z: 0, yaw: 0, pitch: 0, height: 1.62 };

// ═══════════════════════════════════════════════════════════════════
// Fake adapter tests
// ═══════════════════════════════════════════════════════════════════

test('fake adapter: scanBlocks finds wall and tree', () => {
  const adapter = buildSimpleGrid();
  const hits = adapter.scanBlocks(SHARED_OBSERVER, { range: 10, horizontalRays: 5, verticalRays: 1 });
  const names = hits.map((h) => h.name);
  assert.ok(names.includes('stone'), 'expected stone wall');
  assert.ok(names.includes('oak_log'), 'expected oak_log tree');
});

test('fake adapter: findVisibleBlocksByName filters correctly', () => {
  const adapter = buildSimpleGrid();
  const logs = adapter.findVisibleBlocksByName(SHARED_OBSERVER, 'oak_log', { range: 10 });
  assert.equal(logs.length, 1);
  assert.equal(logs[0].name, 'oak_log');
});

test('fake adapter: canDetectEntity respects LOS and range', () => {
  const adapter = createFakePerceptionAdapter();
  // Open air
  const observer = { x: 0, y: 64, z: 0, height: 1.62 };
  const close = { x: 2, y: 64, z: 2, height: 1.8 };
  const far = { x: 60, y: 64, z: 0, height: 1.8 };
  assert.equal(adapter.canDetectEntity(observer, close), true);
  assert.equal(adapter.canDetectEntity(observer, far), false);
});

test('fake adapter: scanEntities filters out-of-range', () => {
  const adapter = createFakePerceptionAdapter();
  const observer = { x: 0, y: 64, z: 0 };
  const entities = [
    { x: 2, y: 64, z: 2, name: 'Creeper', kind: 'mob' },
    { x: 60, y: 64, z: 0, name: 'Zombie', kind: 'mob' },
  ];
  const visible = adapter.scanEntities(observer, entities, { range: 16 });
  assert.equal(visible.length, 1);
  assert.equal(visible[0].type, 'Creeper');
});

test('fake adapter: hazards are detected from scan', () => {
  const adapter = buildSimpleGrid();
  const hits = adapter.scanBlocks(SHARED_OBSERVER, { range: 10, horizontalRays: 7, verticalRays: 1 });
  const hazards = hits.filter((h) => h.name === 'lava');
  assert.equal(hazards.length, 1);
});

test('fake adapter: sound events track and expire', () => {
  const adapter = createFakePerceptionAdapter();
  const observer = { x: 0, y: 64, z: 0 };
  adapter.addSoundEvent('mining', observer, { x: 5, y: 64, z: 0 }, 16);
  assert.equal(adapter.getSoundEvents().length, 1);
  adapter.clearSoundEvents();
  assert.equal(adapter.getSoundEvents().length, 0);
});

test('fake adapter: buildScene produces snapshot shape', () => {
  const adapter = buildSimpleGrid();
  const scene = adapter.buildScene(SHARED_OBSERVER, {
    range: 10,
    lookingAt: { name: 'grass_block', position: { x: 0, y: 63, z: 1 } },
  });
  assert.ok(typeof scene.summary === 'string');
  assert.ok(Array.isArray(scene.visible_blocks));
  assert.ok(Array.isArray(scene.visible_entities));
  assert.ok(Array.isArray(scene.hazards));
  assert.equal(scene.fair_play, true);
  assert.equal(scene.range, 10);
});

// ═══════════════════════════════════════════════════════════════════
// Minecraft adapter structural tests (no live bot)
// ═══════════════════════════════════════════════════════════════════

test('minecraft adapter: exports expected API surface', () => {
  // We can't instantiate a real Mineflayer bot in a headless test without
  // a Minecraft server, but we can verify the factory function and that
  // the adapter shape matches the fake adapter (contract parity).
  const mockBot = {
    entity: {
      position: { x: 0, y: 64, z: 0, offset: (dx, dy, dz) => ({ x: dx, y: dy, z: dz }) },
      yaw: 0,
      pitch: 0,
      height: 1.62,
    },
    blockAt: () => ({ name: 'air', boundingBox: 'empty' }),
    blockAtCursor: () => null,
    entities: {},
    players: {},
  };
  const adapter = createMinecraftPerceptionAdapter(mockBot, { rules: { fairPlay: true } });

  // Check all public methods exist
  const expectedMethods = [
    'getRules', 'setRules',
    'hasLineOfSight', 'raycastFirstSolid',
    'canDetectEntity', 'scanEntities',
    'scanBlocks', 'findVisibleBlocksByName',
    'addSoundEvent', 'getSoundEvents', 'inferSoundSource', 'clearSoundEvents',
    'getMemoryHints', 'getObservedBlocks',
    'buildScene',
  ];
  for (const method of expectedMethods) {
    assert.ok(typeof adapter[method] === 'function', `missing method: ${method}`);
  }

  assert.equal(adapter.getRules().fairPlay, true);
});

test('minecraft adapter: rules can be mutated', () => {
  const mockBot = {
    entity: {
      position: { x: 0, y: 64, z: 0, offset: (dx, dy, dz) => ({ x: dx, y: dy, z: dz }) },
      yaw: 0, pitch: 0, height: 1.62,
    },
    blockAt: () => ({ name: 'air', boundingBox: 'empty' }),
    blockAtCursor: () => null,
    entities: {},
    players: {},
  };
  const adapter = createMinecraftPerceptionAdapter(mockBot);
  adapter.setRules({ fairPlay: true, losEntityRange: 32 });
  const r = adapter.getRules();
  assert.equal(r.fairPlay, true);
  assert.equal(r.losEntityRange, 32);
});

// ═══════════════════════════════════════════════════════════════════
// Cross-adapter parity: same inputs → same core behaviour
// ═══════════════════════════════════════════════════════════════════

test('cross-adapter parity: LOS result matches for identical grid', () => {
  // Fake adapter grid
  const fake = createFakePerceptionAdapter();
  fake.setBlock(3, 64, 0, 'stone');

  const observer = { x: 0, y: 64, z: 0 };
  const target = { x: 5, y: 64, z: 0 };

  const fakeLOS = fake.hasLineOfSight(observer, target);

  // Mock bot with identical blockAt behaviour
  const grid = new Map();
  grid.set('3,64,0', { name: 'stone', boundingBox: 'block' });
  const mockBot = {
    entity: {
      position: { x: 0, y: 64, z: 0, offset: (dx, dy, dz) => ({ x: dx, y: dy, z: dz }) },
      yaw: 0, pitch: 0, height: 1.62,
    },
    blockAt: (vec3) => grid.get(`${vec3.x},${vec3.y},${vec3.z}`) || { name: 'air', boundingBox: 'empty' },
    blockAtCursor: () => null,
    entities: {},
    players: {},
  };
  const mc = createMinecraftPerceptionAdapter(mockBot);
  const mcLOS = mc.hasLineOfSight(observer, target);

  assert.equal(fakeLOS, mcLOS, 'LOS results should match for identical environments');
});

test('cross-adapter parity: raycast distance matches for identical grid', () => {
  const fake = createFakePerceptionAdapter();
  fake.setBlock(0, 64, 4, 'dirt');

  const origin = { x: 0, y: 64, z: 0 };
  const dir = { x: 0, y: 0, z: 1 };

  const fakeHit = fake.raycastFirstSolid(origin, dir, 10, 0.5);

  const grid = new Map();
  grid.set('0,64,4', { name: 'dirt', boundingBox: 'block' });
  const mockBot = {
    entity: {
      position: { x: 0, y: 64, z: 0, offset: (dx, dy, dz) => ({ x: dx, y: dy, z: dz }) },
      yaw: 0, pitch: 0, height: 1.62,
    },
    blockAt: (vec3) => grid.get(`${vec3.x},${vec3.y},${vec3.z}`) || { name: 'air', boundingBox: 'empty' },
    blockAtCursor: () => null,
    entities: {},
    players: {},
  };
  const mc = createMinecraftPerceptionAdapter(mockBot);
  const mcHit = mc.raycastFirstSolid(origin, dir, 10, 0.5);

  assert.ok(fakeHit && mcHit, 'both should hit');
  assert.equal(fakeHit.block.name, mcHit.block.name);
  assert.equal(fakeHit.distance, mcHit.distance);
});
