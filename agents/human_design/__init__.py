"""
DaemonCraft Human Design Module

Provides complete Human Design chart calculation, transit tracking,
conditioning detection, and SOUL prompt injection for Minecraft agents.

Quick Start:
    from agents.human_design import HDCalculator, HDChartStorage, CompleteChartBuilder

    calc = HDCalculator()
    raw = calc.calculate_for_agent("pamplinas")
    chart = CompleteChartBuilder.build(raw)

    storage = HDChartStorage(cast_name="rolemaster")
    storage.save("pamplinas", chart)
"""

from .calculator import HDCalculator, PlanetPosition, hd_gate_at
from .bodygraph import BodygraphState, BodygraphAnalyzer
from .types import (
    TypeEngine,
    AuthorityEngine,
    ProfileCalculator,
    CrossCalculator,
    CompleteChartBuilder,
    TypeAuthorityResult,
)
from .transits import TransitEngine, Transit, TransitImpact
from .storage import HDChartStorage
from .injection import HDContextInjector
from .decision import HDDecisionPipeline, TypeStrategyModifier, Option, ModifiedDecision
from .conditioning import ConditioningDetector, ConditioningAlert
from .variable_lives import VariableLivesEngine, LifePhase

__all__ = [
    # Calculator
    "HDCalculator",
    "PlanetPosition",
    "hd_gate_at",
    # Bodygraph
    "BodygraphState",
    "BodygraphAnalyzer",
    # Types
    "TypeEngine",
    "AuthorityEngine",
    "ProfileCalculator",
    "CrossCalculator",
    "CompleteChartBuilder",
    "TypeAuthorityResult",
    # Transits
    "TransitEngine",
    "Transit",
    "TransitImpact",
    # Storage
    "HDChartStorage",
    # Injection
    "HDContextInjector",
    # Decision
    "HDDecisionPipeline",
    "TypeStrategyModifier",
    "Option",
    "ModifiedDecision",
    # Conditioning
    "ConditioningDetector",
    "ConditioningAlert",
    # Variable Lives
    "VariableLivesEngine",
    "LifePhase",
]

__version__ = "1.0.0"
