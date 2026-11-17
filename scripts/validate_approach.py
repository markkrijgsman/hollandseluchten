#!/usr/bin/env python3
"""Reproducible quantitative validation of the LuchtZorg / Hollandse Luchten PM2.5 methodology.

Computes three empirical benchmarks on the official hackathon datasets:
  1. Outlier (< 100 ug/m3) and daily completeness (>= 18 valid hours) audit on Luchtmeetnet & HoLu sensors.
  2. Leave-One-Out Cross-Validation (LOOCV) of 1/d^2 spatial weighting (0.5 km floor) across official stations.
  3. Co-located / nearby (<= 1.5 km) Hollandse Luchten sensor vs. official reference station comparison:
     raw vs. RIVM-calibrated (pm25_kal), multi-sensor 1/d^2 aggregation gain, empirical coverage of the
     Samen Analyseren uncertainty band (max(20%, 5.3 ug/m3)), low-concentration (< 10 ug/m3) & high-RH (> 80%) effects.

Usage:
  python3 scripts/validate_approach.py [--data-dir ../HackathonHollandseLuchten/data] [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

EARTH_RADIUS_KM = 6371.0088
MIN_DISTANCE_KM = 0.5
CUTOFF = 100.0
MIN_HOURS = 18
NL_LAT = (50.7, 53.6)
NL_LON = (3.3, 7.3)
FIXED_TZ_OFFSET = pd.Timedelta(hours=1)


def haversine_matrix(lat1: np.ndarray, lon1: np.ndarray, lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Pairwise Haversine distance matrix in km between (lat1, lon1) [N] and (lat2, lon2) [M]."""
    p1, p2 = np.radians(lat1)[:, None], np.radians(lat2)[None, :]
    dp = p2 - p1
    dl = np.radians(lon2)[None, :] - np.radians(lon1)[:, None]
    a = np.sin(dp / 2.0) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    bias = float(np.mean(err))
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else float("nan")
    corr = float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 1 else float("nan")
    return {
        "n": int(len(y_true)),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "r2": round(r2, 3),
        "pearson_r": round(corr, 3),
    }


def sensor_uncertainty_hourly(val: pd.Series) -> pd.Series:
    """Exact Samen Analyseren add_uncertainty_sensor_percent: max(20% of value, 5.3 ug/m3)."""
    return np.maximum(0.20 * val, 5.3)


