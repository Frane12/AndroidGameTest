import tempfile
import itertools
import random
import unittest
from pathlib import Path
from unittest.mock import patch

import experiment as bench
from design import make_case, opportunity_key
from policy import TrainingMemory, action
from strict_runner import run_strict


class RoutingRegressionTests(unittest.TestCase):
    def test_empty_policy_never_scans_source_and_chain_keeps_class_key(self):
        c=make_case("xor_overlap_planted",1,generation=23)
        c.update(split="train",feature_key=opportunity_key(c["clauses"],c["n"]))
        policy=dict(positive_classes={},feature_classes={c["feature_key"]:{}})
        with tempfile.TemporaryDirectory() as td, patch.object(
                bench,"run_strict",return_value=(0,"",0.0,"finished")):
            with patch.object(bench,"opportunity_key",side_effect=AssertionError("unnecessary scan")):
                r=bench.run_arm(c,"LTM_GATE",0,policy,Path(td))
            self.assertEqual(r["reason"],"empty_policy_fast_abstain")
            r=bench.run_arm(c,"MI_CHAIN",0,policy,Path(td))
            self.assertEqual(r["feature_key"],c["feature_key"])
            self.assertTrue(r["matched"])

    def test_training_action_survives_freeze_and_routes_into_native(self):
        c=make_case("random3_planted",1,generation=23)
        key=opportunity_key(c["clauses"],c["n"])
        c.update(split="holdout",feature_key=key)
        with tempfile.TemporaryDirectory() as td:
            memory=TrainingMemory(Path(td)/"train.sqlite")
            for i in range(8):
                def trial(t):
                    return dict(par2_s=t,solved=True,trial_audited=True,
                                conflicts=10,probe_s=0)
                memory.insert_pair(sha="train-"+str(i),rep=0,generation=1,
                                   family="test",key=key,base=trial(.1),force=trial(.05))
            frozen=memory.freeze({c["sha"]},candidate_action="LTM_NATIVE")
            memory.close()
            self.assertEqual(action(frozen,key)[0],"LTM_NATIVE")
            with patch.object(bench,"run_strict",return_value=(0,"",0.0,"finished")) as run:
                r=bench.run_arm(c,"LTM_NATIVE_GATE",0,frozen,Path(td))
            self.assertEqual(run.call_args.kwargs["mode"],"LTM_NATIVE")
            self.assertEqual(r["action"],"LTM_NATIVE")

    def test_native_crash_is_not_benchmark_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/"broken"
            exe.write_text("#!/bin/sh\nexit 2\n")
            exe.chmod(0o755)
            with self.assertRaises(RuntimeError):
                run_strict(exe,Path(td)/"x.cnf",0,2)


class NativeIntegrationTests(unittest.TestCase):
    @unittest.skipUnless((bench.ROOT/"mre_ltm3/bin/drnas_ltm3").exists(),"native build required")
    def test_native_result_matches_exhaustive_oracle(self):
        from design import dimacs, satisfies
        from native_paired import parse_model
        rng=random.Random(14159)
        checked={10:0,20:0}
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"tiny.cnf"
            for _ in range(80):
                n=6
                clauses=[tuple(v if rng.getrandbits(1) else -v for v in rng.sample(range(1,n+1),rng.choice((2,3))))
                         for _ in range(rng.randrange(5,35))]
                possible=any(satisfies(clauses,dict(zip(range(1,n+1),bits)))
                             for bits in itertools.product((False,True),repeat=n))
                path.write_text(dimacs(n,clauses))
                rc,out,_,_=run_strict(bench.ROOT/"mre_ltm3/bin/drnas_ltm3",path,0,2,mode="LTM_NATIVE")
                self.assertEqual(rc,10 if possible else 20)
                checked[rc]+=1
                if rc==10: self.assertTrue(satisfies(clauses,parse_model(out)))
        self.assertGreater(checked[10],0)
        self.assertGreater(checked[20],0)

    @unittest.skipUnless((bench.ROOT/"mre_ltm3/bin/drnas_ltm3").exists(),"native build required")
    def test_disabled_matches_reference_and_enabled_changes_real_decisions(self):
        reference=bench.ROOT/"mre_atlas15/bin/drnas_atlas15"
        hooked=bench.ROOT/"mre_ltm3/bin/drnas_ltm3"
        overrides=0
        divergent=0
        with tempfile.TemporaryDirectory() as td:
            for i in range(16):
                c=make_case("xor_overlap_planted",i,generation=23)
                c.update(split="train",feature_key=opportunity_key(c["clauses"],c["n"]))
                with patch.object(bench,"BIN",reference):
                    original=bench.run_arm(c,"BASE",0,None,Path(td))
                with patch.object(bench,"BIN",hooked):
                    disabled=bench.run_arm(c,"BASE",0,None,Path(td))
                    enabled=bench.run_arm(c,"LTM_NATIVE",0,None,Path(td))
                    positive=dict(positive_classes={c["feature_key"]:{"decision":"LTM_NATIVE"}},
                                  feature_classes={c["feature_key"]:{}})
                    gated=bench.run_arm(c,"LTM_NATIVE_GATE",0,positive,Path(td))
                for field in ("status","conflicts","decisions"):
                    self.assertEqual(original[field],disabled[field])
                self.assertEqual(enabled["decision_hash"],gated["decision_hash"])
                self.assertEqual(enabled["native_branch_overrides"],gated["native_branch_overrides"])
                self.assertEqual(disabled["native_branch_overrides"],0)
                self.assertLessEqual(enabled["native_branch_checks"],16)
                self.assertLessEqual(enabled["native_branch_overrides"],enabled["native_branch_checks"])
                overrides+=enabled["native_branch_overrides"]
                divergent+=enabled["decision_hash"]!=disabled["decision_hash"]
        self.assertGreater(overrides,0)
        self.assertGreater(divergent,0)


if __name__=="__main__":
    unittest.main()
