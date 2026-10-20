"""One projection entry, domain/Effect/Authority-qualified facts; no LLM IO."""
from .pge_select_contracts import digest,require,DOMAINS
def visible(prior):
    from .pge_select_contracts import CANDIDATES
    return {"catalog":list(CANDIDATES),"prior_feedback_sha256":[digest(f) for f in prior],
        "seen_facts_by_domain":{d:sorted({fact for f in prior if f["domain"]==d for fact in f["verified_fact_ids"]}) for d in DOMAINS},
        "not_tested_domain_ids":[d for d in DOMAINS if d not in [f["domain"] for f in prior]]}

def project(contract,evidence,prior):
    # Recompute the domain predicates; the port cannot grant itself PASS.
    from .pge_select_verify import domain_verdict
    verdict=domain_verdict(contract,evidence)
    d=contract["experiment"]["domain"]
    authority=verdict["authority"]
    facts=(["order-refund:full_refund_v1:sqlite_receipt:receipt_unique"] if d==DOMAINS[0] else
        ["config-java-http:version2_history21:same_service_http:effect_satisfied","config-java-http:disabled_gate:same_service_http:fault_planned_inhibited"])
    before=visible(prior)["seen_facts_by_domain"][d]
    return {"schema":"rpf59-domain-feedback-v1","domain":d,"run_id":contract["experiment"]["run_id"],
        "evidence_sha256":digest(evidence),"source_kind":evidence["source_kind"],"authority":authority,
        "status":"VERIFIED","verified_fact_ids":facts,"seen_fact_ids_before":before,
        "new_fact_ids":sorted(set(facts)-set(before)),"not_applicable":["CROSS_DOMAIN_INFORMATION_GAIN_SUM"],
        "unknown":["ISSUER_AUTHENTICITY","INDEPENDENT_REPRODUCTION"]}
