"""ATT&CK-grounded v2 synthetic SOC telemetry generator.

Produces seeded, reproducible device-hour feature rows for ML training.

EVERYTHING HERE IS SYNTHETIC. Each attack class is a hand-designed,
jittered approximation of one MITRE ATT&CK technique's observable footprint
in the 15 engineered features below. These are NOT real attack traces, NOT
real tenant data, and must never be presented as such.

The benign class is ANCHORED on real telemetry (see real_baseline.json:
961 unlabeled events from one workstation, device agt-11577e30bab3,
assumed benign): hour concentration, port mix, and process mix follow the
baseline's distributions. Rows from that source carry provenance
"real-anchored". Because the source events are UNLABELED, some
"real-anchored" rows may unknowingly describe malicious activity.

Feature columns (EXACT order, also written to feature_schema.json):
  hour_of_day, day_of_week, off_hours, failed_logins_1h, unique_dst_ips_1h,
  bytes_out_mb_1h, new_process_rarity, dns_query_entropy, alert_count_1h,
  uncommon_port_hits_1h, persistence_events_1h, suspicious_cmdline_hits_1h,
  asset_workstation, asset_server, asset_database

Label columns: is_attack (0/1), tactic, technique_id, severity, provenance.

Severity mapping by tactic:
  impact -> CRITICAL
  credential-access, exfiltration, lateral-movement, command-and-control,
  persistence, privilege-escalation, defense-evasion -> HIGH
  execution, discovery, unknown -> MEDIUM
  benign -> LOW
"""

import numpy as np
import pandas as pd

SEED = 42

FEATURE_COLUMNS = [
    "hour_of_day",
    "day_of_week",
    "off_hours",
    "failed_logins_1h",
    "unique_dst_ips_1h",
    "bytes_out_mb_1h",
    "new_process_rarity",
    "dns_query_entropy",
    "alert_count_1h",
    "uncommon_port_hits_1h",
    "persistence_events_1h",
    "suspicious_cmdline_hits_1h",
    "asset_workstation",
    "asset_server",
    "asset_database",
]
LABEL_COLUMNS = ["is_attack", "tactic", "technique_id", "severity", "provenance"]

SEVERITY_BY_TACTIC = {
    "impact": "CRITICAL",
    "credential-access": "HIGH",
    "exfiltration": "HIGH",
    "lateral-movement": "HIGH",
    "command-and-control": "HIGH",
    "persistence": "HIGH",
    "privilege-escalation": "HIGH",
    "defense-evasion": "HIGH",
    "execution": "MEDIUM",
    "discovery": "MEDIUM",
    "unknown": "MEDIUM",
    "benign": "LOW",
}

# Real baseline (real_baseline.json): 961 unlabeled events, one workstation.
# Hours: 11 -> 1898, 10 -> 24 (connection-level counts; normalized to probs).
# Ports: 8081 (755), 443 (135), 3128 (12) -- 8081 is "uncommon" per the
# detection rule list, so real-anchored benign rows carry HIGH
# uncommon_port_hits_1h. That is honest: this tenant's normal includes it.
# Day of week: capture day was Saturday (2026-09-26).
_BASELINE_HOUR_P = {11: 1898 / 1922, 10: 24 / 1922}
_BASELINE_DAY = 5  # Saturday, the actual capture day


def _hours(rng, n, off_prob):
    """Sample hour_of_day with `off_prob` mass on off-hours (0-7, 18-23)."""
    off = rng.random(n) < off_prob
    off_h = rng.choice(np.r_[0:8, 18:24], n)
    biz_h = rng.integers(8, 18, n)
    return np.where(off, off_h, biz_h).astype(int)


