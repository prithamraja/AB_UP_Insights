import unittest

from query_router.models import (
    ActiveFilter,
    ColumnMetadata,
    ColumnType,
    ContextFrame,
    OperationMode,
    OperationRequest,
    ResultSetReference,
    TimeRange,
)
from query_router.operations import (
    OPERATIONS,
    aggregation_mode,
    run_operation,
)


def make_frame(columns: list[ColumnMetadata], row_count: int = 3) -> ContextFrame:
    return ContextFrame(
        template_id="T02",
        bound_params={"district": "Agra"},
        active_filters=[ActiveFilter(dimension="district", value="Agra")],
        time_range=TimeRange(start="2025-01-01", end="2025-12-31", grain="day"),
        grouping_dimension="district_name",
        result_set=ResultSetReference(id="rs_test", row_count=row_count, columns=columns),
    )


MEASURE_COLUMNS = [
    ColumnMetadata(name="hospital_name", column_type=ColumnType.DIMENSION),
    ColumnMetadata(name="case_count", column_type=ColumnType.ADDITIVE_COUNT),
    ColumnMetadata(name="total_claimed", column_type=ColumnType.ADDITIVE_VALUE),
    ColumnMetadata(name="approval_rate", column_type=ColumnType.RATIO),
    ColumnMetadata(name="total_beds", column_type=ColumnType.SNAPSHOT_STOCK),
    ColumnMetadata(name="mystery", column_type=ColumnType.UNCLASSIFIED),
]

ROWS = [
    {"hospital_name": "Alpha", "case_count": 100, "total_claimed": 5000.0,
     "approval_rate": 80.0, "total_beds": 50, "mystery": 1},
    {"hospital_name": "Beta", "case_count": 300, "total_claimed": 12000.0,
     "approval_rate": 60.0, "total_beds": 150, "mystery": 2},
    {"hospital_name": "Gamma", "case_count": 100, "total_claimed": 3000.0,
     "approval_rate": 90.0, "total_beds": 100, "mystery": 3},
]


class PolicyTableTests(unittest.TestCase):
    """Exhaustive client-vs-requery policy per (aggregation, column type)."""

    def test_aggregation_policy_exhaustive(self):
        expected = {
            ColumnType.ADDITIVE_COUNT: "client",
            ColumnType.ADDITIVE_VALUE: "client",
            ColumnType.RATIO:          "requery",
            ColumnType.SNAPSHOT_STOCK: "client",
            ColumnType.UNCLASSIFIED:   "requery",
            ColumnType.DIMENSION:      "invalid",
            ColumnType.TEMPORAL:       "invalid",
            ColumnType.IDENTIFIER:     "invalid",
        }
        self.assertEqual(set(expected), set(ColumnType), "policy must cover every column type")
        for column_type, mode in expected.items():
            got = aggregation_mode(
                ColumnMetadata(name="c", column_type=column_type), MEASURE_COLUMNS
            )
            self.assertEqual(got, mode, f"aggregation on {column_type} should be {mode}")

    def test_snapshot_stock_across_time_requires_requery(self):
        with_time = MEASURE_COLUMNS + [
            ColumnMetadata(name="month", column_type=ColumnType.TEMPORAL)
        ]
        stock = ColumnMetadata(name="total_beds", column_type=ColumnType.SNAPSHOT_STOCK)
        self.assertEqual(aggregation_mode(stock, with_time), "requery")
        self.assertEqual(aggregation_mode(stock, MEASURE_COLUMNS), "client")

    def test_ratio_aggregations_never_run_client_side(self):
        frame = make_frame(MEASURE_COLUMNS)
        for op in ("sum", "average", "share_of_total"):
            result = run_operation(
                OperationRequest(operation=op, column="approval_rate"), frame, ROWS
            )
            self.assertEqual(result.mode, OperationMode.REJECTED, f"{op} on ratio must not execute")
            self.assertIsNone(result.value)
            self.assertIsNone(result.result)

    def test_unknown_operation_rejected(self):
        result = run_operation(
            OperationRequest(operation="regression"), make_frame(MEASURE_COLUMNS), ROWS
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)


