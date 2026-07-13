import unittest

from query_router.config import (
    CLARIFY_SCORE_MARGIN,
    CLARIFY_UPPER_THRESHOLD,
    NO_MATCH_LOWER_THRESHOLD,
)
from query_router.echo import echo_answer
from query_router.followup_classifier import (
    catalog_question_patterns,
    matches_catalog_question,
    parse_decision,
)
from query_router.models import (
    ActiveFilter,
    ColumnMetadata,
    ColumnType,
    ContextFrame,
    ResultSetReference,
    RouteResult,
    RouteTier,
    TimeRange,
)
from query_router.suggestions import (
    ELICITATION_MOVES,
    FAMILY_MOVES,
    elicitation_chips,
    suggest_followups,
)
from query_router.template_catalog import TEMPLATE_CATALOG
from query_router.zones import corrected_query_chips, question_chips, zone


def make_frame(
    template_id: str = "T02",
    bound_params: dict | None = None,
    grain: str = "day",
) -> ContextFrame:
    params = {"district": "Agra"} if bound_params is None else bound_params
    return ContextFrame(
        template_id=template_id,
        template_question="What is the claims summary for {district}?",
        bound_params=params,
        active_filters=[
            ActiveFilter(dimension=k, value=v)
            for k, v in params.items() if k not in ("year", "month")
        ],
        time_range=TimeRange(
            start="2025-01-01" if grain == "day" else None,
            end="2025-12-31" if grain == "day" else None,
            grain=grain,
        ),
        grouping_dimension=None,
        result_set=ResultSetReference(
            id="rs_x", row_count=1,
            columns=[ColumnMetadata(name="total_cases", column_type=ColumnType.ADDITIVE_COUNT)],
        ),
    )


class ZoneTests(unittest.TestCase):
    def test_below_lower_threshold_is_no_match(self):
        self.assertEqual(zone([]), "no_match")
        self.assertEqual(zone([NO_MATCH_LOWER_THRESHOLD - 0.01, 0.1]), "no_match")

    def test_tight_top_two_below_upper_is_ambiguous(self):
        top = CLARIFY_UPPER_THRESHOLD - 0.05
        self.assertEqual(zone([top, top - CLARIFY_SCORE_MARGIN / 2]), "ambiguous")

    def test_clear_winner_proceeds(self):
        self.assertEqual(zone([CLARIFY_UPPER_THRESHOLD + 0.1, 0.2]), "proceed")
        top = CLARIFY_UPPER_THRESHOLD - 0.05
        self.assertEqual(zone([top, top - CLARIFY_SCORE_MARGIN * 3]), "proceed")

    def test_question_chips_are_readable_and_deduplicated(self):
        chips = question_chips(
            [
                ("T01", "How many beneficiaries are enrolled in {district}?", 0.5),
                ("T01b", "How many beneficiaries are enrolled in {district}?", 0.4),
                ("T21", "What is the utilization of {specialty} across UP?", 0.3),
            ],
            limit=3,
        )
        self.assertEqual(len(chips), 2)
        self.assertNotIn("{", chips[0].label)
        self.assertIn("a district", chips[0].send_text)

    def test_corrected_query_chips_swap_the_entity_in_place(self):
        chips = corrected_query_chips(
            "claims in Lucknoww this year", "Lucknoww", ["Lucknow", "Ballia"], 3
        )
        self.assertEqual(chips[0].send_text, "claims in Lucknow this year")
        self.assertEqual(chips[1].label, "Ballia")


class SuggestionTests(unittest.TestCase):
    def test_every_authored_move_is_an_executable_template(self):
        for moves in list(FAMILY_MOVES.values()) + list(ELICITATION_MOVES.values()):
            for qid in moves:
                self.assertIn(qid, TEMPLATE_CATALOG, f"{qid} is not in the catalog")

    def test_followup_chips_are_prefilled_and_capped(self):
        chips = suggest_followups(make_frame())
        self.assertTrue(0 < len(chips) <= 3)
        for chip in chips:
            self.assertNotIn("{", chip.send_text, "chip must be fully pre-filled")
            self.assertIn("Agra", chip.send_text)

    def test_current_template_is_not_suggested(self):
        chips = suggest_followups(make_frame("T02"))
        claims_summary = TEMPLATE_CATALOG["T02"]["abstract_question"].format(district="Agra")
        self.assertNotIn(claims_summary, [c.send_text for c in chips])

    def test_unfillable_targets_are_skipped(self):
        # A specialty-only frame can't fill district templates
        chips = suggest_followups(make_frame("T21", {"specialty": "CARD"}))
        for chip in chips:
            self.assertNotIn("{", chip.send_text)

    def test_elicitation_chips_for_broad_district_question(self):
        chips = elicitation_chips("district", "Agra")
        self.assertEqual(len(chips), 4)
        for chip in chips:
            self.assertIn("Agra", chip.send_text)


class FollowupParseTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_frame()

    def test_entity_swap_is_a_frame_edit(self):
        decision = parse_decision(
            {"kind": "frame_edit", "slot": "district", "value": "Lucknow"}, self.frame
        )
        self.assertEqual(decision.kind, "frame_edit")
        self.assertEqual(decision.edit.slot, "district")
        self.assertEqual(decision.edit.value, "Lucknow")

    def test_swap_of_unknown_slot_degrades_to_new_question(self):
        decision = parse_decision(
            {"kind": "frame_edit", "slot": "hospital", "value": "X"}, self.frame
        )
        self.assertEqual(decision.kind, "new_question")

    def test_time_edit_carries_iso_dates(self):
        decision = parse_decision(
            {"kind": "frame_edit", "start_date": "2024-01-01", "end_date": "2024-12-31"},
            self.frame,
        )
        self.assertEqual(decision.kind, "frame_edit")
        self.assertEqual(decision.edit.start_date, "2024-01-01")
        self.assertIsNone(decision.edit.slot)

    def test_operation_kind_projects_to_closed_set(self):
        decision = parse_decision(
            {"kind": "operation", "operation": "sum", "column": "total_cases"}, self.frame
        )
        self.assertEqual(decision.kind, "operation")
        self.assertEqual(decision.operation.operation, "sum")

        bad = parse_decision(
            {"kind": "operation", "operation": "regression"}, self.frame
        )
        self.assertEqual(bad.kind, "new_question")

    def test_unknown_kind_is_new_question(self):
        self.assertEqual(parse_decision({}, self.frame).kind, "new_question")

    def test_noop_entity_swap_degrades_to_new_question(self):
        # "district → Agra" when district already IS Agra changes nothing:
        # the LLM latched onto an entity in a complete question. Re-route.
        decision = parse_decision(
            {"kind": "frame_edit", "slot": "district", "value": "Agra"}, self.frame
        )
        self.assertEqual(decision.kind, "new_question")

    def test_noop_swap_check_ignores_case_and_whitespace(self):
        decision = parse_decision(
            {"kind": "frame_edit", "slot": "district", "value": "  agra "}, self.frame
        )
        self.assertEqual(decision.kind, "new_question")

    def test_noop_swap_with_time_edit_still_applies_the_time_edit(self):
        decision = parse_decision(
            {"kind": "frame_edit", "slot": "district", "value": "Agra",
             "start_date": "2024-01-01", "end_date": "2024-12-31"},
            self.frame,
        )
        self.assertEqual(decision.kind, "frame_edit")
        self.assertIsNone(decision.edit.slot)
        self.assertEqual(decision.edit.start_date, "2024-01-01")


class CatalogQuestionGuardTests(unittest.TestCase):
    """Messages that are word-for-word catalog questions bypass the follow-up
    classifier — they can never be frame edits or operations."""

    PATTERNS = catalog_question_patterns([
        "How many hospitals are empanelled in {district}?",
        "What is the monthly case trend in {district}?",
        "What is the claims summary for {district}?",
        "What is the average claim size by specialty?",  # slotless (dashboard)
    ])

    def test_filled_chip_text_matches(self):
        self.assertTrue(matches_catalog_question(
            "How many hospitals are empanelled in Lucknow?", self.PATTERNS
        ))
        self.assertTrue(matches_catalog_question(
            "What is the monthly case trend in Gautam Buddha Nagar?", self.PATTERNS
        ))

    def test_match_ignores_case_punctuation_and_spacing(self):
        self.assertTrue(matches_catalog_question(
            "  how many hospitals are  empanelled in lucknow ", self.PATTERNS
        ))

    def test_slotless_question_matches_exactly(self):
        self.assertTrue(matches_catalog_question(
            "What is the average claim size by specialty?", self.PATTERNS
        ))

    def test_paraphrases_do_not_match(self):
        for message in (
            "how many hospitals do we have in Lucknow?",
            "hospitals empanelled?",
            "total?",
            "what about Lucknow?",
        ):
            self.assertFalse(
                matches_catalog_question(message, self.PATTERNS), message
            )

    def test_every_real_catalog_question_matches_its_own_filled_form(self):
        import re as _re

        questions = [t["abstract_question"] for t in TEMPLATE_CATALOG.values()]
        patterns = catalog_question_patterns(questions)
        for q in questions:
            filled = _re.sub(r"\{\w+?\}", "Lucknow", q)
            self.assertTrue(
                matches_catalog_question(filled, patterns),
                f"catalog question failed to match its own filled form: {filled}",
            )


class EchoTests(unittest.TestCase):
    def test_echo_is_just_the_resolved_question(self):
        frame = make_frame(bound_params={"district": "Lucknow", "hospital_type": "PRIVATE"})
        result = RouteResult(
            tier=RouteTier.TIER2_TEMPLATE,
            raw_query="q", normalized_query="q", total_latency_ms=1,
            query_id="T02",
            query_description="What is the claims summary for Lucknow?",
            context_frame=frame,
        )
        # Filters/period are shown in the breadcrumb, not repeated in prose.
        self.assertEqual(echo_answer(result), "What is the claims summary for Lucknow?")

    def test_echo_ignores_all_time_grain_too(self):
        frame = make_frame(grain="all_time")
        result = RouteResult(
            tier=RouteTier.TIER2_TEMPLATE,
            raw_query="q", normalized_query="q", total_latency_ms=1,
            query_id="T01", query_description="Enrolment in Agra",
            context_frame=frame,
        )
        self.assertEqual(echo_answer(result), "Enrolment in Agra")


class ContextPopTests(unittest.TestCase):
    def test_pop_restores_previous_frame_and_rows(self):
        from query_router.context_store import ContextStore

        store = ContextStore()
        first = make_frame("T01", {"district": "Agra"})
        second = make_frame("T02", {"district": "Lucknow"})
        store.set_frame("s", first, rows=[{"total_cases": 1}])
        store.set_frame("s", second, rows=[{"total_cases": 2}])

        popped = store.pop("s")
        self.assertIsNotNone(popped)
        frame, rows = popped
        self.assertEqual(frame.template_id, "T01")
        self.assertEqual(rows, [{"total_cases": 1}])
        self.assertEqual(frame.history_stack, [])

        current = store.get_with_rows("s")
        self.assertEqual(current[0].template_id, "T01")
        self.assertIsNone(store.pop("s"), "no further history to pop")


if __name__ == "__main__":
    unittest.main()
