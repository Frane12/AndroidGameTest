-- DRNAS ATLAS18 reproducible append-only benchmark/learning audit.
-- Results enter the decision policy ONLY through verified SAT or certified GF2 UNSAT.
-- "UNSAT_UNVERIFIED" remains separately logged and is charged 2*cap in verified PAR2.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS cohort (
  stage INTEGER NOT NULL CHECK(stage IN (1,2,3)),
  source_sha TEXT NOT NULL CHECK(length(source_sha)=64),
  category TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_entry TEXT NOT NULL,
  source_index INTEGER NOT NULL,
  vars INTEGER NOT NULL,
  clauses INTEGER NOT NULL,
  replay_nonblind INTEGER NOT NULL CHECK(replay_nonblind IN (0,1)),
  PRIMARY KEY(stage, source_sha)
);
CREATE TABLE IF NOT EXISTS trial (
  stage INTEGER NOT NULL,
  source_sha TEXT NOT NULL,
  rep INTEGER NOT NULL CHECK(rep>=0),
  arm TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN
    ('SAT_VERIFIED','GF2_UNSAT_VERIFIED','UNSAT_UNVERIFIED','UNKNOWN')),
  e2e_s REAL NOT NULL,
  par2_verified_s REAL NOT NULL,
  par2_reported_s REAL NOT NULL,
  applied_policy TEXT NOT NULL,
  telemetry_json TEXT NOT NULL,
  PRIMARY KEY(stage,source_sha,rep,arm),
  FOREIGN KEY(stage,source_sha) REFERENCES cohort(stage,source_sha)
);
CREATE TABLE IF NOT EXISTS decision_event (
  stage INTEGER NOT NULL,
  source_sha TEXT NOT NULL,
  rep INTEGER NOT NULL,
  arm TEXT NOT NULL,
  event_type TEXT NOT NULL,
  outcome_verified INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY(stage,source_sha,rep,arm,event_type),
  FOREIGN KEY(stage,source_sha,rep,arm)
    REFERENCES trial(stage,source_sha,rep,arm)
);
CREATE TABLE IF NOT EXISTS family_policy (
  based_on_stage INTEGER NOT NULL,
  category TEXT NOT NULL,
  verified_sat_pairs INTEGER NOT NULL,
  c5_e2e_s REAL NOT NULL,
  c6_e2e_s REAL NOT NULL,
  target_policy TEXT NOT NULL,
  rationale TEXT NOT NULL,
  PRIMARY KEY(based_on_stage,category)
);
CREATE INDEX IF NOT EXISTS idx_trial_status ON trial(stage,arm,status);
CREATE INDEX IF NOT EXISTS idx_trial_family ON cohort(stage,category);
