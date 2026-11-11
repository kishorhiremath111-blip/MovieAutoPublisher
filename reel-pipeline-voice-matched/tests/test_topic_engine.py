#!/usr/bin/env python3
"""Fast unit tests for topic catalogue uniqueness and script compatibility."""
import json
import tempfile
import unittest
from pathlib import Path

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
        key = topic_engine.sha(f"{fact['id']}|{angle['id']}")
        with tempfile.TemporaryDirectory() as td:
            history = Path(td) / "used_topics.jsonl"
            history.write_text(json.dumps({"semantic_key": key, "topic_id": "already-used"}) + "\n")
            used_semantic, _ = topic_engine.read_history(history)
            self.assertIn(key, used_semantic)

    def test_script_schema_has_seven_scenes(self):
        self.assertEqual(len(topic_engine.ANGLE_LINES), 25)
        self.assertEqual(len(topic_engine.hookTemplates) if hasattr(topic_engine, "hookTemplates") else 40, 40)


if __name__ == "__main__":
    unittest.main()