def _mk(rng, n, off_prob=0.5, asset_p=(0.65, 0.25, 0.10), **kw):
    """Base row dict with benign-ish defaults; kw overrides any feature."""
    d = {
        "hour_of_day": _hours(rng, n, off_prob),
        "day_of_week": rng.integers(0, 7, n),
        "failed_logins_1h": rng.poisson(0.5, n),
        "unique_dst_ips_1h": rng.poisson(6, n),
        "bytes_out_mb_1h": rng.lognormal(1.5, 0.8, n),
        "new_process_rarity": rng.beta(2.0, 6.0, n),
        "dns_query_entropy": rng.beta(2.0, 6.0, n),
        "alert_count_1h": rng.poisson(1, n),
        "uncommon_port_hits_1h": rng.poisson(1, n),
        "persistence_events_1h": rng.poisson(0.2, n),
        "suspicious_cmdline_hits_1h": rng.poisson(0.3, n),
        "asset_type": rng.choice(
            ["workstation", "server", "database"], n, p=asset_p),
    }
    d.update(kw)
    return d


# ---------------------------------------------------------------------------
# ATT&CK technique generators (24 named + 1 unknown proxy).
# Each returns a dict of raw features; generate() adds labels + one-hots.
# ---------------------------------------------------------------------------

def _t1059_001(rng, n):  # PowerShell
    return _mk(rng, n, off_prob=0.55, asset_p=(0.70, 0.25, 0.05),
               suspicious_cmdline_hits_1h=rng.poisson(5, n),
               new_process_rarity=rng.beta(6.0, 2.0, n),
               alert_count_1h=rng.poisson(2, n))


def _t1059_003(rng, n):  # Windows Command Shell
    return _mk(rng, n, off_prob=0.50, asset_p=(0.70, 0.25, 0.05),
               suspicious_cmdline_hits_1h=rng.poisson(3, n),
               new_process_rarity=rng.beta(4.0, 3.0, n),
               alert_count_1h=rng.poisson(1, n).astype(float) + rng.poisson(1, n))


def _t1053_005(rng, n):  # Scheduled Task/Job
    return _mk(rng, n, off_prob=0.60, asset_p=(0.55, 0.40, 0.05),
               persistence_events_1h=rng.poisson(3, n) + 1,
               suspicious_cmdline_hits_1h=rng.poisson(2, n),
               new_process_rarity=rng.beta(3.0, 4.0, n),
               alert_count_1h=rng.poisson(2, n))


def _t1547_001(rng, n):  # Registry Run Keys / Startup Folder
    return _mk(rng, n, off_prob=0.55, asset_p=(0.75, 0.20, 0.05),
               persistence_events_1h=rng.poisson(4, n) + 1,
               suspicious_cmdline_hits_1h=rng.poisson(1, n),
               new_process_rarity=rng.beta(4.0, 3.0, n),
               alert_count_1h=rng.poisson(2, n))


def _t1055(rng, n):  # Process Injection
    return _mk(rng, n, off_prob=0.60, asset_p=(0.60, 0.35, 0.05),
               new_process_rarity=rng.beta(7.0, 2.0, n),
               suspicious_cmdline_hits_1h=rng.poisson(2, n),
               alert_count_1h=rng.poisson(3, n),
               failed_logins_1h=rng.poisson(1, n))


def _t1134(rng, n):  # Access Token Manipulation
    return _mk(rng, n, off_prob=0.55, asset_p=(0.55, 0.40, 0.05),
               new_process_rarity=rng.beta(5.0, 2.5, n),
               failed_logins_1h=rng.poisson(4, n),
               alert_count_1h=rng.poisson(2, n).astype(float) + rng.poisson(1, n),
               suspicious_cmdline_hits_1h=rng.poisson(1, n).astype(float) + 0.5)


def _t1027(rng, n):  # Obfuscated Files or Information
    return _mk(rng, n, off_prob=0.50, asset_p=(0.65, 0.30, 0.05),
               suspicious_cmdline_hits_1h=rng.poisson(6, n),
               new_process_rarity=rng.beta(6.0, 2.0, n),
               dns_query_entropy=rng.beta(4.0, 3.0, n),
               alert_count_1h=rng.poisson(2, n))


