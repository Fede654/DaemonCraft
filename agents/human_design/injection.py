"""
DaemonCraft Human Design — SOUL Context Injection

Injects HD context blocks into agent SOUL prompts.
"""

from datetime import datetime
from typing import Optional

from .storage import HDChartStorage
from .transits import TransitEngine
from .constants import TYPE_STRATEGIES, TYPE_NOT_SELF, TYPE_SIGNATURES


class HDContextInjector:
    """
    Injects Human Design context into agent SOUL prompts.

    Produces three blocks:
    1. Natal Chart (static — loaded once per session)
    2. Current Energetic State (dynamic — changes with transits)
    3. Life Arc (dynamic — changes with agent age)
    """

    def __init__(self, storage: HDChartStorage, transit_engine: TransitEngine):
        self.storage = storage
        self.transits = transit_engine

    def inject(self, soul_prompt: str, agent_id: str, is_first_turn: bool = False) -> str:
        """
        Inject HD context into a SOUL prompt.

        Args:
            soul_prompt: The base SOUL prompt
            agent_id: Agent identifier
            is_first_turn: If True, inject full natal block. If False, summary only.

        Returns:
            SOUL prompt with [[hd-context]] block inserted
        """
        try:
            chart = self.storage.load(agent_id)
            derived = self.storage.get_derived(agent_id)
        except FileNotFoundError:
            # No chart yet — inject minimal placeholder
            return self._inject_placeholder(soul_prompt)

        if is_first_turn:
            natal_block = self._generate_natal_block(chart, derived)
        else:
            natal_block = self._generate_natal_summary(derived)

        current_block = self._generate_current_block(agent_id, chart, derived)
        life_block = self._generate_life_block(agent_id, derived)

        hd_context = f"""### Your Human Design Context

{natal_block}

### Current Energetic State
{current_block}

### Life Arc
{life_block}
"""

        # Replace placeholder or insert before Core Instructions
        if "[[hd-context]]" in soul_prompt:
            soul_prompt = soul_prompt.replace(
                "[[hd-context]]",
                f"[[hd-context]]\n{hd_context}\n[[/hd-context]]"
            )
        else:
            # Insert before Core Instructions if present
            if "## Core Instructions" in soul_prompt:
                soul_prompt = soul_prompt.replace(
                    "## Core Instructions",
                    f"## Human Design Context\n{hd_context}\n\n## Core Instructions"
                )
            else:
                soul_prompt = soul_prompt + f"\n\n{hd_context}\n"

        return soul_prompt

    def _generate_natal_block(self, chart: dict, derived: dict) -> str:
        var = chart.get("variable", {})
        cross = chart.get("cross", {})

        return f"""You are a **{derived['type']}** with **{derived['authority']}** authority and **{derived['profile']}** profile.
Your incarnation cross is: **{cross.get('cross_type', 'Unknown')}**.

**Defined Centers**: {', '.join(derived['defined_centers'])}
**Open Centers**: {', '.join(derived['open_centers'])}
**Active Channels**: {', '.join(derived['channels'])}

**Variable**:
- Motivation: {var.get('motivation', '?')} (Left=strategic goals / Right=inspired vision)
- Cognition: {var.get('cognition', '?')} (Left=detail focus / Right=pattern perception)
- Environment: {var.get('environment', '?')} (Left=fixed base / Right=variety needed)
- Perspective: {var.get('perspective', '?')} (Left=personal purpose / Right=collective purpose)

**Strategy**: {derived['strategy']}
When you follow your strategy, you feel: {derived.get('signature', 'aligned')}
When you ignore it, you feel: {derived['not_self_theme']}"""

    def _generate_natal_summary(self, derived: dict) -> str:
        return f"Natal: {derived['type']}/{derived['authority']}/{derived['profile']} — Strategy: {derived['strategy']}"

    def _generate_current_block(self, agent_id: str, chart: dict, derived: dict) -> str:
        daily = self.transits.get_daily_transits()
        lines = []

        solar = daily.get("sun")
        if solar:
            impact = self.transits.calculate_impact(solar, chart)
            lines.append(f"**Solar Transit**: Gate {solar.gate} in {solar.center} — {impact.message}")

        lunar = daily.get("moon")
        if lunar:
            lines.append(f"**Lunar Transit**: Gate {lunar.gate} in {lunar.center} — emotional atmosphere today")

        # Check for conditioning transits
        for planet, transit in daily.items():
            if planet in ("sun", "moon"):
                continue
            impact = self.transits.calculate_impact(transit, chart)
            if impact.type == "conditioning":
                lines.append(f"⚠️ **{planet.title()} Transit**: {impact.message}")

        if not lines:
            lines.append("No significant transits today. Your natal design is the primary influence.")

        return "\n".join(lines)

    def _generate_life_block(self, agent_id: str, derived: dict) -> str:
        # In production, this would read from agent's life history
        # For now, default to experimentation phase
        return """Current phase: **Experimentation** (early life)
Phase guidance: Everything is trial and error. Fail publicly — your failures are data."""

    def _inject_placeholder(self, soul_prompt: str) -> str:
        placeholder = "(Human Design chart not yet calculated for this agent)"
        if "[[hd-context]]" in soul_prompt:
            return soul_prompt.replace("[[hd-context]]", f"[[hd-context]]\n{placeholder}\n[[/hd-context]]")
        return soul_prompt
