"""
DaemonCraft Human Design — Chart Calculator

Stage 1 of the HD pipeline: datetime + location → planetary positions → gates/lines.
"""

from datetime import datetime
from typing import Dict, Optional

try:
    from flatlib import const
    from flatlib.chart import Chart
    from flatlib.datetime import Datetime as FlatDateTime
    from flatlib.geopos import GeoPos
    FLATLIB_AVAILABLE = True
except ImportError:
    FLATLIB_AVAILABLE = False

from .constants import (
    DEGREES_PER_GATE,
    DEGREES_PER_LINE,
    DEGREES_PER_COLOR,
    DEGREES_PER_TONE,
    DEGREES_PER_BASE,
    PERSONALITY_PLANETS,
    DESIGN_PLANETS,
)


class PlanetPosition:
    """A planet's position mapped to HD substructure."""

    def __init__(self, degree: float, gate: int, line: int, color: int,
                 tone: int, base: int, side: str, sign: str):
        self.degree = degree
        self.gate = gate
        self.line = line
        self.color = color
        self.tone = tone
        self.base = base
        self.side = side
        self.sign = sign

    def to_dict(self) -> dict:
        return {
            "degree": self.degree,
            "gate": self.gate,
            "line": self.line,
            "color": self.color,
            "tone": self.tone,
            "base": self.base,
            "side": self.side,
            "sign": self.sign,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PlanetPosition":
        return cls(**d)


def hd_gate_at(degree: float) -> int:
    """Map 0-360 ecliptic longitude to HD gate 1-64."""
    return int(degree / DEGREES_PER_GATE) + 1


def hd_line(degree: float) -> int:
    """Line 1-6 within a gate."""
    within_gate = degree % DEGREES_PER_GATE
    return int(within_gate / DEGREES_PER_LINE) + 1


def hd_color(degree: float) -> int:
    """Color 1-6 within a line."""
    within_line = degree % DEGREES_PER_LINE
    return int(within_line / DEGREES_PER_COLOR) + 1


def hd_tone(degree: float) -> int:
    """Tone 1-6 within a color."""
    within_color = degree % DEGREES_PER_COLOR
    return int(within_color / DEGREES_PER_TONE) + 1


def hd_base(degree: float) -> int:
    """Base 1-5 within a tone."""
    within_tone = degree % DEGREES_PER_TONE
    return int(within_tone / DEGREES_PER_BASE) + 1


def zodiac_sign(degree: float) -> str:
    """Return zodiac sign name from 0-360 degree."""
    signs = [
        "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
        "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
    ]
    return signs[int(degree // 30.0) % 12]


class HDCalculator:
    """
    Calculate a complete Human Design chart from a birth datetime + location.

    Uses flatlib (pyswisseph) for precise planetary positions, then maps
    each planet to HD gate/line/color/tone/base.
    """

    def __init__(self):
        if not FLATLIB_AVAILABLE:
            raise RuntimeError(
                "flatlib is required for HD chart calculation. "
                "Install: pip install flatlib pyswisseph"
            )

    def calculate(self,
                  birth_dt: datetime,
                  latitude: float = -34.6037,
                  longitude: float = -58.3816,
                  timezone: str = "UTC") -> Dict[str, PlanetPosition]:
        """
        Calculate planetary positions and map to HD substructure.

        Args:
            birth_dt: UTC datetime of agent creation
            latitude: Birth latitude (default Buenos Aires)
            longitude: Birth longitude
            timezone: Timezone string

        Returns:
            Dict mapping planet name → PlanetPosition
        """
        # flatlib Datetime format: "YYYY/MM/DD", "HH:MM", "+00:00"
        date_str = birth_dt.strftime("%Y/%m/%d")
        time_str = birth_dt.strftime("%H:%M")
        tz_offset = self._tz_offset_str(birth_dt)

        flat_dt = FlatDateTime(date_str, time_str, tz_offset)
        pos = GeoPos(latitude, longitude)

        chart = Chart(flat_dt, pos, hsys=const.HOUSES_PORPHYRIUS, IDs=const.LIST_OBJECTS)

        positions = {}
        for obj in chart.objects:
            planet_id = obj.id.lower()
            degree = float(obj.lon)

            side = "personality" if planet_id in PERSONALITY_PLANETS else "design"

            positions[planet_id] = PlanetPosition(
                degree=degree,
                gate=hd_gate_at(degree),
                line=hd_line(degree),
                color=hd_color(degree),
                tone=hd_tone(degree),
                base=hd_base(degree),
                side=side,
                sign=zodiac_sign(degree),
            )

        return positions

    def _tz_offset_str(self, dt: datetime) -> str:
        """Convert UTC datetime to flatlib offset string."""
        # flatlib expects offsets like +00:00 or -03:00
        # For UTC birth times, always +00:00
        return "+00:00"

    def calculate_for_agent(self,
                            agent_id: str,
                            birth_dt: Optional[datetime] = None) -> dict:
        """
        Full chart calculation with metadata for an agent.

        Returns a dict ready for HDChartStorage.save().
        """
        if birth_dt is None:
            birth_dt = datetime.utcnow()

        positions = self.calculate(birth_dt)

        # Separate personality vs design gates
        personality_gates = []
        design_gates = []

        for planet, pos in positions.items():
            if pos.side == "personality":
                personality_gates.append(pos.gate)
            else:
                design_gates.append(pos.gate)

        # Remove duplicates while preserving order
        personality_gates = list(dict.fromkeys(personality_gates))
        design_gates = list(dict.fromkeys(design_gates))

        return {
            "agent_id": agent_id,
            "timestamp": birth_dt.isoformat(),
            "planets": {k: v.to_dict() for k, v in positions.items()},
            "gates": {
                "personality": personality_gates,
                "design": design_gates,
            },
        }

    @staticmethod
    def earth_opposite_gate(sun_gate: int) -> int:
        """Earth is always in the gate opposite the Sun (32 gates away, mod 64)."""
        return ((sun_gate + 31) % 64) + 1
