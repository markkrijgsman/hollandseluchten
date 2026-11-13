"""Calls the validated Analyse-Together R functions through Rscript (JSON in, JSON out)."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

R_SCRIPT = Path(__file__).resolve().parents[2] / "r" / "analysis.R"
REF_PATTERN = re.compile(r"^NL.[0-9].")


class RError(RuntimeError):
    pass


def _python_fallback(rows: list[dict], cutoff: float) -> dict:
    """Exact mirror of r/analysis.R (add_ref_kal, value < cutoff, add_uncertainty_sensor_percent)
    when Rscript is not installed on the local development machine."""
    if not rows:
        return {"rows": [], "removed_outliers": 0, "functions": [], "parameters": {}}

    # 1. add_ref_kal: reference stations (substr(station,1,2) == "NL" & parameter == "pm25") get pm25_kal
    kal_rows = []
    for r in rows:
        if r.get("parameter") == "pm25_kal":
            kal_rows.append(dict(r))
        elif str(r.get("station", "")).startswith("NL") and r.get("parameter") == "pm25":
            copy = dict(r)
            copy["parameter"] = "pm25_kal"
            kal_rows.append(copy)

    # 2. outlier cut-off: value < cutoff
    n_before = len(kal_rows)
    filtered = [r for r in kal_rows if r["value"] < cutoff]
    removed = n_before - len(filtered)

    # 3. add_uncertainty_sensor_percent(uc_pm25 = 20, uc_min_pm25 = 5.3)
    for r in filtered:
        if REF_PATTERN.match(str(r.get("station", ""))):
            r["sd"] = 0.0
        else:
            r["sd"] = max(0.20 * float(r["value"]), 5.3)

    return {
        "rows": filtered,
        "removed_outliers": removed,
        "functions": ["add_ref_kal", "outlier cut-off (value < cutoff)", "add_uncertainty_sensor_percent"],
        "parameters": {
            "outlier_cutoff": cutoff,
            "sensor_uncertainty_percent": 20,
            "sensor_uncertainty_min_ug_m3": 5.3,
        },
    }


def run_r_analysis(rows: list[dict], cutoff: float, analyse_together_dir: Path,
                   rscript: str = "Rscript", timeout: int = 120) -> dict:
    if not shutil.which(rscript) and os.environ.get("HL_REQUIRE_R") != "1":
        return _python_fallback(rows, cutoff)
    payload = {"analyse_together_dir": str(analyse_together_dir), "cutoff": cutoff, "rows": rows}
    try:
        proc = subprocess.run([rscript, str(R_SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RError(f"could not run R: {exc}") from exc
    if proc.returncode != 0:
        raise RError(f"R analysis failed: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)
