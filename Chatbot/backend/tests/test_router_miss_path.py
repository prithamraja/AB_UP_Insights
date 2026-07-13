"""Regression: nearest-question chips on the miss path must keep entities the
user already gave — "…in Lucknow" must not degrade to "…in a district?".
The fill previously happened only on the reranker near-miss branch, so
zone-level no-match chips rendered with bare placeholders."""
import time
import unittest
from types import SimpleNamespace

from query_router import router


TEMPLATE_MAP = {
    "Q7": {"param_slots": [{"name": "block", "entity_type": "block"}]},
    "Q9": {"param_slots": [{"name": "block", "entity_type": "block"}]},
}

SCORED = [
    ("Q7", "How many claims were filed in {block}?", 0.22),
    ("Q9", "What is enrolment by gender in {block}?", 0.18),
]


class StubValidator:
    def validate(self, value, entity_type):
        if entity_type == "block" and value:
            return SimpleNamespace(resolved_value="Baruasagar")
        raise ValueError(f"unknown {entity_type}: {value}")


class NoMatchChipFillTests(unittest.TestCase):
    def setUp(self):
        self._real_extract = router.extract_entities

        def fake_extract(user_query, slots, client, **kwargs):
            found = {}
            if "block" in slots:
                found["block"] = "baruasagar"
            return found  # never a district → elicitation is skipped

        router.extract_entities = fake_extract

    def tearDown(self):
        router.extract_entities = self._real_extract

    def _run(self):
        return router._no_match(
            SCORED,
            "how many women in baruasagar block",
            "how many women in baruasagar block",
            time.monotonic(),
            validator=StubValidator(),
            openai_client=object(),
            template_map=TEMPLATE_MAP,
        )

    def test_miss_chips_are_prefilled_with_user_entities(self):
        result = self._run()
        self.assertEqual(result.clarification.reason, "no_match")
        labels = [chip.label for chip in result.clarification.options]
        self.assertTrue(labels)
        for label in labels:
            self.assertNotIn("{block}", label)
            self.assertNotIn("a block", label)
        self.assertIn("How many claims were filed in Baruasagar?", labels)

    def test_extraction_failure_degrades_to_placeholders(self):
        def broken_extract(user_query, slots, client, **kwargs):
            raise RuntimeError("LLM down")

        router.extract_entities = broken_extract
        result = self._run()
        labels = [chip.label for chip in result.clarification.options]
        self.assertIn("How many claims were filed in a block?", labels)


if __name__ == "__main__":
    unittest.main()
