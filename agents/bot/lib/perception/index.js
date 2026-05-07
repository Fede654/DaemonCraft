/**
 * Perception Primitive — Public API
 *
 * DC-DEP-3 / HRM-119
 *
 * Usage:
 *   import { canSee, renderScene, createMinecraftPerceptionAdapter } from './lib/perception/index.js';
 */

// Core (pure, environment-agnostic)
export {
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
} from './core.js';

// Adapters
export { createMinecraftPerceptionAdapter } from './adapters/minecraft.js';
export { createFakePerceptionAdapter } from './adapters/fake.js';
