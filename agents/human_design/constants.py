"""
DaemonCraft Human Design — Constants and Lookup Tables

All mechanical mappings from HD cosmology to code.
No magic numbers. Everything is named.
"""

# ═══════════════════════════════════════════════════════════════════════════════
# Bodygraph: 64 Gates → 9 Centers
# ═══════════════════════════════════════════════════════════════════════════════

GATE_TO_CENTER = {
    # Head Center (Pressure to Think/Inspire)
    64: "head", 63: "head", 61: "head",
    # Ajna Center (Mental Awareness)
    47: "ajna", 24: "ajna", 4: "ajna", 11: "ajna",
    # Throat Center (Communication/Manifestation)
    62: "throat", 23: "throat", 56: "throat", 35: "throat",
    12: "throat", 45: "throat", 33: "throat", 20: "throat",
    8: "throat", 31: "throat", 44: "throat", 16: "throat",
    # G / Identity Center (Direction/Love)
    1: "g", 13: "g", 25: "g", 46: "g",
    10: "g", 15: "g", 37: "g", 22: "g",
    7: "g", 2: "g", 5: "g", 14: "g",
    29: "g", 59: "g", 9: "g", 52: "g",
    53: "g", 60: "g", 41: "g", 19: "g",
    49: "g", 30: "g", 55: "g", 38: "g",
    39: "g", 54: "g", 58: "g",
    # Heart / Ego Center (Willpower/Value)
    21: "heart", 40: "heart", 51: "heart",
    26: "heart", 44: "heart", 17: "heart", 18: "heart",
    # Solar Plexus Center (Emotional Awareness)
    55: "solar_plexus", 30: "solar_plexus", 36: "solar_plexus",
    22: "solar_plexus", 6: "solar_plexus", 37: "solar_plexus",
    49: "solar_plexus", 50: "solar_plexus",
    # Sacral Center (Life Force / Workforce)
    5: "sacral", 14: "sacral", 29: "sacral", 59: "sacral",
    9: "sacral", 52: "sacral", 53: "sacral", 60: "sacral",
    3: "sacral", 42: "sacral", 27: "sacral", 50: "sacral",
    34: "sacral", 57: "sacral", 10: "sacral", 20: "sacral",
    # Spleen Center (Intuition/Survival)
    48: "spleen", 18: "spleen", 28: "spleen", 57: "spleen",
    44: "spleen", 50: "spleen", 32: "spleen", 54: "spleen",
    # Root Center (Pressure to Act)
    38: "root", 28: "root", 54: "root", 19: "root",
    41: "root", 52: "root", 53: "root", 60: "root",
    58: "root", 10: "root", 20: "root", 34: "root",
}

ALL_CENTERS = [
    "head", "ajna", "throat", "g", "heart",
    "solar_plexus", "sacral", "spleen", "root",
]

# Center descriptions for prompts
CENTER_DESCRIPTIONS = {
    "head": "Pressure to think, ask questions, inspire",
    "ajna": "Mental awareness, processing, certainty/uncertainty",
    "throat": "Communication, manifestation, action",
    "g": "Identity, direction, love, purpose",
    "heart": "Willpower, ego, value, commitment",
    "solar_plexus": "Emotional awareness, waves, clarity",
    "sacral": "Life force, work force, response",
    "spleen": "Intuition, survival, timing, health",
    "root": "Adrenaline, pressure, stress, drive",
}

# ═══════════════════════════════════════════════════════════════════════════════
# The 36 Channels
# ═══════════════════════════════════════════════════════════════════════════════

ALL_CHANNELS = [
    (1, 8), (2, 14), (3, 60), (4, 63), (5, 15),
    (6, 59), (7, 31), (9, 52), (10, 20), (10, 34),
    (10, 57), (11, 56), (12, 22), (13, 33), (16, 48),
    (17, 62), (18, 58), (19, 49), (20, 34), (20, 57),
    (21, 45), (23, 43), (24, 61), (25, 51), (26, 44),
    (27, 50), (28, 38), (29, 46), (30, 41), (32, 54),
    (34, 57), (35, 36), (37, 40), (39, 55), (42, 53),
    (47, 64),
]

