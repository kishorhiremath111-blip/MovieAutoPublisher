import unittest
from datetime import datetime, timedelta, timezone

from ai_updates_publisher import ROTATION, is_fresh_story, make_hook, published_timestamp, story_interest_score


class StorySelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)

    def test_parses_rss_date(self):
        parsed = published_timestamp("Tue, 20 Oct 2026 10:00:00 GMT")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 10)
        self.assertEqual(parsed.day, 20)

    def test_parses_iso_date(self):
        parsed = published_timestamp("2026-10-19T10:00:00Z")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.day, 19)

    def test_recent_story_passes_freshness_gate(self):
        story = {"published": (self.now - timedelta(days=2)).isoformat()}
        self.assertTrue(is_fresh_story(story, now=self.now, max_age_days=14))

    def test_stale_story_fails_freshness_gate(self):
        story = {"published": (self.now - timedelta(days=30)).isoformat()}
        self.assertFalse(is_fresh_story(story, now=self.now, max_age_days=14))

    def test_undated_story_fails_freshness_gate(self):
        self.assertFalse(is_fresh_story({"published": ""}, now=self.now))

    def test_curiosity_headline_scores_above_generic_headline(self):
        curious = {
            "category": "FACTS",
            "title": "Scientists discover a rare clue hidden beneath the ocean",
            "summary": "Researchers describe evidence from a new study."
        }
        generic = {
            "category": "FACTS",
            "title": "Researchers publish a report about the ocean",
            "summary": "Researchers describe evidence from a new study."
        }
        self.assertGreater(story_interest_score(curious), story_interest_score(generic))


    def test_gen_x_rotation_only_uses_ai_science_and_anime(self):
        self.assertTrue(set(ROTATION).issubset({"AI", "SCIENCE", "ANIME"}))
        self.assertEqual(set(ROTATION), {"AI", "SCIENCE", "ANIME"})

    def test_spoken_hook_uses_the_actual_story_title(self):
        story = {"category": "SPACE", "title": "A strange signal from a distant planet"}
        self.assertIn(story["title"], make_hook(story))
        self.assertTrue(make_hook(story).endswith("."))


if __name__ == "__main__":
    unittest.main()
