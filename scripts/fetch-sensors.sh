#!/bin/sh
# Downloads the Hollandse Luchten sensor data into <data-dir> and verifies it. Used by setup.sh and by the Docker
# data-init service, so the download logic lives in one place. POSIX sh: it also runs in the Alpine image.
#
#   scripts/fetch-sensors.sh <data-dir>
#
# The file (hourly PM2.5 of the citizen sensor kits, 2020-2025) is not in the git repositories. It is published on
# Zenodo (record 23762846, "Five years of Hollandse Luchten ... sensor data"). The size and MD5 below are the ones
# Zenodo lists for the file; the download only gets its real name once both match.
# Exit status: 0 = file present (already there or downloaded and verified), 1 = could not be downloaded.
set -eu

URL="https://zenodo.org/records/23762846/files/data_sensors.parquet?download=1"
BYTES=83888493
MD5="9bbbd14b42af5daa071300ce28e72cb7"

DIR="${1:?usage: fetch-sensors.sh <data-dir>}"
FILE="$DIR/data_sensors.parquet"
PART="$FILE.part"

md5_of() { if command -v md5sum >/dev/null 2>&1; then md5sum "$1" | cut -d' ' -f1; else md5 -q "$1"; fi; }

if [ -f "$FILE" ]; then echo "ok       data_sensors.parquet"; exit 0; fi

mkdir -p "$DIR"
echo "downloading data_sensors.parquet from Zenodo (about 80 MB) ..."
# -C - resumes an interrupted download
if curl --fail --location --silent --show-error --progress-bar -C - -o "$PART" "$URL" \
   && [ "$(wc -c < "$PART" | tr -d ' ')" = "$BYTES" ] && [ "$(md5_of "$PART")" = "$MD5" ]; then
  mv "$PART" "$FILE"
  echo "ok       data_sensors.parquet (downloaded and verified)"
else
  rm -f "$PART"
  echo "WARNING  data_sensors.parquet could not be downloaded or did not match the expected size and checksum."
  echo "         Download it by hand from $URL into $DIR."
  exit 1
fi
