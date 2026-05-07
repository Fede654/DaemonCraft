"""
DaemonCraft Human Design — Type and Authority Engine

Stage 3-4 of the HD pipeline: bodygraph → Type + Authority + Profile + Variable.
"""

from typing import Dict, List, Optional, Tuple

from .constants import (
    MOTOR_CHANNELS,
    TYPE_STRATEGIES,
    TYPE_NOT_SELF,
    TYPE_SIGNATURES,
    TYPE_AURAS,
    AUTHORITY_HIERARCHY,
    CROSS_TYPES,
)


class TypeAuthorityResult:
    """Complete type, authority, and strategy for an agent."""

    def __init__(self,
                 type_name: str,
                 authority: str,
                 strategy: str,
                 not_self: str,
                 signature: str,
                 aura: str):
        self.type = type_name
        self.authority = authority
        self.strategy = strategy
        self.not_self = not_self
        self.signature = signature
        self.aura = aura

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "authority": self.authority,
            "strategy": self.strategy,
            "not_self_theme": self.not_self,
            "signature": self.signature,
            "aura": self.aura,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TypeAuthorityResult":
        return cls(
            type_name=d["type"],
            authority=d["authority"],
            strategy=d["strategy"],
            not_self=d["not_self_theme"],
            signature=d["signature"],
            aura=d.get("aura", ""),
        )


class TypeEngine:
    """
    Determine HD Type from bodygraph state.

    Rules (Ra Uru Hu):
    1. Sacral defined + motor-to-throat = Manifesting Generator
    2. Sacral defined, no motor-to-throat = Generator
    3. No sacral, motor-to-throat = Manifestor
    4. No sacral, no motor-to-throat = Projector
    5. No centers defined at all = Reflector
    """

    @classmethod
    def determine(cls, bodygraph) -> str:
        """
        Determine type from BodygraphState or dict.

        Args:
            bodygraph: BodygraphState instance or dict with 'defined_centers' and 'channels'
        """
        if hasattr(bodygraph, "defined_centers"):
            defined = set(bodygraph.defined_centers)
            channels = bodygraph.channels
        else:
            defined = set(bodygraph.get("defined_centers", []))
            channels = bodygraph.get("channels", [])

        # Reflector: zero defined centers
        if len(defined) == 0:
            return "Reflector"

        has_sacral = "sacral" in defined
        has_throat = "throat" in defined

        # Check for motor-to-throat channel
        has_motor_to_throat = False
        if has_throat:
            for ch in channels:
                parts = ch.split("-")
                if len(parts) == 2:
                    g1, g2 = int(parts[0]), int(parts[1])
                    if (g1, g2) in MOTOR_CHANNELS or (g2, g1) in MOTOR_CHANNELS:
                        has_motor_to_throat = True
                        break

        if has_sacral:
            if has_motor_to_throat:
                return "Manifesting Generator"
            return "Generator"

        # No sacral
        if has_motor_to_throat:
            return "Manifestor"

        return "Projector"


class AuthorityEngine:
    """
    Determine Authority from defined centers.

    Hierarchy (highest priority first):
    1. Solar Plexus defined → Emotional Authority
    2. Sacral defined → Sacral Authority
    3. Heart/Ego defined → Ego Authority
    4. G defined → Self-Projected Authority
    5. Spleen defined → Splenic Authority
    6. Ajna/Head defined (no motors below) → Mental Authority
    7. No inner authority → Lunar Authority (Reflectors) or None
    """

    @classmethod
    def determine(cls, bodygraph) -> str:
        """Determine authority from BodygraphState or dict."""
        if hasattr(bodygraph, "defined_centers"):
            defined = set(bodygraph.defined_centers)
            channels = bodygraph.channels
        else:
            defined = set(bodygraph.get("defined_centers", []))
            channels = bodygraph.get("channels", [])

        # Check hierarchy
        for center, authority_name in AUTHORITY_HIERARCHY:
            if center in defined:
                # Mental authority special case: only if no motor centers defined
                if authority_name == "mental":
                    motor_centers = {"sacral", "heart", "root", "solar_plexus"}
                    if motor_centers & defined:
                        continue  # Skip mental if any motor is defined
                return authority_name

        # No inner authority found
        if len(defined) == 0:
            return "lunar"  # Reflector

        return "none"


