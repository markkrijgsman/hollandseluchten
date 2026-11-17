// Toegang tot de backend (REST API) op één plek: adres, HTTP-aanroepen en de vertaling van
// `audit` en `considerations` uit de API-antwoorden naar wat de pagina's tonen.
// Antwoordvorm: zie backend/API.md (`considerations`, getypeerde `audit`-stappen met een `code`).
(function () {
  "use strict";
  const t = (nl, en) => window.I18N.t(nl, en);

  const CLOUD_API_URL = "https://luchtzorg-backend-103343530026.europe-west4.run.app";

  function apiBase() {
    const param = new URLSearchParams(window.location.search).get("api");
    if (param) return param.replace(/\/+$/, "");
    if (window.HL_API_URL) return window.HL_API_URL.replace(/\/+$/, "");
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
      return "http://localhost:8000";
    }
    return CLOUD_API_URL;
  }

  // Live cloud backend is now permanently available across both localhost and hosted domains.
  function isRemoteHost() {
    return false;
  }

  const qs = (params) =>
    Object.entries(params)
      .filter(([, v]) => v != null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&");

  // Een jaar over 15 km duurt op de backend ongeveer 10 s (R + parquet): ruime time-outs.
  const TIMEOUT = { quick: 8000, series: 30000, year: 40000 };

  async function get(path, params = {}, timeoutMs = TIMEOUT.quick) {
    const query = qs(params);
    const url = `${apiBase()}${path}${query ? `?${query}` : ""}`;
    const effTimeout = isRemoteHost() ? Math.min(timeoutMs, 900) : timeoutMs;
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(effTimeout) });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        const detail = body && body.detail;
        return {
          ok: false,
          status: res.status,
          url,
          error: (detail && (detail.message || detail)) || `HTTP ${res.status}`,
          audit: (detail && detail.audit) || [],
        };
      }
      return { ok: true, status: 200, url, data: body };
    } catch (err) {
      return { ok: false, status: 0, url, offline: true, error: err.message || "Backend unreachable" };
    }
  }

  // ---- audit: getypeerde stappen (`code`) naar rijen voor de audit-tabel ------------------------
  const SA = "Samen Analyseren";
  const API = "REST API";
  const fmt = (v) => (v == null ? "–" : Number(v).toLocaleString(window.I18N.lang === "en" ? "en" : "nl", { maximumFractionDigits: 2 }));

  const STEPS = {
    request: (s) => ({
      label: t("Aanvraag", "Request"),
      fn: "REST API",
      params: { radius_km: s.radius_km, outlier_cutoff: s.outlier_cutoff, min_hours_per_station: s.min_hours_per_station },
      result: s.date || `${s.start} – ${s.end}${s.resolution ? ` (${s.resolution})` : ""}`,
      source: API,
    }),
    select_stations: (s) => ({
      label: s.kind === "sensor" ? t("Sensoren selecteren", "Select sensors") : t("Meetstations selecteren", "Select stations"),
      fn: s.source || "–",
      params: s.station_types ? { stations: s.stations, station_types: Object.entries(s.station_types).map(([k, v]) => `${k}: ${v}`) } : { stations: s.stations },
      result: s.skipped ? s.reason : t(`${(s.stations || []).length} station(s)`, `${(s.stations || []).length} station(s)`),
      source: API,
    }),
    r_functions: (s) => ({
      label: t("Samen Analyseren-functies", "Samen Analyseren functions"),
      fn: (s.functions || []).join(" · "),
      params: s.parameters,
      result: t(`${s.hourly_values_in} uurwaarden (${s.outliers_removed} uitschieters verwijderd)`, `${s.hourly_values_in} hourly values (${s.outliers_removed} outliers removed)`),
      source: SA,
    }),
    station_means: (s) => ({
      label: s.action,
      fn: "pandas",
      params: s.excluded_for_too_few_hours ? { te_weinig_uren: s.excluded_for_too_few_hours } : {},
      result: t(`${s.station_periods_used} meegenomen, ${s.station_periods_excluded_for_too_few_hours} te weinig uren`, `${s.station_periods_used} used, ${s.station_periods_excluded_for_too_few_hours} too few hours`),
      source: API,
    }),
    weighted_mean: (s) => ({
      label: s.action,
      fn: s.weights,
      params: s.basis ? { basis: s.basis } : { periods_from_sensors: s.periods_from_sensors },
      result: s.result != null ? `${fmt(s.result)} µg/m³` : t(`${s.periods} perioden`, `${s.periods} periods`),
      source: API,
    }),
    compare: (s) => ({ label: s.action, fn: `against=${s.against}`, params: { levels: (s.levels || []).map((l) => `${l.id}: ${l.limit}${l.verified ? "" : " (?)"}`) }, result: `${(s.levels || []).length} niveaus`, source: API }),
    weekday_split: (s) => ({
      label: s.action,
      fn: "Python",
      params: { weekday_days: s.weekday_days, weekend_days: s.weekend_days },
      result: s.difference != null ? `${fmt(s.difference)} µg/m³` : "–",
      source: API,
    }),
    linear_trend: (s) => ({
      label: s.action,
      fn: "OLS",
      params: { stable_below: `${s.stable_below} µg/m³/dag`, n_points: s.n_points },
      result: `${s.slope_ug_m3_per_day} µg/m³/dag → ${s.direction}`,
      source: API,
    }),
    events_above_threshold: (s) => ({
      label: s.action,
      fn: `> ${s.threshold} µg/m³`,
      params: { n_days_with_data: s.n_days_with_data },
      result: `${s.n_events}`,
      source: API,
    }),
    versions: (s) => ({
      label: t("Versies van code en data", "Code and data versions"),
      fn: "git · bestanden",
      params: { analyse_together: (s.analyse_together_commit || "?").slice(0, 8) },
      result: "OK",
      source: API,
    }),
  };

  function auditSteps(audit) {
    return (audit || []).map((s) => {
      const known = STEPS[s.code];
      if (known) return known(s);
      const { step, action, code, ...rest } = s; // onbekende stap: toon wat er is
      return { label: action || code || "?", fn: code || "–", params: rest, result: "OK", source: API };
    });
  }

  // ---- considerations: opmerkingen bij een resultaat, met niveau en herkomst ---------------------
  const LEVEL_ORDER = { warning: 0, caution: 1, info: 2 };

  // Voegt de considerations van meerdere antwoorden samen, ernstigste eerst. Dezelfde opmerking uit meerdere
  // antwoorden (zelfde code, zelfde niveau van de norm) komt één keer voor: de eerst genoemde telt.
  function considerations(...responses) {
    const seen = new Set();
    const out = [];
    responses.forEach((r) => {
      ((r && r.considerations) || []).forEach((c) => {
        const key = `${c.code}|${(c.facts && c.facts.level_name) || ""}`;
        if (!seen.has(key)) {
          seen.add(key);
          out.push(c);
        }
      });
    });
    return out.sort((a, b) => LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]);
  }

  const originLabel = (origin) =>
    ({
      "analyse-together": t("methode Samen Analyseren", "Samen Analyseren method"),
      "this-api": t("keuze van deze API", "choice made in this API"),
      config: t("configuratiebestand", "config file"),
    })[origin] || origin;

  window.Api = { apiBase, isRemoteHost, get, TIMEOUT, auditSteps, considerations, originLabel };
})();
