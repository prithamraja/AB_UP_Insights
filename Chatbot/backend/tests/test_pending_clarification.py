import unittest

from query_router import router
from query_router.context_store import ContextStore
from query_router.models import (
    EntityNotFound,
    ExtractedEntity,
    PendingClarification,
    RouteTier,
)
from query_router.router import _fill_slots_or_clarify, serve_pending_answer
from query_router.zones import question_chips


class StubValidator:
    def __init__(self, known: dict[str, list[str]]):
        self.known = known

    def validate(self, raw, entity_type):
        for value in self.known.get(entity_type, []):
            if value.lower() == str(raw).strip().lower():
                return ExtractedEntity(
                    slot_name=entity_type, raw_value=str(raw), resolved_value=value,
                    entity_type=entity_type, confidence="exact",
                )
        raise EntityNotFound(entity_type, str(raw), self.known.get(entity_type, [])[:3])


class FakeConn:
    def __init__(self, columns, rows):
        self.description = columns
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def execute(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return self

    def fetchmany(self, n):
        return self._rows


TEMPLATE_MAP = {
    "TX1": {
        "abstract_question": "What is the claims summary for {district}?",
        "date_filter": None,
        "sql_template": "SELECT district, cases FROM t WHERE district = ?",
        "param_slots": [{"name": "district", "entity_type": "district", "position": 1}],
    },
    "TX2": {
        "abstract_question": "Enrolment in {block} of {district}?",
        "date_filter": None,
        "sql_template": "SELECT * FROM t WHERE block = ? AND district = ?",
        "param_slots": [
            {"name": "block", "entity_type": "block", "position": 1},
            {"name": "district", "entity_type": "district", "position": 2},
        ],
    },
}

VALIDATOR = StubValidator({"district": ["Lucknow", "Agra"], "block": ["Mohanlalganj"]})


class FillSlotsTests(unittest.TestCase):
    def _fill(self, query_id, slot_type, raw):
        return _fill_slots_or_clarify(
            query_id, slot_type, raw, VALIDATOR, "original query", "original query", 0.0
        )

    def test_all_slots_validate(self):
        validated, clarify = self._fill("TX1", {"district": "district"}, {"district": "lucknow"})
        self.assertIsNone(clarify)
        self.assertEqual(validated[0].resolved_value, "Lucknow")

    def test_missing_slot_pauses_with_pending_state(self):
        _, clarify = self._fill(
            "TX2", {"block": "block", "district": "district"},
            {"block": "Mohanlalganj", "district": None},
        )
        self.assertEqual(clarify.tier, RouteTier.CLARIFY)
        self.assertEqual(clarify.clarification.reason, "missing_parameter")
        self.assertEqual(clarify.pending.query_id, "TX2")
        self.assertEqual(clarify.pending.missing_slot, "district")
        self.assertEqual(clarify.pending.filled, {"block": "Mohanlalganj"},
                         "already-validated slots must survive into pending state")
        self.assertEqual(clarify.pending.original_query, "original query")

    def test_unknown_entity_pauses_with_pending_and_chips(self):
        _, clarify = self._fill("TX1", {"district": "district"}, {"district": "Lucknoww"})
        self.assertEqual(clarify.clarification.reason, "unknown_entity")
        self.assertTrue(clarify.clarification.options)
        self.assertEqual(clarify.pending.missing_slot, "district")


class ServePendingAnswerTests(unittest.TestCase):
    def setUp(self):
        router._result_cache.clear()

    def _pending(self, query_id, missing, filled):
        return PendingClarification(
            query_id=query_id, missing_slot=missing,
            slot_type=missing, filled=filled,
            original_query="gender split for women in lucknow",
        )

    def test_short_answer_resumes_and_executes_the_pending_template(self):
        conn = FakeConn(["district", "cases"], [("Lucknow", 42)])
        result = serve_pending_answer(
            self._pending("TX1", "district", {}), "lucknow",
            template_map=TEMPLATE_MAP, cache_conn=conn, validator=VALIDATOR,
            dashboard_results={}, dashboard_questions={},
            start_date=None, end_date=None,
        )
        self.assertEqual(result.tier, RouteTier.TIER2_TEMPLATE)
        self.assertEqual(conn.last_params, ["Lucknow"])
        self.assertEqual(result.result, [{"district": "Lucknow", "cases": 42}])
        self.assertEqual(result.query_description, "What is the claims summary for Lucknow?")
        self.assertEqual(result.raw_query, "gender split for women in lucknow",
                         "the answer resumes the ORIGINAL question")

    def test_chained_clarification_when_another_slot_is_still_missing(self):
        result = serve_pending_answer(
            self._pending("TX2", "block", {}), "Mohanlalganj",
            template_map=TEMPLATE_MAP, cache_conn=FakeConn([], []), validator=VALIDATOR,
            dashboard_results={}, dashboard_questions={},
            start_date=None, end_date=None,
        )
        self.assertEqual(result.tier, RouteTier.CLARIFY)
        self.assertEqual(result.pending.missing_slot, "district")
        self.assertEqual(result.pending.filled, {"block": "Mohanlalganj"})

    def test_unknown_template_raises(self):
        with self.assertRaises(ValueError):
            serve_pending_answer(
                self._pending("NOPE", "district", {}), "lucknow",
                template_map=TEMPLATE_MAP, cache_conn=FakeConn([], []), validator=VALIDATOR,
                dashboard_results={}, dashboard_questions={},
                start_date=None, end_date=None,
            )


class PendingStoreTests(unittest.TestCase):
    def test_take_is_one_shot(self):
        store = ContextStore()
        pending = PendingClarification(
            query_id="TX1", missing_slot="district", slot_type="district",
            filled={}, original_query="q",
        )
        store.set_pending("s", pending)
        self.assertEqual(store.take_pending("s").query_id, "TX1")
        self.assertIsNone(store.take_pending("s"), "consumed on first take")

    def test_pending_expires_with_inactivity(self):
        now = [0.0]
        store = ContextStore(inactivity_timeout_seconds=10, clock=lambda: now[0])
        store.set_pending("s", PendingClarification(
            query_id="TX1", missing_slot="district", slot_type="district",
            filled={}, original_query="q",
        ))
        now[0] = 11
        self.assertIsNone(store.take_pending("s"))

    def test_reset_clears_pending(self):
        store = ContextStore()
        store.set_pending("s", PendingClarification(
            query_id="TX1", missing_slot="district", slot_type="district",
            filled={}, original_query="q",
        ))
        store.reset("s")
        self.assertIsNone(store.take_pending("s"))


class FilledChipTests(unittest.TestCase):
    def test_known_entities_are_substituted_into_chips(self):
        chips = question_chips(
            [("T09", "What is the gender breakdown of beneficiaries in {district}?", 0.5)],
            limit=3,
            fill={"district": "Lucknow"},
        )
        self.assertEqual(
            chips[0].send_text,
            "What is the gender breakdown of beneficiaries in Lucknow?",
        )

    def test_unknown_slots_stay_readable(self):
        chips = question_chips(
            [("T11", "Enrolment in {block} of {district}?", 0.5)],
            limit=3,
            fill={"district": "Lucknow"},
        )
        self.assertEqual(chips[0].send_text, "Enrolment in a block of Lucknow?")


if __name__ == "__main__":
    unittest.main()
