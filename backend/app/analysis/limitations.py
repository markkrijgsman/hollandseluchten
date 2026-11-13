"""Plain-language limitations attached to results. Numbers come from what R reported, not from copies."""

ESTIMATE = "A weighted mean of nearby stations is an estimate, not a measurement at your coordinate."


def uncertainty_note(r_parameters: dict) -> str:
    pct = r_parameters["sensor_uncertainty_percent"]
    minimum = r_parameters["sensor_uncertainty_min_ug_m3"]
    return f"Uncertainty of sensors is a fixed estimate ({pct:g}%, min {minimum:g} ug/m3) and is not reduced by averaging."


def outlier_note(r_parameters: dict) -> str:
    cutoff = r_parameters["outlier_cutoff"]
    return (f"Hourly values of {cutoff:g} ug/m3 or more are removed as outliers. This is the default of the "
            "Analyse-Together tool; it was not tuned for this data, and lower faulty readings are not detected.")


def daily_limitations(r_parameters: dict, basis: str) -> list[str]:
    notes = ["Daily mean of hourly values; PM2.5 on a different day or hour can differ a lot.",
             ESTIMATE, uncertainty_note(r_parameters), outlier_note(r_parameters)]
    if basis == "reference_stations":
        notes.append("No sensor data used: estimate is based on official stations only.")
    return notes


def series_limitations(r_parameters: dict, sensor_periods: int, periods: int, expected: int) -> list[str]:
    notes = [ESTIMATE, uncertainty_note(r_parameters), outlier_note(r_parameters),
             "The summary mean is the plain mean of the periods that have data; periods without data are skipped."]
    if sensor_periods < periods:
        notes.append("Periods without sensor data use official stations only; the basis can change over the series.")
    if periods < expected:
        notes.append(f"{expected - periods} of {expected} periods have no usable data.")
    return notes
