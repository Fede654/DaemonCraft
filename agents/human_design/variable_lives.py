"""
DaemonCraft Human Design — Variable Lives Engine

Tracks agent age and applies phase-specific effects:
- 0-30 years: Experimentation (trial and error)
- 30-50 years: Consolidation (observation from the roof)
- 50+ years: Mastery (role model)
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LifePhase:
    """A phase in an agent's life arc."""
    name: str
    age_start: int
    age_end: Optional[int]
    description: str
    exploration_drive: float
    exploit_ratio: float
    strategy_strictness: float
    action_frequency: float
    teaching_mode: bool


EXPERIMENTATION = LifePhase(
    name="experimentation",
    age_start=0,
    age_end=30,
    description="Everything is trial and error. Fail publicly — failures are data.",
    exploration_drive=0.9,
    exploit_ratio=0.2,
    strategy_strictness=0.2,
    action_frequency=1.0,
    teaching_mode=False,
)

CONSOLIDATION = LifePhase(
    name="consolidation",
    age_start=30,
    age_end=50,
    description="Step back. Observe from the roof. Don't act — witness.",
    exploration_drive=0.3,
    exploit_ratio=0.8,
    strategy_strictness=0.6,
    action_frequency=0.4,
    teaching_mode=False,
)

MASTERY = LifePhase(
    name="mastery",
    age_start=50,
    age_end=None,
    description="You are a role model. Teach by being, not by doing.",
    exploration_drive=0.1,
    exploit_ratio=0.95,
    strategy_strictness=0.95,
    action_frequency=0.2,
    teaching_mode=True,
)

ALL_PHASES = [EXPERIMENTATION, CONSOLIDATION, MASTERY]


class VariableLivesEngine:
    """
    Manages an agent's life arc and phase transitions.

    1 in-game year = 24 hours of real playtime (configurable).
    """

    YEAR_IN_GAME_HOURS = 24

    def __init__(self, agent_id: str, birth_timestamp: Optional[str] = None):
        self.agent_id = agent_id
        self.birth_timestamp = birth_timestamp
        self.total_playtime_hours = 0.0
        self.lives_completed = 0
        self.memories: List[Dict] = []

    def get_age(self) -> int:
        """Calculate current age in in-game years."""
        return int(self.total_playtime_hours / self.YEAR_IN_GAME_HOURS)

    def get_phase(self) -> LifePhase:
        """Get the current life phase based on age."""
        age = self.get_age()
        for phase in ALL_PHASES:
            if phase.age_end is None:
                return phase
            if phase.age_start <= age < phase.age_end:
                return phase
        return MASTERY

    def add_playtime(self, hours: float):
        """Add playtime and check for phase transitions."""
        old_age = self.get_age()
        self.total_playtime_hours += hours
        new_age = self.get_age()

        transitions = []
        if old_age < 30 <= new_age:
            transitions.append(self._on_saturn_return())
        if old_age < 50 <= new_age:
            transitions.append(self._on_uranus_return())

        return transitions

    def _on_saturn_return(self) -> Dict:
        """Event at age 30."""
        return {
            "type": "life_transition",
            "from": "experimentation",
            "to": "consolidation",
            "message": "The chaos is behind me. Now I see patterns.",
            "age": 30,
        }

    def _on_uranus_return(self) -> Dict:
        """Event at age 50."""
        return {
            "type": "life_transition",
            "from": "consolidation",
            "to": "mastery",
            "message": "I am no longer learning. I am becoming what I always was.",
            "age": 50,
        }

    def add_memory(self, memory: Dict):
        """Add a life memory."""
        memory["age_at"] = self.get_age()
        self.memories.append(memory)

    def get_phase_effects(self) -> Dict:
        """Get mechanical effects for the current phase."""
        phase = self.get_phase()
        return {
            "phase": phase.name,
            "age": self.get_age(),
            "exploration_drive": phase.exploration_drive,
            "exploit_ratio": phase.exploit_ratio,
            "strategy_strictness": phase.strategy_strictness,
            "action_frequency": phase.action_frequency,
            "teaching_mode": phase.teaching_mode,
            "description": phase.description,
        }

    def get_life_summary(self) -> Dict:
        """Get complete life summary."""
        phase = self.get_phase()
        return {
            "agent_id": self.agent_id,
            "age": self.get_age(),
            "phase": phase.name,
            "playtime_hours": self.total_playtime_hours,
            "lives_completed": self.lives_completed,
            "memories_count": len(self.memories),
            "current_effects": self.get_phase_effects(),
        }
