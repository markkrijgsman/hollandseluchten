#!/bin/sh
# Fills /data (a Docker volume) on the first run; later runs find everything in place and finish at once.
set -eu
REPO=/data/HackathonHollandseLuchten

if [ ! -f "$REPO/data/reference_measurements.parquet" ]; then
  echo "cloning HackathonHollandseLuchten (reference measurements) ..."
  rm -rf "$REPO"
  git clone --depth 1 https://github.com/provincieNH/HackathonHollandseLuchten.git "$REPO"
fi
[ -f "$REPO/data/reference_measurements.parquet" ] || { echo "reference_measurements.parquet is missing"; exit 1; }

# Sensor data is optional for the backend: without it only the official stations are used, so a failed download
# must not stop the stack. Run `docker compose run --rm data-init` again to retry.
fetch-sensors.sh "$REPO/data" || echo "continuing without sensor data"
