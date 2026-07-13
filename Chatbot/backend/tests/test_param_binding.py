"""Regression: templates that repeat a slot across several SQL placeholders
(T91 filters both its enrolled and treated subqueries by district; T99 has
five district placeholders) must receive one value per placeholder, not one
per logical entity. The normal route previously bound each validated entity
once, so every such template failed at the database despite correct routing.
Both execution paths (_serve_query_id and requery_template) now share
bind_param_values."""
import time
import unittest
from types import SimpleNamespace

from query_router import router
from query_router.models import ExtractedEntity, RouteTier
from query_router.template_catalog import TEMPLATE_CATALOG


def _entity(slot, resolved):
    return ExtractedEntity(
        slot_name=slot, raw_value=resolved.lower(),
        resolved_value=resolved, entity_type="district",
        confidence="high",
    )


class _CapturingConn:
    """Records every (sql, params) executed; returns one dummy row."""
    def __init__(self):
        self.captured = []

    def execute(self, sql, params):
        self.captured.append((sql, list(params)))
        return SimpleNamespace(
            description=["x"],
            fetchmany=lambda n: [(1,)],
        )


class _StubValidator:
    def validate(self, value, entity_type):
        return SimpleNamespace(resolved_value=value)


# Same shape as the T118/T257 comparison family: two logical districts, each
# bound at two interleaved positions.
_INTERLEAVED = {
    "abstract_question": "Compare {district} with {district_2}?",
    "date_filter": None,
    "sql_template": "SELECT ?, ?, ?, ?",
    "param_slots": [
        {"name": "district",   "entity_type": "district", "position": 1},
        {"name": "district_2", "entity_type": "district", "position": 2},
        {"name": "district",   "entity_type": "district", "position": 3},
        {"name": "district_2", "entity_type": "district", "position": 4},
    ],
    "result_ttl_seconds": 0,  # keep the router result cache out of these tests
}


class BindParamValuesTests(unittest.TestCase):
    def test_t91_binds_district_twice(self):
        slots = TEMPLATE_CATALOG["T91"]["param_slots"]
        self.assertEqual(
            router.bind_param_values(slots, {"district": "Lucknow"}),
            ["Lucknow", "Lucknow"],
        )

    def test_t99_binds_district_five_times(self):
        slots = TEMPLATE_CATALOG["T99"]["param_slots"]
        self.assertEqual(
            router.bind_param_values(slots, {"district": "Agra"}),
            ["Agra"] * 5,
        )

    def test_interleaved_two_district_template(self):
        self.assertEqual(
            router.bind_param_values(
                _INTERLEAVED["param_slots"],
                {"district": "Agra", "district_2": "Lucknow"},
            ),
            ["Agra", "Lucknow", "Agra", "Lucknow"],
        )

    def test_positions_win_over_declaration_order(self):
        slots = [
            {"name": "b", "position": 2},
            {"name": "a", "position": 1},
        ]
        self.assertEqual(
            router.bind_param_values(slots, {"a": "A", "b": "B"}),
            ["A", "B"],
        )

    def test_missing_parameter_raises(self):
        slots = TEMPLATE_CATALOG["T91"]["param_slots"]
        with self.assertRaises(ValueError) as ctx:
            router.bind_param_values(slots, {}, context=" for T91")
        self.assertIn("missing parameter(s) for T91: district", str(ctx.exception))

    def test_every_catalog_template_binds_all_placeholders(self):
        """One value per '?' for the whole catalog, with a value per slot name."""
        for qid, template in TEMPLATE_CATALOG.items():
            slots = template["param_slots"]
            params = {s["name"]: s["name"].upper() for s in slots}
            bound = router.bind_param_values(slots, params)
            self.assertEqual(
                len(bound), template["sql_template"].count("?"),
                f"{qid}: bound {len(bound)} values for "
                f"{template['sql_template'].count('?')} placeholders",
            )


class ExecutionPathParityTests(unittest.TestCase):
    """The normal route and the compare requery must bind identically."""

    def _serve(self, conn, entities):
        return router._serve_query_id(
            "TX_INTERLEAVED", entities, None,
            user_query="compare agra with lucknow",
            normalized="compare agra with lucknow",
            start=time.monotonic(),
            cache_conn=conn,
            dashboard_results={},
            template_map={"TX_INTERLEAVED": _INTERLEAVED},
            dashboard_questions={},
            start_date=None,
            end_date=None,
        )

    def test_serve_query_id_repeats_values_per_slot(self):
        conn = _CapturingConn()
        result = self._serve(
            conn, [_entity("district", "Agra"), _entity("district_2", "Lucknow")]
        )
        self.assertEqual(result.tier, RouteTier.TIER2_TEMPLATE)
        self.assertEqual(len(conn.captured), 1)
        self.assertEqual(conn.captured[0][1], ["Agra", "Lucknow", "Agra", "Lucknow"])

    def test_serve_query_id_missing_slot_falls_back_without_executing(self):
        conn = _CapturingConn()
        result = self._serve(conn, [_entity("district", "Agra")])
        self.assertEqual(result.tier, RouteTier.FALLBACK)
        self.assertEqual(conn.captured, [])

    def test_requery_binds_identically_to_normal_route(self):
        serve_conn = _CapturingConn()
        self._serve(
            serve_conn,
            [_entity("district", "Agra"), _entity("district_2", "Lucknow")],
        )

        requery_conn = _CapturingConn()
        router.requery_template(
            "TX_INTERLEAVED",
            template_map={"TX_INTERLEAVED": _INTERLEAVED},
            cache_conn=requery_conn,
            validator=_StubValidator(),
            bound_params={"district": "Agra", "district_2": "Kanpur"},
            swap_slot="district_2",
            swap_value="Lucknow",
            start_date=None,
            end_date=None,
        )

        self.assertEqual(serve_conn.captured[0][1], requery_conn.captured[0][1])


if __name__ == "__main__":
    unittest.main()
