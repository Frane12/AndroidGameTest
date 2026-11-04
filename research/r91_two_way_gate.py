"""R91 experimental two-way feedback controller. Research harness, NOT a SAT solver.

Messages are untrusted suggestions: this module never injects clauses.
The solver integration must independently verify every imported clause.
"""
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class Suggestion:
    clause_id: str
    proof_verified: bool
    preparation_seconds: float
    source: str = "xor"

@dataclass
class TwoWayGate:
    min_samples: int = 4
    min_net_gain_seconds: float = 0.0
    max_pending: int = 32
    pending: dict = field(default_factory=dict)
    accepted: int = 0
    rejected: int = 0
    useful: int = 0
    cost_seconds: float = 0.0
    estimated_saved_seconds: float = 0.0

    def propose(self, msg: Suggestion) -> bool:
        # B -> A: only externally proof-verified clauses may be queued.
        if not msg.proof_verified or msg.preparation_seconds < 0:
            self.rejected += 1
            return False
        if len(self.pending) >= self.max_pending:
            self.rejected += 1
            return False
        if self.accepted >= self.min_samples and self.estimated_saved_seconds - self.cost_seconds <= self.min_net_gain_seconds:
            self.rejected += 1
            return False
        if msg.clause_id in self.pending:
            self.rejected += 1
            return False
        self.pending[msg.clause_id] = msg
        self.accepted += 1
        self.cost_seconds += msg.preparation_seconds
        return True

    def feedback(self, clause_id: str, used_in_propagation: bool,
                 used_in_conflict: bool, estimated_saved_seconds: float = 0.0) -> None:
        # A -> B: explicit observed usefulness, with conservative cost accounting.
        if clause_id not in self.pending:
            raise KeyError("unknown or already acknowledged clause")
        if estimated_saved_seconds < 0:
            raise ValueError("negative estimated saving")
        self.pending.pop(clause_id)
        if used_in_propagation or used_in_conflict:
            self.useful += 1
            self.estimated_saved_seconds += estimated_saved_seconds

    def stats(self) -> dict:
        return dict(accepted=self.accepted, rejected=self.rejected,
                    useful=self.useful, pending=len(self.pending),
                    cost_seconds=self.cost_seconds,
                    estimated_saved_seconds=self.estimated_saved_seconds,
                    estimated_net_seconds=self.estimated_saved_seconds-self.cost_seconds)

if __name__ == "__main__":
    g = TwoWayGate(min_samples=2)
    assert not g.propose(Suggestion("bad", False, 0.01))
    assert g.propose(Suggestion("c1", True, 0.02))
    g.feedback("c1", False, False)
    assert g.propose(Suggestion("c2", True, 0.02))
    g.feedback("c2", False, False)
    assert not g.propose(Suggestion("c3", True, 0.02)), "gate must stop unproductive exchange"
    h = TwoWayGate(min_samples=2)
    for i in range(2):
        assert h.propose(Suggestion(f"good{i}", True, 0.01))
        h.feedback(f"good{i}", True, False, 0.04)
    assert h.propose(Suggestion("good2", True, 0.01))
    print("R91 controller self-test PASS", g.stats(), h.stats())
