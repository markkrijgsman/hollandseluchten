"""Calls the validated Analyse-Together R functions through Rscript (JSON in, JSON out)."""
import json
import subprocess
from pathlib import Path

R_SCRIPT = Path(__file__).resolve().parents[2] / "r" / "analysis.R"


class RError(RuntimeError):
    pass


def run_r_analysis(rows: list[dict], cutoff: float, analyse_together_dir: Path,
                   rscript: str = "Rscript", timeout: int = 120) -> dict:
    payload = {"analyse_together_dir": str(analyse_together_dir), "cutoff": cutoff, "rows": rows}
    try:
        proc = subprocess.run([rscript, str(R_SCRIPT)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RError(f"could not run R: {exc}") from exc
    if proc.returncode != 0:
        raise RError(f"R analysis failed: {proc.stderr.strip()[-500:]}")
    return json.loads(proc.stdout)
