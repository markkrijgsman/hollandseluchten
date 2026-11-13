(function () {
  "use strict";
  const M = window.MOCK;
  const A = window.A;
  const C = window.Charts;
  const I = window.I18N;
  const D = window.Address;
  const { esc } = C;
  const { fmt } = A;
  const t = (nl, en) => I.t(nl, en);
  const N = D.NORMS;

  const COLORS = { you: "#2277FF", city: "#202333", grey: "#B0BAC2" };

  const DATE_MIN = "2020-01-01";
  const DATE_MAX = "2026-09-30";
  const state = { lookup: null, period: "month", customRange: null, backendDate: null, backendBundle: null };
  let leafletMap = null;

  const CHROME = {
    "nav.address": ["Check mijn plek", "Check my spot"],
    "nav.ask": ["Stel een vraag", "Ask a question"],
    title: ["Moet ik me zorgen maken over de lucht hier?", "Should I be concerned about the air here?"],
    subtitle: [
      "Ontdek in één oogopslag hoe schoon de lucht vandaag en op de lange termijn is op jouw plek.",
      "See at a glance how clean the air is today and in the long run at your location.",
    ],
    "form.locate": ["Gebruik mijn locatie", "Use my location"],
    "form.or": ["of", "or"],
    "form.postcode": ["Postcode of plaats", "Postcode or place"],
    "form.number": ["Huisnr. (optioneel)", "House no. (optional)"],
    "form.submit": ["Zoek op", "Look up"],
    "form.privacy": [
      "Je locatie of postcode wordt alleen gebruikt om het dichtstbijzijnde meetpunt te vinden en wordt nooit opgeslagen.",
      "Your location or postcode is only used to find the nearest monitoring station and is never stored.",
    ],
    "form.try": ["Of kies een voorbeeld:", "Or try an example:"],
    "form.period": ["Periode:", "Period:"],
    "form.rangeFrom": ["Van", "From"],
    "form.rangeTo": ["Tot en met", "To (inclusive)"],
    "form.apply": ["Toepassen", "Apply"],
  };

  function makeCtx(input) {
    const audit = {
      vraag: t(`Luchtkwaliteit op ${input}`, `Air quality at ${input}`),
      tijdstip: new Date().toISOString(),
      versie: "prototype-0.2",
      let_op: t(
        "Het adres wordt opgezocht via PDOK; referentiestations komen uit Luchtmeetnet (/pm25) en de Haarlemse wijkvergelijking gebruikt 6 burgersensoren.",
        "The address is looked up via PDOK; reference stations come from Luchtmeetnet (/pm25) and the Haarlem neighbourhood comparison uses 6 citizen sensors."
      ),
      stappen: [],
      beperkingen: [],
    };
    return {
      audit,
      step(stap, functie, parameters, resultaat, bron = "Samen Analyseren") {
        audit.stappen.push({ nr: audit.stappen.length + 1, stap, bron, functie, parameters, resultaat });
      },
      caveat(text) {
        if (!audit.beperkingen.includes(text)) audit.beperkingen.push(text);
      },
    };
  }

  const periodLabel = (key) => ({
    year: t("afgelopen 12 maanden", "the last 12 months"),
    quarter: t("afgelopen 3 maanden", "the last 3 months"),
    month: t("afgelopen maand", "the last month"),
  })[key];

  function renderSearchPeriodSelect() {
    const sel = document.getElementById("search-period");
    if (!sel) return;
    const opts = [
      ["week", "Afgelopen 7 dagen", "Last 7 days"],
      ["month", "Afgelopen 30 dagen", "Last 30 days"],
      ["quarter", "Afgelopen 3 maanden", "Last 3 months"],
      ["year", "Heel jaar (365 dagen)", "Full year (365 days)"],
      ["custom", "Eigen periode…", "Custom period…"],
    ];
    sel.innerHTML = opts.map(([k, nl, en]) => `<option value="${k}"${state.period === k ? " selected" : ""}>${esc(t(nl, en))}</option>`).join("");

    const lbl = document.getElementById("search-period-label");
    if (lbl) lbl.textContent = t("Periode:", "Period:");
    const applyBtn = document.getElementById("search-apply");
    if (applyBtn) applyBtn.textContent = t("Toepassen", "Apply");
    const fromSpan = document.querySelector("#search-from-label span");
    if (fromSpan) fromSpan.textContent = t("Van", "From");
    const toSpan = document.querySelector("#search-to-label span");
    if (toSpan) toSpan.textContent = t("Tot en met", "To (inclusive)");

    const customRow = document.getElementById("search-custom-row");
    if (customRow) customRow.hidden = state.period !== "custom";
  }

  function bindSearchPeriod() {
    const sel = document.getElementById("search-period");
    if (!sel) return;
    sel.addEventListener("change", async (e) => {
      state.period = e.target.value;
      if (state.period === "custom" && !state.customRange) {
        const clamp = (d) => (d < DATE_MIN ? DATE_MIN : d > DATE_MAX ? DATE_MAX : d);
        const to = clamp(new Date().toISOString().slice(0, 10));
        const from = clamp(new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10));
        state.customRange = { from, to };
        D.setCustomRange(from, to);
      }
      renderSearchPeriodSelect();
      if (state.period === "custom") {
        const fi = document.getElementById("search-from");
        const ti = document.getElementById("search-to");
        if (fi && state.customRange) fi.value = state.customRange.from;
        if (ti && state.customRange) ti.value = state.customRange.to;
        return;
      }
      if (state.lookup) {
        if (state.backendBundle && state.backendBundle.ok) {
          const { lat, lon } = state.lookup.place;
          const tsRes = await D.fetchBackendTimeseries(lat, lon, state.backendBundle.latestDate, state.period, state.backendBundle.radiusKm);
          if (tsRes.ok) {
            state.backendBundle.timeseries = tsRes.data;
            state.backendBundle.timeseriesRange = tsRes.range;
          }
        }
        const y = window.scrollY;
        render();
        window.scrollTo(0, y);
      }
    });

    const rangeForm = document.getElementById("search-range-form");
    if (rangeForm) {
      rangeForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const from = document.getElementById("search-from").value;
        const to = document.getElementById("search-to").value;
        const err = document.getElementById("search-range-error");
        const fail = (nl, en) => { err.hidden = false; err.textContent = t(nl, en); };
        if (!from || !to) return fail("Vul beide datums in.", "Enter both dates.");
        if (from > to) return fail("De startdatum ligt na de einddatum.", "The start date is after the end date.");
        if (from < DATE_MIN || to > DATE_MAX) {
          return fail(
            `Kies datums tussen ${A.longDate(DATE_MIN)} en ${A.longDate(DATE_MAX)}.`,
            `Choose dates between ${A.longDate(DATE_MIN)} and ${A.longDate(DATE_MAX)}.`
          );
        }
        err.hidden = true;
        state.customRange = { from, to };
        D.setCustomRange(from, to);
        state.backendDate = to;
        if (state.lookup) {
          const { lat, lon } = state.lookup.place;
          state.backendBundle = await D.fetchBackendBundle(lat, lon, to, "custom", 15);
          const y = window.scrollY;
          render();
          window.scrollTo(0, y);
        }
      });
    }
  }

  const clsName = (c) => t(c.nl, c.en);

  function gradeText(g) {
    return {
      A: t("Onder het WHO-gezondheidsadvies", "Below the WHO health guideline"),
      B: t("Binnen de wet, boven WHO-advies", "Within legal limits, above WHO advice"),
      C: t("Boven de EU-grens vanaf 2030", "Above the 2030 EU limit"),
      D: t("Ruim boven de EU-grens vanaf 2030", "Well above the 2030 EU limit"),
      E: t("Boven de huidige wettelijke grens", "Above the current legal limit"),
    }[g.grade];
  }

  function todayAdvice(cls) {
    return {
      goed: t("Geen gezondheidsklachten te verwachten. Je kunt gewoon buiten zijn en buiten sporten.", "No health effects expected. Going outside and outdoor exercise are fine."),
      matig: t("Voor de meeste mensen geen probleem. Mensen met astma of COPD kunnen lichte klachten krijgen.", "No problem for most people. People with asthma or COPD may notice mild symptoms."),
      onvoldoende: t("Heb je longklachten of een hartziekte? Beperk dan vandaag zware inspanning buiten.", "Do you have lung problems or heart disease? Limit heavy outdoor exercise today."),
      slecht: t("Ook gezonde mensen kunnen klachten krijgen (hoesten, kortademig). Beperk zware inspanning buiten.", "Healthy people may also notice symptoms (coughing, shortness of breath). Limit heavy outdoor exercise."),
      zeer_slecht: t("Iedereen: vermijd zware inspanning buiten. Gevoelige mensen blijven bij voorkeur binnen.", "Everyone: avoid heavy outdoor exercise. Sensitive people are best off staying indoors."),
    }[cls.key];
  }

  function concernVerdict(ix, r, placeLabel) {
    const key = ix ? ix.cls.key : "goed";
    const diff = r && !r.tooFar ? r.mean - r.city : 0;
    const sameAsCity = Math.abs(diff) < 1.5;
    const citySentence = r && !r.tooFar
      ? sameAsCity
        ? t("De lucht op jouw plek is ongeveer net zo schoon als gemiddeld in de rest van Haarlem.", "The air at your spot is about as clean as the average across the rest of Haarlem.")
        : diff > 0
          ? t("Het meetpunt bij jou in de buurt meet iets meer fijnstof dan gemiddeld in Haarlem.", "The sensor near you measures slightly more particulate matter than the Haarlem average.")
          : t("Het meetpunt bij jou in de buurt meet iets minder fijnstof dan gemiddeld in Haarlem.", "The sensor near you measures slightly less particulate matter than the Haarlem average.")
      : "";

    if (key === "goed") {
      return {
        pill: t("Geen reden tot zorg vandaag", "No reason for concern today"),
        statusColor: "#258758",
        statusBg: "#e9f6ef",
        headline: t("Nee, je hoeft je vandaag geen zorgen te maken.", "No, you don’t need to worry today."),
        lead: `${t(`De luchtkwaliteit bij ${placeLabel} is vandaag goed.`, `Air quality at ${placeLabel} is good today.`)} ${todayAdvice(ix.cls)} ${citySentence}`.trim(),
      };
    }
    if (key === "matig") {
      return {
        pill: t("Let op bij gevoelige longen", "Take care with sensitive lungs"),
        statusColor: "#8f6000",
        statusBg: "#fff8de",
        headline: t("Voor de meeste mensen geen probleem; let op bij gevoelige longen.", "Fine for most people; take care if you have sensitive lungs."),
        lead: `${t(`Er zit vandaag wat meer fijnstof in de lucht bij ${placeLabel}.`, `There is slightly more particulate matter in the air at ${placeLabel} today.`)} ${todayAdvice(ix.cls)} ${citySentence}`.trim(),
      };
    }
    return {
      pill: t("Vandaag ongezonde lucht", "Poor air quality today"),
      statusColor: "#c93434",
      statusBg: "#fcecec",
      headline: t("Ja, de lucht is vandaag viezer dan normaal — doe buiten rustig aan.", "Yes, the air is dirtier than usual today — take it easy outdoors."),
      lead: `${t(`Bij ${placeLabel} is vandaag veel fijnstof gemeten.`, `Elevated particulate matter was measured at ${placeLabel} today.`)} ${todayAdvice(ix.cls)} ${citySentence}`.trim(),
    };
  }

  function longTermText(g) {
    const base = t(
      "Fijnstof is vooral schadelijk als je er jarenlang elke dag aan blootstaat. Er is geen grens waaronder het helemaal onschadelijk is; hoe lager, hoe beter.",
      "Particulate matter is mainly harmful when you breathe it every day for years. There is no level below which it is completely harmless; lower is better."
    );
    const level = {
      A: t("Bij jou is het erg schoon voor Nederlandse begrippen.", "Where you live it is very clean by Dutch standards."),
      B: t("Bij jou is het vergelijkbaar met de meeste steden in Nederland.", "Where you live it is comparable with most cities in the Netherlands."),
      C: t("Bij jou zit het boven de strengere grens die vanaf 2030 geldt.", "Where you live it is above the stricter limit that applies from 2030."),
      D: t("Bij jou zit het ruim boven de grens die vanaf 2030 geldt.", "Where you live it is well above the limit that applies from 2030."),
      E: t("Bij jou is het viezer dan de wet toestaat.", "Where you live it is dirtier than the law allows."),
    }[g.grade];
    return `${level} ${base}`;
  }

  function mapWidgetHtml() {
    return `<div class="map-wrap">
      <div id="location-map" class="location-map" role="region" aria-label="${esc(t("Kaart met jouw locatie en meetpunten", "Map showing your location and sensors"))}"></div>
      <div class="map-legend">
        <span><i class="map-dot user"></i>${esc(t("Jouw plek", "Your spot"))}</span>
        <span><i class="map-dot near"></i>${esc(t("Dichtstbijzijnde sensor", "Nearest sensor"))}</span>
        <span><i class="map-dot other"></i>${esc(t("Andere sensoren", "Other sensors"))}</span>
        <span class="map-hint">${esc(t("Tip: klik op de kaart om een andere plek te kiezen", "Tip: click the map to pick another spot"))}</span>
      </div>
    </div>`;
  }

  function dataSourceBadge(r) {
    if (r && r.fromBackend && r.backend && !r.backend.fromEmbeddedParquet) {
      const date = r.backend.latestDate || "";
      return `<p class="data-source-badge data-source-live" role="status">
        <span aria-hidden="true">●</span> ${esc(t(`Live meetdata van Luchtmeetnet API · ${date}`, `Live data from Luchtmeetnet API · ${date}`))}
      </p>`;
    }
    if (r && r.fromBackend && r.backend && r.backend.fromEmbeddedParquet) {
      return `<p class="data-source-badge data-source-embedded" role="status">
        <span aria-hidden="true">◑</span> ${esc(t("Ingebedde dataset (backend niet bereikbaar)", "Embedded dataset (backend offline)"))}
      </p>`;
    }
    return `<p class="data-source-badge data-source-demo" role="status">
      <span aria-hidden="true">○</span> ${esc(t("Demodata (geen backend)", "Demo data (no backend)"))}
    </p>`;
  }

  // LAAG 1: Eén rustige kaart met het directe antwoord + kaartje
  function verdictCard(lk, r, apiRes) {
    const p = lk.place;
    const where = [p.buurt, p.wijk].filter(Boolean).join(", ");
    const livePm = apiRes && apiRes.ok && apiRes.data ? apiRes.data.pm25 : null;
    const ix = r && !r.tooFar ? r.index : livePm != null ? D.lki(livePm) : D.lki(10);
    const v = concernVerdict(ix, r, p.label);

    const g = r && !r.tooFar ? r.grade : livePm != null ? D.grade(livePm) : D.grade(10);
    const nearText = r && !r.tooFar
      ? `${esc(r.near.s.naam)} (${fmt(r.near.km)} km)`
      : apiRes && apiRes.ok && apiRes.data && apiRes.data.reference && apiRes.data.reference.stations[0]
        ? `${esc(apiRes.data.reference.stations[0].name)} (${fmt(apiRes.data.reference.stations[0].distance_km)} km)`
        : esc(r && r.near ? `${r.near.s.naam} (${fmt(r.near.km)} km)` : "Luchtmeetnet");

    const q = r && !r.tooFar
      ? t(`Wat is de gemiddelde luchtkwaliteit in ${r.near.s.buurt}?`, `What is the average air quality in ${r.near.s.buurt}?`)
      : t("Hoe verhouden onze sensoren zich tot het officiële meetstation?", "How do our sensors compare with the official monitoring station?");

    return `<section class="card verdict-card" style="--status-color:${v.statusColor};--status-bg:${v.statusBg}">
      <div class="verdict-top">
        <div class="location-tag">
          <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M10 2a6 6 0 0 0-6 6c0 4.5 6 10 6 10s6-5.5 6-10a6 6 0 0 0-6-6zm0 8a2 2 0 1 1 0-4 2 2 0 0 1 0 4z" fill="currentColor"/></svg>
          <b>${esc(p.label)}</b>${where ? ` · <span>${esc(where)}</span>` : ""}
        </div>
        <span class="status-pill"><i class="status-dot" aria-hidden="true"></i>${esc(v.pill)}</span>
      </div>

      <h2 class="verdict-headline">${esc(v.headline)}</h2>
      <p class="verdict-lead">${esc(v.lead)}</p>
      ${dataSourceBadge(r)}

      <div class="quick-facts">
        <div class="fact-box">
          <span class="fact-label">${esc(t("Lucht vandaag", "Air today"))}</span>
          <div class="fact-value">
            ${ix ? `<span class="fact-badge" style="--c:${ix.cls.color};--fg:${ix.cls.fg || "#fff"}">${ix.n}</span><span>${esc(clsName(ix.cls))}</span>` : "–"}
          </div>
          <span class="fact-sub">${esc(t("RIVM-schaal 1 (schoon) t/m 11", "RIVM scale 1 (clean) to 11"))}</span>
        </div>

        <div class="fact-box">
          <span class="fact-label">${esc(t("Lange termijn (jaargemiddelde)", "Long-term (annual average)"))}</span>
          <div class="fact-value">
            <span class="fact-badge" style="--c:${g.color};--fg:${g.fg || "#fff"}">${g.grade}</span>
            <span>${esc(r && !r.tooFar ? `${fmt(r.mean)} µg/m³` : livePm != null ? `${fmt(livePm)} µg/m³` : g.grade)}</span>
          </div>
          <span class="fact-sub">${esc(gradeText(g))}</span>
        </div>

        <div class="fact-box">
          <span class="fact-label">${esc(t("Gemeten bij", "Measured at"))}</span>
          <div class="fact-value"><span>${nearText}</span></div>
          <span class="fact-sub">${esc(t("Dichtstbijzijnde meetpunt", "Nearest monitoring point"))}</span>
        </div>
      </div>

      ${mapWidgetHtml()}

      ${lk.offline ? `<p class="notice">${esc(t("Geen verbinding met PDOK: je adres is bij benadering bepaald op je postcode.", "No connection to PDOK: your address was approximated from your postcode."))}</p>` : ""}

      <div class="verdict-actions">
        <span class="muted">${esc(t("Wil je zelf een vraag stellen over de metingen?", "Want to ask your own question about the measurements?"))}</span>
        <a class="btn-outline" href="index.html?q=${encodeURIComponent(q)}">${esc(t("Stel een vraag →", "Ask a question →"))}</a>
      </div>
    </section>`;
  }

  // LAAG 2A: Gezondheid & wat je zelf kunt doen
  function healthDrawer(r) {
    const ix = r.index;
    const icon = (path) => `<svg viewBox="0 0 48 48" class="icon" aria-hidden="true"><circle cx="24" cy="24" r="20" fill="#EEF4FF"/>${path}<circle cx="38" cy="10" r="3" fill="#F9FF8E" stroke="#202333" stroke-width="1"/></svg>`;
    const today = icon('<path d="M12 26h6l3-8 5 14 3-6h7" fill="none" stroke="#2277FF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>');
    const longTerm = icon('<rect x="14" y="15" width="20" height="19" rx="3" fill="none" stroke="#2277FF" stroke-width="2.4"/><path d="M14 21h20M19 12v5M29 12v5" stroke="#2277FF" stroke-width="2.4" stroke-linecap="round"/>');
    const act = icon('<path d="M24 35c-7-4-11-8-11-13a5.5 5.5 0 0 1 11-1 5.5 5.5 0 0 1 11 1c0 5-4 9-11 13z" fill="none" stroke="#2277FF" stroke-width="2.4" stroke-linejoin="round"/>');
    return `<details class="drawer" id="gezondheid">
      <summary>
        <div class="summary-text">
          <span class="summary-title">${esc(t("Wat betekent dit voor mijn gezondheid & wat kan ik doen?", "What does this mean for my health & what can I do?"))}</span>
          <span class="summary-sub">${esc(t("Advies voor vandaag, op de lange termijn en tips voor schone lucht", "Advice for today, in the long run, and tips for clean air"))}</span>
        </div>
        <span class="summary-tag">${esc(t("Uitleg & tips", "Health & tips"))}</span>
      </summary>
      <div class="drawer-body">
        <div class="health-cols">
          <div class="health-col">${today}<h3>${esc(t("Vandaag", "Today"))}</h3><p>${esc(ix ? todayAdvice(ix.cls) : "–")}</p></div>
          <div class="health-col">${longTerm}<h3>${esc(t("Op de lange termijn", "In the long run"))}</h3><p>${esc(longTermText(r.grade))}</p></div>
          <div class="health-col">${act}<h3>${esc(t("Wat kun je zelf doen?", "What can you do?"))}</h3><p>${esc(t(
            "Lokaal zijn houtstook en verkeer de grootste bronnen. Stook liever geen hout, zeker niet bij windstil weer. Heb je longklachten, sport dan op vieze dagen in een park of binnen.",
            "Locally, wood burning and traffic are the biggest sources. Avoid burning wood, especially on still days. If you have lung problems, exercise in a park or indoors on dirty days."
          ))}</p></div>
        </div>
      </div>
    </details>`;
  }

  // LAAG 2B: Vergelijking met de rest van Haarlem
  function compareDrawer(r) {
    if (r.tooFar) return "";
    const diff = r.mean - r.city;
    const rel = r.city ? Math.round((Math.abs(diff) / r.city) * 100) : 0;
    const same = Math.abs(diff) < 1.5;
    const subSummary = same
      ? t("Ongeveer even schoon als gemiddeld in Haarlem", "About as clean as the Haarlem average")
      : diff > 0
        ? t(`${rel}% meer fijnstof dan gemiddeld in Haarlem`, `${rel}% more particulate matter than the Haarlem average`)
        : t(`${rel}% minder fijnstof dan gemiddeld in Haarlem`, `${rel}% less particulate matter than the Haarlem average`);

    const detail = same
      ? t(
          `Het verschil (${fmt(Math.abs(diff))} µg/m³) is kleiner dan wat goedkope sensoren onderling al kunnen afwijken. Je woont dus niet op een viezere of schonere plek dan gemiddeld.`,
          `The difference (${fmt(Math.abs(diff))} µg/m³) is smaller than how far low-cost sensors already disagree. So you do not live somewhere dirtier or cleaner than average.`
        )
      : t(
          `Het verschil is ${fmt(Math.abs(diff))} µg/m³. Dat kan aan je buurt liggen (verkeer, houtstook), maar ook aan de sensor zelf.`,
          `The difference is ${fmt(Math.abs(diff))} µg/m³. That could be your neighbourhood (traffic, wood burning), but also the sensor itself.`
        );

    const spanDays = D.daysBetween(r.period.start, r.period.end);
    const daily = r.period.key === "custom" ? spanDays <= 120 : r.period.key !== "year";
    let labels, you, city, tick;
    if (daily) {
      labels = r.dates;
      you = r.est;
      city = r.cityDaily;
      const step = labels.length <= 14 ? 1 : 7;
      tick = (d, i) => (i % step === 0 ? A.shortDate(d) : null);
    } else {
      const byMonth = (vals) => A.groupMean(r.dates, vals, (x) => x.slice(0, 7));
      const ym = byMonth(r.est);
      const cm = byMonth(r.cityDaily);
      labels = [...ym.keys()];
      you = labels.map((k) => ym.get(k));
      city = labels.map((k) => cm.get(k));
      tick = (k) => `${A.monthShort(Number(k.slice(5, 7)) - 1)} '${k.slice(2, 4)}`;
    }
    const youName = t(`Jouw buurt (${r.near.s.naam})`, `Your spot (${r.near.s.naam})`);
    const cityName = t("Gemiddelde Haarlem", "Haarlem average");
    const rows = r.perSensor.slice().sort((a, b) => b.mean - a.mean);

    return `<details class="drawer" id="vergelijking">
      <summary>
        <div class="summary-text">
          <span class="summary-title">${esc(t("Hoe verhoudt mijn buurt zich tot de rest van Haarlem?", "How does my neighbourhood compare with the rest of Haarlem?"))}</span>
          <span class="summary-sub">${esc(subSummary)}</span>
        </div>
        <span class="summary-tag">${esc(t("Grafieken", "Charts"))}</span>
      </summary>
      <div class="drawer-body">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:10px">
          <label for="period" class="muted small">${esc(t("Kies periode:", "Choose period:"))} ${periodSelect()}</label>
          <span class="muted small">${esc(A.longDate(r.period.start))} – ${esc(A.longDate(r.period.end))}</span>
        </div>
        ${customRangeFields(r)}
        <div class="stats">
          <div><span class="muted small">${esc(t("Jouw plek", "Your spot"))}</span><b style="color:${COLORS.you}">${fmt(r.mean)}</b><span class="muted small">µg/m³</span></div>
          <div><span class="muted small">${esc(cityName)}</span><b>${fmt(r.city)}</b><span class="muted small">µg/m³</span></div>
          <div><span class="muted small">${esc(t("Verschil", "Difference"))}</span><b>${diff >= 0 ? "+" : "−"}${fmt(Math.abs(diff))}</b><span class="muted small">${diff >= 0 ? "+" : "−"}${rel}%</span></div>
        </div>
        <p>${esc(detail)}</p>
        ${C.lineChart({
          labels,
          tickLabel: tick,
          series: [
            { name: youName, color: COLORS.you, values: you, width: 2.4 },
            { name: cityName, color: COLORS.city, values: city, dashed: true, width: 2 },
          ],
        })}
        <h3>${esc(t("Alle meetpunten in Haarlem", "All sensors in Haarlem"))}</h3>
        ${C.barChart({
          items: rows.map((x) => ({
            label: x.s.naam,
            sub: x.s.buurt,
            value: x.mean,
            color: x.s.id === r.near.s.id ? COLORS.you : x.cov < 0.75 ? COLORS.grey : "#9DB7E5",
          })),
          refLine: { value: r.city, label: `${cityName}: ${fmt(r.city)}` },
          legendItems: [
            { name: youName, color: COLORS.you },
            { name: t("Andere meetpunten", "Other sensors"), color: "#9DB7E5" },
            ...(rows.some((x) => x.cov < 0.75) ? [{ name: t("Te weinig data (< 75%)", "Too little data (< 75%)"), color: COLORS.grey }] : []),
          ],
        })}
      </div>
    </details>`;
  }

  // LAAG 2C: Normen (WHO & EU)
  function normsDrawer(r) {
    if (r.tooFar) return "";
    const status = (ok) => `<span class="pill ${ok ? "ok" : "bad"}">${esc(ok ? t("Voldoet", "Met") : t("Boven advies/norm", "Exceeded"))}</span>`;
    const yearRows = [
      [t("WHO-gezondheidsadvies", "WHO health guideline"), t("gezondheidsadvies", "health advice"), `${N.who} µg/m³`, r.mean <= N.who],
      [t("EU-grens vanaf 2030", "EU limit from 2030"), t("wet (vanaf 2030)", "law (from 2030)"), `${N.eu2030} µg/m³`, r.mean <= N.eu2030],
      [t("Huidige wettelijke grens", "Current legal limit"), t("huidige wet", "current law"), `${N.euNow} µg/m³`, r.mean <= N.euNow],
    ];
    const year = r.period.key === "year";
    const dayRows = year
      ? [
          [t("WHO-advies per dag", "WHO daily guideline"), t("gezondheidsadvies", "health advice"), t(`${N.whoDay} µg/m³ (max. 3–4 dagen/jaar)`, `${N.whoDay} µg/m³ (max 3–4 days/yr)`), r.daysOverWho <= 4, t(`${r.daysOverWho} dagen`, `${r.daysOverWho} days`)],
          [t("EU-daggrens vanaf 2030", "EU daily limit from 2030"), t("wet (vanaf 2030)", "law (from 2030)"), t(`${N.euDay2030} µg/m³ (max. 18 dagen/jaar)`, `${N.euDay2030} µg/m³ (max 18 days/yr)`), r.daysOverEu <= 18, t(`${r.daysOverEu} dagen`, `${r.daysOverEu} days`)],
        ]
      : [];

    const summarySub = r.mean <= N.eu2030
      ? t("Voldoet aan de wet (ook voor 2030), maar ligt boven het strenge WHO-advies", "Meets legal limits (including 2030), but above the strict WHO guideline")
      : t("Voldoet aan de huidige wet, maar ligt boven de grens voor 2030", "Meets current law, but above the 2030 limit");

    return `<details class="drawer" id="normen">
      <summary>
        <div class="summary-text">
          <span class="summary-title">${esc(t("Voldoet de lucht aan de normen van de overheid en de WHO?", "Does the air meet government and WHO limits?"))}</span>
          <span class="summary-sub">${esc(summarySub)}</span>
        </div>
        <span class="summary-tag">${esc(t("Wet & WHO", "Law & WHO"))}</span>
      </summary>
      <div class="drawer-body">
        <p>${esc(t(
          "De wettelijke grens van de EU is nu 25 µg/m³ en wordt in 2030 aangescherpt naar 10 µg/m³. De Wereldgezondheidsorganisatie (WHO) adviseert 5 µg/m³ voor je gezondheid.",
          "The current EU legal limit is 25 µg/m³ and tightens to 10 µg/m³ in 2030. The World Health Organization (WHO) recommends 5 µg/m³ for health."
        ))}</p>
        ${C.normScale({ value: r.mean, valueLabel: t(`Jouw plek: ${fmt(r.mean)} µg/m³`, `Your spot: ${fmt(r.mean)} µg/m³`) })}
        <div class="table-wrap"><table class="norms"><thead><tr><th>${esc(t("Norm", "Limit"))}</th><th>${esc(t("Soort", "Type"))}</th><th>${esc(t("Grens", "Threshold"))}</th><th>${esc(t("Bij jou", "Where you live"))}</th><th></th></tr></thead><tbody>
          ${yearRows.map(([n, k, v, ok]) => `<tr><td>${esc(n)}</td><td>${esc(k)}</td><td>${esc(v)}</td><td>${fmt(r.mean)} µg/m³</td><td>${status(ok)}</td></tr>`).join("")}
          ${dayRows.map(([n, k, v, ok, val]) => `<tr><td>${esc(n)}</td><td>${esc(k)}</td><td>${esc(v)}</td><td>${esc(val)}</td><td>${status(ok)}</td></tr>`).join("")}
        </tbody></table></div>
      </div>
    </details>`;
  }

  function backendBox(bundle) {
    if (!bundle) return "";
    if (!bundle.ok) {
      return `<div class="backend-box">
        <strong>${esc(t("Lokale REST API (http://localhost:8000)", "Local REST API (http://localhost:8000)"))}</strong>
        <p class="muted small" style="margin:6px 0 0">${esc(String(bundle.error || "Backend niet bereikbaar — teruggevallen op lokale demodata."))}</p>
      </div>`;
    }
    const d = bundle.pm25;
    const grp = d && (d.basis === "sensors" ? d.sensors : d.reference);
    const stations = (grp && grp.stations) || [];
    const base = D.apiBase();
    return `<div class="backend-box">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
        <strong>${esc(t("Live REST API · Officiële Parquet-dataset (Luchtmeetnet + Analyse-Together)", "Live REST API · Official Parquet dataset (Luchtmeetnet + Analyse-Together)"))}</strong>
        ${d ? `<span class="pill ok">${esc(t(`Gewogen daggemiddelde (${d.date}): ${fmt(d.pm25)} µg/m³`, `Weighted daily mean (${d.date}): ${fmt(d.pm25)} µg/m³`))}</span>` : ""}
      </div>
      <div class="backend-controls">
        <label for="backend-date" class="muted small">${esc(t("Meetdatum (2020 – sep 2026):", "Measurement date (2020 – Sep 2026):"))}</label>
        <input type="date" id="backend-date" value="${esc(bundle.latestDate)}" min="2020-01-01" max="2026-09-30" />
        <span class="muted small">${esc(t(`${stations.length} station(s) binnen ${bundle.radiusKm} km (1/d² gewogen)`, `${stations.length} station(s) within ${bundle.radiusKm} km (1/d² weighted)`))}</span>
      </div>
      ${
        stations.length
          ? `<div class="table-wrap"><table class="norms"><thead><tr>
              <th>${esc(t("Station", "Station"))}</th>
              <th>${esc(t("Afstand", "Distance"))}</th>
              <th>${esc(t("Gewicht (1/d²)", "Weight (1/d²)"))}</th>
              <th>${esc(t("Geldige uren", "Valid hours"))}</th>
              <th>${esc(t("Daggemiddelde", "Daily mean"))}</th>
            </tr></thead><tbody>
              ${stations
                .map(
                  (s) => `<tr>
                  <td><b>${esc(s.name)}</b> <span class="muted small">${esc(s.id)}</span></td>
                  <td>${fmt(s.distance_km)} km</td>
                  <td>${Math.round(s.weight * 100)}%</td>
                  <td>${s.valid_hours} / 24 u</td>
                  <td><b>${fmt(s.daily_mean)} µg/m³</b></td>
                </tr>`
                )
                .join("")}
            </tbody></table></div>`
          : ""
      }
      <p class="muted small" style="margin:8px 0 0">
        <b>REST API endpoints gebruikt:</b>
        <a href="${esc(base + (bundle.stations && bundle.stations.reproduce ? bundle.stations.reproduce : "/stations"))}" target="_blank" rel="noopener"><code>GET /stations</code></a> ·
        ${d && d.reproduce ? `<a href="${esc(base + d.reproduce)}" target="_blank" rel="noopener"><code>GET /pm25</code></a> · ` : ""}
        ${bundle.compareWho && bundle.compareWho.reproduce ? `<a href="${esc(base + bundle.compareWho.reproduce)}" target="_blank" rel="noopener"><code>GET /pm25/compare (WHO)</code></a> · ` : ""}
        ${bundle.timeseries && bundle.timeseries.reproduce ? `<a href="${esc(base + bundle.timeseries.reproduce)}" target="_blank" rel="noopener"><code>GET /pm25/timeseries</code></a> · ` : ""}
        <a href="${esc(base + "/docs")}" target="_blank" rel="noopener">Swagger UI (/docs)</a>
      </p>
    </div>`;
  }

  function params(obj) {
    const label = (k) => k.replace(/_/g, " ");
    return Object.entries(obj || {})
      .map(([k, v]) => `<div><span class="muted">${esc(label(k))}:</span> ${esc(Array.isArray(v) ? v.join(", ") : typeof v === "object" && v !== null ? JSON.stringify(v) : v)}</div>`)
      .join("");
  }

  // LAAG 2D: Voor onderzoekers / nieuwsgierigen: Audit Trail & ruwe stationsdata
  function auditDrawer(audit, bundle) {
    const badgeClass = (bron) => (bron === "Samen Analyseren" ? "sa" : bron === "REST API" || bron === "Backend API" ? "api" : "own");
    const badgeLabel = (bron) =>
      bron === "Samen Analyseren"
        ? "Samen Analyseren"
        : bron === "PDOK"
          ? "PDOK"
          : bron === "Geolocation"
            ? "Browser API"
            : bron === "REST API" || bron === "Backend API"
              ? "REST API"
              : t("Aanvullend", "Added by us");
    return `<details class="drawer" id="berekening">
      <summary>
        <div class="summary-text">
          <span class="summary-title">${esc(t("Hoe is dit precies berekend? (Meetdata & Audit Trail)", "How was this calculated? (Station data & Audit Trail)"))}</span>
          <span class="summary-sub">${esc(t(`Transparant overzicht van alle ${audit.stappen.length} rekenstappen, filters en aannames`, `Transparent log of all ${audit.stappen.length} calculation steps, filters, and assumptions`))}</span>
        </div>
        <span class="summary-tag">${esc(t("Voor onderzoekers", "Audit trail"))}</span>
      </summary>
      <div class="drawer-body">
        ${backendBox(bundle)}
        ${audit.beperkingen.length ? `<div class="caveats"><h3>${esc(t("Kanttekeningen & onzekerheid", "Limitations & uncertainty"))}</h3><ul>${audit.beperkingen.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
        <p class="muted small">${esc(t(
          "Groen = gevalideerde R-functie uit Samen Analyseren, blauw = lokale REST API (localhost:8000), oranje = aanvullende stap.",
          "Green = validated R function from Samen Analyseren, blue = local REST API (localhost:8000), orange = additional step."
        ))}</p>
        <div class="table-wrap"><table class="steps"><thead><tr><th>#</th><th>${esc(t("Stap", "Step"))}</th><th>${esc(t("Functie", "Function"))}</th><th>${esc(t("Instellingen", "Settings"))}</th><th>${esc(t("Uitkomst", "Outcome"))}</th></tr></thead><tbody>
        ${audit.stappen.map((s) => `<tr><td>${s.nr}</td><td>${esc(s.stap)}</td>
          <td><span class="badge ${badgeClass(s.bron)}">${esc(badgeLabel(s.bron))}</span><code>${esc(s.functie)}</code></td>
          <td>${params(s.parameters)}</td><td>${esc(s.resultaat)}</td></tr>`).join("")}
        </tbody></table></div>
        <button type="button" class="btn-outline" id="download">${esc(t("Download volledige audit trail (JSON)", "Download full audit trail (JSON)"))}</button>
      </div>
    </details>`;
  }

  function periodSelect() {
    const opt = (k, nl, en) => `<option value="${k}"${state.period === k ? " selected" : ""}>${esc(t(nl, en))}</option>`;
    return `<select id="period" class="select" aria-label="${esc(t("Periode", "Period"))}">
      ${opt("week", "Afgelopen 7 dagen", "Last 7 days")}${opt("month", "Afgelopen 30 dagen", "Last 30 days")}${opt("quarter", "Afgelopen 3 maanden", "Last 3 months")}${opt("year", "Heel jaar (365 dagen)", "Full year (365 days)")}${opt("custom", "Eigen periode…", "Custom period…")}
    </select>`;
  }

  // Van/tot-datums, alleen zichtbaar bij "Eigen periode".
  function customRangeFields(r) {
    if (state.period !== "custom") return "";
    const from = state.customRange ? state.customRange.from : r.period.start;
    const to = state.customRange ? state.customRange.to : r.period.end;
    return `<form id="custom-range" class="custom-range" novalidate>
      <label>${esc(t("Van", "From"))} <input type="date" id="range-from" value="${esc(from)}" min="${DATE_MIN}" max="${DATE_MAX}" required></label>
      <label>${esc(t("Tot en met", "To (inclusive)"))} <input type="date" id="range-to" value="${esc(to)}" min="${DATE_MIN}" max="${DATE_MAX}" required></label>
      <button type="submit" class="btn-outline">${esc(t("Toepassen", "Apply"))}</button>
      <span class="form-error" id="range-error" role="alert" aria-live="polite" hidden></span>
    </form>`;
  }

  function render() {
    const out = document.getElementById("result");
    const lk = state.lookup;
    if (!lk) {
      out.innerHTML = "";
      return;
    }

    // Remember which drawers were open before re-rendering
    const openDrawers = new Set(
      Array.from(out.querySelectorAll("details.drawer[open]")).map((d) => d.id)
    );

    const houseStr = lk.house && lk.house.number ? ` ${lk.house.number}${lk.house.letter || ""}` : "";
    const input = lk.fromGeolocation
      ? t(`mijn locatie (${lk.place.label})`, `my location (${lk.place.label})`)
      : `${lk.postcode}${houseStr}`.trim();
    const ctx = makeCtx(input);

    if (lk.fromGeolocation) {
      ctx.step(
        t("Apparaatlocatie opvragen", "Request device location"),
        "navigator.geolocation.getCurrentPosition",
        { nauwkeurigheid: lk.accuracyM ? `± ${lk.accuracyM} m` : "standaard" },
        `${lk.place.lat.toFixed(4)}°N, ${lk.place.lon.toFixed(4)}°E`,
        "Geolocation"
      );
      ctx.step(
        t("Coördinaten vertalen naar adres", "Reverse-geocode coordinates to address"),
        lk.place.source === "geolocation+pdok" ? "PDOK Locatieserver · reverse" : t("aanvullend: coördinaten", "added: coordinates"),
        { lat: lk.place.lat.toFixed(4), lon: lk.place.lon.toFixed(4) },
        lk.place.label,
        lk.place.source === "geolocation+pdok" ? "PDOK" : "Aanvullend"
      );
    } else {
      ctx.step(
        t("Adres of postcode opzoeken", "Look up address or postcode"),
        lk.offline ? t("aanvullend: postcodetabel (offline)", "added: postcode table (offline)") : "PDOK Locatieserver / GET /geocode",
        { zoekopdracht: lk.postcode, ...(houseStr.trim() ? { huisnummer: houseStr.trim() } : { modus: t("alleen postcode/plaats", "postcode/place only") }) },
        `${lk.place.label} (${lk.place.lat.toFixed(4)}, ${lk.place.lon.toFixed(4)})`,
        lk.offline ? "Aanvullend" : "PDOK"
      );
    }

    const r =
      state.backendBundle && state.backendBundle.ok
        ? D.buildResultFromBackend(state.backendBundle, state.period, ctx)
        : D.analyse(lk.place, state.period, ctx);

    out.innerHTML =
      verdictCard(lk, r, state.backendBundle && state.backendBundle.pm25 ? { ok: true, data: state.backendBundle.pm25 } : null) +
      `<section class="drilldown-section" aria-labelledby="drilldown-heading">
        <div class="drilldown-head">
          <h2 id="drilldown-heading">${esc(t("Meer weten? Klik om verder te kijken", "Want to know more? Click to explore further"))}</h2>
          <p>${esc(t("Van praktisch gezondheidsadvies tot alle onderliggende meetdata", "From practical health advice to all underlying sensor data"))}</p>
        </div>
        ${!r.tooFar ? healthDrawer(r) : ""}
        ${compareDrawer(r)}
        ${normsDrawer(r)}
        ${auditDrawer(ctx.audit, state.backendBundle)}
      </section>`;

    openDrawers.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.open = true;
    });

    bind(ctx.audit, lk, r);
  }

  function initMap(lk, r) {
    const el = document.getElementById("location-map");
    if (!el || !window.L || !lk || !lk.place) return;
    if (leafletMap) {
      leafletMap.remove();
      leafletMap = null;
    }
    const L = window.L;
    const p = lk.place;
    const map = L.map(el, { scrollWheelZoom: false }).setView([p.lat, p.lon], 14);
    leafletMap = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; CARTO',
      maxZoom: 19,
    }).addTo(map);

    const bounds = [[p.lat, p.lon]];

    if (r && r.near && r.near.s) {
      const ns = r.near.s;
      bounds.push([ns.lat, ns.lon]);
      L.polyline(
        [
          [p.lat, p.lon],
          [ns.lat, ns.lon],
        ],
        { color: "#258758", weight: 2.2, dashArray: "6 5", opacity: 0.85 }
      ).addTo(map);
    }

    const meanById = {};
    if (r && Array.isArray(r.perSensor)) {
      r.perSensor.forEach((item) => {
        meanById[item.s.id] = item.mean;
      });
    }
    const mapStations =
      r && r.fromBackend && Array.isArray(r.allStations) && r.allStations.length
        ? r.allStations.map((st) => ({
            id: st.id,
            naam: st.name.trim(),
            buurt: `${st.station_type || st.kind} · ${st.area_type || ""}`,
            lat: st.lat,
            lon: st.lon,
          }))
        : M.sensors;

    mapStations.forEach((s) => {
      const isNear = r && r.near && r.near.s && r.near.s.id === s.id;
      const val = meanById[s.id];
      const marker = L.circleMarker([s.lat, s.lon], {
        radius: isNear ? 8 : 6,
        fillColor: isNear ? "#258758" : "#6b7080",
        color: "#ffffff",
        weight: 2,
        fillOpacity: 0.95,
      }).addTo(map);
      const valText = val != null ? `<br/>${esc(t("Daggemiddelde", "Daily mean"))}: <b>${fmt(val)} µg/m³</b>` : "";
      const nearBadge = isNear ? ` · <b>${esc(t("dichtstbijzijnd", "nearest"))} (${fmt(r.near.km)} km)</b>` : "";
      marker.bindPopup(
        `<b>${esc(s.naam)}</b> <span style="color:#6b7080">(${esc(s.id)})</span><br/>${esc(s.buurt)}${nearBadge}${valText}`
      );
    });

    if ((!r || !r.fromBackend) && M.reference && M.reference.lat && M.reference.lon) {
      L.circleMarker([M.reference.lat, M.reference.lon], {
        radius: 6,
        fillColor: "#202333",
        color: "#ffffff",
        weight: 2,
        fillOpacity: 0.9,
      })
        .addTo(map)
        .bindPopup(`<b>${esc(I.refName())}</b><br/><span style="color:#6b7080">${esc(M.reference.id)}</span>`);
    }

    L.circleMarker([p.lat, p.lon], {
      radius: 14,
      fillColor: "#2277ff",
      color: "transparent",
      fillOpacity: 0.2,
      interactive: false,
    }).addTo(map);

    const userMarker = L.circleMarker([p.lat, p.lon], {
      radius: 8,
      fillColor: "#2277ff",
      color: "#ffffff",
      weight: 2.5,
      fillOpacity: 1,
    }).addTo(map);
    userMarker.bindPopup(
      `<b>${esc(t("Jouw gekozen plek", "Your selected spot"))}</b><br/>${esc(p.label)}<br/><span style="color:#6b7080">${p.lat.toFixed(4)}°N, ${p.lon.toFixed(4)}°E</span>`
    );

    if (bounds.length > 1 && r && !r.tooFar) {
      map.fitBounds(bounds, { padding: [32, 32], maxZoom: 14 });
    }

    map.on("click", async (ev) => {
      const { lat, lng } = ev.latlng;
      const place = await D.reverseGeocode(lat, lng);
      if (place.postcode) {
        document.getElementById("postcode").value = place.postcode;
        document.getElementById("number").value = "";
      }
      const url = new URL(window.location.href);
      url.searchParams.delete("postcode");
      url.searchParams.delete("nr");
      url.searchParams.set("lat", lat.toFixed(4));
      url.searchParams.set("lon", lng.toFixed(4));
      history.replaceState(null, "", url);
      await refreshWithPlace({
        postcode: place.postcode || `${lat.toFixed(4)}, ${lng.toFixed(4)}`,
        house: { number: "", letter: "" },
        place,
        fromGeolocation: false,
      });
    });
  }

  function bind(audit, lk, r) {
    initMap(lk, r);
    const periodEl = document.getElementById("period");
    const rangeForm = document.getElementById("custom-range");
    if (rangeForm) {
      rangeForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const from = document.getElementById("range-from").value;
        const to = document.getElementById("range-to").value;
        const err = document.getElementById("range-error");
        const fail = (nl, en) => {
          err.hidden = false;
          err.textContent = t(nl, en);
        };
        if (!from || !to) return fail("Vul beide datums in.", "Enter both dates.");
        if (from > to) return fail("De startdatum ligt na de einddatum.", "The start date is after the end date.");
        if (from < DATE_MIN || to > DATE_MAX) {
          return fail(
            `Kies datums tussen ${A.longDate(DATE_MIN)} en ${A.longDate(DATE_MAX)}.`,
            `Choose dates between ${A.longDate(DATE_MIN)} and ${A.longDate(DATE_MAX)}.`
          );
        }
        err.hidden = true;
        state.customRange = { from, to };
        D.setCustomRange(from, to);
        // De meetdatum (/pm25) volgt de einddatum van de gekozen periode.
        state.backendDate = to;
        if (state.lookup) {
          const { lat, lon } = state.lookup.place;
          state.backendBundle = await D.fetchBackendBundle(lat, lon, to, "custom", 15);
        }
        const y = window.scrollY;
        render();
        window.scrollTo(0, y);
      });
    }
    if (periodEl) {
      periodEl.addEventListener("change", async (e) => {
        state.period = e.target.value;
        renderSearchPeriodSelect();
        if (state.period === "custom") {
          // Begin met de periode die al getoond werd, zodat de datums meteen kloppen.
          if (!state.customRange && r && r.period) state.customRange = { from: r.period.start, to: r.period.end };
          if (state.customRange) D.setCustomRange(state.customRange.from, state.customRange.to);
        }
        if (state.backendBundle && state.backendBundle.ok && state.lookup) {
          const { lat, lon } = state.lookup.place;
          const tsRes = await D.fetchBackendTimeseries(
            lat,
            lon,
            state.backendBundle.latestDate,
            state.period,
            state.backendBundle.radiusKm
          );
          if (tsRes.ok) {
            state.backendBundle.timeseries = tsRes.data;
            state.backendBundle.timeseriesRange = tsRes.range;
          }
        }
        const y = window.scrollY;
        render();
        window.scrollTo(0, y);
      });
    }
    const backendDateEl = document.getElementById("backend-date");
    if (backendDateEl) {
      backendDateEl.addEventListener("change", async (e) => {
        if (!e.target.value || !state.lookup) return;
        state.backendDate = e.target.value;
        const { lat, lon } = state.lookup.place;
        state.backendBundle = await D.fetchBackendBundle(lat, lon, state.backendDate, state.period, 15);
        const y = window.scrollY;
        render();
        window.scrollTo(0, y);
      });
    }
    const dlBtn = document.getElementById("download");
    if (dlBtn) {
      dlBtn.addEventListener("click", () => {
        const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `audit-adres-${audit.tijdstip.slice(0, 19).replace(/[:T]/g, "-")}.json`;
        a.click();
        URL.revokeObjectURL(a.href);
      });
    }
  }

  function showError(msg, invalidFieldId) {
    const el = document.getElementById("form-error");
    el.hidden = !msg;
    el.textContent = msg || "";
    ["postcode", "number"].forEach((id) => {
      const input = document.getElementById(id);
      if (input) {
        if (msg && invalidFieldId === id) input.setAttribute("aria-invalid", "true");
        else input.removeAttribute("aria-invalid");
      }
    });
  }

  async function refreshWithPlace(res) {
    state.lookup = res;
    state.backendBundle = await D.fetchBackendBundle(res.place.lat, res.place.lon, state.backendDate, state.period, 15);
    render();
  }

  async function submit(postcode, number) {
    showError("");
    const btn = document.getElementById("go");
    btn.disabled = true;
    btn.textContent = t("Zoeken…", "Searching…");
    const res = await D.lookup(postcode, number);
    btn.disabled = false;
    btn.textContent = t(CHROME["form.submit"][0], CHROME["form.submit"][1]);
    if (res.error) {
      const fieldMap = { postcode: "postcode", number: "number" };
      showError(
        {
          postcode: t("Vul een geldige postcode of plaatsnaam in, bijvoorbeeld 2011 RD.", "Enter a valid postcode or place name, for example 2011 RD."),
          number: t("Vul een geldig huisnummer in (bijv. 12 of 12A), of laat het huisnummer leeg.", "Enter a valid house number (e.g. 12 or 12A), or leave it blank."),
          notfound: t("Dit adres of deze postcode kunnen we niet vinden. Controleer de invoer of laat het huisnummer weg.", "We cannot find this address or postcode. Check your input or leave the house number blank."),
          offline: t("Geen verbinding met de adresservice, en zonder verbinding herkennen we alleen Haarlemse postcodes.", "No connection to the address service, and offline we only recognise Haarlem postcodes."),
        }[res.error],
        fieldMap[res.error] || "postcode"
      );
      return;
    }
    const url = new URL(window.location.href);
    url.searchParams.delete("lat");
    url.searchParams.delete("lon");
    url.searchParams.set("postcode", res.postcode);
    if (res.house && res.house.number) {
      url.searchParams.set("nr", `${res.house.number}${res.house.letter}`);
    } else {
      url.searchParams.delete("nr");
    }
    history.replaceState(null, "", url);
    await refreshWithPlace(res);
  }

  async function useMyLocation() {
    showError("");
    const btn = document.getElementById("locate");
    const labelSpan = btn.querySelector("span");
    btn.disabled = true;
    if (labelSpan) labelSpan.textContent = t("Locatie bepalen…", "Locating…");
    const res = await D.locate();
    btn.disabled = false;
    if (labelSpan) labelSpan.textContent = t(CHROME["form.locate"][0], CHROME["form.locate"][1]);
    if (res.error) {
      showError(
        {
          geolocation_unsupported: t("Je browser ondersteunt geen locatiebepaling. Vul hierboven je postcode in.", "Your browser does not support geolocation. Enter your postcode above."),
          geolocation_denied: t("Toegang tot je locatie is geweigerd. Geef toestemming in je browser of vul je postcode in.", "Location access was denied. Grant permission in your browser or enter your postcode."),
          geolocation_timeout: t("Het bepalen van je locatie duurde te lang. Probeer het opnieuw of vul je postcode in.", "Determining your location timed out. Try again or enter your postcode."),
          geolocation_unavailable: t("Je locatie kon niet worden bepaald. Vul hierboven je postcode in.", "Your location could not be determined. Enter your postcode above."),
        }[res.error]
      );
      return;
    }
    if (res.postcode) {
      document.getElementById("postcode").value = res.postcode;
      document.getElementById("number").value = "";
    }
    const url = new URL(window.location.href);
    url.searchParams.delete("postcode");
    url.searchParams.delete("nr");
    url.searchParams.set("lat", res.place.lat.toFixed(4));
    url.searchParams.set("lon", res.place.lon.toFixed(4));
    history.replaceState(null, "", url);
    await refreshWithPlace(res);
  }

  function applyChrome() {
    document.title = t("Hoe is de lucht op mijn adres? · Hollandse Luchten", "How is the air at my address? · Hollandse Luchten");
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const pair = CHROME[el.dataset.i18n];
      if (pair) el.textContent = t(pair[0], pair[1]);
    });
    document.getElementById("foot").textContent = t(
      "Hollandse Luchten · Burgerwetenschap voor gezonde lucht in Noord-Holland.",
      "Hollandse Luchten · Citizen science for healthy air in Noord-Holland."
    );
  }

  ["postcode", "number"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("input", () => {
        el.removeAttribute("aria-invalid");
        const err = document.getElementById("form-error");
        if (err && !err.hidden) showError("");
      });
    }
  });

  document.getElementById("lookup").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(document.getElementById("postcode").value, document.getElementById("number").value);
  });
  document.getElementById("locate").addEventListener("click", () => {
    useMyLocation();
  });
  document.querySelectorAll("[data-pc]").forEach((b) =>
    b.addEventListener("click", () => {
      document.getElementById("postcode").value = b.dataset.pc;
      document.getElementById("number").value = b.dataset.nr || "";
      submit(b.dataset.pc, b.dataset.nr || "");
    })
  );
  document.querySelectorAll(".lang-toggle button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.lang !== I.lang) I.set(b.dataset.lang);
    })
  );
  I.onChange(() => {
    applyChrome();
    renderSearchPeriodSelect();
    render();
  });

  applyChrome();
  renderSearchPeriodSelect();
  bindSearchPeriod();
  const params0 = new URLSearchParams(window.location.search);
  if (params0.get("postcode")) {
    document.getElementById("postcode").value = params0.get("postcode");
    document.getElementById("number").value = params0.get("nr") || "";
    submit(params0.get("postcode"), params0.get("nr") || "");
  } else if (params0.get("lat") && params0.get("lon")) {
    const lat = Number(params0.get("lat"));
    const lon = Number(params0.get("lon"));
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      D.reverseGeocode(lat, lon).then((place) =>
        refreshWithPlace({ postcode: place.postcode || "", house: { number: "", letter: "" }, place, fromGeolocation: true })
      );
    }
  } else {
    // Show a welcoming default example right away so citizens immediately see how simple it is
    document.getElementById("postcode").value = "2011 RD";
    document.getElementById("number").value = "2";
    submit("2011RD", "2");
  }
})();
