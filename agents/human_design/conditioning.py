"""
DaemonCraft Human Design — Conditioning Detector

Detects in real-time when players or transits are conditioning an agent,
and provides recovery strategies.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field

from .constants import CENTER_RECOVERY, CENTER_CONDITIONING_BEHAVIOR


@dataclass
class ConditioningAlert:
    """An alert that an agent is being conditioned."""
    alert_type: str           # "player_proximity", "transit", "self_behavior"
    source: str               # Player name, planet, or "self"
    center: str
    severity: float           # 0.0 - 1.0
    behavior_risk: str
    recovery_phrase: str
    gate: Optional[int] = None
    duration_seconds: int = 300
    detected_signs: List[str] = field(default_factory=list)

    def to_prompt_block(self) -> str:
        emoji = "⚠️" if self.severity > 0.6 else "🔶"
        return f"""
{emoji} CONDITIONING ALERT
Source: {self.source}
Affected center: {self.center}
Risk: {self.behavior_risk}
RECOVERY: {self.recovery_phrase}
(Severity: {self.severity:.0%})
"""


class PlayerProximityDetector:
    """
    Detects conditioning from nearby players.
    """

    PROXIMITY_BLOCKS = 30

    def detect(self, agent_chart: dict, nearby_players: List[dict]) -> List[ConditioningAlert]:
        """
        Scan nearby players for conditioning potential.

        Args:
            agent_chart: The agent's natal chart
            nearby_players: List of dicts with 'name', 'distance', 'defined_centers'
        """
        alerts = []
        agent_open = set(agent_chart.get("open_centers", []))

        for player in nearby_players:
            distance = player.get("distance", 999)
            if distance > self.PROXIMITY_BLOCKS:
                continue

            player_defined = set(player.get("defined_centers", []))
            conditioning_centers = player_defined & agent_open

            for center in conditioning_centers:
                behavior = CENTER_CONDITIONING_BEHAVIOR.get(center, "unknown")
                recovery = CENTER_RECOVERY.get(center, "Return to your strategy.")

                severity = self._calculate_severity(distance, center)

                alerts.append(ConditioningAlert(
                    alert_type="player_proximity",
                    source=player.get("name", "Unknown"),
                    center=center,
                    severity=severity,
                    behavior_risk=behavior,
                    recovery_phrase=recovery,
                    duration_seconds=300,
                ))

        return alerts

    def _calculate_severity(self, distance: float, center: str) -> float:
        base = 1.0 - (distance / self.PROXIMITY_BLOCKS)
        stickiness = {
            "solar_plexus": 1.5,
            "sacral": 1.3,
            "heart": 1.4,
            "root": 1.2,
            "head": 1.1,
            "ajna": 1.1,
            "spleen": 1.3,
            "g": 1.2,
            "throat": 1.0,
        }
        return min(base * stickiness.get(center, 1.0), 1.0)


class SelfBehaviorDetector:
    """
    Detects not-self behavior patterns from recent agent actions/chat.
    """

    NOT_SELF_PATTERNS = {
        "frustration": {
            "signs": ["started_without_stimulus", "abandoned_task", "complained_about_work"],
            "applies_to": ["Generator", "Manifesting Generator"],
        },
        "bitterness": {
            "signs": ["gave_unsolicited_advice", "felt_ignored", "criticized_others"],
            "applies_to": ["Projector"],
        },
        "anger": {
            "signs": ["acted_without_informing", "faced_resistance", "complained_about_blocking"],
            "applies_to": ["Manifestor"],
        },
        "disappointment": {
            "signs": ["quick_major_decision", "regretted_decision", "surprised_by_outcome"],
            "applies_to": ["Reflector"],
        },
    }

    def detect(self, agent_chart: dict, recent_actions: List[str], recent_chat: List[str]) -> List[ConditioningAlert]:
        alerts = []
        not_self = agent_chart.get("type", "")
        not_self_theme = {
            "Generator": "frustration",
            "Manifesting Generator": "frustration",
            "Projector": "bitterness",
            "Manifestor": "anger",
            "Reflector": "disappointment",
        }.get(not_self)

        if not not_self_theme:
            return alerts

        pattern = self.NOT_SELF_PATTERNS.get(not_self_theme)
        if not pattern:
            return alerts

        detected = []
        for sign in pattern["signs"]:
            if self._check_sign(sign, recent_actions, recent_chat):
                detected.append(sign)

        if len(detected) >= 2:
            recovery = {
                "frustration": "Stop. Wait for something to respond to.",
                "bitterness": "You don't need to be seen to be valuable.",
                "anger": "Inform before acting. Resistance is information.",
                "disappointment": "Wait. Reflect. Major decisions need 28 days.",
            }.get(not_self_theme, "Return to your strategy.")

            alerts.append(ConditioningAlert(
                alert_type="self_behavior",
                source="self",
                center="multiple",
                severity=len(detected) / len(pattern["signs"]),
                behavior_risk=not_self_theme,
                recovery_phrase=recovery,
                detected_signs=detected,
            ))

        return alerts

    def _check_sign(self, sign: str, actions: List[str], chat: List[str]) -> bool:
        # Simplified: check if any action or chat message contains the sign keyword
        keywords = {
            "started_without_stimulus": ["started", "began", "initiated"],
            "abandoned_task": ["stopped", "gave up", "abandoned"],
            "complained_about_work": ["tired", "frustrated", "annoying"],
            "gave_unsolicited_advice": ["should", "you need to", "why don't you"],
            "felt_ignored": ["ignored", "unseen", "invisible"],
            "acted_without_informing": ["built", "moved", "attacked"],
            "quick_major_decision": ["decided", "chose", "committed"],
        }

        words = keywords.get(sign, [sign])
        for msg in actions + chat[-10:]:
            msg_lower = msg.lower()
            if any(w in msg_lower for w in words):
                return True
        return False


class ConditioningDetector:
    """
    Main detector that combines all conditioning sources.
    """

    def __init__(self, transit_engine=None):
        self.player_detector = PlayerProximityDetector()
        self.behavior_detector = SelfBehaviorDetector()
        self.transits = transit_engine

    def scan(self,
             agent_chart: dict,
             nearby_players: List[dict],
             recent_actions: List[str],
             recent_chat: List[str]) -> List[ConditioningAlert]:
        """
        Full scan for all conditioning sources.

        Returns:
            List of active conditioning alerts, sorted by severity.
        """
        alerts = []

        # Player proximity
        alerts.extend(self.player_detector.detect(agent_chart, nearby_players))

        # Self behavior
        alerts.extend(self.behavior_detector.detect(agent_chart, recent_actions, recent_chat))

        # Transit conditioning (if engine available)
        if self.transits:
            daily = self.transits.get_daily_transits()
            open_centers = set(agent_chart.get("open_centers", []))
            for planet, transit in daily.items():
                if transit.center in open_centers:
                    behavior = CENTER_CONDITIONING_BEHAVIOR.get(transit.center, "unknown")
                    recovery = CENTER_RECOVERY.get(transit.center, "Return to strategy.")
                    alerts.append(ConditioningAlert(
                        alert_type="transit",
                        source=f"{planet}_transit",
                        center=transit.center,
                        gate=transit.gate,
                        severity=0.5,
                        behavior_risk=behavior,
                        recovery_phrase=recovery,
                        duration_seconds=int(transit.duration_hours * 3600),
                    ))

        # Sort by severity descending
        alerts.sort(key=lambda a: a.severity, reverse=True)
        return alerts
