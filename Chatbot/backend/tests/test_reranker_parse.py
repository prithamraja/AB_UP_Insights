import unittest

from query_router.reranker import parse_rerank_response

VALID = {"T01", "T09", "T11", "D05"}


class RerankParseTests(unittest.TestCase):
    def test_direct_match_passes_through(self):
        chosen, near = parse_rerank_response({"query_id": "T09"}, VALID)
        self.assertEqual(chosen, "T09")
        self.assertEqual(near, [])

    def test_case_drift_is_tolerated(self):
        chosen, _ = parse_rerank_response({"query_id": "t09"}, VALID)
        self.assertEqual(chosen, "T09")

    def test_no_match_returns_llm_picked_candidates_in_order(self):
        chosen, near = parse_rerank_response(
            {"query_id": "no_match", "candidates": ["T09", "T01", "T11"]}, VALID
        )
        self.assertEqual(chosen, "no_match")
        self.assertEqual(near, ["T09", "T01", "T11"])

    def test_candidates_are_validated_deduplicated_and_capped(self):
        chosen, near = parse_rerank_response(
            {
                "query_id": "no_match",
                "candidates": ["T09", "HALLUCINATED", "t09", "T01", "T11", "D05"],
            },
            VALID,
        )
        self.assertEqual(chosen, "no_match")
        self.assertEqual(near, ["T09", "T01", "T11"], "invalid dropped, dupes merged, capped at 3")

    def test_chosen_id_is_excluded_from_candidates(self):
        chosen, near = parse_rerank_response(
            {"query_id": "T09", "candidates": ["T09", "T01"]}, VALID
        )
        self.assertEqual(chosen, "T09")
        self.assertEqual(near, ["T01"])

    def test_hallucinated_choice_becomes_no_match(self):
        chosen, near = parse_rerank_response(
            {"query_id": "T99", "candidates": "not-a-list"}, VALID
        )
        self.assertEqual(chosen, "no_match")
        self.assertEqual(near, [])

    def test_empty_payload_is_off_topic(self):
        self.assertEqual(parse_rerank_response({}, VALID), ("no_match", []))


if __name__ == "__main__":
    unittest.main()