def _t1070_004(rng, n):  # File Deletion (log clearing)
    return _mk(rng, n, off_prob=0.70, asset_p=(0.50, 0.45, 0.05),
               suspicious_cmdline_hits_1h=rng.poisson(3, n),
               new_process_rarity=rng.beta(3.0, 4.0, n),
               alert_count_1h=rng.poisson(2, n).astype(float) + rng.poisson(1, n))


def _t1562_001(rng, n):  # Impair Defenses: Disable or Modify Tools
    return _mk(rng, n, off_prob=0.60, asset_p=(0.60, 0.35, 0.05),
               alert_count_1h=rng.poisson(5, n),
               suspicious_cmdline_hits_1h=rng.poisson(3, n),
               persistence_events_1h=rng.poisson(1, n),
               new_process_rarity=rng.beta(4.0, 3.0, n))


def _t1003_001(rng, n):  # LSASS Memory
    return _mk(rng, n, off_prob=0.70, asset_p=(0.55, 0.40, 0.05),
               new_process_rarity=rng.beta(7.0, 2.0, n),
               suspicious_cmdline_hits_1h=rng.poisson(5, n),
               alert_count_1h=rng.poisson(4, n),
               failed_logins_1h=rng.poisson(1, n))


def _t1110(rng, n):  # Brute Force
    return _mk(rng, n, off_prob=0.65, asset_p=(0.30, 0.60, 0.10),
               failed_logins_1h=rng.poisson(40, n) + rng.integers(5, 15, n),
               unique_dst_ips_1h=rng.poisson(3, n),
               alert_count_1h=rng.poisson(4, n),
               uncommon_port_hits_1h=rng.poisson(1, n))


def _t1555(rng, n):  # Credentials from Password Stores
    return _mk(rng, n, off_prob=0.55, asset_p=(0.80, 0.15, 0.05),
               new_process_rarity=rng.beta(5.0, 3.0, n),
               alert_count_1h=rng.poisson(2, n).astype(float) + rng.poisson(1, n),
               bytes_out_mb_1h=rng.lognormal(2.0, 0.6, n),
               suspicious_cmdline_hits_1h=rng.poisson(1, n).astype(float) + 0.5)


def _t1083(rng, n):  # File and Directory Discovery
    return _mk(rng, n, off_prob=0.40, asset_p=(0.60, 0.35, 0.05),
               new_process_rarity=rng.beta(3.0, 5.0, n),
               alert_count_1h=rng.poisson(1, n),
               suspicious_cmdline_hits_1h=rng.poisson(1, n),
               unique_dst_ips_1h=rng.poisson(3, n))


def _t1057(rng, n):  # Process Discovery
    return _mk(rng, n, off_prob=0.40, asset_p=(0.60, 0.35, 0.05),
               new_process_rarity=rng.beta(2.5, 5.0, n),
               alert_count_1h=rng.poisson(1, n),
               suspicious_cmdline_hits_1h=rng.poisson(1, n).astype(float) + 0.5)


def _t1018(rng, n):  # Remote System Discovery
    return _mk(rng, n, off_prob=0.50, asset_p=(0.45, 0.50, 0.05),
               unique_dst_ips_1h=rng.poisson(25, n),
               alert_count_1h=rng.poisson(2, n),
               new_process_rarity=rng.beta(3.0, 4.0, n))


def _t1021_001(rng, n):  # Remote Desktop Protocol
    return _mk(rng, n, off_prob=0.70, asset_p=(0.40, 0.55, 0.05),
               failed_logins_1h=rng.poisson(8, n),
               unique_dst_ips_1h=rng.poisson(12, n),
               alert_count_1h=rng.poisson(3, n),
               uncommon_port_hits_1h=rng.poisson(0.5, n))


