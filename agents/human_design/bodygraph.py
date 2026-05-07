"""
DaemonCraft Human Design — Bodygraph Analysis

Stage 2 of the HD pipeline: planetary positions → defined centers, channels,
open centers, and complete bodygraph state.
"""

from typing import List, Dict, Set, Tuple

from .constants import (
    GATE_TO_CENTER,
    ALL_CENTERS,
    ALL_CHANNELS,
    CHANNEL_NAMES,
    CENTER_DESCRIPTIONS,
)


class BodygraphState:
    """
    Represents the complete energetic state of an agent's Bodygraph:
    which centers are defined, which are open, and which channels are active.
    """

    def __init__(self,
                 personality_gates: List[int],
                 design_gates: List[int],
                 channels: List[str],
                 defined_centers: List[str],
                 open_centers: List[str]):
        self.personality_gates = personality_gates
        self.design_gates = design_gates
        self.channels = channels
        self.defined_centers = defined_centers
        self.open_centers = open_centers

    @property
    def all_gates(self) -> Set[int]:
        """All activated gates (both personality and design)."""
        return set(self.personality_gates) | set(self.design_gates)

    def to_dict(self) -> dict:
        return {
            "gates": {
                "personality": self.personality_gates,
                "design": self.design_gates,
            },
            "channels": self.channels,
            "defined_centers": self.defined_centers,
            "open_centers": self.open_centers,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "BodygraphState":
        return cls(
            personality_gates=d["gates"]["personality"],
            design_gates=d["gates"]["design"],
            channels=d.get("channels", []),
            defined_centers=d.get("defined_centers", []),
            open_centers=d.get("open_centers", []),
        )


class BodygraphAnalyzer:
    """
    Analyzes planetary positions to determine centers, channels, and
    complete bodygraph state.
    """

    @classmethod
    def analyze(cls, positions: Dict[str, dict]) -> BodygraphState:
        """
        Determine bodygraph state from planetary positions dict.

        Args:
            positions: Dict from calculator, e.g. {"sun": {"gate": 34, ...}, ...}

        Returns:
            BodygraphState with centers, channels, and gates.
        """
        personality_gates = []
        design_gates = []

        for planet, pos in positions.items():
            gate = pos.get("gate", 0)
            side = pos.get("side", "personality")
            if side == "personality":
                personality_gates.append(gate)
            else:
                design_gates.append(gate)

        # Remove duplicates
        personality_gates = list(dict.fromkeys(personality_gates))
        design_gates = list(dict.fromkeys(design_gates))
        all_gates = set(personality_gates) | set(design_gates)

        # Determine channels: both gates must be activated
        channels = []
        for g1, g2 in ALL_CHANNELS:
            if g1 in all_gates and g2 in all_gates:
                # Canonical ordering: smaller gate first
                if g1 < g2:
                    channels.append(f"{g1}-{g2}")
                else:
                    channels.append(f"{g2}-{g1}")

        # Determine defined centers
        # A center is "defined" if it has at least one active channel
        # passing through it. This is more accurate than just counting gates.
        defined_centers = set()
        for ch in channels:
            g1, g2 = map(int, ch.split("-"))
            c1 = GATE_TO_CENTER.get(g1)
            c2 = GATE_TO_CENTER.get(g2)
            if c1:
                defined_centers.add(c1)
            if c2:
                defined_centers.add(c2)

        # Fallback: if no channels but gates exist, count gates per center
        if not defined_centers:
            center_gate_counts: Dict[str, int] = {}
            for gate in all_gates:
                center = GATE_TO_CENTER.get(gate)
                if center:
                    center_gate_counts[center] = center_gate_counts.get(center, 0) + 1
            # A center with 2+ gates is considered "defined" as fallback
            for center, count in center_gate_counts.items():
                if count >= 2:
                    defined_centers.add(center)

        open_centers = [c for c in ALL_CENTERS if c not in defined_centers]

        return BodygraphState(
            personality_gates=personality_gates,
            design_gates=design_gates,
            channels=channels,
            defined_centers=sorted(list(defined_centers), key=ALL_CENTERS.index),
            open_centers=open_centers,
        )

    @classmethod
    def describe_channel(cls, channel: str) -> str:
        """Return human-readable description of a channel."""
        parts = channel.split("-")
        if len(parts) != 2:
            return f"Unknown channel {channel}"
        g1, g2 = int(parts[0]), int(parts[1])
        name = CHANNEL_NAMES.get((g1, g2)) or CHANNEL_NAMES.get((g2, g1))
        if name:
            return f"{channel} ({name})"
        return channel

    @classmethod
    def describe_center(cls, center: str) -> str:
        """Return description of a center."""
        return CENTER_DESCRIPTIONS.get(center, f"Center {center}")
