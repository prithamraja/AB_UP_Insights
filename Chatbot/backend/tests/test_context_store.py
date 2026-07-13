import unittest

from query_router.context_store import ContextStore, build_context_frame
from query_router.models import (
    ColumnMetadata,
    ColumnType,
    ExtractedEntity,
    RouteResult,
    RouteTier,
)


def make_result(query_id: str, district: str = "Agra") -> RouteResult:
    return RouteResult(
        tier=RouteTier.TIER2_TEMPLATE,
        entities=[
            ExtractedEntity(
                slot_name="district",
                raw_value=district,
                resolved_value=district,
                entity_type="district",
                confidence="exact",
            )
        ],
        result=[{"district_name": district, "total_cases": 12}],
        raw_query=f"claims in {district}",
        normalized_query=f"claims in {district.lower()}",
        total_latency_ms=1,
        query_id=query_id,
        start_date="2025-01-01",
        end_date="2025-12-31",
        date_filter_applied=True,
    )


DECLARED_COLUMNS = [
    ColumnMetadata(name="district_name", column_type=ColumnType.DIMENSION),
    ColumnMetadata(name="total_cases", column_type=ColumnType.ADDITIVE_COUNT),
]


class ContextFrameTests(unittest.TestCase):
    def test_builds_renderable_frame(self):
        frame = build_context_frame(make_result("T02"), DECLARED_COLUMNS)

        self.assertIsNotNone(frame)
        self.assertEqual(frame.template_id, "T02")
        self.assertEqual(frame.bound_params, {"district": "Agra"})
        self.assertEqual(frame.active_filters[0].value, "Agra")
        self.assertEqual(frame.time_range.grain, "day")
        self.assertEqual(frame.grouping_dimension, "district_name")
        self.assertEqual(frame.result_set.row_count, 1)
        self.assertEqual(
            frame.result_set.columns[1].column_type,
            ColumnType.ADDITIVE_COUNT,
        )

    def test_caps_history_and_expires_inactive_session(self):
        now = [0.0]
        store = ContextStore(
            inactivity_timeout_seconds=10,
            history_depth=2,
            clock=lambda: now[0],
        )

        first = build_context_frame(make_result("T01", "Agra"), DECLARED_COLUMNS)
        second = build_context_frame(make_result("T02", "Lucknow"), DECLARED_COLUMNS)
        third = build_context_frame(make_result("T03", "Varanasi"), DECLARED_COLUMNS)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNotNone(third)

        store.set_frame("session", first)
        now[0] = 1
        store.set_frame("session", second)
        now[0] = 2
        current = store.set_frame("session", third)

        self.assertEqual([item.template_id for item in current.history_stack], ["T01", "T02"])

        now[0] = 12
        self.assertIsNone(store.get("session"))


if __name__ == "__main__":
    unittest.main()