def _t1570(rng, n):  # Lateral Tool Transfer
    return _mk(rng, n, off_prob=0.65, asset_p=(0.40, 0.55, 0.05),
               bytes_out_mb_1h=rng.lognormal(4.0, 0.7, n),
               unique_dst_ips_1h=rng.poisson(10, n),
               new_process_rarity=rng.beta(4.0, 3.0, n),
               alert_count_1h=rng.poisson(2, n).astype(float) + rng.poisson(1, n))


def _t1071_001(rng, n):  # Web Protocols (C2 beaconing)
    return _mk(rng, n, off_prob=0.50, asset_p=(0.60, 0.35, 0.05),
               unique_dst_ips_1h=rng.integers(1, 3, n),
               bytes_out_mb_1h=rng.lognormal(0.5, 0.4, n),
               dns_query_entropy=rng.beta(6.0, 2.5, n),
               alert_count_1h=rng.poisson(1, n).astype(float) + rng.poisson(1, n))


def _t1105(rng, n):  # Ingress Tool Transfer
    return _mk(rng, n, off_prob=0.55, asset_p=(0.60, 0.35, 0.05),
               bytes_out_mb_1h=rng.lognormal(3.0, 0.6, n),
               unique_dst_ips_1h=rng.poisson(3, n),
               new_process_rarity=rng.beta(5.0, 2.5, n),
               alert_count_1h=rng.poisson(2, n))


def _t1008(rng, n):  # Fallback Channels
    return _mk(rng, n, off_prob=0.55, asset_p=(0.60, 0.35, 0.05),
               unique_dst_ips_1h=rng.poisson(12, n),
               dns_query_entropy=rng.beta(5.0, 3.0, n),
               uncommon_port_hits_1h=rng.poisson(4, n),
               alert_count_1h=rng.poisson(2, n))


def _t1041(rng, n):  # Exfiltration Over C2 Channel
    return _mk(rng, n, off_prob=0.80, asset_p=(0.30, 0.50, 0.20),
               bytes_out_mb_1h=rng.lognormal(6.9, 0.6, n),
               unique_dst_ips_1h=rng.poisson(3, n),
               alert_count_1h=rng.poisson(2, n).astype(float) + rng.poisson(1, n))


def _t1048(rng, n):  # Exfiltration Over Alternative Protocol
    return _mk(rng, n, off_prob=0.80, asset_p=(0.25, 0.55, 0.20),
               bytes_out_mb_1h=rng.lognormal(6.5, 0.6, n),
               uncommon_port_hits_1h=rng.poisson(8, n),
               unique_dst_ips_1h=rng.poisson(4, n),
               alert_count_1h=rng.poisson(3, n))


def _t1486(rng, n):  # Data Encrypted for Impact (ransomware)
    return _mk(rng, n, off_prob=0.50, asset_p=(0.55, 0.40, 0.05),
               new_process_rarity=rng.beta(8.0, 1.5, n),
               alert_count_1h=rng.poisson(7, n),
               suspicious_cmdline_hits_1h=rng.poisson(2, n),
               bytes_out_mb_1h=rng.lognormal(3.0, 0.7, n))


def _t1490(rng, n):  # Inhibit System Recovery
    return _mk(rng, n, off_prob=0.60, asset_p=(0.50, 0.45, 0.05),
               suspicious_cmdline_hits_1h=rng.poisson(5, n),
               persistence_events_1h=rng.poisson(2, n),
               alert_count_1h=rng.poisson(4, n),
               new_process_rarity=rng.beta(5.0, 2.5, n))


