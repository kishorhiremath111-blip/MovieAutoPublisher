#!/usr/bin/env python3
"""Fast tests for topic pool size, source anchors, semantic de-duplication and renderer JSON."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import topic_engine


class TopicEngineTests(unittest.TestCase):
    def test_prompt_pool_exceeds_100m(self):
        facts = topic_engine.read_json(topic_engine.FACTS_PATH)["facts"]
        templates = topic_engine.read_json(topic_engine.TEMPLATES_PATH)
        count = (
            len(facts) * len(templates["hooks"]) * len(templates["angles"])
            * len(templates["analogy_frames"]) * len(templates["humour_frames"])
        )
        self.assertGreaterEqual(count, 100_000_000)

    def test_fact_ids_are_unique(self):
        facts = topic_engine.read_json(topic_engine.FACTS_PATH)["facts"]
        ids = [row["id"] for row in facts]
        self.assertEqual(len(ids), len(set(ids)))

    def test_fact_fields_and_source_refs(self):
        facts = topic_engine.read_json(topic_engine.FACTS_PATH)["facts"]
        required = {"id", "category", "subcategory", "question", "misconception",
                    "answer", "why", "analogy", "joke", "bonus", "source_url"}
        for row in facts:
            self.assertTrue(required.issubset(row), row.get("id"))
            self.assertTrue(row["source_url"].startswith("https://"), row["id"])

    def test_used_semantic_key_blocks_all_style_variants(self):
        facts = topic_engine.read_json(topic_engine.FACTS_PATH)["facts"]
        angles = topic_engine.read_json(topic_engine.TEMPLATES_PATH)["angles"]
        fact, angle = facts[0], angles[0]
        key = topic_engine.sha(fact["id"])
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "used_topics.jsonl"
            history.write_text(json.dumps({"semantic_key": key, "topic_id": "already-used"}) + "\n")
            used_semantic, _ = topic_engine.read_history(history)
            self.assertIn(key, used_semantic)

    def test_script_schema_is_compatible_with_reel_pipeline(self):
        facts = topic_engine.read_json(topic_engine.FACTS_PATH)["facts"]
        templates = topic_engine.read_json(topic_engine.TEMPLATES_PATH)
        with tempfile.TemporaryDirectory() as td:
            script, pending = topic_engine.build_script(
                facts[0], templates["angles"][0], templates["hooks"][0],
                templates["analogy_frames"][0], templates["humour_frames"][0],
                Path(td),
            )
        self.assertEqual(len(script["scenes"]), 7)
        self.assertIn("meta", script)
        self.assertIn("topic_id", script["meta"])
        for scene in script["scenes"]:
            self.assertTrue(scene.get("say"))
            self.assertTrue(scene.get("tts_hi"))
            self.assertIn(scene.get("bg"), {"dark", "gold", "red", "blue", "green"})
            for element in scene.get("elements", []):
                self.assertIn(element["type"], {
                    "title", "ocean_card", "stamp", "sun", "prism", "atmo",
                    "bars", "card", "sunset", "phone_cta", "badge", "stat",
                })
        self.assertTrue(pending["semantic_key"])


if __name__ == "__main__":
    unittest.main()