class ClientOpsTests(unittest.TestCase):
    def setUp(self):
        self.frame = make_frame(MEASURE_COLUMNS)

    def run_op(self, **kwargs):
        return run_operation(OperationRequest(**kwargs), self.frame, ROWS)

    def test_sum_average_on_additive(self):
        self.assertEqual(self.run_op(operation="sum", column="case_count").value, 500.0)
        self.assertEqual(self.run_op(operation="average", column="total_claimed").value,
                         (5000 + 12000 + 3000) / 3)

    def test_min_max_names_the_row(self):
        result = self.run_op(operation="max", column="approval_rate")  # min/max on ratio is fine
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertEqual(result.value, 90.0)
        self.assertIn("Gamma", result.answer)
        self.assertEqual(self.run_op(operation="min", column="case_count").value, 100.0)

    def test_count(self):
        self.assertEqual(self.run_op(operation="count").value, 3.0)

    def test_default_column_prefers_additive_value(self):
        result = self.run_op(operation="sum")
        self.assertEqual(result.column, "total_claimed")
        self.assertEqual(result.value, 20000.0)

    def test_share_of_total_with_label(self):
        result = self.run_op(operation="share_of_total", column="case_count", label="beta")
        self.assertEqual(result.value, 60.0)
        self.assertIn("accounts for 60.0%", result.answer)

    def test_share_of_total_adds_ratio_column(self):
        result = self.run_op(operation="share_of_total", column="case_count")
        self.assertEqual(result.result[0]["share_of_case_count_pct"], 20.0)
        added = result.result_columns[-1]
        self.assertEqual(added.column_type, ColumnType.RATIO)

    def test_percent_change_sorts_by_temporal(self):
        columns = [
            ColumnMetadata(name="month", column_type=ColumnType.TEMPORAL),
            ColumnMetadata(name="claims", column_type=ColumnType.ADDITIVE_COUNT),
        ]
        rows = [
            {"month": "2025-03", "claims": 150},
            {"month": "2025-01", "claims": 100},
            {"month": "2025-02", "claims": 120},
        ]
        result = run_operation(
            OperationRequest(operation="percent_change", column="claims"),
            make_frame(columns), rows,
        )
        self.assertEqual(result.value, 50.0)

    def test_percent_change_needs_two_rows(self):
        result = run_operation(
            OperationRequest(operation="percent_change", column="case_count"),
            self.frame, ROWS[:1],
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)

    def test_sort_and_top_bottom(self):
        result = self.run_op(operation="sort", column="total_claimed", direction="asc")
        self.assertEqual([r["hospital_name"] for r in result.result],
                         ["Gamma", "Alpha", "Beta"])
        top = self.run_op(operation="top_n", column="case_count", n=1)
        self.assertEqual([r["hospital_name"] for r in top.result], ["Beta"])
        bottom = self.run_op(operation="bottom_n", column="total_claimed", n=2)
        self.assertEqual([r["hospital_name"] for r in bottom.result], ["Gamma", "Alpha"])

    def test_filter_rows_numeric_and_string(self):
        numeric = self.run_op(
            operation="filter_rows",
            filter_column="case_count", filter_operator=">", filter_value="100",
        )
        self.assertEqual([r["hospital_name"] for r in numeric.result], ["Beta"])
        text = self.run_op(
            operation="filter_rows",
            filter_column="hospital_name", filter_operator="contains", filter_value="alp",
        )
        self.assertEqual(len(text.result), 1)
        bad = self.run_op(
            operation="filter_rows",
            filter_column="case_count", filter_operator="~", filter_value="1",
        )
        self.assertEqual(bad.mode, OperationMode.REJECTED)

    def test_numeric_strings_are_coerced(self):
        rows = [{"hospital_name": "Alpha", "total_claimed": "1,500.50"},
                {"hospital_name": "Beta", "total_claimed": "500"}]
        result = run_operation(
            OperationRequest(operation="sum", column="total_claimed"),
            self.frame, rows,
        )
        self.assertEqual(result.value, 2000.5)

    def test_empty_table_rejected(self):
        result = run_operation(OperationRequest(operation="sum"), self.frame, [])
        self.assertEqual(result.mode, OperationMode.REJECTED)


class CompareTests(unittest.TestCase):
    def setUp(self):
        self.columns = [
            ColumnMetadata(name="district_name", column_type=ColumnType.DIMENSION),
            ColumnMetadata(name="total_cases", column_type=ColumnType.ADDITIVE_COUNT),
        ]
        self.frame = make_frame(self.columns, row_count=1)
        self.rows = [{"district_name": "Agra", "total_cases": 1200}]

    def test_compare_merges_requery_rows(self):
        def requery(slot, value):
            self.assertEqual(slot, "district")
            return [{"district_name": value, "total_cases": 950}]

        result = run_operation(
            OperationRequest(operation="compare", comparator=["Lucknow"]),
            self.frame, self.rows, requery=requery,
        )
        self.assertEqual(result.mode, OperationMode.REQUERY)
        self.assertEqual(
            [r["compared_district"] for r in result.result], ["Agra", "Lucknow"]
        )
        self.assertIn("1,200 vs 950", result.answer)
        self.assertEqual(result.result_columns[0].column_type, ColumnType.DIMENSION)

    def test_compare_without_comparator_rejected(self):
        result = run_operation(
            OperationRequest(operation="compare"), self.frame, self.rows,
            requery=lambda s, v: [],
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)

    def test_compare_unknown_slot_rejected(self):
        result = run_operation(
            OperationRequest(operation="compare", comparator=["Lucknow"],
                             comparator_slot="specialty"),
            self.frame, self.rows, requery=lambda s, v: [],
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)

    def test_compare_requery_failure_is_reported(self):
        def requery(slot, value):
            raise ValueError("no such district")

        result = run_operation(
            OperationRequest(operation="compare", comparator=["Atlantis"]),
            self.frame, self.rows, requery=requery,
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)
        self.assertIn("Atlantis", result.answer)


