"""
DaemonCraft Human Design — Transit Engine

Calculates daily planetary transits and their impact on agents.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .calculator import HDCalculator, hd_gate_at
from .constants import GATE_TO_CENTER, ALL_PLANETS


class Transit:
    """A single planetary transit activation."""

    def __init__(self,
                 planet: str,
                 gate: int,
                 line: int,
                 center: str,
                 degree: float,
                 duration_hours: float = 24.0):
        self.planet = planet
        self.gate = gate
        self.line = line
        self.center = center
        self.degree = degree
        self.duration_hours = duration_hours

    def to_dict(self) -> dict:
        return {
            "planet": self.planet,
            "gate": self.gate,
            "line": self.line,
            "center": self.center,
            "degree": self.degree,
            "duration_hours": self.duration_hours,
        }


class TransitImpact:
    """How a transit affects a specific agent."""

    def __init__(self,
                 impact_type: str,  # "reinforcement", "temporary_channel", "conditioning"
                 strength: float,
                 message: str,
                 duration_hours: float = 24.0,
                 not_self_risk: Optional[str] = None):
        self.type = impact_type
        self.strength = strength
        self.message = message
        self.duration_hours = duration_hours
        self.not_self_risk = not_self_risk

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "strength": self.strength,
            "message": self.message,
            "duration_hours": self.duration_hours,
            "not_self_risk": self.not_self_risk,
        }


class TransitEngine:
    """
    Calculates planetary transits for any given date.

    Caches results per-day to avoid recalculating ephemeris repeatedly.
    """

    def __init__(self):
        self.calculator = HDCalculator()
        self._cache: Dict[str, Dict[str, Transit]] = {}

    def get_daily_transits(self, date: Optional[datetime] = None) -> Dict[str, Transit]:
        """
        Get all planetary transits for a given date.

        Returns:
            Dict mapping planet name → Transit
        """
        if date is None:
            date = datetime.utcnow()

        cache_key = date.strftime("%Y-%m-%d")
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Calculate positions for noon UTC on this date
        noon = date.replace(hour=12, minute=0, second=0, microsecond=0)

        try:
            positions = self.calculator.calculate(noon)
        except Exception:
            # Fallback: return empty transits on calculation failure
            return {}

        transits = {}
        for planet, pos in positions.items():
            if planet == "earth":
                continue

            gate = pos.gate
            center = GATE_TO_CENTER.get(gate, "unknown")

            # Approximate duration based on planet
            duration = self._planet_duration(planet)

            transits[planet] = Transit(
                planet=planet,
                gate=gate,
                line=pos.line,
                center=center,
                degree=pos.degree,
                duration_hours=duration,
            )

        self._cache[cache_key] = transits
        return transits

    def calculate_impact(self, transit: Transit, agent_chart: dict) -> TransitImpact:
        """
        Calculate how a specific transit affects an agent.

        Args:
            transit: The transit to evaluate
            agent_chart: The agent's natal chart dict
        """
        gate = transit.gate
        center = transit.center

        all_gates = set(agent_chart.get("gates", {}).get("personality", []))
        all_gates.update(agent_chart.get("gates", {}).get("design", []))

        defined_centers = set(agent_chart.get("defined_centers", []))
        open_centers = set(agent_chart.get("open_centers", []))

        # Case 1: Gate defined natally → reinforcement
        if gate in all_gates:
            return TransitImpact(
                impact_type="reinforcement",
                strength=0.5,  # Subtle boost
                message=f"Gate {gate} natal reinforced by {transit.planet} transit",
                duration_hours=transit.duration_hours,
            )

        # Case 2: Center defined, gate not → temporary channel
        if center in defined_centers:
            return TransitImpact(
                impact_type="temporary_channel",
                strength=1.0,
                message=f"Temporary channel formed in {center} center",
                duration_hours=transit.duration_hours,
            )

        # Case 3: Center open → conditioning
        if center in open_centers:
            from .constants import CENTER_CONDITIONING_BEHAVIOR
            risk = CENTER_CONDITIONING_BEHAVIOR.get(center, "unknown_behavior")
            return TransitImpact(
                impact_type="conditioning",
                strength=0.7,
                message=f"Open {center} temporarily defined by {transit.planet} transit",
                duration_hours=transit.duration_hours,
                not_self_risk=risk,
            )

        return TransitImpact(
            impact_type="neutral",
            strength=0.0,
            message=f"No significant impact from {transit.planet} in Gate {gate}",
            duration_hours=transit.duration_hours,
        )

    def get_agent_transits(self, agent_chart: dict, date: Optional[datetime] = None) -> List[dict]:
        """
        Get all transit impacts for an agent on a given date.

        Returns list of dicts with transit + impact info.
        """
        daily = self.get_daily_transits(date)
        results = []

        for planet, transit in daily.items():
            impact = self.calculate_impact(transit, agent_chart)
            results.append({
                "planet": planet,
                "transit": transit.to_dict(),
                "impact": impact.to_dict(),
            })

        return results

    def get_solar_transit(self, date: Optional[datetime] = None) -> Optional[Transit]:
        """Get the current solar transit (global climate)."""
        daily = self.get_daily_transits(date)
        return daily.get("sun")

    def get_lunar_transit(self, date: Optional[datetime] = None) -> Optional[Transit]:
        """Get the current lunar transit (emotional atmosphere)."""
        daily = self.get_daily_transits(date)
        return daily.get("moon")

    @staticmethod
    def _planet_duration(planet: str) -> float:
        """Approximate hours a planet stays in one gate."""
        durations = {
            "sun": 5.7 * 24,      # ~5.7 days
            "moon": 10.5,          # ~10.5 hours
            "mercury": 3.5 * 24,
            "venus": 5.5 * 24,
            "mars": 4.5 * 24,
            "jupiter": 365.0 * 24,
            "saturn": 210.0 * 24,  # ~7 months
            "uranus": 1825.0 * 24, # ~5 years
            "neptune": 730.0 * 24, # ~2 years
            "pluto": 1460.0 * 24,  # ~4 years
            "north_node": 30.0 * 24,
            "south_node": 30.0 * 24,
        }
        return durations.get(planet, 24.0)
