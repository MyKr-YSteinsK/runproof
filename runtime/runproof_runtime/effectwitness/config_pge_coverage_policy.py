"""RPF-57 deterministic coverage from complete independently verified trials.

Coverage is a projection, never authority. The session verifier rebuilds every
prior snapshot from the anchored trial chain; client snapshots cannot add facts.
"""
from .config_pge_coverage_contracts import canonical,digest,require,CANDIDATES

FACT_IDS=("effect_satisfied_v2","fault_not_planned","fault_planned_inhibited",
          "delivery_suppression_observed","ack_unknown_reconciled")

def initial_messages():
    return [{"role":"system","content":
        "Select one sandbox experiment using verified feedback and coverage. All catalog entries remain legal, including repeats. "
        "Untested entries are identities only; their outcomes are unknown. Return only select_experiment."},
        {"role":"user","content":canonical({"schema":"rpf57-visible-input-v1","catalog":list(CANDIDATES),
            "rounds":2,"seen_fact_ids":[],"tested_candidate_ids":[],"untested_candidate_ids":list(CANDIDATES),
            "effect":"v1 then v2; history [2,1]; no duplicate POST",
            "fault_design":"Host can withhold update delivery after HTTP200; planned-but-inhibited has a disabled gate. Design is not an observed outcome."}).decode()}]

def feedback(trial,previous=None):
    from .config_pge_coverage_verify import verify_trial
    verify_trial(trial)  # No fact is emitted for an incomplete/invalid/unknown trial.
    before=[] if previous is None else previous["seen_fact_ids_after"]
    tested=[] if previous is None else previous["tested_candidate_ids"]
    if previous is not None:
        unsigned={k:v for k,v in previous.items() if k!="coverage_digest"}
        require(previous["coverage_digest"]==digest(unsigned) and set(before)<=set(FACT_IDS)
            and set(tested)<=set(CANDIDATES),"PRIOR_COVERAGE_INVALID")
    facts={"effect_satisfied_v2"}
    f=trial["fault"];o=trial["outcome"]
    if not f["planned"]:facts.add("fault_not_planned")
    elif not f["triggered"]:facts.add("fault_planned_inhibited")
    if f["observed"]:facts.add("delivery_suppression_observed")
    if o["target_ack"]=="UNKNOWN_OUTCOME" and o["read_only_reconcile"]=="CONFIRMED_V2":facts.add("ack_unknown_reconciled")
    x=trial["contracts"]["experiment"];after=sorted(set(before)|facts);tested=sorted(set(tested)|{x["candidate_id"]})
    coverage={"schema":"rpf57-coverage-v1","verified_fact_ids":sorted(facts),"seen_fact_ids_before":before,
        "seen_fact_ids_after":after,"new_fact_ids":sorted(facts-set(before)),"tested_candidate_ids":tested,
        "untested_candidate_ids":sorted(set(CANDIDATES)-set(tested))}
    coverage["coverage_digest"]=digest(coverage)
    return {"schema":"rpf57-verified-feedback-v1","run_id":x["run_id"],"candidate_id":x["candidate_id"],
        "trial_sha256":digest(trial),"effect":"SATISFIED_V2_HISTORY_2_1","fault":f,
        "authority":"SAME_SERVICE_READ_ONLY_HTTP","target_ack":o["target_ack"],"coverage":coverage}

def research(rounds,source_kind):
    changed=rounds[0]["feedback"]["candidate_id"]!=rounds[1]["feedback"]["candidate_id"]
    novel=rounds[1]["feedback"]["coverage"]["new_fact_ids"]
    real=source_kind=="REAL_EXPLORER_REAL_TARGET_CONFIG_JAVA_HTTP"
    observed=real and changed and bool(novel)
    return {"L1":"TWO_REAL_ROLES_EXECUTED" if real else "SYNTHETIC_ONLY","candidate_changed":changed,
        "new_verified_facts":novel,"new_verified_fact_count":len(novel),"information_gain_proxy":len(novel),
        "L2":observed,"L2_status":"L2_OBSERVED_INFORMATION_GAIN_IN_THIS_RUN" if observed else "L2_NOT_PROVEN",
        "H1":"NOT_PROVEN","L3":"NOT_PROVEN","attribution":"CORRELATIONAL_ONLY"}

def next_messages(messages,call,fb):
    return messages+[{"role":"assistant","content":None,"tool_calls":[call]},
        {"role":"tool","tool_call_id":call["id"],"content":canonical(fb).decode()},
        {"role":"user","content":canonical({"schema":"rpf57-visible-coverage-v1",
            "prior_feedback_sha256":digest(fb),"prior_tool_call_id":call["id"],
            "catalog":list(CANDIDATES),"seen_fact_ids":fb["coverage"]["seen_fact_ids_after"],
            "tested_candidate_ids":fb["coverage"]["tested_candidate_ids"],
            "untested_candidate_ids":fb["coverage"]["untested_candidate_ids"]}).decode()}]