class DistributionOpsTests(unittest.TestCase):
    """median / stdev / percentile / range — per-row distribution statistics,
    client-safe on every measure type including ratios."""

    def setUp(self):
        self.frame = make_frame(MEASURE_COLUMNS)

    def run_op(self, **kwargs):
        return run_operation(OperationRequest(**kwargs), self.frame, ROWS)

    def test_median(self):
        result = self.run_op(operation="median", column="case_count")
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertEqual(result.value, 100.0)
        self.assertIn("rows shown", result.answer)

    def test_median_on_ratio_runs_client_side(self):
        # Unlike average: a median district rate is a legitimate row statistic.
        result = self.run_op(operation="median", column="approval_rate")
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertEqual(result.value, 80.0)

    def test_stdev(self):
        result = self.run_op(operation="stdev", column="case_count")
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertAlmostEqual(result.value, 115.4701, places=3)  # sample stdev

    def test_stdev_needs_two_values(self):
        result = run_operation(
            OperationRequest(operation="stdev", column="case_count"),
            self.frame, ROWS[:1],
        )
        self.assertEqual(result.mode, OperationMode.REJECTED)

    def test_percentile_median_equivalence(self):
        result = self.run_op(operation="percentile", column="total_claimed", n=50)
        self.assertEqual(result.value, 5000.0)
        self.assertIn("50th percentile", result.answer)

    def test_percentile_interpolates(self):
        # sorted case_count [100, 100, 300], rank 0.9 * 2 = 1.8 → 100 + 0.8 * 200
        result = self.run_op(operation="percentile", column="case_count", n=90)
        self.assertAlmostEqual(result.value, 260.0)

    def test_percentile_requires_valid_n(self):
        self.assertEqual(
            self.run_op(operation="percentile", column="case_count").mode,
            OperationMode.REJECTED,
        )
        self.assertEqual(
            self.run_op(operation="percentile", column="case_count", n=150).mode,
            OperationMode.REJECTED,
        )

    def test_range_names_both_endpoints(self):
        result = self.run_op(operation="range", column="total_claimed")
        self.assertEqual(result.value, 9000.0)
        self.assertIn("Gamma", result.answer)  # min row
        self.assertIn("Beta", result.answer)   # max row


class ValueFrequencyTests(unittest.TestCase):
    """mode / count_distinct — any column, dimensions included."""

    def setUp(self):
        self.frame = make_frame(MEASURE_COLUMNS)

    def run_op(self, **kwargs):
        return run_operation(OperationRequest(**kwargs), self.frame, ROWS)

    def test_mode_on_numeric_column(self):
        result = self.run_op(operation="mode", column="case_count")
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertEqual(result.value, 100.0)
        self.assertIn("2 of 3 rows", result.answer)

    def test_mode_all_unique_is_honest(self):
        result = self.run_op(operation="mode", column="hospital_name")
        self.assertEqual(result.mode, OperationMode.CLIENT)
        self.assertIsNone(result.value)
        self.assertIn("no most common value", result.answer)

    def test_mode_defaults_to_dimension_column(self):
        result = self.run_op(operation="mode")
        self.assertEqual(result.column, "hospital_name")

    def test_mode_reports_ties(self):
        rows = ROWS + [{"hospital_name": "Delta", "case_count": 300}]
        result = run_operation(
            OperationRequest(operation="mode", column="case_count"), self.frame, rows
        )
        self.assertIsNone(result.value)
        self.assertIn("tie as most common", result.answer)
        self.assertIn("100", result.answer)
        self.assertIn("300", result.answer)

    def test_count_distinct(self):
        self.assertEqual(
            self.run_op(operation="count_distinct", column="hospital_name").value, 3.0
        )
        self.assertEqual(
            self.run_op(operation="count_distinct", column="case_count").value, 2.0
        )

    def test_unknown_column_rejected(self):
        result = self.run_op(operation="count_distinct", column="nonexistent")
        self.assertEqual(result.mode, OperationMode.REJECTED)


class OperationSetTests(unittest.TestCase):
    def test_closed_set_matches_spec(self):
        self.assertEqual(OPERATIONS, {
            "sum", "average", "min", "max", "count", "share_of_total",
            "sort", "filter_rows", "percent_change", "top_n", "bottom_n", "compare",
            "median", "mode", "stdev", "percentile", "range", "count_distinct",
        })


if __name__ == "__main__":
    unittest.main()
