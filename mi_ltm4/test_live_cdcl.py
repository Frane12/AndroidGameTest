"""LTM4.1 native log parsing tests without needing a compiler or solver."""
import unittest
from live_cdcl import parse_native_log,aggregate_by_formula


class NativeCDCLTraceTests(unittest.TestCase):
    def test_real_format_reason_graph_and_learning_episode(self):
        log = """MICRO_EVENT seq=1 kind=decision variable=7 number=1
MICRO_EVENT seq=2 kind=assign lit=7 level=1 reason=-1
MICRO_EVENT seq=3 kind=assign lit=-4 level=1 reason=5
REDUCE2_NODE conflict=1 cid=8 learned=0 clause=7,4
REDUCE2_NODE conflict=1 cid=5 learned=1 clause=-7,-4
REDUCE2_EDGE conflict=1 from=8 to=5 var=4
MICRO_EVENT seq=4 kind=conflict cid=8 level=1 number=1 decisions=1 propagations=2 visits=7 trail=2
MICRO_EVENT seq=5 kind=learn from=1 backjump=0 width=1 clause=-7
"""
        report = parse_native_log(log)
        self.assertEqual(report["observed_conflicts"],1)
        self.assertEqual(report["observed_learns"],1)
        self.assertEqual(len(report["episodes"]),1)
        ep=report["episodes"][0]
        self.assertTrue(ep["reason_graph_available"])
        self.assertEqual(ep["reason_nodes"],2)
        self.assertEqual(ep["reason_edges"],1)
        self.assertEqual(ep["features"]["reason_learned"],"1")
        self.assertEqual(ep["features"]["bcp_since_decision"],"1")
        self.assertTrue(ep["observational_only"])

    def test_renamed_variable_ids_same_episode_key(self):
        a = """MICRO_EVENT seq=1 kind=decision variable=7 number=1
MICRO_EVENT seq=2 kind=assign lit=-2 level=1 reason=42
MICRO_EVENT seq=3 kind=conflict cid=12 level=1 number=1
MICRO_EVENT seq=4 kind=learn from=1 backjump=0 width=2 clause=7,2
"""
        b = a.replace("variable=7","variable=15").replace("lit=-2","lit=-8").replace(
            "cid=12","cid=3").replace("reason=42","reason=2").replace(
            "clause=7,2","clause=15,8")
        first=parse_native_log(a)["episodes"][0]
        second=parse_native_log(b)["episodes"][0]
        self.assertEqual(first["key"],second["key"])

    def test_directed_reason_shape_invariant_to_clause_identifiers(self):
        first = """REDUCE2_NODE conflict=1 cid=8 learned=0 clause=7,4
REDUCE2_NODE conflict=1 cid=5 learned=1 clause=-7,-4
REDUCE2_EDGE conflict=1 from=8 to=5 var=4
MICRO_EVENT seq=1 kind=conflict cid=8 level=2 number=1
MICRO_EVENT seq=2 kind=learn from=2 backjump=0 width=2 clause=7,4
"""
        second = first.replace("cid=8","cid=80").replace(
            "cid=5","cid=50").replace("from=8 to=5","from=80 to=50")
        a=parse_native_log(first)["episodes"][0]
        b=parse_native_log(second)["episodes"][0]
        self.assertEqual(a["key"],b["key"])
        self.assertEqual(a["features"]["reason_graph_shape"],
                         b["features"]["reason_graph_shape"])

    def test_incomplete_conflict_no_false_learning(self):
        report=parse_native_log("MICRO_EVENT seq=1 kind=conflict cid=0 level=0 number=1")
        self.assertEqual(report["episodes"],[])

    def test_nonmonotone_sequence_is_rejected(self):
        text = """MICRO_EVENT seq=2 kind=decision variable=4 number=1
MICRO_EVENT seq=1 kind=decision variable=5 number=2"""
        with self.assertRaises(AssertionError):
            parse_native_log(text)

    def test_per_formula_support_not_per_event_or_seed(self):
        trace=parse_native_log("""MICRO_EVENT seq=1 kind=conflict cid=0 level=2 number=1
MICRO_EVENT seq=2 kind=learn from=2 backjump=0 width=1 clause=4
""")
        agg=aggregate_by_formula([
            dict(sha256="a",trace=trace),dict(sha256="a",trace=trace),
            dict(sha256="b",trace=trace)])
        self.assertEqual(agg["distinct_formulas"],2)
        self.assertEqual(list(agg["support_formulas"].values()),[2])
        self.assertEqual(list(agg["episode_counts"].values()),[3])


if __name__ == "__main__":
    unittest.main()
