// Adres opzoeken en de luchtkwaliteit op dat adres schatten. Het adres komt uit de
// PDOK Locatieserver (echt); de metingen zijn de nepdata uit mock-data.js.
(function () {
  "use strict";
  const M = window.MOCK;
  const A = window.A;
  const t = (nl, en) => window.I18N.t(nl, en);

  const PDOK = "https://api.pdok.nl/bzk/locatieserver/search/v3_1/free";
  const FILTERS = { enabled: true, cutoff: 100, stuckDays: 7 };
  const MAX_KM = 4;

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
    return /^[1-9][0-9]{3}[A-Z]{2}$/.test(pc) ? pc : null;
  }

  function parseNumber(raw) {
    const m = String(raw || "").trim().match(/^(\d{1,5})\s*([A-Za-z]?)/);
    return m ? { number: Number(m[1]), letter: m[2].toUpperCase() } : null;
  }

  async function geocode(postcode, house) {
    const q = `postcode:${postcode} AND huisnummer:${house.number}${house.letter ? ` AND huisletter:${house.letter}` : ""}`;
    const url = `${PDOK}?q=${encodeURIComponent(q)}&fq=type:adres&rows=1&fl=weergavenaam,straatnaam,woonplaatsnaam,gemeentenaam,wijknaam,buurtnaam,centroide_ll`;
    const res = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!res.ok) throw new Error(`PDOK ${res.status}`);
    const doc = (await res.json()).response.docs[0];
    if (!doc) return null;
    const [lon, lat] = doc.centroide_ll.match(/[-\d.]+/g).map(Number);
    return {
      label: doc.weergavenaam,
      gemeente: doc.gemeentenaam,
      wijk: doc.wijknaam,
      buurt: doc.buurtnaam,
      lat,
      lon,
      source: "pdok",
    };
  }

  function fallback(postcode, house) {
    const id = POSTCODE_FALLBACK[postcode.slice(0, 4)];
    if (!id) return null;
    const s = M.sensors.find((x) => x.id === id);
    return {
      label: `${postcode.slice(0, 4)} ${postcode.slice(4)} ${house.number}${house.letter}, Haarlem`,
      gemeente: "Haarlem",
      wijk: s.buurt,
      buurt: null,
      lat: s.lat,
      lon: s.lon,
      source: "fallback",
    };
  }

  async function lookup(rawPostcode, rawNumber) {
    const postcode = normalizePostcode(rawPostcode);
    const house = parseNumber(rawNumber);
    if (!postcode) return { error: "postcode" };
    if (!house) return { error: "number" };
    try {
      const found = await geocode(postcode, house);
      return found ? { postcode, house, place: found } : { error: "notfound", postcode, house };
    } catch (e) {
      const place = fallback(postcode, house);
      return place ? { postcode, house, place, offline: true } : { error: "offline", postcode, house };
    }
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

  window.Address = { NORMS, LKI_UPPER, LKI_CLASSES, GRADES, MAX_KM, FILTERS, lookup, analyse, lki, grade, periodFor };
})();
