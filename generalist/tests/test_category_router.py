import hashlib
import unittest
from generalist.category_router import bucket, partition, learn, evaluate, par2

def trial(i, arm="drnas_base", family="graph-coloring", sec=2.0,
          status="SAT", cap=30.0, verified=True):
    sha = hashlib.sha256(("source-%s" % i).encode()).hexdigest()
    return dict(original_sha256=sha, family=family, arm=arm, status=status,
                e2e_s=sec, cap_s=cap, verified=verified)

class CategoryRouterTests(unittest.TestCase):
    def test_family(self):
        self.assertEqual(bucket({"family": "php_20_21"}), "pigeonhole")
        self.assertEqual(bucket({"family": "crypto-sha"}), "crypto")
        self.assertEqual(bucket({"family": "graph", "xor_certified": True}), "xor")
        self.assertEqual(bucket({"family": "irrelevant"}), "unknown")

    def test_sha_disjoint_reproducible(self):
        rows = [trial(i, arm) for i in range(120)
                for arm in ("drnas_base", "experimental")]
        a,b = partition(rows)
        self.assertTrue(a and b)
        self.assertFalse({x["original_sha256"] for x in a} &
                         {x["original_sha256"] for x in b})
        self.assertEqual(a, partition(rows)[0])

    def test_training_paired_and_fallback(self):
        rows = [trial(i, arm, sec=1.0 if arm == "experimental" else 5.0)
                for i in range(15) for arm in ("drnas_base", "experimental")]
        model = learn(rows, min_paired=8)
        self.assertEqual(model["graph"]["arm"], "experimental")
        self.assertEqual(model["crypto"]["arm"], "drnas_base")
        self.assertEqual(evaluate(rows, model)["graph"]["par2_ratio"], 5.0)

    def test_unsolved_penalty_and_reject_unverified(self):
        self.assertEqual(par2(trial(1, status="TIMEOUT")), 60.0)
        with self.assertRaises(ValueError):
            partition([trial(1, verified=False)])

    def test_missing_arm_not_imputed(self):
        rows = [trial(1)]
        out = evaluate(rows, {"graph": {"arm": "experimental"}})
        self.assertEqual(out["graph"]["fallback"], 1)
        self.assertEqual(out["graph"]["paired"], 0)

if __name__ == "__main__":
    unittest.main()
