# attack_enterprise.json — MITRE ATT&CK Enterprise (from mitre/cti STIX bundle)
# Top-level: source, retrieved_at (UTC ISO), technique_count, techniques[], tactics[], mitigations[], technique_mitigations{}.
# techniques[]: {id ("T1059.001"), name, description (<=600 chars), tactics[] (tactic names), platforms[], data_sources[]}.
# tactics[]: {id ("defense-evasion" shortname), name, description (<=300 chars)} — 14-15 tactics incl. sub-technique parents.
# mitigations[]: {id ("M1031"), name, description (<=400 chars)}.
# technique_mitigations: {technique_id: [mitigation_ids]} — only "mitigates" relationships where both ends survived filtering.
# Filtering: revoked=true and x_mitre_deprecated=true objects are excluded; entries without a T-/M-number are dropped.
# Note: current ATT&CK renamed Defense Evasion -> Defense Impairment + Stealth; names here reflect the live dataset.
# Compact JSON (no STIX boilerplate); regenerate with the repo's parse script, then bump retrieved_at.