class ProfileCalculator:
    """Calculate Profile and Variable from planetary positions."""

    @classmethod
    def calculate(cls, positions: Dict[str, dict]) -> dict:
        """
        Calculate profile and variable arrows.

        Returns:
            {"profile": "3/5", "variable": {"motivation": "←", ...}}
        """
        sun_line = positions.get("sun", {}).get("line", 1)
        earth_line = positions.get("earth", {}).get("line", sun_line)
        moon_line = positions.get("moon", {}).get("line", 1)

        # Profile: conscious/unconscious lines
        profile = f"{sun_line}/{earth_line}"

        # Variable: simplified mapping from lines
        # Lines 1-3 = Left (←), Lines 4-6 = Right (→)
        def arrow(line):
            return "←" if line <= 3 else "→"

        variable = {
            "motivation": arrow(sun_line),
            "cognition": arrow(sun_line),
            "environment": arrow(moon_line),
            "perspective": arrow(moon_line),
        }

        return {
            "profile": profile,
            "variable": variable,
        }


class CrossCalculator:
    """Calculate Incarnation Cross from planetary positions."""

    @classmethod
    def calculate(cls, positions: Dict[str, dict]) -> dict:
        """
        Calculate the four gates of the incarnation cross.

        Returns:
            {"conscious_sun": 34, "conscious_earth": 20, ...}
        """
        sun_gate = positions.get("sun", {}).get("gate", 1)
        north_gate = positions.get("north_node", {}).get("gate", 1)
        south_gate = positions.get("south_node", {}).get("gate", 1)

        # Earth is opposite Sun
        earth_gate = ((sun_gate + 31) % 64) + 1

        # Identify cross type
        gates = tuple(sorted([sun_gate, earth_gate, north_gate, south_gate]))
        cross_type = CROSS_TYPES.get(gates, "Unknown Cross")

        return {
            "conscious_sun": sun_gate,
            "conscious_earth": earth_gate,
            "unconscious_north_node": north_gate,
            "unconscious_south_node": south_gate,
            "cross_type": cross_type,
        }


class CompleteChartBuilder:
    """
    Orchestrates the full chart calculation pipeline.

    Takes the raw output from HDCalculator and produces a complete
    chart dict ready for storage.
    """

    @classmethod
    def build(cls, calculator_output: dict) -> dict:
        """
        Build complete chart from calculator output.

        Args:
            calculator_output: Output from HDCalculator.calculate_for_agent()

        Returns:
            Complete chart dict with type, authority, profile, variable, cross.
        """
        from .bodygraph import BodygraphAnalyzer

        positions = calculator_output.get("planets", {})
        gates = calculator_output.get("gates", {})

        # Analyze bodygraph
        bodygraph = BodygraphAnalyzer.analyze(positions)

        # Determine type and authority
        type_name = TypeEngine.determine(bodygraph)
        authority = AuthorityEngine.determine(bodygraph)

        # Calculate profile and variable
        profile_data = ProfileCalculator.calculate(positions)

        # Calculate cross
        cross = CrossCalculator.calculate(positions)

        # Build complete chart
        chart = {
            "agent_id": calculator_output.get("agent_id", ""),
            "schema_version": "1.0.0",
            "timestamp": calculator_output.get("timestamp", ""),
            "planets": positions,
            "gates": {
                "personality": bodygraph.personality_gates,
                "design": bodygraph.design_gates,
            },
            "channels": bodygraph.channels,
            "defined_centers": bodygraph.defined_centers,
            "open_centers": bodygraph.open_centers,
            "type": type_name,
            "authority": authority,
            "profile": profile_data["profile"],
            "variable": profile_data["variable"],
            "cross": cross,
        }

        return chart