def _unknown(rng, n):  # 0-day proxy: novel combos matching no known footprint
    out = _mk(rng, n, off_prob=0.5)
    pat = rng.random(n)
    ia = pat < 0.40
    ib = (pat >= 0.40) & (pat < 0.75)
    ic = pat >= 0.75
    na, nb, nc = int(ia.sum()), int(ib.sum()), int(ic.sum())

    # A: database + off-hours + very high DNS entropy + rare process
    out["hour_of_day"][ia] = _hours(rng, na, 1.0)
    out["asset_type"][ia] = "database"
    out["dns_query_entropy"][ia] = rng.beta(9.0, 1.2, na)
    out["new_process_rarity"][ia] = rng.beta(7.0, 2.0, na)
    out["persistence_events_1h"][ia] = rng.poisson(2, na)
    out["alert_count_1h"][ia] = rng.poisson(0.5, na)

    # B: workstation + huge fan-out + huge egress + uncommon ports
    out["asset_type"][ib] = "workstation"
    out["unique_dst_ips_1h"][ib] = rng.poisson(40, nb)
    out["bytes_out_mb_1h"][ib] = rng.lognormal(5.5, 0.5, nb)
    out["uncommon_port_hits_1h"][ib] = rng.poisson(15, nb)
    out["failed_logins_1h"][ib] = rng.poisson(0.5, nb)

    # C: server + business hours + max-rarity process + cmdline hits
    out["hour_of_day"][ic] = _hours(rng, nc, 0.0)
    out["asset_type"][ic] = "server"
    out["new_process_rarity"][ic] = 0.95 + rng.random(nc) * 0.05
    out["suspicious_cmdline_hits_1h"][ic] = rng.poisson(3, nc)
    out["alert_count_1h"][ic] = rng.poisson(0.5, nc)
    return out


# technique_id -> (tactic, generator)
TECHNIQUES = {
    "T1059.001": ("execution", _t1059_001),
    "T1059.003": ("execution", _t1059_003),
    "T1053.005": ("persistence", _t1053_005),   # Scheduled Task: execution+persistence
    "T1547.001": ("persistence", _t1547_001),
    "T1055": ("privilege-escalation", _t1055),
    "T1134": ("privilege-escalation", _t1134),
    "T1027": ("defense-evasion", _t1027),
    "T1070.004": ("defense-evasion", _t1070_004),
    "T1562.001": ("defense-evasion", _t1562_001),
    "T1003.001": ("credential-access", _t1003_001),
    "T1110": ("credential-access", _t1110),
    "T1555": ("credential-access", _t1555),
    "T1083": ("discovery", _t1083),
    "T1057": ("discovery", _t1057),
    "T1018": ("discovery", _t1018),
    "T1021.001": ("lateral-movement", _t1021_001),
    "T1570": ("lateral-movement", _t1570),
    "T1071.001": ("command-and-control", _t1071_001),
    "T1105": ("command-and-control", _t1105),
    "T1008": ("command-and-control", _t1008),
    "T1041": ("exfiltration", _t1041),
    "T1048": ("exfiltration", _t1048),
    "T1486": ("impact", _t1486),
    "T1490": ("impact", _t1490),
    "unknown": ("unknown", _unknown),
}

# Rows per class: benign ~50%, rest spread across 24 techniques + unknown.
N_BENIGN_REAL = 10000
N_BENIGN_TEMPLATE = 10000
N_PER_TECHNIQUE = 750
N_UNKNOWN = 2000


# ---------------------------------------------------------------------------
# Benign generators
# ---------------------------------------------------------------------------

def _benign_real(rng, n):
    """Benign rows anchored on real_baseline.json distributions.

    Hour mix from the baseline's hour counts (11 dominates); single
    workstation (the capture device); port mix 8081-heavy, which is
    "uncommon" per the detection rule list -- hence the high
    uncommon_port_hits_1h. Provenance: "real-anchored".
    """
    hour_choices = np.array(list(_BASELINE_HOUR_P.keys()))
    hour_probs = np.array(list(_BASELINE_HOUR_P.values()))
    return {
        "hour_of_day": rng.choice(hour_choices, n, p=hour_probs),
        "day_of_week": np.full(n, _BASELINE_DAY),
        "failed_logins_1h": rng.poisson(0.3, n),
        "unique_dst_ips_1h": rng.poisson(10, n),
        "bytes_out_mb_1h": rng.lognormal(2.0, 0.8, n),
        "new_process_rarity": rng.beta(1.2, 8.0, n),
        "dns_query_entropy": rng.beta(2.0, 6.0, n),
        "alert_count_1h": rng.poisson(0.3, n),
        "uncommon_port_hits_1h": rng.poisson(25, n),
        "persistence_events_1h": rng.poisson(0.05, n),
        "suspicious_cmdline_hits_1h": rng.poisson(0.1, n),
        "asset_type": np.array(["workstation"] * n, dtype=object),
    }