def run_validation(data_dir: Path) -> dict:
    ref_path = data_dir / "reference_measurements.parquet"
    meta_path = data_dir / "reference_station_metadata.csv"
    sens_path = data_dir / "data_sensors.parquet"

    meta = pd.read_csv(meta_path).rename(columns={
        "meetlocatie_id": "station",
        "meetlocatie_naam": "name",
        "breedtegraad": "lat",
        "lengtegraad": "lon",
        "stationstype": "station_type",
        "gebiedstype": "area_type",
    })

    # --- 1. Load Reference PM2.5 (2020-2026) ---
    ref_tbl = pq.read_table(
        ref_path,
        columns=["meetlocatie_id", "begindatumtijd", "waarde"],
        filters=[("component", "==", "PM2.5")],
    )
    ref = ref_tbl.to_pandas().dropna(subset=["waarde"]).rename(
        columns={"meetlocatie_id": "station", "waarde": "value"}
    )
    ref["day"] = ref["begindatumtijd"].str[:10]
    ref["hour"] = ref["begindatumtijd"].str[:13]
    del ref_tbl

    ref_total_hours = len(ref)
    ref_ge_100 = ref[ref["value"] >= CUTOFF]
    ref_nye_ge_100 = ref_ge_100[ref_ge_100["day"].str[5:].isin(["12-31", "01-01"])]

    ref_clean = ref[ref["value"] < CUTOFF]
    ref_daily_all = ref_clean.groupby(["day", "station"], as_index=False).agg(
        hours=("value", "size"), mean=("value", "mean")
    )
    ref_daily = ref_daily_all[ref_daily_all["hours"] >= MIN_HOURS].copy()
    ref_daily = ref_daily.merge(meta[["station", "name", "lat", "lon", "station_type", "area_type"]], on="station")

    dataset_audit = {
        "reference": {
            "stations": int(ref_daily["station"].nunique()),
            "date_from": str(ref["day"].min()),
            "date_to": str(ref["day"].max()),
            "hourly_rows": int(ref_total_hours),
            "outliers_ge_100": int(len(ref_ge_100)),
            "outliers_ge_100_pct": round(100.0 * len(ref_ge_100) / ref_total_hours, 4),
            "outliers_on_new_years_pct_of_outliers": round(
                100.0 * len(ref_nye_ge_100) / max(len(ref_ge_100), 1), 1
            ),
            "station_days_total": int(len(ref_daily_all)),
            "station_days_ge_18h": int(len(ref_daily)),
            "station_days_excluded_lt_18h_pct": round(
                100.0 * (1.0 - len(ref_daily) / len(ref_daily_all)), 2
            ),
        }
    }
    del ref, ref_clean, ref_daily_all

    # --- 2. Benchmark 1: Leave-One-Out Cross-Validation (LOOCV) on 2025-01-01..2026-09-30 ---
    ref_recent = ref_daily[ref_daily["day"] >= "2025-01-01"].copy()
    stations_df = ref_recent[["station", "name", "lat", "lon", "station_type", "area_type"]].drop_duplicates("station").reset_index(drop=True)
    dist_mat = haversine_matrix(
        stations_df["lat"].to_numpy(), stations_df["lon"].to_numpy(),
        stations_df["lat"].to_numpy(), stations_df["lon"].to_numpy(),
    )
    np.fill_diagonal(dist_mat, np.inf)  # hold out self!

    piv = ref_recent.pivot(index="day", columns="station", values="mean")
    piv = piv.reindex(columns=stations_df["station"])
    vals = piv.to_numpy()  # shape [D, S]
    valid_mask = ~np.isnan(vals)

    loocv_results = {}
    for radius in (5.0, 15.0):
        in_rad = dist_mat <= radius  # [S_target, S_neighbor]
        eff_d = np.maximum(dist_mat, MIN_DISTANCE_KM)
        base_w = np.where(in_rad, 1.0 / (eff_d ** 2), 0.0)  # [S_target, S_neighbor]

        yt_all, yp_all, st_type_all, nearest_all = [], [], [], []
        for s_i in range(len(stations_df)):
            w_row = base_w[s_i]  # [S_neighbor]
            if w_row.sum() == 0:
                continue
            target_col = vals[:, s_i]
            day_ok = ~np.isnan(target_col)
            if not np.any(day_ok):
                continue
            sub_vals = np.where(valid_mask[day_ok], vals[day_ok], 0.0)
            sub_w = np.where(valid_mask[day_ok], w_row[None, :], 0.0)
            w_sum = sub_w.sum(axis=1)
            has_nb = w_sum > 0
            if not np.any(has_nb):
                continue
            preds = (sub_vals[has_nb] * sub_w[has_nb]).sum(axis=1) / w_sum[has_nb]
            trues = target_col[day_ok][has_nb]

            # Nearest active neighbor distance per day
            active_dists = np.where(valid_mask[day_ok][has_nb] & in_rad[s_i][None, :], dist_mat[s_i][None, :], np.inf)
            nearest_d = active_dists.min(axis=1)

            yt_all.append(trues)
            yp_all.append(preds)
            st_type_all.extend([stations_df.loc[s_i, "station_type"]] * len(trues))
            nearest_all.append(nearest_d)

        yt = np.concatenate(yt_all)
        yp = np.concatenate(yp_all)
        nd = np.concatenate(nearest_all)
        st_types = np.array(st_type_all)

        by_type = {}
        for t_name in ("achtergrond", "verkeer", "industrie"):
            m = st_types == t_name
            if np.any(m):
                by_type[t_name] = metrics(yt[m], yp[m])

        by_dist = {}
        for label, lo_d, hi_d in [("le_2km", 0.0, 2.0), ("2_to_5km", 2.0, 5.0), ("5_to_15km", 5.0, 15.0)]:
            m = (nd > lo_d) & (nd <= hi_d) if lo_d > 0 else (nd <= hi_d)
            if np.any(m):
                by_dist[label] = metrics(yt[m], yp[m])

        loocv_results[f"radius_{int(radius)}km"] = {
            "overall": metrics(yt, yp),
            "coverage_pct_of_station_days": round(100.0 * len(yt) / len(ref_recent), 1),
            "by_station_type": by_type,
            "by_nearest_neighbor_distance": by_dist,
        }

    # --- 3. Benchmark 2: Citizen Sensors vs. Co-Located / Nearby Official Stations (<= 1.5 km) ---
    sensor_validation = None
    if sens_path.exists():
        sens_tbl = pq.read_table(
            sens_path,
            columns=["kit_id", "timestamp_from", "pm25_raw", "pm25_kal", "rh", "latitude", "longitude"],
        )
        sens = sens_tbl.to_pandas()
        del sens_tbl

        sens_in_nl = sens[
            sens["latitude"].between(*NL_LAT) & sens["longitude"].between(*NL_LON)
        ].copy()
        total_sens_rows = len(sens_in_nl)
        raw_nonnull = sens_in_nl["pm25_raw"].dropna()
        kal_nonnull = sens_in_nl["pm25_kal"].dropna()

        sens_kal = sens_in_nl.dropna(subset=["pm25_kal"]).copy()
        ts = pd.to_datetime(sens_kal["timestamp_from"], utc=True) + FIXED_TZ_OFFSET
        sens_kal["day"] = ts.dt.strftime("%Y-%m-%d")
        sens_kal["hour"] = ts.dt.strftime("%Y-%m-%dT%H")

        outliers_kal = int((sens_kal["pm25_kal"] >= CUTOFF).sum())
        outliers_raw = int((raw_nonnull >= CUTOFF).sum())

        # Hourly aggregation per kit (matching SensorRepository.hourly_range + R cutoff + uncertainty)
        hourly_kit = sens_kal.groupby(["kit_id", "hour"], as_index=False).agg(
            day=("day", "first"),
            pm25_kal=("pm25_kal", "mean"),
            pm25_raw=("pm25_raw", "mean"),
            rh=("rh", "mean"),
            lat=("latitude", "median"),
            lon=("longitude", "median"),
        )
        del sens, sens_in_nl, sens_kal

        hourly_kit_clean = hourly_kit[hourly_kit["pm25_kal"] < CUTOFF].copy()
        hourly_kit_clean["sd"] = sensor_uncertainty_hourly(hourly_kit_clean["pm25_kal"])

        kit_daily_all = hourly_kit_clean.groupby(["day", "kit_id"], as_index=False).agg(
            hours=("pm25_kal", "size"),
            kal_mean=("pm25_kal", "mean"),
            raw_mean=("pm25_raw", "mean"),
            sd_mean=("sd", "mean"),
            rh_mean=("rh", "mean"),
            lat=("lat", "median"),
            lon=("lon", "median"),
        )
        kit_daily = kit_daily_all[kit_daily_all["hours"] >= MIN_HOURS].copy()

        dataset_audit["sensors"] = {
            "kits_in_nl": int(kit_daily_all["kit_id"].nunique()),
            "date_from": str(kit_daily_all["day"].min()),
            "date_to": str(kit_daily_all["day"].max()),
            "raw_rows_in_nl": int(len(raw_nonnull)),
            "kal_rows_in_nl": int(len(kal_nonnull)),
            "calibration_availability_pct": round(100.0 * len(kal_nonnull) / max(total_sens_rows, 1), 1),
            "raw_outliers_ge_100": outliers_raw,
            "raw_outliers_ge_100_pct": round(100.0 * outliers_raw / max(len(raw_nonnull), 1), 3),
            "kal_outliers_ge_100": outliers_kal,
            "kal_outliers_ge_100_pct": round(100.0 * outliers_kal / max(len(kal_nonnull), 1), 3),
            "kit_days_total": int(len(kit_daily_all)),
            "kit_days_ge_18h": int(len(kit_daily)),
            "kit_days_excluded_lt_18h_pct": round(100.0 * (1.0 - len(kit_daily) / len(kit_daily_all)), 2),
        }
        del hourly_kit, hourly_kit_clean, kit_daily_all

        # Match each kit's median position to nearest official PM2.5 station
        kit_pos = kit_daily.groupby("kit_id", as_index=False).agg(lat=("lat", "median"), lon=("lon", "median"))
        ref_pos = meta[meta["station"].isin(ref_daily["station"].unique())].reset_index(drop=True)
        kd_mat = haversine_matrix(
            kit_pos["lat"].to_numpy(), kit_pos["lon"].to_numpy(),
            ref_pos["lat"].to_numpy(), ref_pos["lon"].to_numpy(),
        )
        nearest_idx = kd_mat.argmin(axis=1)
        kit_pos["ref_station"] = ref_pos.loc[nearest_idx, "station"].to_numpy()
        kit_pos["ref_name"] = ref_pos.loc[nearest_idx, "name"].to_numpy()
        kit_pos["ref_type"] = ref_pos.loc[nearest_idx, "station_type"].to_numpy()
        kit_pos["dist_km"] = kd_mat[np.arange(len(kit_pos)), nearest_idx]

        close_kits = kit_pos[kit_pos["dist_km"] <= 1.5].copy()
        paired = kit_daily.merge(
            close_kits[["kit_id", "ref_station", "ref_name", "ref_type", "dist_km"]], on="kit_id"
        ).merge(
            ref_daily[["day", "station", "mean"]].rename(columns={"station": "ref_station", "mean": "ref_mean"}),
            on=["day", "ref_station"],
        )

        # Raw vs calibrated on identical kit-days (where raw_mean is also < 100 and non-null)
        paired_both = paired.dropna(subset=["raw_mean", "kal_mean"]).copy()
        paired_raw_clean = paired_both[paired_both["raw_mean"] < CUTOFF]

        # Empirical coverage of Samen Analyseren uncertainty interval [kal_mean - sd_mean, kal_mean + sd_mean]
        within_uc = np.abs(paired["kal_mean"] - paired["ref_mean"]) <= paired["sd_mean"]

        # Multi-sensor 1/d^2 weighted mean at the official station coordinates (radius <= 2.5 km)
        close_25 = kit_pos[kit_pos["dist_km"] <= 2.5].copy()
        p25 = kit_daily.merge(
            close_25[["kit_id", "ref_station", "ref_name", "dist_km"]], on="kit_id"
        ).merge(
            ref_daily[["day", "station", "mean"]].rename(columns={"station": "ref_station", "mean": "ref_mean"}),
            on=["day", "ref_station"],
        )
        p25["w"] = 1.0 / np.maximum(p25["dist_km"], MIN_DISTANCE_KM) ** 2
        p25["wy"] = p25["w"] * p25["kal_mean"]
        p25["wu"] = p25["w"] * p25["sd_mean"]
        agg = p25.groupby(["day", "ref_station"], as_index=False).agg(
            n_kits=("kit_id", "size"),
            w_sum=("w", "sum"),
            wy_sum=("wy", "sum"),
            wu_sum=("wu", "sum"),
            ref_mean=("ref_mean", "first"),
        )
        agg["idw_pred"] = agg["wy_sum"] / agg["w_sum"]
        agg["idw_uc"] = agg["wu_sum"] / agg["w_sum"]
        agg_multi = agg[agg["n_kits"] >= 3]

        # Low concentration (< 10 ug/m3) vs higher (>= 10 ug/m3)
        low_c = paired[paired["ref_mean"] < 10.0]
        high_c = paired[paired["ref_mean"] >= 10.0]

        # High relative humidity (RH > 80% vs <= 80%)
        paired_rh = paired_raw_clean.dropna(subset=["rh_mean"])
        rh_high = paired_rh[paired_rh["rh_mean"] > 80.0]
        rh_norm = paired_rh[paired_rh["rh_mean"] <= 80.0]

        sensor_validation = {
            "co_located_kits_le_1_5km": int(close_kits["kit_id"].nunique()),
            "reference_stations_matched": sorted(close_kits["ref_name"].unique().tolist()),
            "paired_kit_days": int(len(paired)),
            "single_kit_raw_lt_100": metrics(
                paired_raw_clean["ref_mean"].to_numpy(), paired_raw_clean["raw_mean"].to_numpy()
            ),
            "single_kit_calibrated_pm25_kal": metrics(
                paired["ref_mean"].to_numpy(), paired["kal_mean"].to_numpy()
            ),
            "multi_sensor_idw_ge_3_kits_le_2_5km": {
                **metrics(agg_multi["ref_mean"].to_numpy(), agg_multi["idw_pred"].to_numpy()),
                "uncertainty_coverage_pct": round(
                    100.0 * float((np.abs(agg_multi["idw_pred"] - agg_multi["ref_mean"]) <= agg_multi["idw_uc"]).mean()),
                    1,
                ),
            },
            "uncertainty_band_coverage_single_kit_pct": round(100.0 * float(within_uc.mean()), 1),
            "by_concentration_regime_calibrated": {
                "ref_lt_10_ug_m3": {
                    **metrics(low_c["ref_mean"].to_numpy(), low_c["kal_mean"].to_numpy()),
                    "mean_relative_error_pct": round(
                        100.0 * float(np.mean(np.abs(low_c["kal_mean"] - low_c["ref_mean"]) / np.maximum(low_c["ref_mean"], 1.0))),
                        1,
                    ),
                },
                "ref_ge_10_ug_m3": {
                    **metrics(high_c["ref_mean"].to_numpy(), high_c["kal_mean"].to_numpy()),
                    "mean_relative_error_pct": round(
                        100.0 * float(np.mean(np.abs(high_c["kal_mean"] - high_c["ref_mean"]) / high_c["ref_mean"])),
                        1,
                    ),
                },
            },
            "by_humidity_regime": {
                "rh_gt_80_pct": {
                    "raw": metrics(rh_high["ref_mean"].to_numpy(), rh_high["raw_mean"].to_numpy()),
                    "calibrated": metrics(rh_high["ref_mean"].to_numpy(), rh_high["kal_mean"].to_numpy()),
                },
                "rh_le_80_pct": {
                    "raw": metrics(rh_norm["ref_mean"].to_numpy(), rh_norm["raw_mean"].to_numpy()),
                    "calibrated": metrics(rh_norm["ref_mean"].to_numpy(), rh_norm["kal_mean"].to_numpy()),
                },
            },
        }

    return {
        "parameters": {
            "outlier_cutoff_ug_m3": CUTOFF,
            "min_valid_hours_per_day": MIN_HOURS,
            "idw_power": 2,
            "idw_distance_floor_km": MIN_DISTANCE_KM,
            "sensor_uncertainty_formula": "max(20% of value, 5.3 ug/m3)",
        },
        "dataset_audit": dataset_audit,
        "loocv_reference_stations_2025_2026": loocv_results,
        "citizen_sensors_vs_reference_2020_2025": sensor_validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    default_data = Path(__file__).resolve().parent.parent.parent / "HackathonHollandseLuchten" / "data"
    parser.add_argument("--data-dir", type=Path, default=default_data)
    parser.add_argument("--json", type=Path, default=None, help="Optional path to save JSON output")
    args = parser.parse_args()

    res = run_validation(args.data_dir)
    text = json.dumps(res, indent=2)
    print(text)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
