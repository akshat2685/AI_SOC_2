"""Synthetic SOC telemetry generator.

Produces seeded, reproducible alert-like records for ML prototyping.

EVERYTHING HERE IS SYNTHETIC. The distributions below are hand-designed to
mimic plausible SOC telemetry shapes (diurnal benign traffic, distinctive
per-attack feature shifts). They are NOT real tenant data, NOT real attack
traces, and must never be presented as such.

Schema per record:
  hour_of_day (0-23), day_of_week (0-6), off_hours (0/1, derived),
  src_asset_type in {workstation, server, database},
  failed_logins_1h, unique_dst_ips_1h, bytes_out_mb_1h,
  new_process_rarity (0-1), dns_query_entropy (0-1), alert_count_1h,
  attack_type in {benign, brute_force, phishing, c2_beacon, lateral_movement,
                  exfiltration, ransomware, unknown_anomaly},
  severity in {low, medium, high, critical}
"""

import numpy as np
import pandas as pd

SEED = 42
N_DEFAULT = 20000

ATTACK_TYPES = [
    "benign",
    "brute_force",
    "phishing",
    "c2_beacon",
    "lateral_movement",
    "exfiltration",
    "ransomware",
    "unknown_anomaly",
]
SEVERITIES = ["low", "medium", "high", "critical"]
ASSET_TYPES = ["workstation", "server", "database"]

# Rows per class: ~93% benign, ~6% known attacks, ~1% novel anomalies.
CLASS_COUNTS = {
    "benign": 18600,
    "brute_force": 300,
    "phishing": 250,
    "c2_beacon": 200,
    "lateral_movement": 200,
    "exfiltration": 150,
    "ransomware": 100,
    "unknown_anomaly": 200,
}

# P(low, medium, high, critical) per attack type.
SEVERITY_DIST = {
    "benign": [0.80, 0.15, 0.04, 0.01],
    "brute_force": [0.05, 0.35, 0.50, 0.10],
    "phishing": [0.02, 0.18, 0.55, 0.25],
    "c2_beacon": [0.02, 0.20, 0.60, 0.18],
    "lateral_movement": [0.02, 0.15, 0.50, 0.33],
    "exfiltration": [0.00, 0.05, 0.25, 0.70],
    "ransomware": [0.00, 0.02, 0.18, 0.80],
    "unknown_anomaly": [0.05, 0.30, 0.40, 0.25],
}


def _hours(rng, n, off_prob):
    """Sample hour_of_day with `off_prob` mass on off-hours (0-7, 18-23)."""
    off = rng.random(n) < off_prob
    off_h = rng.choice(np.r_[0:8, 18:24], n)
    biz_h = rng.integers(8, 18, n)
    return np.where(off, off_h, biz_h).astype(int)


def _benign(rng, n):
    hour = _hours(rng, n, 0.25)  # diurnal: mostly business hours
    return {
        "hour_of_day": hour,
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.65, 0.25, 0.10]),
        "failed_logins_1h": rng.poisson(0.5, n),
        "unique_dst_ips_1h": rng.poisson(8, n),
        "bytes_out_mb_1h": rng.lognormal(1.5, 0.8, n),
        "new_process_rarity": rng.beta(1.0, 8.0, n),
        "dns_query_entropy": rng.beta(2.0, 6.0, n),
        "alert_count_1h": rng.poisson(0.3, n),
    }


def _brute_force(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.60),
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.35, 0.55, 0.10]),
        "failed_logins_1h": rng.poisson(28, n) + rng.integers(5, 15, n),
        "unique_dst_ips_1h": rng.poisson(3, n),
        "bytes_out_mb_1h": rng.lognormal(1.0, 0.5, n),
        "new_process_rarity": rng.beta(2.0, 5.0, n),
        "dns_query_entropy": rng.beta(2.0, 5.0, n),
        "alert_count_1h": rng.poisson(2, n),
    }


def _phishing(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.20),  # arrives during work hours
        "day_of_week": rng.integers(0, 5, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.85, 0.12, 0.03]),
        "failed_logins_1h": rng.poisson(1.0, n),
        "unique_dst_ips_1h": rng.poisson(6, n),
        "bytes_out_mb_1h": rng.lognormal(1.5, 0.7, n),
        "new_process_rarity": rng.beta(6.0, 2.0, n),   # novel payload process
        "dns_query_entropy": rng.beta(5.0, 2.5, n),    # lookalike domains
        "alert_count_1h": rng.poisson(1.5, n),
    }


def _c2_beacon(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.50),
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.60, 0.35, 0.05]),
        "failed_logins_1h": rng.poisson(0.5, n),
        "unique_dst_ips_1h": rng.integers(1, 3, n),    # few, regular C2 hosts
        "bytes_out_mb_1h": rng.lognormal(0.5, 0.4, n),  # small steady beacons
        "new_process_rarity": rng.beta(3.0, 4.0, n),
        "dns_query_entropy": rng.beta(5.0, 3.0, n),    # DGA-like entropy
        "alert_count_1h": rng.poisson(1.0, n),
    }


def _lateral_movement(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.65),
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.30, 0.50, 0.20]),
        "failed_logins_1h": rng.poisson(6, n),
        "unique_dst_ips_1h": rng.poisson(22, n),       # scanning internal hosts
        "bytes_out_mb_1h": rng.lognormal(2.5, 0.8, n),
        "new_process_rarity": rng.beta(4.0, 3.0, n),
        "dns_query_entropy": rng.beta(3.0, 4.0, n),
        "alert_count_1h": rng.poisson(3, n),
    }


