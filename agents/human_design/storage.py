"""
DaemonCraft Human Design — Chart Storage

Persists HD charts to disk and caches derived properties.
"""

import hashlib
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional


class HDChartStorage:
    """
    Storage for Human Design charts per agent.

    Layout:
        ~/.local/share/daemoncraft/<cast>/hd_charts/
            <agent_id>.json          # Natal chart
            .cache/
                <agent_id>_derived.json    # Cached derived properties
                daily_transits/
                    YYYY-MM-DD.json        # Daily transit cache
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(self, cast_name: str = "default"):
        self.base_path = Path.home() / ".local" / "share" / "daemoncraft" / cast_name / "hd_charts"
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.cache_path = self.base_path / ".cache"
        self.cache_path.mkdir(exist_ok=True)
        self.transit_cache_path = self.cache_path / "daily_transits"
        self.transit_cache_path.mkdir(exist_ok=True)

    def save(self, agent_id: str, chart: dict, backup_old: bool = True) -> Path:
        """
        Save a chart to disk. Optionally backup existing chart.
        """
        chart_file = self.base_path / f"{agent_id}.json"

        # Backup if exists
        if backup_old and chart_file.exists():
            old = json.loads(chart_file.read_text())
            old_version = old.get("schema_version", "unknown")
            backup = self.base_path / f"{agent_id}_v{old_version}.json"
            backup.write_text(chart_file.read_text(), encoding="utf-8")

        # Add metadata
        chart["agent_id"] = agent_id
        chart["schema_version"] = self.SCHEMA_VERSION
        chart["saved_at"] = datetime.utcnow().isoformat()
        chart["digest"] = self._compute_digest(chart)

        # Write
        chart_file.write_text(
            json.dumps(chart, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Invalidate derived cache
        self._invalidate_cache(agent_id)

        return chart_file

    def load(self, agent_id: str) -> dict:
        """Load a chart. Verify integrity."""
        chart_file = self.base_path / f"{agent_id}.json"

        if not chart_file.exists():
            raise FileNotFoundError(f"No HD chart found for agent '{agent_id}'")

        chart = json.loads(chart_file.read_text())

        # Verify digest
        stored = chart.pop("digest", None)
        computed = self._compute_digest(chart)
        if stored and stored != computed:
            raise ValueError(f"Chart integrity check failed for '{agent_id}'")

        return chart

    def load_or_create(self, agent_id: str, calculator=None, birth_dt=None) -> dict:
        """Load if exists, or create using calculator."""
        try:
            return self.load(agent_id)
        except FileNotFoundError:
            if calculator is None:
                raise ValueError("No chart exists and no calculator provided")

            raw = calculator.calculate_for_agent(agent_id, birth_dt)
            from .types import CompleteChartBuilder
            chart = CompleteChartBuilder.build(raw)
            self.save(agent_id, chart)
            return chart

    def get_derived(self, agent_id: str) -> dict:
        """
        Load cached derived properties, or compute from chart.
        """
        cache_file = self.cache_path / f"{agent_id}_derived.json"

        if cache_file.exists():
            return json.loads(cache_file.read_text())

        chart = self.load(agent_id)

        from .constants import TYPE_STRATEGIES, TYPE_NOT_SELF, TYPE_SIGNATURES

        derived = {
            "agent_id": agent_id,
            "type": chart.get("type", "Unknown"),
            "authority": chart.get("authority", "none"),
            "profile": chart.get("profile", "1/1"),
            "variable": chart.get("variable", {}),
            "cross": chart.get("cross", {}),
            "defined_centers": chart.get("defined_centers", []),
            "open_centers": chart.get("open_centers", []),
            "channels": chart.get("channels", []),
            "strategy": TYPE_STRATEGIES.get(chart.get("type"), "unknown"),
            "not_self_theme": TYPE_NOT_SELF.get(chart.get("type"), "unknown"),
            "signature": TYPE_SIGNATURES.get(chart.get("type"), "unknown"),
            "computed_at": datetime.utcnow().isoformat(),
        }

        cache_file.write_text(json.dumps(derived, indent=2), encoding="utf-8")
        return derived

    def get_transit_cache(self, date: datetime) -> Optional[dict]:
        """Load cached transit report for a date."""
        cache_file = self.transit_cache_path / f"{date.strftime('%Y-%m-%d')}.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text())
        return None

    def save_transit_cache(self, date: datetime, transits: dict):
        """Cache transit report for a date."""
        cache_file = self.transit_cache_path / f"{date.strftime('%Y-%m-%d')}.json"
        cache_file.write_text(json.dumps(transits, indent=2), encoding="utf-8")

    def list_charts(self) -> list:
        """List all agent IDs with stored charts."""
        return [f.stem for f in self.base_path.glob("*.json") if not f.stem.startswith(".")]

    def delete(self, agent_id: str):
        """Delete chart and derived cache for an agent."""
        chart_file = self.base_path / f"{agent_id}.json"
        cache_file = self.cache_path / f"{agent_id}_derived.json"
        if chart_file.exists():
            chart_file.unlink()
        if cache_file.exists():
            cache_file.unlink()

    def _compute_digest(self, chart: dict) -> str:
        """SHA-256 of canonical JSON (excluding volatile metadata)."""
        canonical = {k: v for k, v in chart.items()
                     if k not in ("digest", "saved_at", "computed_at")}
        data = json.dumps(canonical, sort_keys=True).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def _invalidate_cache(self, agent_id: str):
        """Remove derived cache when chart changes."""
        cache_file = self.cache_path / f"{agent_id}_derived.json"
        if cache_file.exists():
            cache_file.unlink()
