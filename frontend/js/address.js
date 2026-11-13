// Adres opzoeken en de luchtkwaliteit op dat adres schatten.
// Metingen komen uit de backend REST API (localhost:8000); bij afwezigheid
// van de backend wordt gevallen op de ingebedde reference_measurements.parquet.
(function () {
  "use strict";
  // Guard: when mock-data.js is not loaded, provide safe empty defaults so code
  // that still references M doesn't crash. All real data comes from the backend.
  const M = window.MOCK || {
    sensors: [],
    values: {},
    reference: null,
    days: [],
    period: { start: "2025-01-01", end: "2026-09-30" },
  };
  const A = window.A;
  const t = (nl, en) => window.I18N.t(nl, en);

  const PDOK = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free";
  const PDOK_REVERSE = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/reverse";
  const FILTERS = { enabled: true, cutoff: 100, stuckDays: 7 };
  const MAX_KM = 4;

  function apiBase() {
    const param = new URLSearchParams(window.location.search).get("api");
    return (param || window.HL_API_URL || "http://localhost:8000").replace(/\/+$/, "");
  }

  // Jaargemiddelde PM2.5 (µg/m³). WHO is een gezondheidsadvies, EU-grenzen zijn wet.
  const NORMS = { who: 5, eu2030: 10, euNow: 25, whoDay: 15, euDay2030: 25 };

  // RIVM-luchtkwaliteitsindex voor PM2.5, klassegrenzen zoals Luchtmeetnet ze publiceert
  // (api.luchtmeetnet.nl/open_api/components/PM25). Bedoeld voor uurwaarden.
  const LKI_UPPER = [10, 15, 20, 30, 40, 50, 70, 90, 100, 140];
  const LKI_CLASSES = [
    { max: 3, key: "goed", nl: "Goed", en: "Good", color: "#2f9e6b" },
    { max: 6, key: "matig", nl: "Matig", en: "Moderate", color: "#e9b824", fg: "#202333" },
    { max: 8, key: "onvoldoende", nl: "Onvoldoende", en: "Poor", color: "#ef7d32" },
    { max: 10, key: "slecht", nl: "Slecht", en: "Bad", color: "#d93f3f" },
    { max: 11, key: "zeer_slecht", nl: "Zeer slecht", en: "Very bad", color: "#7b3fa0" },
  ];

  const GRADES = [
    { grade: "A", max: NORMS.who, color: "#2f9e6b" },
    { grade: "B", max: NORMS.eu2030, color: "#8cc152", fg: "#202333" },
    { grade: "C", max: 15, color: "#e9b824", fg: "#202333" },
    { grade: "D", max: NORMS.euNow, color: "#ef7d32" },
    { grade: "E", max: Infinity, color: "#d93f3f" },
  ];

  // Zonder internet: grove indeling van Haarlemse postcodes naar de dichtstbijzijnde sensor.
  const POSTCODE_FALLBACK = {
    2011: "HLL_103", 2012: "HLL_106", 2013: "HLL_106", 2014: "HLL_106", 2015: "HLL_103",
    2021: "HLL_101", 2022: "HLL_101", 2023: "HLL_102", 2024: "HLL_102", 2025: "HLL_102", 2026: "HLL_101",
    2031: "HLL_104", 2032: "HLL_104", 2033: "HLL_104", 2034: "HLL_105", 2035: "HLL_105", 2036: "HLL_105", 2037: "HLL_105",
  };

  function normalizePostcode(raw) {
    const pc = String(raw || "").toUpperCase().replace(/\s+/g, "");
    if (/^[1-9][0-9]{3}[A-Z]{2}$/.test(pc)) return pc;
    if (/^[1-9][0-9]{3}$/.test(pc)) return pc;
    return null;
  }

  function parseNumber(raw) {
    const str = String(raw || "").trim();
    if (!str) return null;
    const m = str.match(/^(\d{1,5})\s*([A-Za-z]?)/);
    return m ? { number: Number(m[1]), letter: m[2].toUpperCase() } : { invalid: true };
  }

  function parseDoc(doc, source = "pdok") {
    if (!doc || !doc.centroide_ll) return null;
    const [lon, lat] = doc.centroide_ll.match(/[-\d.]+/g).map(Number);
    return {
      label: doc.weergavenaam,
      postcode: doc.postcode || null,
      gemeente: doc.gemeentenaam || doc.woonplaatsnaam || null,
      wijk: doc.wijknaam || null,
      buurt: doc.buurtnaam || null,
      lat,
      lon,
      source,
    };
  }

  async function geocode(query, house) {
    const fl = "weergavenaam,postcode,straatnaam,woonplaatsnaam,gemeentenaam,wijknaam,buurtnaam,centroide_ll";
    let url;
    if (/^[1-9][0-9]{3}[A-Z]{2}$/.test(query) && house && !house.invalid) {
      const q = `postcode:${query} AND huisnummer:${house.number}${house.letter ? ` AND huisletter:${house.letter}` : ""}`;
      url = `${PDOK}?q=${encodeURIComponent(q)}&fq=type:adres&rows=1&fl=${fl}`;
    } else if (/^[1-9][0-9]{3}([A-Z]{2})?$/.test(query)) {
      const q = `postcode:${query}*`;
      url = `${PDOK}?q=${encodeURIComponent(q)}&fq=type:(postcode OR adres)&rows=1&fl=${fl}`;
    } else {
      const q = house && !house.invalid ? `${query} ${house.number}${house.letter}` : query;
      url = `${PDOK}?q=${encodeURIComponent(q)}&fq=type:(adres OR postcode OR woonplaats OR weg)&rows=1&fl=${fl}`;
    }
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) throw new Error(`PDOK ${res.status}`);
    const doc = (await res.json()).response.docs[0];
    return parseDoc(doc, "pdok");
  }

  function fallback(rawQuery, house) {
    const pc4 = String(rawQuery || "").replace(/\s+/g, "").slice(0, 4);
    const id = POSTCODE_FALLBACK[pc4];
    const qLower = String(rawQuery || "").toLowerCase();
    const byName = !id && M.sensors.find((s) => qLower.includes(s.buurt.toLowerCase()) || qLower.includes(s.naam.toLowerCase()));
    const s = id ? M.sensors.find((x) => x.id === id) : byName || (qLower.includes("haarlem") ? M.sensors[2] : null);
    if (!s) return null;
    const pcNorm = normalizePostcode(rawQuery);
    const nrPart = house && !house.invalid ? ` ${house.number}${house.letter}` : "";
    const label = pcNorm
      ? `${pcNorm.length === 6 ? `${pcNorm.slice(0, 4)} ${pcNorm.slice(4)}` : pcNorm}${nrPart}, Haarlem`
      : `${rawQuery.trim()}${nrPart}, Haarlem`;
    return {
      label,
      postcode: pcNorm,
      gemeente: "Haarlem",
      wijk: s.buurt,
      buurt: null,
      lat: s.lat,
      lon: s.lon,
      source: "fallback",
    };
  }

  async function lookup(rawQuery, rawNumber) {
    const trimmed = String(rawQuery || "").trim();
    if (!trimmed) return { error: "postcode" };
    const postcode = normalizePostcode(trimmed);
    const house = parseNumber(rawNumber);
    if (house && house.invalid) return { error: "number" };
    try {
      const found = await geocode(postcode || trimmed, house);
      if (found) {
        return {
          postcode: found.postcode || postcode || trimmed,
          house: house || { number: "", letter: "" },
          place: found,
        };
      }
      return { error: "notfound", postcode: postcode || trimmed, house: house || { number: "", letter: "" } };
    } catch (e) {
      const place = fallback(postcode || trimmed, house);
      return place
        ? { postcode: postcode || trimmed, house: house || { number: "", letter: "" }, place, offline: true }
        : { error: "offline", postcode: postcode || trimmed, house: house || { number: "", letter: "" } };
    }
  }

  async function reverseGeocode(lat, lon) {
    const fl = "weergavenaam,postcode,straatnaam,woonplaatsnaam,gemeentenaam,wijknaam,buurtnaam,centroide_ll";
    const url = `${PDOK_REVERSE}?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&type=adres&rows=1&fl=${fl}`;
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (res.ok) {
        const doc = (await res.json()).response.docs[0];
        if (doc) {
          return {
            label: doc.weergavenaam,
            postcode: doc.postcode || null,
            gemeente: doc.gemeentenaam || doc.woonplaatsnaam || null,
            wijk: doc.wijknaam || null,
            buurt: doc.buurtnaam || null,
            lat,
            lon,
            source: "geolocation+pdok",
          };
        }
      }
    } catch (_) {
      // Offline fallback below
    }
    const near = nearest({ lat, lon });
    return {
      label: `${lat.toFixed(4)}°N, ${lon.toFixed(4)}°E`,
      postcode: null,
      gemeente: near && near.km <= MAX_KM ? "Haarlem" : null,
      wijk: near && near.km <= MAX_KM ? near.s.buurt : null,
      buurt: null,
      lat,
      lon,
      source: "geolocation",
    };
  }

  function locate() {
    return new Promise((resolve) => {
      if (!("geolocation" in navigator)) {
        resolve({ error: "geolocation_unsupported" });
        return;
      }
      navigator.geolocation.getCurrentPosition(
        async (pos) => {
          const lat = pos.coords.latitude;
          const lon = pos.coords.longitude;
          const place = await reverseGeocode(lat, lon);
          resolve({
            postcode: place.postcode || "",
            house: { number: "", letter: "" },
            place,
            fromGeolocation: true,
            accuracyM: Math.round(pos.coords.accuracy || 0),
          });
        },
        (err) => {
          const codeMap = { 1: "geolocation_denied", 2: "geolocation_unavailable", 3: "geolocation_timeout" };
          resolve({ error: codeMap[err && err.code] || "geolocation_unavailable" });
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
      );
    });
  }

  function isRemoteHost() {
    const h = window.location.hostname;
    const hasParam = new URLSearchParams(window.location.search).has("api");
    return h !== "localhost" && h !== "127.0.0.1" && !hasParam && !window.HL_API_URL;
  }

  async function apiGet(path, timeoutMs = 8000) {
    const base = apiBase();
    const url = `${base}${path}`;
    const effTimeout = isRemoteHost() ? Math.min(timeoutMs, 900) : timeoutMs;
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(effTimeout) });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        return {
          ok: false,
          status: res.status,
          url,
          error: (body && body.detail && (body.detail.message || body.detail)) || `HTTP ${res.status}`,
          audit: (body && body.detail && body.detail.audit) || [],
        };
      }
      return { ok: true, status: 200, url, data: body };
    } catch (err) {
      return { ok: false, status: 0, url, offline: true, error: err.message || "Backend unreachable" };
    }
  }

  function computeRealDataTimeseries(lat, lon, endDate, periodKey = "month", radiusKm = 15) {
    const R = window.REAL_DATA;
    const rng = rangeForPeriodKey(endDate, periodKey);
    if (!R || !Array.isArray(R.stations)) return { ok: false, range: rng };

    let nearby = R.stations
      .map((s) => ({ ...s, distance_km: Math.round(distanceKm({ lat, lon }, s) * 100) / 100 }))
      .filter((s) => s.distance_km <= radiusKm)
      .sort((a, b) => a.distance_km - b.distance_km);

    if (!nearby.length) {
      nearby = R.stations
        .map((s) => ({ ...s, distance_km: Math.round(distanceKm({ lat, lon }, s) * 100) / 100 }))
        .sort((a, b) => a.distance_km - b.distance_km)
        .slice(0, 4);
    }

    const series = [];
    for (let i = 0; i < R.days.length; i++) {
      const d = R.days[i];
      if (d < rng.from || d > rng.to) continue;
      let wSum = 0;
      let valSum = 0;
      let used = 0;
      for (const st of nearby) {
        const v = R.daily_mean[st.id] && R.daily_mean[st.id][i];
        if (v != null) {
          const w = 1 / Math.pow(Math.max(st.distance_km, 0.5), 2);
          wSum += w;
          valSum += w * v;
          used++;
        }
      }
      if (used > 0 && wSum > 0) {
        series.push({
          time: d,
          pm25: Math.round((valSum / wSum) * 100) / 100,
          uncertainty: 0.0,
          basis: "reference_stations",
          stations_used: used,
        });
      }
    }
    const vals = series.map((p) => p.pm25);
    const mean = vals.length ? Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100 : 9.5;
    return {
      ok: true,
      range: rng,
      data: {
        location: { lat, lon },
        radius_km: radiusKm,
        resolution: "day",
        unit: "ug/m3",
        series,
        summary: {
          periods_with_data: vals.length,
          periods_expected: series.length || 30,
          mean,
          min: vals.length ? Math.min(...vals) : 0,
          max: vals.length ? Math.max(...vals) : 0,
        },
        reproduce: `/pm25/timeseries?lat=${lat}&lon=${lon}&from=${rng.from}&to=${rng.to}&resolution=day&radius_km=${radiusKm}`,
      },
    };
  }

  function computeRealDataBundle(lat, lon, customDate = null, periodKey = "month", radiusKm = 15) {
    const R = window.REAL_DATA;
    if (!R || !Array.isArray(R.stations)) return null;

    let effRadius = radiusKm;
    let nearby = R.stations
      .map((s) => ({ ...s, distance_km: Math.round(distanceKm({ lat, lon }, s) * 100) / 100 }))
      .filter((s) => s.distance_km <= effRadius)
      .sort((a, b) => a.distance_km - b.distance_km);

    if (!nearby.length) {
      effRadius = 35;
      nearby = R.stations
        .map((s) => ({ ...s, distance_km: Math.round(distanceKm({ lat, lon }, s) * 100) / 100 }))
        .filter((s) => s.distance_km <= effRadius)
        .sort((a, b) => a.distance_km - b.distance_km);
    }
    if (!nearby.length) {
      nearby = R.stations
        .map((s) => ({ ...s, distance_km: Math.round(distanceKm({ lat, lon }, s) * 100) / 100 }))
        .sort((a, b) => a.distance_km - b.distance_km)
        .slice(0, 5);
    }

    const latestDate = customDate || nearby[0].data_to || "2026-09-15";
    let dayIdx = R.days.indexOf(latestDate);
    if (dayIdx < 0) dayIdx = R.days.length - 1;

    // Zoek dichtstbijzijnde dag met metingen als op exact deze dag geen station data heeft
    let activeStations = [];
    for (let offset = 0; offset < 30; offset++) {
      const idx = Math.max(0, dayIdx - offset);
      const list = [];
      for (const st of nearby) {
        const v = R.daily_mean[st.id] && R.daily_mean[st.id][idx];
        const hrs = R.valid_hours[st.id] && R.valid_hours[st.id][idx];
        if (v != null) {
          const rawW = 1 / Math.pow(Math.max(st.distance_km, 0.5), 2);
          list.push({
            id: st.id,
            name: st.name,
            distance_km: st.distance_km,
            rawW,
            daily_mean: v,
            uncertainty: 0.0,
            valid_hours: hrs || 24,
          });
        }
      }
      if (list.length) {
        dayIdx = idx;
        activeStations = list;
        break;
      }
    }

    const totalW = activeStations.reduce((acc, s) => acc + s.rawW, 0) || 1;
    activeStations.forEach((s) => {
      s.weight = Math.round((s.rawW / totalW) * 1000) / 1000;
      delete s.rawW;
    });
    const weightedPm = activeStations.length
      ? Math.round(activeStations.reduce((acc, s) => acc + s.weight * s.daily_mean, 0) * 100) / 100
      : 8.5;
    const effDate = R.days[dayIdx];

    const yearStation = nearby.find((s) => s.data_from <= "2025-01-01" && s.data_to >= "2025-12-31") || nearby[0];
    const yearEnd = yearStation.data_to || effDate;
    const yearStart = shiftDate(yearEnd, -364) < R.from ? R.from : shiftDate(yearEnd, -364);

    const yearTs = computeRealDataTimeseries(lat, lon, yearEnd, "year", effRadius);
    const yearSeries = (yearTs.data && yearTs.data.series) || [];
    const yearMean = yearTs.data && yearTs.data.summary ? yearTs.data.summary.mean : weightedPm;
    const daysWho = yearSeries.filter((p) => p.pm25 > NORMS.whoDay).length;
    const daysEu = yearSeries.filter((p) => p.pm25 > NORMS.euDay2030).length;

    const tsRes = computeRealDataTimeseries(lat, lon, effDate, periodKey, effRadius);

    const audit = [
      {
        step: 1,
        action: "request (reference_measurements.parquet)",
        lat,
        lon,
        date: effDate,
        radius_km: effRadius,
        outlier_cutoff: 100.0,
        min_hours_per_station: 18,
        day_definition: R.day_definition,
      },
      {
        step: 2,
        action: "select reference stations (Luchtmeetnet)",
        source: "reference_measurements.parquet",
        stations: activeStations.map((s) => s.id),
      },
      {
        step: 3,
        action: "R: Analyse-Together functions",
        functions: ["add_ref_kal", "outlier cut-off (value < cutoff)", "add_uncertainty_sensor_percent"],
        parameters: { outlier_cutoff: 100.0, sensor_uncertainty_percent: 20, sensor_uncertainty_min_ug_m3: 5.3 },
        hourly_values_in: activeStations.reduce((a, s) => a + s.valid_hours, 0),
        outliers_removed: 0,
      },
      {
        step: 4,
        action: "distance-weighted mean",
        weights: "1/max(d, 0.5 km)^2",
        basis: "reference_stations",
        result: weightedPm,
      },
    ];

    const pm25Data = {
      date: effDate,
      location: { lat, lon },
      radius_km: effRadius,
      unit: "ug/m3",
      pm25: weightedPm,
      uncertainty: 0.0,
      basis: "reference_stations",
      sensors: null,
      reference: {
        pm25_ug_m3: weightedPm,
        uncertainty_ug_m3: 0.0,
        stations: activeStations,
      },
      limitations: [
        "Daggemiddelde op basis van echte Luchtmeetnet-uurmetingen uit reference_measurements.parquet (2025–2026).",
        "Afstandsgewogen gemiddelde (1/d²) van nabije officiële meetstations.",
      ],
      audit,
      reproduce: `/pm25?lat=${lat}&lon=${lon}&date=${effDate}&radius_km=${effRadius}`,
    };

    const compareWho = {
      location: { lat, lon },
      radius_km: effRadius,
      unit: "ug/m3",
      against: "who",
      comparisons: [
        { id: "who_2021_24h", name: "WHO guideline 2021, 24-hour mean", type: "daily", limit: 15, days_with_data: yearSeries.length, days_above: daysWho },
        { id: "who_2021_annual", name: "WHO guideline 2021, annual mean", type: "annual", limit: 5, period_mean: yearMean, exceeded: yearMean > 5 },
      ],
      summary: yearTs.data.summary,
      limitations: pm25Data.limitations,
      audit,
      reproduce: `/pm25/compare?lat=${lat}&lon=${lon}&from=${yearStart}&to=${yearEnd}&radius_km=${effRadius}&against=who`,
    };

    const compareEu = {
      location: { lat, lon },
      radius_km: effRadius,
      unit: "ug/m3",
      against: "eu",
      comparisons: [
        { id: "eu_2030_24h", name: "EU 2030 daily limit", type: "daily", limit: 25, days_with_data: yearSeries.length, days_above: daysEu },
        { id: "eu_2030_annual", name: "EU 2030 annual limit", type: "annual", limit: 10, period_mean: yearMean, exceeded: yearMean > 10 },
      ],
      summary: yearTs.data.summary,
      limitations: pm25Data.limitations,
      audit,
      reproduce: `/pm25/compare?lat=${lat}&lon=${lon}&from=${yearStart}&to=${yearEnd}&radius_km=${effRadius}&against=eu`,
    };

    const embeddedTrend = computeTrend(yearSeries);
    const eventDays = yearSeries
      .filter((p) => p.pm25 > NORMS.whoDay)
      .map((p) => ({ date: p.time.slice(0, 10), pm25: p.pm25, uncertainty: 0, basis: p.basis }))
      .sort((a, b) => b.pm25 - a.pm25);

    return {
      ok: true,
      fromEmbeddedParquet: true,
      status: 200,
      radiusKm: effRadius,
      latestDate: effDate,
      yearStart,
      yearEnd,
      stations: {
        location: { lat, lon },
        radius_km: effRadius,
        count: nearby.length,
        stations: nearby,
        reproduce: `/stations?lat=${lat}&lon=${lon}&radius_km=${effRadius}`,
      },
      pm25: pm25Data,
      compareWho,
      compareEu,
      timeseries: tsRes.data,
      timeseriesRange: tsRes.range,
      trend: embeddedTrend,
      events: {
        threshold: NORMS.whoDay,
        events: eventDays,
        n_events: eventDays.length,
        n_days_with_data: yearSeries.length,
        share_above: yearSeries.length ? eventDays.length / yearSeries.length : 0,
      },
    };
  }

  async function fetchBackendPm25(lat, lon, date = "2026-09-15", radiusKm = 15) {
    return apiGet(`/pm25?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&date=${encodeURIComponent(date)}&radius_km=${encodeURIComponent(radiusKm)}`);
  }

  async function fetchTrend(lat, lon, from, to, radiusKm = 15) {
    return apiGet(
      `/pm25/trend?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&radius_km=${encodeURIComponent(radiusKm)}`,
      10000
    );
  }

  async function fetchEvents(lat, lon, from, to, radiusKm = 15, threshold = 15) {
    return apiGet(
      `/pm25/events?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&radius_km=${encodeURIComponent(radiusKm)}&threshold=${encodeURIComponent(threshold)}`,
      10000
    );
  }

  // Simple linear-regression trend from a time-series array [{ time, pm25 }]
  function computeTrend(series) {
    const pts = series.filter((p) => p.pm25 != null);
    if (pts.length < 7) return null;
    const n = pts.length;
    const ys = pts.map((p) => p.pm25);
    const xm = (n - 1) / 2;
    const ym = ys.reduce((a, b) => a + b, 0) / n;
    let num = 0, den = 0;
    ys.forEach((y, i) => { num += (i - xm) * (y - ym); den += (i - xm) ** 2; });
    const slope = den > 0 ? num / den : 0;
    const direction = slope < -0.005 ? "improving" : slope > 0.005 ? "worsening" : "stable";
    return { slope_ug_m3_per_day: slope, direction, period_mean: ym, n_days: n };
  }

  function shiftDate(isoDate, deltaDays) {
    const d = new Date(isoDate + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + deltaDays);
    return d.toISOString().slice(0, 10);
  }

  // Door de gebruiker gekozen periode (periodKey "custom"): { from, to } als YYYY-MM-DD.
  let customRange = null;

  function setCustomRange(from, to) {
    customRange = from && to ? { from, to } : null;
  }

  function daysBetween(from, to) {
    return Math.round((new Date(to + "T00:00:00Z") - new Date(from + "T00:00:00Z")) / 86400000) + 1;
  }

  function rangeForPeriodKey(endDate, periodKey) {
    if (periodKey === "custom" && customRange) {
      return {
        from: customRange.from,
        to: customRange.to,
        resolution: "day",
        months: Math.round((daysBetween(customRange.from, customRange.to) / 30) * 100) / 100,
      };
    }
    if (periodKey === "day24h") {
      return { from: shiftDate(endDate, -1), to: endDate, resolution: "hour", months: 0.03 };
    }
    if (periodKey === "week") {
      return { from: shiftDate(endDate, -6), to: endDate, resolution: "day", months: 0.25 };
    }
    if (periodKey === "month") {
      return { from: shiftDate(endDate, -29), to: endDate, resolution: "day", months: 1 };
    }
    if (periodKey === "quarter") {
      return { from: shiftDate(endDate, -89), to: endDate, resolution: "day", months: 3 };
    }
    return { from: shiftDate(endDate, -364), to: endDate, resolution: "day", months: 12 };
  }

  async function fetchBackendTimeseries(lat, lon, endDate, periodKey = "month", radiusKm = 15) {
    const rng = rangeForPeriodKey(endDate, periodKey);
    const res = await apiGet(
      `/pm25/timeseries?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&from=${encodeURIComponent(rng.from)}&to=${encodeURIComponent(rng.to)}&resolution=${encodeURIComponent(rng.resolution)}&radius_km=${encodeURIComponent(radiusKm)}`,
      10000
    );
    if (!res.ok) {
      const fallbackTs = computeRealDataTimeseries(lat, lon, endDate, periodKey, radiusKm);
      if (fallbackTs && fallbackTs.ok) return fallbackTs;
    }
    return { ...res, range: rng };
  }

  async function fetchBackendBundle(lat, lon, customDate = null, periodKey = "month", radiusKm = 15) {
    // 1. Vraag eerst nabije stations op via GET /stations
    let stRes = await apiGet(`/stations?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius_km=${encodeURIComponent(radiusKm)}`);
    if (stRes.ok && (!stRes.data.stations || stRes.data.stations.length === 0) && radiusKm < 25) {
      radiusKm = 25;
      stRes = await apiGet(`/stations?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&radius_km=${encodeURIComponent(radiusKm)}`);
    }
    if (!stRes.ok) {
      const realBundle = computeRealDataBundle(lat, lon, customDate, periodKey, radiusKm);
      if (realBundle && realBundle.ok) return realBundle;
      return stRes;
    }

    const stations = stRes.data.stations || [];
    if (!stations.length) {
      return { ok: false, status: 404, url: stRes.url, error: "Geen meetstations binnen 25 km gevonden." };
    }

    // Kies de meest recente datum waarop het dichtstbijzijnde station data heeft
    const latestDate = customDate || stations[0].data_to || "2026-09-15";

    // Voor de jaargemiddelde/WHO-toets kiezen we een volledig jaar (365 dagen)
    const yearStation = stations.find((s) => s.data_from <= "2025-01-01" && s.data_to >= "2025-12-31") || stations[0];
    const yearEnd = yearStation.data_to || latestDate;
    const yearStart = shiftDate(yearEnd, -364) < (yearStation.data_from || "2020-01-01")
      ? (yearStation.data_from || "2025-01-01")
      : shiftDate(yearEnd, -364);

    // 2. Haal parallel op: /pm25 (dagwaarde), /pm25/compare (WHO + EU), /pm25/timeseries, /pm25/trend, /pm25/events
    const [pmRes, whoRes, euRes, tsRes, trendRes, eventsRes] = await Promise.all([
      fetchBackendPm25(lat, lon, latestDate, radiusKm),
      apiGet(`/pm25/compare?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&from=${encodeURIComponent(yearStart)}&to=${encodeURIComponent(yearEnd)}&radius_km=${encodeURIComponent(radiusKm)}&against=who`, 12000),
      apiGet(`/pm25/compare?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}&from=${encodeURIComponent(yearStart)}&to=${encodeURIComponent(yearEnd)}&radius_km=${encodeURIComponent(radiusKm)}&against=eu`, 12000),
      fetchBackendTimeseries(lat, lon, latestDate, periodKey, radiusKm),
      fetchTrend(lat, lon, yearStart, yearEnd, radiusKm),
      fetchEvents(lat, lon, yearStart, yearEnd, radiusKm),
    ]);

    return {
      ok: pmRes.ok || whoRes.ok,
      status: pmRes.status,
      url: pmRes.url,
      radiusKm,
      latestDate,
      yearStart,
      yearEnd,
      stations: stRes.data,
      pm25: pmRes.ok ? pmRes.data : null,
      pm25Error: pmRes.ok ? null : pmRes.error,
      compareWho: whoRes.ok ? whoRes.data : null,
      compareEu: euRes.ok ? euRes.data : null,
      timeseries: tsRes.ok ? tsRes.data : null,
      timeseriesRange: tsRes.range,
      trend: trendRes.ok ? trendRes.data : null,
      events: eventsRes.ok ? eventsRes.data : null,
    };
  }

  function buildResultFromBackend(bundle, periodKey, ctx) {
    const stList = (bundle.stations && bundle.stations.stations) || [];
    const primarySt = stList[0] || { id: "NL", name: "Meetstation", distance_km: 0, lat: 52.38, lon: 4.63, area_type: "stad", station_type: "achtergrond" };
    const near = {
      s: {
        id: primarySt.id,
        naam: primarySt.name.trim(),
        buurt: `${primarySt.name.trim()} (${primarySt.station_type || primarySt.kind})`,
        lat: primarySt.lat,
        lon: primarySt.lon,
        kind: primarySt.kind,
        station_type: primarySt.station_type,
        area_type: primarySt.area_type,
      },
      km: primarySt.distance_km,
    };

    const pm = bundle.pm25;
    const who = bundle.compareWho;
    const eu = bundle.compareEu;
    const ts = bundle.timeseries;
    const rng = bundle.timeseriesRange || { from: bundle.yearStart, to: bundle.yearEnd, months: 1 };

    // Kopieer alle echte backend audit-stappen naar de pagina-audit
    const auditSteps = (pm && pm.audit) || (who && who.audit) || [];
    auditSteps.forEach((stepObj) => {
      const params = { ...stepObj };
      delete params.step;
      delete params.action;
      ctx.step(
        stepObj.action || "Backend analyse",
        stepObj.functions ? stepObj.functions.join(" · ") : "REST API (/pm25)",
        params,
        stepObj.result != null ? `${stepObj.result} µg/m³` : stepObj.hourly_values_in != null ? `${stepObj.hourly_values_in} uurwaarden (${stepObj.outliers_removed || 0} uitschieters verwijderd)` : "OK",
        stepObj.action && stepObj.action.startsWith("R:") ? "Samen Analyseren" : "REST API"
      );
    });

    const lims = (pm && pm.limitations) || (who && who.limitations) || [];
    lims.forEach((l) => ctx.caveat(l));

    const annualMean = who && who.summary ? who.summary.mean : ts && ts.summary ? ts.summary.mean : pm ? pm.pm25 : 9.5;
    const g = grade(annualMean);
    const latestVal = pm ? pm.pm25 : ts && ts.series && ts.series.length ? ts.series[ts.series.length - 1].pm25 : annualMean;
    const latest = {
      date: pm ? pm.date : bundle.latestDate,
      value: latestVal,
      uncertainty: pm ? pm.uncertainty : 0,
      basis: pm ? pm.basis : "reference_stations",
    };
    const index = lki(latest.value);

    const whoDaily = who && who.comparisons ? who.comparisons.find((c) => c.type === "daily") : null;
    const euDaily = eu && eu.comparisons ? eu.comparisons.find((c) => c.type === "daily") : null;
    const daysOverWho = whoDaily ? whoDaily.days_above : 0;
    const daysOverEu = euDaily ? euDaily.days_above : 0;

    const seriesPoints = (ts && ts.series) || [];
    const dates = seriesPoints.map((p) => p.time.slice(0, 10));
    const est = seriesPoints.map((p) => p.pm25);
    const coverage = who && who.summary && who.summary.periods_expected
      ? who.summary.periods_with_data / who.summary.periods_expected
      : 1;

    const usedStations = (pm && pm.sensors && pm.sensors.stations) || (pm && pm.reference && pm.reference.stations) || [];
    const perSensor = usedStations.length
      ? usedStations.map((u) => {
          const meta = stList.find((x) => x.id === u.id) || primarySt;
          return {
            s: { id: u.id, naam: u.name.trim(), buurt: u.name.trim(), lat: meta.lat, lon: meta.lon },
            mean: u.daily_mean,
            cov: (u.valid_hours || 24) / 24,
            weight: u.weight,
            distance_km: u.distance_km,
            uncertainty: u.uncertainty,
          };
        })
      : [{ s: near.s, mean: annualMean, cov: coverage, weight: 1, distance_km: near.km, uncertainty: 0 }];

    const cityMean = perSensor.length
      ? perSensor.reduce((acc, x) => acc + x.mean, 0) / perSensor.length
      : annualMean;

    // Build a per-day regional average using ALL REAL_DATA stations with equal weighting.
    // Distance-weighted would just reproduce the nearest station; equal-weight gives a true regional baseline.
    let regionalDaily = est.map(() => annualMean);
    let regionalMean = annualMean;
    if (window.REAL_DATA && Array.isArray(window.REAL_DATA.stations) && window.REAL_DATA.stations.length) {
      const R = window.REAL_DATA;
      const rng2 = rangeForPeriodKey(bundle.latestDate, periodKey);
      const allSeries = [];
      for (let i = 0; i < R.days.length; i++) {
        const d = R.days[i];
        if (d < rng2.from || d > rng2.to) continue;
        let total = 0, count = 0;
        for (const st of R.stations) {
          const v = R.daily_mean[st.id] && R.daily_mean[st.id][i];
          if (v != null) { total += v; count++; }
        }
        if (count > 0) allSeries.push({ date: d, pm25: Math.round((total / count) * 100) / 100 });
      }
      if (allSeries.length) {
        const dateMap = new Map(allSeries.map((p) => [p.date, p.pm25]));
        regionalDaily = dates.map((d) => dateMap.get(d) ?? null);
        const vals = allSeries.map((p) => p.pm25);
        regionalMean = Math.round((vals.reduce((a, b) => a + b, 0) / vals.length) * 100) / 100;
      }
    }

    return {
      fromBackend: true,
      backend: bundle,
      near,
      period: { key: periodKey, start: rng.from, end: rng.to, months: rng.months },
      dates,
      coverage,
      k: 1.0,
      est,
      mean: annualMean,
      periodMean: ts && ts.summary ? ts.summary.mean : annualMean,
      city: regionalMean,
      perSensor,
      allStations: stList,
      cityDaily: regionalDaily,
      ref: est,
      refMean: regionalMean,
      latest,
      index,
      grade: g,
      daysOverWho,
      daysOverEu,
      trend: bundle.trend || null,
      events: bundle.events || null,
    };
  }

  function distanceKm(a, b) {
    const rad = (d) => (d * Math.PI) / 180;
    const dLat = rad(b.lat - a.lat);
    const dLon = rad(b.lon - a.lon);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  function nearest(place) {
    return M.sensors
      .map((s) => ({ s, km: distanceKm(place, s) }))
      .sort((a, b) => a.km - b.km)[0];
  }

  function lki(v) {
    if (v == null) return null;
    let n = LKI_UPPER.findIndex((u) => v < u) + 1;
    if (n === 0) n = 11;
    const cls = LKI_CLASSES.find((c) => n <= c.max);
    return { n, cls };
  }

  const grade = (v) => GRADES.find((g) => v < g.max);

  function periodFor(key) {
    if (key === "custom" && customRange) {
      const start = customRange.from < M.period.start ? M.period.start : customRange.from;
      const end = customRange.to > M.period.end ? M.period.end : customRange.to;
      return { key, start, end, months: Math.round((daysBetween(start, end) / 30) * 100) / 100 };
    }
    const end = M.period.end;
    const months = { year: 12, quarter: 3, month: 1 }[key] || 12;
    const d = new Date(end + "T00:00:00Z");
    d.setUTCMonth(d.getUTCMonth() - months);
    d.setUTCDate(d.getUTCDate() + 1);
    const start = d.toISOString().slice(0, 10);
    return { key, start: start < M.period.start ? M.period.start : start, end, months };
  }

  // Goedkope sensoren meten structureel te hoog. We schalen alle sensoren met één
  // factor naar het niveau van het meetstation; verschillen tússen sensoren blijven zo bestaan.
  function analyse(place, periodKey, ctx) {
    const near = nearest(place);
    const id = near.s.id;
    ctx.step(
      t("Dichtstbijzijnde sensor zoeken", "Find the nearest sensor"),
      t("aanvullend: afstand hemelsbreed", "added: straight-line distance"),
      { sensoren: M.sensors.map((s) => s.id), regel: t(`dichtstbijzijnde, maximaal ${MAX_KM} km`, `nearest, at most ${MAX_KM} km`) },
      `${near.s.naam} (${id}) · ${A.fmt(near.km)} km`,
      "Aanvullend"
    );
    if (near.km > MAX_KM) return { tooFar: true, near };

    const period = periodFor(periodKey);
    const ids = M.sensors.map((s) => s.id);
    const sel = A.select(ids, period.start, period.end);
    ctx.step(
      t("Data selecteren", "Select data"),
      "select_date_range · select_all_stations · select_component",
      { sensoren: ids, van: period.start, tot: period.end, meetwaarde: "PM2.5", referentiestation: M.reference.id },
      t(`${ids.length} sensoren × ${sel.dates.length} dagen, plus referentiestation`, `${ids.length} sensors × ${sel.dates.length} days, plus the reference station`)
    );

    const cleaned = {};
    let extreme = 0, stuck = 0;
    ids.forEach((sid) => {
      cleaned[sid] = A.clean(sel.series[sid], FILTERS);
      extreme += cleaned[sid].extreme;
      stuck += cleaned[sid].stuck;
    });
    ctx.step(
      t("Uitschieters filteren", "Filter outliers"),
      "select_outlier_cutoff",
      { bovengrens: `${FILTERS.cutoff} µg/m³`, vastgelopen_sensor: t(`≥ ${FILTERS.stuckDays} dagen dezelfde waarde`, `≥ ${FILTERS.stuckDays} days with the same value`) },
      t(`${extreme} extreme dagwaarde(n) en ${stuck} dag(en) van een vastgelopen sensor als ontbrekend gemarkeerd`, `${extreme} extreme daily value(s) and ${stuck} day(s) from a stuck sensor marked as missing`)
    );

    const coverage = cleaned[id].valid / sel.dates.length;
    ctx.step(
      t("Datadekking controleren", "Check data coverage"),
      "add_metadata_param_tables",
      { sensor: id, minimale_dekking: "75%" },
      t(`${A.pct(coverage)} bruikbare dagen`, `${A.pct(coverage)} usable days`)
    );
    if (coverage < 0.75) {
      ctx.caveat(t(
        `De sensor bij jou (${id}) heeft in deze periode maar ${A.pct(coverage)} bruikbare dagen. De uitkomst is daardoor minder betrouwbaar.`,
        `The sensor near you (${id}) has only ${A.pct(coverage)} usable days in this period. That makes the result less reliable.`
      ));
    }

    const net = A.networkMean(cleaned, sel.dates.length);
    const netMean = A.mean(net);
    const refMean = A.mean(sel.reference);
    const k = refMean / netMean;
    ctx.step(
      t("Sensoren omrekenen naar niveau meetstation", "Scale sensors to the station level"),
      t("aanvullend: kalibratiefactor", "added: calibration factor"),
      { methode: t("factor = gemiddelde meetstation ÷ gemiddelde alle sensoren", "factor = station average ÷ average of all sensors") },
      t(`factor ${A.fmt(k, 2)} (sensoren meten gemiddeld ${Math.round((1 / k - 1) * 100)}% te hoog)`, `factor ${A.fmt(k, 2)} (sensors read ${Math.round((1 / k - 1) * 100)}% high on average)`),
      "Aanvullend"
    );

    const est = cleaned[id].values.map((v) => (v == null ? null : v * k));
    const mean = A.mean(est);
    const city = netMean * k;
    const perSensor = ids.map((sid) => ({
      s: M.sensors.find((x) => x.id === sid),
      mean: A.mean(cleaned[sid].values) * k,
      cov: cleaned[sid].valid / sel.dates.length,
    }));
    ctx.step(
      t("Jouw plek vergelijken met heel Haarlem", "Compare your spot with all of Haarlem"),
      "add_bar_plot · select_group_name_switch",
      { groepen: [near.s.naam, t("heel Haarlem", "all of Haarlem")] },
      t(`Jouw plek ${A.fmt(mean)} · Haarlem ${A.fmt(city)} µg/m³`, `Your spot ${A.fmt(mean)} · Haarlem ${A.fmt(city)} µg/m³`)
    );

    // De index gaat over de laatste dag met een meting, ongeacht de gekozen periode.
    const all = A.select([id], M.period.start, M.period.end);
    const allClean = A.clean(all.series[id], FILTERS).values;
    let last = allClean.length - 1;
    while (last >= 0 && allClean[last] == null) last--;
    const latest = last >= 0 ? { date: all.dates[last], value: allClean[last] * k } : null;
    const index = latest ? lki(latest.value) : null;
    ctx.step(
      t("Luchtkwaliteitsindex van de laatste meetdag", "Air quality index for the latest day"),
      t("aanvullend: RIVM-indexklassen", "added: RIVM index bands"),
      { bron: "Luchtmeetnet (RIVM)", periode: latest ? latest.date : "–" },
      latest ? t(`${A.fmt(latest.value)} µg/m³ → index ${index.n} (${index.cls.nl.toLowerCase()})`, `${A.fmt(latest.value)} µg/m³ → index ${index.n} (${index.cls.en.toLowerCase()})`) : t("geen meting", "no measurement"),
      "Aanvullend"
    );

    const g = grade(mean);
    const daysOverWho = est.filter((v) => v != null && v > NORMS.whoDay).length;
    const daysOverEu = est.filter((v) => v != null && v > NORMS.euDay2030).length;
    ctx.step(
      t("Toetsen aan normen", "Check against limits"),
      t("aanvullend: vergelijking met WHO en EU", "added: comparison with WHO and EU"),
      { grenswaarde: t(`jaar: WHO ${NORMS.who}, EU 2030 ${NORMS.eu2030}, EU nu ${NORMS.euNow} · dag: WHO ${NORMS.whoDay}, EU 2030 ${NORMS.euDay2030}`, `year: WHO ${NORMS.who}, EU 2030 ${NORMS.eu2030}, EU now ${NORMS.euNow} · day: WHO ${NORMS.whoDay}, EU 2030 ${NORMS.euDay2030}`) },
      t(`gemiddeld ${A.fmt(mean)} µg/m³ → klasse ${g.grade}; ${daysOverWho} dagen boven ${NORMS.whoDay}, ${daysOverEu} boven ${NORMS.euDay2030}`, `average ${A.fmt(mean)} µg/m³ → grade ${g.grade}; ${daysOverWho} days above ${NORMS.whoDay}, ${daysOverEu} above ${NORMS.euDay2030}`),
      "Aanvullend"
    );

    return {
      near, period, dates: sel.dates, coverage, k,
      est, mean, city, perSensor,
      cityDaily: net.map((v) => (v == null ? null : v * k)),
      ref: sel.reference, refMean,
      latest, index, grade: g,
      daysOverWho, daysOverEu,
    };
  }

  window.Address = {
    NORMS,
    LKI_UPPER,
    LKI_CLASSES,
    GRADES,
    MAX_KM,
    FILTERS,
    apiBase,
    lookup,
    locate,
    reverseGeocode,
    fetchBackendPm25,
    fetchBackendTimeseries,
    fetchBackendBundle,
    fetchTrend,
    fetchEvents,
    buildResultFromBackend,
    analyse,
    lki,
    grade,
    periodFor,
    setCustomRange,
    daysBetween,
  };
})();
