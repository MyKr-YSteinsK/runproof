"""Baselines share guards and visible records, differing only in ranking."""
from .pge_r75_policy import decide


def fixed_order(v, evidence, state, *, trusted_records):
    return decide(v, evidence, state, trusted_records=trusted_records, policy='B0-fixed-v1')


def no_feedback(v, evidence, state, *, trusted_records):
    # Ablation hides facts from scoring only; safety still consumes all visible evidence.
    return decide(v, evidence, state, trusted_records=trusted_records, policy='B1-no-feedback-v1')
