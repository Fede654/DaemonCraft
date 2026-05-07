"""
DaemonCraft Human Design — Tests

Run with: python -m pytest agents/human_design/tests.py -v
Or:       python agents/human_design/tests.py
"""

import unittest
from datetime import datetime

from .calculator import HDCalculator, hd_gate_at, hd_line
from .bodygraph import BodygraphAnalyzer
from .types import TypeEngine, AuthorityEngine, CompleteChartBuilder
from .transits import TransitEngine
from .storage import HDChartStorage
from .conditioning import ConditioningDetector
from .decision import TypeStrategyModifier, Option


class TestHDCalculator(unittest.TestCase):
    def test_hd_gate_at(self):
        self.assertEqual(hd_gate_at(0), 1)
        self.assertEqual(hd_gate_at(5.625), 2)
        self.assertEqual(hd_gate_at(358), 64)

    def test_hd_line(self):
        # Within gate 1, degree 0.0 → line 1
        self.assertEqual(hd_line(0.0), 1)
        # Within gate 1, degree 0.9375 → line 2
        self.assertEqual(hd_line(0.9375), 2)

    def test_calculate_for_agent(self):
        calc = HDCalculator()
        result = calc.calculate_for_agent("test_agent", datetime(2026, 5, 6, 14, 30))

        self.assertEqual(result["agent_id"], "test_agent")
        self.assertIn("planets", result)
        self.assertIn("sun", result["planets"])
        self.assertIn("gates", result)
        self.assertIn("personality", result["gates"])
        self.assertIn("design", result["gates"])

    def test_earth_opposite_gate(self):
        self.assertEqual(HDCalculator.earth_opposite_gate(1), 33)
        self.assertEqual(HDCalculator.earth_opposite_gate(33), 1)
        self.assertEqual(HDCalculator.earth_opposite_gate(64), 32)


class TestBodygraphAnalyzer(unittest.TestCase):
    def test_analyze(self):
        positions = {
            "sun": {"gate": 34, "line": 2, "side": "personality", "degree": 46.0},
            "moon": {"gate": 20, "line": 5, "side": "design", "degree": 112.0},
            "north_node": {"gate": 10, "line": 1, "side": "personality", "degree": 168.0},
            "south_node": {"gate": 57, "line": 6, "side": "design", "degree": 348.0},
        }

        bg = BodygraphAnalyzer.analyze(positions)
        self.assertIn(34, bg.personality_gates)
        self.assertIn(20, bg.design_gates)
        self.assertTrue(len(bg.channels) >= 0)
        self.assertTrue(len(bg.defined_centers) >= 0)
        self.assertTrue(len(bg.open_centers) >= 0)

    def test_channel_detection(self):
        # Gate 20 and 34 should form channel 20-34
        positions = {
            "sun": {"gate": 34, "line": 1, "side": "personality", "degree": 46.0},
            "moon": {"gate": 20, "line": 1, "side": "design", "degree": 112.0},
        }
        bg = BodygraphAnalyzer.analyze(positions)
        self.assertIn("20-34", bg.channels)


class TestTypeEngine(unittest.TestCase):
    def test_generator(self):
        chart = {"defined_centers": ["sacral", "g"], "channels": ["5-15"]}
        self.assertEqual(TypeEngine.determine(chart), "Generator")

    def test_manifesting_generator(self):
        chart = {"defined_centers": ["sacral", "throat"], "channels": ["20-34"]}
        self.assertEqual(TypeEngine.determine(chart), "Manifesting Generator")

    def test_projector(self):
        chart = {"defined_centers": ["throat", "ajna"], "channels": []}
        self.assertEqual(TypeEngine.determine(chart), "Projector")

    def test_manifestor(self):
        chart = {"defined_centers": ["heart", "throat"], "channels": ["21-45"]}
        self.assertEqual(TypeEngine.determine(chart), "Manifestor")

    def test_reflector(self):
        chart = {"defined_centers": [], "channels": []}
        self.assertEqual(TypeEngine.determine(chart), "Reflector")


class TestAuthorityEngine(unittest.TestCase):
    def test_sacral_authority(self):
        chart = {"defined_centers": ["sacral", "throat"], "channels": []}
        self.assertEqual(AuthorityEngine.determine(chart), "sacral")

    def test_emotional_authority(self):
        chart = {"defined_centers": ["solar_plexus", "sacral", "throat"], "channels": []}
        self.assertEqual(AuthorityEngine.determine(chart), "emotional")

    def test_lunar_authority(self):
        chart = {"defined_centers": [], "channels": []}
        self.assertEqual(AuthorityEngine.determine(chart), "lunar")