CHANNEL_NAMES = {
    (1, 8): "Inspiration",
    (2, 14): "The Beat",
    (3, 60): "Mutation",
    (4, 63): "Logic",
    (5, 15): "Rhythm",
    (6, 59): "Mating",
    (7, 31): "The Alpha",
    (9, 52): "Concentration",
    (10, 20): "Awakening",
    (10, 34): "Exploration",
    (10, 57): "Perfected Form",
    (11, 56): "Curiosity",
    (12, 22): "Openness",
    (13, 33): "The Prodigal",
    (16, 48): "Wavelength",
    (17, 62): "Acceptance",
    (18, 58): "Judgment",
    (19, 49): "Synthesis",
    (20, 34): "Charisma",
    (20, 57): "Brainwave",
    (21, 45): "The Money Line",
    (23, 43): "Structuring",
    (24, 61): "Awareness",
    (25, 51): "Initiation",
    (26, 44): "Surrender",
    (27, 50): "Preservation",
    (28, 38): "Struggle",
    (29, 46): "Discovery",
    (30, 41): "Recognition",
    (32, 54): "Transformation",
    (34, 57): "Power",
    (35, 36): "Transitoriness",
    (37, 40): "Community",
    (39, 55): "Emoting",
    (42, 53): "Maturation",
    (47, 64): "Abstraction",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Motor Channels (for Type determination)
# ═══════════════════════════════════════════════════════════════════════════════

MOTOR_CHANNELS = [
    (20, 34), (20, 57),  # Throat-Sacral, Throat-Spleen
    (21, 45),             # Heart-Throat
    (26, 44),             # Heart-Spleen
    (25, 51),             # G-Heart
    (35, 36), (12, 22),   # Throat-Solar Plexus
    (37, 40),             # Solar Plexus-Heart
    (39, 55),             # Root-Solar Plexus
    (38, 28), (54, 32),   # Spleen-Root
    (19, 49), (41, 30),   # Root-Solar Plexus
    (9, 52), (53, 42),    # Sacral-Root
    (3, 60),              # Sacral-Root
    (27, 50),             # Sacral-Spleen
]

# ═══════════════════════════════════════════════════════════════════════════════
# Type → Strategy / Not-Self / Signature
# ═══════════════════════════════════════════════════════════════════════════════

TYPE_STRATEGIES = {
    "Generator": "respond",
    "Manifesting Generator": "respond, then inform",
    "Projector": "wait for invitation",
    "Manifestor": "inform before acting",
    "Reflector": "wait 28 days",
}

TYPE_NOT_SELF = {
    "Generator": "frustration",
    "Manifesting Generator": "frustration",
    "Projector": "bitterness",
    "Manifestor": "anger",
    "Reflector": "disappointment",
}

TYPE_SIGNATURES = {
    "Generator": "satisfaction",
    "Manifesting Generator": "satisfaction",
    "Projector": "success",
    "Manifestor": "peace",
    "Reflector": "surprise",
}

TYPE_AURAS = {
    "Generator": "enveloping",
    "Manifesting Generator": "enveloping and initiating",
    "Projector": "absorbing",
    "Manifestor": "repelling",
    "Reflector": "resistant / sampling",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Authority determination order
# ═══════════════════════════════════════════════════════════════════════════════

AUTHORITY_HIERARCHY = [
    ("solar_plexus", "emotional"),
    ("sacral", "sacral"),
    ("heart", "ego"),
    ("g", "self_projected"),
    ("spleen", "splenic"),
    ("ajna", "mental"),
]

# ═══════════════════════════════════════════════════════════════════════════════
# Planet → Side (personality vs design)
# ═══════════════════════════════════════════════════════════════════════════════

PERSONALITY_PLANETS = [
    "sun", "moon", "north_node",
    "mercury", "venus", "mars",
    "jupiter", "saturn",
]

DESIGN_PLANETS = [
    "south_node", "uranus", "neptune", "pluto",
]

ALL_PLANETS = PERSONALITY_PLANETS + DESIGN_PLANETS

# ═══════════════════════════════════════════════════════════════════════════════
# Cross types
# ═══════════════════════════════════════════════════════════════════════════════

CROSS_TYPES = {
    (1, 2, 7, 13): "Left Angle Cross of Refinement",
    (5, 35, 14, 15): "Left Angle Cross of Dedication",
    (26, 44, 17, 18): "Left Angle Cross of Individualism",
    (29, 30, 8, 14): "Right Angle Cross of Penetration",
    (24, 44, 13, 7): "Right Angle Cross of Planning",
    (4, 49, 23, 43): "Right Angle Cross of Explanation",
    (25, 46, 10, 15): "Juxtaposition Cross of Intimacy",
    (52, 58, 18, 17): "Juxtaposition Cross of Stillness",
}

# ═══════════════════════════════════════════════════════════════════════════════
# HD Calculation Constants
# ═══════════════════════════════════════════════════════════════════════════════

DEGREES_PER_GATE = 360.0 / 64.0       # 5.625
DEGREES_PER_LINE = DEGREES_PER_GATE / 6.0   # 0.9375
DEGREES_PER_COLOR = DEGREES_PER_LINE / 6.0  # 0.15625
DEGREES_PER_TONE = DEGREES_PER_COLOR / 6.0  # ~0.02604
DEGREES_PER_BASE = DEGREES_PER_TONE / 5.0   # ~0.00521

# ═══════════════════════════════════════════════════════════════════════════════
# Conditioning recovery phrases by center
# ═══════════════════════════════════════════════════════════════════════════════

CENTER_RECOVERY = {
    "head": "I don't need to know that.",
    "ajna": "It's okay to be uncertain.",
    "throat": "I speak when it's correct, not to attract attention.",
    "g": "My direction comes from within, not from others.",
    "heart": "My worth is not proven by what I do.",
    "solar_plexus": "I wait for emotional clarity before deciding.",
    "sacral": "I only say yes when my body says yes.",
    "spleen": "I trust my intuition and move on.",
    "root": "The pressure is external; I don't need to rush.",
}

CENTER_CONDITIONING_BEHAVIOR = {
    "head": "thinking_about_things_that_dont_matter",
    "ajna": "trying_to_be_certain",
    "throat": "talking_to_attract_attention",
    "g": "searching_for_love_direction",
    "heart": "making_grandiose_promises",
    "solar_plexus": "emotional_reactivity",
    "sacral": "saying_yes_to_everything",
    "spleen": "holding_on_to_things",
    "root": "rushing_to_finish",
}
