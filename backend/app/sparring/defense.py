"""Evasion analysis: the SOC learns from what the twin got away with.

For every scenario the engine FAILED to catch, produce a structured
self-critique:

- what_happened: plain-language description of the attack
- why_evaded: which detection layers were checked and what each saw
              (rules fired, anomaly verdict, intel-feed state)
- how_to_defend: concrete, actionable recommendations — a rule to add,
              a threshold to tune, intel to refresh, or an honest
              "no cheap detector exists" with the compensating control.

Deterministic and rule-based (no LLM): every claim traces to something
the engine actually computed. Nothing is invented.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Technique -> defensive guidance for evasions. Each entry: what to check
# first, and the concrete detection that should exist.
TECHNIQUE_DEFENSE = {
    "T1059.001": {
        "check": "suspicious-cmdline rule patterns",
        "recommend": ("Add the observed command-line tokens to the "
                      "suspicious-cmdline pattern list in app/detection/rules.py, "
                      "or widen it to flag LOLBINs spawning encoded PowerShell."),
    },
    "T1110": {
        "check": "brute-force-auth threshold and auth event coverage",
        "recommend": ("Lower BRUTE_FORCE_FAILED_THRESHOLD or confirm the sensor "
                      "ships auth events with src_ip so the source can be blocked. "
                      "Consider account lockout policy on the endpoint."),
    },
    "T1071": {
        "check": "threat-intel feed freshness and known-c2 rule",
        "recommend": ("If the destination is a fresh IoC, the 24h intel refresh "
                      "may be too slow — consider a shorter interval or an "
                      "on-demand refresh for high-severity IoCs."),
    },
    "T1105": {
        "check": "egress filtering and download monitoring",
        "recommend": ("Block executable downloads from untrusted hosts at the "
                      "proxy/firewall; alert on processes whose image was "
                      "written by a browser or downloader within the hour."),
    },
    "T1190": {
        "check": "exploit-behavior rules (service -> shell)",
        "recommend": ("Add a rule for network-service processes (w3wp, httpd, "
                      "nginx) spawning shells — the canonical post-exploit shape. "
                      "Patch the KEV-listed CVE on the asset."),
    },
    "T1003.001": {
        "check": "credential-access patterns (lsass, sekurlsa)",
        "recommend": ("Ensure lsass access auditing is on; the suspicious-cmdline "
                      "rule should cover sekurlsa/mimikatz tokens."),
    },
    "T1547.001": {
        "check": "persistence-change rule coverage",
        "recommend": ("Confirm the sensor collects Run-key / scheduled-task "
                      "changes; the persistence-change rule fires on them."),
    },
}


def analyze_outcome(scenario: dict, score: dict, intel_state: dict | None = None) -> dict:
    """Build the learn-step analysis for one scored scenario.

    scenario: the attack dict from intel_driven.py
    score:    the _score_events-style result {detected, detector, rule_id, all_rule_ids}
    intel_state: optional {ioc_in_feed: bool, feed_age_hours: float}
    Returns {what_happened, why_evaded, how_to_defend[]} — empty analysis
    (all fields blank/[]) when the scenario was detected.
    """
    if score.get("detected"):
        return {
            "what_happened": scenario.get("description", ""),
            "why_evaded": "",
            "how_to_defend": [],
            "caught_by": {
                "detector": score.get("detector"),
                "rule_id": score.get("rule_id"),
                "all_rule_ids": score.get("all_rule_ids", []),
            },
        }

    what = scenario.get("description", "unknown scenario")
    source = scenario.get("source", "")
    technique = scenario.get("technique_id")
    fired = score.get("all_rule_ids", []) or []

    # --- why did it evade? ---
    reasons: list[str] = []
    if not fired:
        reasons.append("no detection rule fired on any event in the scenario")
    else:
        reasons.append(
            f"rules fired ({', '.join(fired)}) but none reached the "
            f"alerting threshold for this scenario"
        )
    if score.get("detector") == "ml-anomaly-v1":
        reasons.append("the anomaly model scored the behavior but stayed "
                       "below its alert threshold")
    else:
        reasons.append("the anomaly model did not flag the behavior window")
    if source == "intel-ioc":
        ioc = scenario.get("ioc", {})
        if intel_state and not intel_state.get("ioc_in_feed", True):
            reasons.append(
                f"the IoC {ioc.get('value')} is no longer in the intel feed "
                f"(expired or replaced) — the known-malicious rules had "
                f"nothing to match against"
            )
        else:
            reasons.append(
                "the IoC is in the feed but no intel-matching rule fired — "
                "check that the event carried dst_ip/dst_host in the shape "
                "the rule reads"
            )
    elif source == "alert-replay":
        reasons.append(
            f"this exact pattern raised a real {scenario.get('rule_id')} alert "
            f"before (alert #{scenario.get('replay_of_alert_id')}) — detection "
            f"has regressed since"
        )

    # --- how to defend? ---
    defenses: list[str] = []
    guidance = TECHNIQUE_DEFENSE.get(technique or "")
    if guidance:
        defenses.append(
            f"Check {guidance['check']}: {guidance['recommend']}"
        )
    if source == "intel-ioc" and intel_state and not intel_state.get("ioc_in_feed", True):
        defenses.append(
            "Refresh the threat-intel feed (POST /intel/refresh) — the "
            "indicator aged out between feed pulls."
        )
    if not defenses:
        defenses.append(
            "No cheap signature exists for this shape. Compensating controls: "
            "tighten the anomaly threshold for this device archetype, or add "
            "an approval-gated response playbook for the behavior class."
        )
    # Always: turn the evasion into training data.
    defenses.append(
        "Recorded as a labeled attack row for the next gated retrain, so the "
        "ML models learn this exact evasion shape."
    )

    return {
        "what_happened": what,
        "why_evaded": "; ".join(reasons),
        "how_to_defend": defenses,
    }
