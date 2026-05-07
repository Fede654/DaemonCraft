/**
 * Perception utilities — backward-compat re-export
 *
 * DC-DEP-3: The canonical implementation now lives in lib/perception/.
 * This file re-exports the core so existing imports continue to work.
 */

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
} from './perception/core.js';
