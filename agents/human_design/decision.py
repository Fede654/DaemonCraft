"""
DaemonCraft Human Design — Decision Modifiers

Modifies agent decisions based on HD type, authority, transits, and profile.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Option:
    """A decision option with metadata."""
    name: str
    weight: float = 1.0
    initiated_by_self: bool = False
    has_external_stimulus: bool = False
    is_response_opportunity: bool = False
    has_invitation: bool = False
    has_informed: bool = False
    is_guidance: bool = False
    target_location: Optional[Dict[str, float]] = None
    related_gates: List[int] = None

    def __post_init__(self):
        if self.related_gates is None:
            self.related_gates = []


@dataclass
class ModifiedDecision:
    """Result of applying HD modifiers to a decision."""
    options: List[Option]
    rejected_options: List[Option]
    modifiers_applied: List[str]
    explanation: str


class TypeStrategyModifier:
    """
    Modifies options based on HD Type strategy.

    - Generators: penalize self-initiated, boost responses
    - Projectors: require invitation for guidance
    - Manifestors: add resistance risk if not informed
    - Reflectors: encourage waiting
    """

    def modify(self, options: List[Option], chart: dict) -> ModifiedDecision:
        type_name = chart.get("type", "Generator")

        if type_name in ("Generator", "Manifesting Generator"):
            return self._generator_filter(options)
        elif type_name == "Projector":
            return self._projector_filter(options)
        elif type_name == "Manifestor":
            return self._manifestor_filter(options)
        elif type_name == "Reflector":
            return self._reflector_filter(options)

        return ModifiedDecision(
            options=options,
            rejected_options=[],
            modifiers_applied=[],
            explanation="No type modifier applied"
        )

    def _generator_filter(self, options: List[Option]) -> ModifiedDecision:
        modified = []
        rejected = []

        for opt in options:
            if opt.initiated_by_self and not opt.has_external_stimulus:
                opt.weight *= 0.1
                rejected.append(opt)
            elif opt.has_external_stimulus and opt.is_response_opportunity:
                opt.weight *= 1.5
                modified.append(opt)
            else:
                modified.append(opt)

        return ModifiedDecision(
            options=modified,
            rejected_options=rejected,
            modifiers_applied=["generator_strategy"],
            explanation="Generator: penalized self-initiated, boosted responses"
        )

    def _projector_filter(self, options: List[Option]) -> ModifiedDecision:
        modified = []
        rejected = []

        for opt in options:
            if opt.is_guidance and not opt.has_invitation:
                opt.weight *= 0.15
                rejected.append(opt)
            elif opt.has_invitation:
                opt.weight *= 2.0
                modified.append(opt)
            else:
                modified.append(opt)

        return ModifiedDecision(
            options=modified,
            rejected_options=rejected,
            modifiers_applied=["projector_strategy"],
            explanation="Projector: requires invitation for guidance"
        )

    def _manifestor_filter(self, options: List[Option]) -> ModifiedDecision:
        modified = []

        for opt in options:
            if opt.initiated_by_self and not opt.has_informed:
                opt.weight *= 0.7
            elif opt.has_informed:
                opt.weight *= 1.3
            modified.append(opt)

        return ModifiedDecision(
            options=modified,
            rejected_options=[],
            modifiers_applied=["manifestor_strategy"],
            explanation="Manifestor: actions without informing carry resistance risk"
        )

    def _reflector_filter(self, options: List[Option]) -> ModifiedDecision:
        modified = []

        for opt in options:
            # Reflectors benefit from waiting and group consensus
            if opt.has_external_stimulus:
                opt.weight *= 1.2
            modified.append(opt)

        return ModifiedDecision(
            options=modified,
            rejected_options=[],
            modifiers_applied=["reflector_strategy"],
            explanation="Reflector: boosted options with external input"
        )


class TransitOpportunityModifier:
    """
    Boosts options that align with current planetary transits.
    """

    def __init__(self, transit_engine):
        self.transits = transit_engine

    def modify(self, options: List[Option], chart: dict) -> ModifiedDecision:
        daily = self.transits.get_daily_transits()
        modified = list(options)

        for planet, transit in daily.items():
            for opt in modified:
                if transit.gate in opt.related_gates:
                    opt.weight *= 1.3

        return ModifiedDecision(
            options=modified,
            rejected_options=[],
            modifiers_applied=["transit_opportunity"],
            explanation=f"Applied transit boosts from {len(daily)} planets"
        )


class HDDecisionPipeline:
    """
    Complete decision modification pipeline.

    Applies modifiers in order:
    1. Type Strategy Filter
    2. Transit Opportunity Booster
    3. Sort by final weight
    """

    def __init__(self, transit_engine=None):
        self.type_mod = TypeStrategyModifier()
        self.transit_mod = TransitOpportunityModifier(transit_engine) if transit_engine else None

    def process(self, options: List[Option], chart: dict) -> ModifiedDecision:
        # Step 1: Type strategy
        result = self.type_mod.modify(options, chart)

        # Step 2: Transit opportunities
        if self.transit_mod:
            result = self.transit_mod.modify(result.options, chart)

        # Sort by final weight
        result.options.sort(key=lambda o: o.weight, reverse=True)

        return result