def _exfiltration(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.75),  # quiet hours
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.20, 0.45, 0.35]),
        "failed_logins_1h": rng.poisson(1.0, n),
        "unique_dst_ips_1h": rng.poisson(4, n),
        "bytes_out_mb_1h": rng.lognormal(6.9, 0.6, n),  # ~1 GB exfil
        "new_process_rarity": rng.beta(3.0, 5.0, n),
        "dns_query_entropy": rng.beta(2.0, 5.0, n),
        "alert_count_1h": rng.poisson(2, n),
    }


def _ransomware(rng, n):
    return {
        "hour_of_day": _hours(rng, n, 0.45),
        "day_of_week": rng.integers(0, 7, n),
        "src_asset_type": rng.choice(ASSET_TYPES, n, p=[0.55, 0.35, 0.10]),
        "failed_logins_1h": rng.poisson(2, n),
        "unique_dst_ips_1h": rng.poisson(10, n),
        "bytes_out_mb_1h": rng.lognormal(3.5, 0.7, n),
        "new_process_rarity": rng.beta(7.0, 1.5, n),   # brand-new encryptor binary
        "dns_query_entropy": rng.beta(3.0, 4.0, n),
        "alert_count_1h": rng.poisson(6, n),           # noisy: many detections
    }


def _unknown_anomaly(rng, n):
    """Novel combos that match no known class signature (the 0-day proxy).

    Pattern A: database + off-hours + very high DNS entropy + rare process.
    Pattern B: workstation + huge fan-out + huge egress, few failed logins.
    Pattern C: server + never-before-seen process during business hours.
    """
    out = {k: np.zeros(n) for k in (
        "hour_of_day", "day_of_week", "failed_logins_1h", "unique_dst_ips_1h",
        "bytes_out_mb_1h", "new_process_rarity", "dns_query_entropy",
        "alert_count_1h")}
    out["src_asset_type"] = np.array(["workstation"] * n, dtype=object)
    pat = rng.random(n)
    ia = pat < 0.40
    ib = (pat >= 0.40) & (pat < 0.75)
    ic = pat >= 0.75
    na, nb, nc = ia.sum(), ib.sum(), ic.sum()

    out["hour_of_day"][ia] = _hours(rng, na, 1.0)
    out["src_asset_type"][ia] = "database"
    out["failed_logins_1h"][ia] = rng.poisson(0.3, na)
    out["unique_dst_ips_1h"][ia] = rng.poisson(3, na)
    out["bytes_out_mb_1h"][ia] = rng.lognormal(2.0, 0.6, na)
    out["new_process_rarity"][ia] = rng.beta(7.0, 2.0, na)
    out["dns_query_entropy"][ia] = rng.beta(9.0, 1.2, na)
    out["alert_count_1h"][ia] = rng.poisson(0.5, na)

    out["hour_of_day"][ib] = _hours(rng, nb, 0.5)
    out["src_asset_type"][ib] = "workstation"
    out["failed_logins_1h"][ib] = rng.poisson(0.5, nb)
    out["unique_dst_ips_1h"][ib] = rng.poisson(35, nb)
    out["bytes_out_mb_1h"][ib] = rng.lognormal(5.5, 0.5, nb)
    out["new_process_rarity"][ib] = rng.beta(2.0, 6.0, nb)
    out["dns_query_entropy"][ib] = rng.beta(2.0, 6.0, nb)
    out["alert_count_1h"][ib] = rng.poisson(1.0, nb)

    out["hour_of_day"][ic] = _hours(rng, nc, 0.0)  # hides in business hours
    out["src_asset_type"][ic] = "server"
    out["failed_logins_1h"][ic] = 0
    out["unique_dst_ips_1h"][ic] = rng.poisson(5, nc)
    out["bytes_out_mb_1h"][ic] = rng.lognormal(1.5, 0.5, nc)
    out["new_process_rarity"][ic] = 0.95 + rng.random(nc) * 0.05
    out["dns_query_entropy"][ic] = rng.beta(4.0, 4.0, nc)
    out["alert_count_1h"][ic] = rng.poisson(0.5, nc)

    out["day_of_week"] = rng.integers(0, 7, n)
    return out


_SAMPLERS = {
    "benign": _benign,
    "brute_force": _brute_force,
    "phishing": _phishing,
    "c2_beacon": _c2_beacon,
    "lateral_movement": _lateral_movement,
    "exfiltration": _exfiltration,
    "ransomware": _ransomware,
    "unknown_anomaly": _unknown_anomaly,
}


def generate(n_per_class=None, seed=SEED):
    """Generate the synthetic telemetry DataFrame.

    Returns a shuffled DataFrame with features + attack_type + severity.
    """
    rng = np.random.default_rng(seed)
    counts = n_per_class or CLASS_COUNTS
    frames = []
    for atk, cnt in counts.items():
        cols = _SAMPLERS[atk](rng, cnt)
        df = pd.DataFrame(cols)
        df["attack_type"] = atk
        # severity correlated with attack type
        sev_idx = rng.choice(len(SEVERITIES), cnt, p=SEVERITY_DIST[atk])
        df["severity"] = [SEVERITIES[i] for i in sev_idx]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    # derived feature
    df["off_hours"] = (
        (df["hour_of_day"] < 8) | (df["hour_of_day"] >= 18) | (df["day_of_week"] >= 5)
    ).astype(int)
    # shuffle reproducibly
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    cols = ["hour_of_day", "day_of_week", "off_hours", "src_asset_type",
            "failed_logins_1h", "unique_dst_ips_1h", "bytes_out_mb_1h",
            "new_process_rarity", "dns_query_entropy", "alert_count_1h",
            "attack_type", "severity"]
    return df[cols]


if __name__ == "__main__":
    df = generate()
    print("shape:", df.shape)
    print(df["attack_type"].value_counts())
    print(df["severity"].value_counts())
    print(df.describe().round(2).to_string())