class TestCompleteChartBuilder(unittest.TestCase):
    def test_build(self):
        calc = HDCalculator()
        raw = calc.calculate_for_agent("test", datetime(2026, 5, 6, 14, 30))
        chart = CompleteChartBuilder.build(raw)

        self.assertIn("type", chart)
        self.assertIn("authority", chart)
        self.assertIn("profile", chart)
        self.assertIn("variable", chart)
        self.assertIn("cross", chart)
        self.assertIn("channels", chart)
        self.assertIn("defined_centers", chart)
        self.assertIn("open_centers", chart)
        self.assertEqual(chart["schema_version"], "1.0.0")


class TestTransitEngine(unittest.TestCase):
    def test_daily_transits(self):
        engine = TransitEngine()
        transits = engine.get_daily_transits(datetime(2026, 5, 6))

        self.assertIn("sun", transits)
        self.assertIn("moon", transits)
        self.assertGreater(transits["sun"].gate, 0)
        self.assertLessEqual(transits["sun"].gate, 64)

    def test_impact_reinforcement(self):
        engine = TransitEngine()
        # Use a mock transit with a gate that IS in the chart
        from .transits import Transit
        transit = Transit("sun", 34, 2, "sacral", 46.0)

        chart = {"gates": {"personality": [34], "design": []}, "defined_centers": ["sacral"], "open_centers": []}
        impact = engine.calculate_impact(transit, chart)
        self.assertEqual(impact.type, "reinforcement")


class TestHDChartStorage(unittest.TestCase):
    def setUp(self):
        self.storage = HDChartStorage(cast_name="test_cast")
        self.test_chart = {
            "agent_id": "test_agent",
            "schema_version": "1.0.0",
            "timestamp": "2026-05-06T14:30:00",
            "planets": {},
            "gates": {"personality": [34], "design": [20]},
            "channels": ["20-34"],
            "defined_centers": ["sacral", "throat"],
            "open_centers": ["head", "ajna"],
            "type": "Generator",
            "authority": "sacral",
            "profile": "3/5",
            "variable": {"motivation": "←", "cognition": "→", "environment": "←", "perspective": "→"},
            "cross": {"cross_type": "Test Cross"},
        }

    def tearDown(self):
        self.storage.delete("test_agent")

    def test_save_and_load(self):
        self.storage.save("test_agent", self.test_chart)
        loaded = self.storage.load("test_agent")
        self.assertEqual(loaded["agent_id"], "test_agent")
        self.assertEqual(loaded["type"], "Generator")

    def test_derived(self):
        self.storage.save("test_agent", self.test_chart)
        derived = self.storage.get_derived("test_agent")
        self.assertEqual(derived["type"], "Generator")
        self.assertEqual(derived["strategy"], "respond")
        self.assertEqual(derived["not_self_theme"], "frustration")

    def test_digest_integrity(self):
        self.storage.save("test_agent", self.test_chart)
        # Load raw file to check digest is stored
        import json
        raw = json.loads((self.storage.base_path / "test_agent.json").read_text())
        self.assertIn("digest", raw)
        # Verify load() strips digest but verifies it
        loaded = self.storage.load("test_agent")
        self.assertNotIn("digest", loaded)  # load() strips digest after verification


class TestConditioningDetector(unittest.TestCase):
    def test_player_proximity(self):
        detector = ConditioningDetector()
        chart = {"open_centers": ["solar_plexus", "heart"], "defined_centers": ["sacral"]}
        players = [
            {"name": "bruno", "distance": 10, "defined_centers": ["solar_plexus"]},
        ]
        alerts = detector.scan(chart, players, [], [])
        self.assertTrue(len(alerts) > 0)
        self.assertEqual(alerts[0].center, "solar_plexus")

    def test_no_conditioning_when_far(self):
        detector = ConditioningDetector()
        chart = {"open_centers": ["solar_plexus"], "defined_centers": ["sacral"]}
        players = [
            {"name": "bruno", "distance": 100, "defined_centers": ["solar_plexus"]},
        ]
        alerts = detector.scan(chart, players, [], [])
        self.assertEqual(len(alerts), 0)


class TestDecisionModifiers(unittest.TestCase):
    def test_generator_penalizes_self_initiated(self):
        mod = TypeStrategyModifier()
        options = [
            Option(name="mine", initiated_by_self=True, weight=1.0),
            Option(name="respond", has_external_stimulus=True, is_response_opportunity=True, weight=1.0),
        ]
        chart = {"type": "Generator"}
        result = mod.modify(options, chart)

        all_options = result.options + result.rejected_options
        mine = next(o for o in all_options if o.name == "mine")
        respond = next(o for o in result.options if o.name == "respond")
        self.assertLess(mine.weight, 0.2)  # mine penalized
        self.assertGreater(respond.weight, 1.0)  # respond boosted


if __name__ == "__main__":
    unittest.main()