def _benign_browsing(rng, n):
    return _mk(rng, n, off_prob=0.15, asset_p=(0.90, 0.08, 0.02),
               unique_dst_ips_1h=rng.poisson(12, n),
               bytes_out_mb_1h=rng.lognormal(2.5, 0.8, n),
               dns_query_entropy=rng.beta(2.5, 5.0, n),
               uncommon_port_hits_1h=rng.poisson(2, n),
               new_process_rarity=rng.beta(1.5, 8.0, n))


def _benign_updates(rng, n):
    return _mk(rng, n, off_prob=0.70, asset_p=(0.70, 0.28, 0.02),
               bytes_out_mb_1h=rng.lognormal(4.0, 0.7, n),
               unique_dst_ips_1h=rng.poisson(4, n),
               new_process_rarity=rng.beta(2.0, 6.0, n),
               alert_count_1h=rng.poisson(0.5, n))


def _benign_dev(rng, n):
    return _mk(rng, n, off_prob=0.20, asset_p=(0.85, 0.13, 0.02),
               new_process_rarity=rng.beta(3.0, 5.0, n),
               unique_dst_ips_1h=rng.poisson(8, n),
               bytes_out_mb_1h=rng.lognormal(2.0, 0.7, n),
               suspicious_cmdline_hits_1h=rng.poisson(0.5, n))


def generate(seed=SEED):
    """Generate the v2 dataset.

    Returns a shuffled DataFrame with the 15 feature columns + label
    columns (is_attack, tactic, technique_id, severity, provenance).
    """
    rng = np.random.default_rng(seed)
    frames = []

    def _frame(raw, is_attack, tactic, technique_id, provenance):
        df = pd.DataFrame(raw)
        df["off_hours"] = (
            (df["hour_of_day"] < 8) | (df["hour_of_day"] >= 18)
            | (df["day_of_week"] >= 5)
        ).astype(int)
        dummies = pd.get_dummies(df["asset_type"], prefix="asset").astype(int)
        for col in ("asset_workstation", "asset_server", "asset_database"):
            df[col] = dummies.get(col, 0)
        df["is_attack"] = is_attack
        df["tactic"] = tactic
        df["technique_id"] = technique_id
        df["severity"] = SEVERITY_BY_TACTIC[tactic]
        df["provenance"] = provenance
        return df[FEATURE_COLUMNS + LABEL_COLUMNS]

    # benign: real-anchored + templates
    frames.append(_frame(_benign_real(rng, N_BENIGN_REAL),
                         0, "benign", "benign", "real-anchored"))
    frames.append(_frame(_benign_browsing(rng, 4000),
                         0, "benign", "benign", "template"))
    frames.append(_frame(_benign_updates(rng, 3000),
                         0, "benign", "benign", "template"))
    frames.append(_frame(_benign_dev(rng, 3000),
                         0, "benign", "benign", "template"))

    # attacks: 24 ATT&CK techniques + 1 unknown 0-day proxy
    for tid, (tactic, gen) in TECHNIQUES.items():
        n = N_UNKNOWN if tid == "unknown" else N_PER_TECHNIQUE
        frames.append(_frame(gen(rng, n), 1, tactic, tid, "attack-synthetic"))

    df = pd.concat(frames, ignore_index=True)
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    return df


if __name__ == "__main__":
    df = generate()
    print("shape:", df.shape)
    print(df["tactic"].value_counts())
    print(df["provenance"].value_counts())
    print(df["severity"].value_counts())
    print(df[FEATURE_COLUMNS].describe().round(2).to_string())
