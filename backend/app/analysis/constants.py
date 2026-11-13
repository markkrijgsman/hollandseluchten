"""Fixed vocabulary and parameters of the analysis, shared so the audit text and the code cannot drift apart."""

UNIT = "ug/m3"
DAY_DEFINITION = "00:00-24:00 fixed UTC+1 (as in the Luchtmeetnet files)"
MIN_DISTANCE_KM = 0.5  # distance floor so a station at ~0 km does not get an infinite weight
WEIGHT_FORMULA = f"1/max(d, {MIN_DISTANCE_KM} km)^2"
SENSOR_PREFIX = "HL_"  # keeps kit ids from matching the reference-station pattern "^NL.[0-9]." in R
SENSOR, REFERENCE = "sensor", "reference"  # station kinds
BASIS = {SENSOR: "sensors", REFERENCE: "reference_stations"}  # kind -> name in responses
