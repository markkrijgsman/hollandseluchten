"""Calls the validated Analyse-Together R functions through Rscript (JSON in, JSON out).

Rows travel as columns ({"station": [...], "value": [...], ...}); one JSON object per row is far slower to
build and to parse for the hundreds of thousands of hourly values in a year.
"""
import json
import shutil
import subprocess
from pathlib import Path

R_SCRIPT = Path(__file__).resolve().parents[2] / "r" / "analysis.R"


class RError(RuntimeError):
    pass


def run_r_analysis(columns: dict[str, list], cutoff: float, analyse_together_dir: Path,
                   rscript: str = "Rscript", timeout: int = 120) -> dict:
    """`columns`: station, parameter, value, date. Returns {"rows": columns incl. sd, ...}."""
    if not shutil.which(rscript):
        raise RError(f"R is not installed ('{rscript}' not found); the Analyse-Together functions need it. See API.md")
    if not (analyse_together_dir / "funs" / "data_to_tool_fun.R").is_file():
        raise RError(f"Analyse-Together checkout not found at {analyse_together_dir} (set HL_ANALYSE_TOGETHER_DIR)")
    payload = {"analyse_together_dir": str(analyse_together_dir), "cutoff": cutoff, "rows": columns}
    try:
        proc = subprocess.run([rscript, str(R_SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RError(f"could not run R: {exc}") from exc
    if proc.returncode != 0:
        raise RError(f"R analysis failed: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)
