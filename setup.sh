#!/usr/bin/env bash
# One-call setup of everything the backend needs, for running WITHOUT Docker. Safe to run again: it only adds what
# is missing. If you would rather not install R and Python packages yourself, use Docker instead:
#   docker compose up --build      (see the README; the containers bring R, Python and the data)
#
#   ./setup.sh                clone with HTTPS
#   ./setup.sh --ssh          clone with SSH (git@github.com:...)
#   ./setup.sh --no-sensors   do not download the sensor data (about 80 MB)
#
# Expected layout (the backend finds the other repositories by this layout):
#   <parent>/hollandseluchten/             this repository
#   <parent>/Analyse-Together/             R functions the analyses call (GPL-3, sourced at runtime, never copied)
#   <parent>/HackathonHollandseLuchten/    the data (data/*.parquet, data/*.csv)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(dirname "$REPO")"
BACKEND="$REPO/backend"

BASE="https://github.com/"
GET_SENSORS=1
for arg in "$@"; do
  case "$arg" in
    --ssh) BASE="git@github.com:" ;;
    --no-sensors) GET_SENSORS=0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

step "Checking tools"
command -v git >/dev/null || fail "git is not installed"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null || fail "python3 is not installed (3.11 or newer needed)"
"$PYTHON" -c 'import sys; sys.exit(sys.version_info < (3, 11))' || fail "Python 3.11 or newer is needed ($("$PYTHON" -V)); set PYTHON=/path/to/python3.11"
command -v Rscript >/dev/null || fail "R is not installed. The analyses need it (no substitute). macOS: 'brew install r'; Debian/Ubuntu: 'sudo apt install r-base'"
echo "git, $("$PYTHON" -V), $(Rscript --version 2>&1 | head -1)"

clone() {  # clone <name> <path-on-github>
  if [[ -d "$PARENT/$1/.git" ]]; then echo "$1: already cloned ($PARENT/$1)"; else
    git clone "$BASE$2" "$PARENT/$1"
  fi
}
step "Cloning the other repositories next to this one"
clone Analyse-Together rivm-syso/Analyse-Together.git
clone HackathonHollandseLuchten provincieNH/HackathonHollandseLuchten.git

step "R packages used by r/analysis.R"
Rscript -e 'need <- setdiff(c("dplyr", "jsonlite"), rownames(installed.packages()))
if (length(need)) install.packages(need, repos = "https://cloud.r-project.org") else cat("dplyr and jsonlite are installed\n")'

step "Backend: virtual environment and dependencies"
[[ -d "$BACKEND/.venv" ]] || "$PYTHON" -m venv "$BACKEND/.venv"
"$BACKEND/.venv/bin/pip" install --quiet --upgrade pip
"$BACKEND/.venv/bin/pip" install --quiet -e "$BACKEND[chat,dev]"
echo "installed into $BACKEND/.venv"

step "Checking the data files"
DATA="$PARENT/HackathonHollandseLuchten/data"
missing=0
for f in reference_measurements.parquet reference_station_metadata.csv; do
  [[ -f "$DATA/$f" ]] && echo "ok       $f" || { echo "MISSING  $f"; missing=1; }
done
# Sensor data is optional for the backend (without it only the official Luchtmeetnet stations are used), so a
# failed download only warns. HL_SENSOR_PARQUET can point to a copy kept somewhere else.
# The download and its verification are in scripts/fetch-sensors.sh (shared with the Docker setup).
if [[ -n "${HL_SENSOR_PARQUET:-}" && -f "$HL_SENSOR_PARQUET" ]]; then
  echo "ok       data_sensors.parquet (from HL_SENSOR_PARQUET=$HL_SENSOR_PARQUET)"
elif [[ $GET_SENSORS == 0 ]]; then
  [[ -f "$DATA/data_sensors.parquet" ]] && echo "ok       data_sensors.parquet" \
    || echo "skipped  data_sensors.parquet (--no-sensors): only the official stations will be used"
else
  "$REPO/scripts/fetch-sensors.sh" "$DATA" || echo "         Until then only the official stations are used (or set HL_SENSOR_PARQUET)."
fi
[[ $missing == 0 ]] || fail "required data files are missing in $DATA"

step "End-to-end check: the Analyse-Together R functions through the backend"
(cd "$BACKEND" && .venv/bin/python - <<'PY'
from app.integrations.r_bridge import run_r_analysis
from app.settings import Settings

s = Settings.from_env()
out = run_r_analysis({"station": ["NL00001"], "parameter": ["pm25"], "value": [10.0], "date": ["2025-05-01T00"]},
                     100.0, s.analyse_together_dir, s.rscript)
assert out["functions"][0] == "add_ref_kal" and len(out["rows"]["value"]) == 1, out
print("R functions ran:", ", ".join(out["functions"]))
PY
) || fail "the R functions could not run; see the message above"

cat <<DONE

Setup complete.

  Start the backend:   cd $BACKEND && .venv/bin/uvicorn app.main:app      (docs: http://localhost:8000/docs)
  Start the frontend:  python3 -m http.server 8080 --directory $REPO/frontend
  Run the tests:       cd $BACKEND && .venv/bin/pytest

  Chat needs an API key:  export OPENAI_API_KEY=...  or  export GEMINI_API_KEY=...   (without it /chat answers 503)
  No R or Python on this machine? 'docker compose up --build' runs everything in containers instead.
DONE
