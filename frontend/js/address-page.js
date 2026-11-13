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

  const state = { lookup: null, period: "year" };

  const CHROME = {
    "nav.address": ["Mijn adres", "My address"],
    "nav.ask": ["Stel een vraag", "Ask a question"],
    badge: ["Prototype · nepdata", "Prototype · mock data"],
    "side.tools": ["Luchtkwaliteit", "Air quality"],
    "side.page": ["Op deze pagina", "On this page"],
    "side.overview": ["Overzicht", "Overview"],
    "side.compare": ["Vergelijking met Haarlem", "Compared with Haarlem"],
    "side.norms": ["Normen", "Limits"],
    "side.health": ["Gezondheid", "Health"],
    "side.audit": ["Zo is het berekend", "How it was calculated"],
    title: ["Lucht op mijn adres", "Air at my address"],
    "help.lead": ["Benieuwd hoe we hierop komen?", "Curious how we got here?"],
    "help.button": ["Zo is het berekend", "How it was calculated"],
    "form.postcode": ["Postcode", "Postcode"],
    "form.number": ["Huisnummer", "House number"],
    "form.submit": ["Bekijk mijn lucht", "Check my air"],
    "form.try": ["Probeer:", "Try:"],
    empty: [
      "Vul je postcode en huisnummer in. Je ziet dan hoe schoon de lucht bij jou is, hoe dat zich verhoudt tot de rest van Haarlem en wat het betekent voor je gezondheid.",
      "Enter your postcode and house number. You will see how clean the air is where you live, how it compares with the rest of Haarlem, and what it means for your health.",
    ],
  };

  function makeCtx(input) {
    const audit = {
      vraag: t(`Luchtkwaliteit op ${input}`, `Air quality at ${input}`),
      tijdstip: new Date().toISOString(),
      versie: "prototype-0.1",
      let_op: t(
        "Prototype: het adres is echt (PDOK), de metingen zijn nepdata. De functienamen tonen welke Samen Analyseren-module in de echte versie wordt aangeroepen.",
        "Prototype: the address is real (PDOK), the measurements are mock data. The function names show which Samen Analyseren module the real version would call."
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

  const info = (id, label) =>
    `<button type="button" class="info" data-ctx="${id}" aria-expanded="false" aria-controls="${id}" title="${esc(label || t("Uitleg", "Explanation"))}"><span aria-hidden="true">i</span><span class="sr">${esc(label || t("Uitleg", "Explanation"))}</span></button>`;
  const explain = (id) =>
    `<button type="button" class="btn-ghost" data-ctx="${id}" aria-expanded="false" aria-controls="${id}"><span class="info-dot" aria-hidden="true">i</span>${esc(t("Uitleg", "Explanation"))}</button>`;
  const ctxBox = (id, html) => `<div class="context" id="${id}" hidden>${html}</div>`;

  const periodLabel = (key) => ({
    year: t("afgelopen 12 maanden", "the last 12 months"),
    quarter: t("afgelopen 3 maanden", "the last 3 months"),
    month: t("afgelopen maand", "the last month"),
  })[key];

  const clsName = (c) => t(c.nl, c.en);

  function gradeText(g) {
    return {
      A: t("Onder het WHO-gezondheidsadvies", "Below the WHO health guideline"),
      B: t("Binnen de wettelijke grenzen, boven het WHO-advies", "Within the legal limits, above the WHO guideline"),
      C: t("Boven de EU-grens die vanaf 2030 geldt", "Above the EU limit that applies from 2030"),
      D: t("Ruim boven de EU-grens van 2030", "Well above the EU limit for 2030"),
      E: t("Boven de huidige wettelijke grens", "Above the current legal limit"),
    }[g.grade];
  }

  function todayAdvice(cls) {
    return {
      goed: t("Geen gezondheidsklachten te verwachten. Je kunt gewoon buiten sporten.", "No health effects expected. Outdoor exercise is fine."),
      matig: t("Mensen met astma, COPD of hart- en vaatziekten kunnen lichte klachten krijgen. Voor anderen geen probleem.", "People with asthma, COPD or heart disease may notice mild symptoms. No problem for others."),
      onvoldoende: t("Heb je longklachten of een hartziekte? Beperk dan zware inspanning buiten.", "Do you have lung problems or heart disease? Then limit heavy outdoor exercise."),
      slecht: t("Ook gezonde mensen kunnen klachten krijgen (hoesten, kortademig). Beperk zware inspanning buiten.", "Healthy people may also notice symptoms (coughing, shortness of breath). Limit heavy outdoor exercise."),
      zeer_slecht: t("Iedereen: vermijd zware inspanning buiten. Gevoelige mensen blijven bij voorkeur binnen.", "Everyone: avoid heavy outdoor exercise. Sensitive people are best off staying indoors."),
    }[cls.key];
  }

  function longTermText(g) {
    const base = t(
      "Fijnstof is vooral schadelijk als je er jarenlang aan blootstaat: het vergroot de kans op hart-, vaat- en longziekten. Er is geen grens waaronder het helemaal onschadelijk is; hoe lager, hoe beter.",
      "Particulate matter is mainly harmful when you breathe it for years: it raises the risk of heart, vascular and lung disease. There is no level below which it is completely harmless; lower is better."
    );
    const level = {
      A: t("Bij jou is het erg schoon voor Nederlandse begrippen.", "Where you live it is very clean by Dutch standards."),
      B: t("Bij jou is het vergelijkbaar met de meeste plekken in Nederland.", "Where you live it is comparable with most places in the Netherlands."),
      C: t("Bij jou zit het boven de strengere grens die vanaf 2030 geldt.", "Where you live it is above the stricter limit that applies from 2030."),
      D: t("Bij jou zit het ruim boven de grens die vanaf 2030 geldt.", "Where you live it is well above the limit that applies from 2030."),
      E: t("Bij jou is het viezer dan de wet toestaat.", "Where you live it is dirtier than the law allows."),
    }[g.grade];
    return `${level} ${base}`;
  }

  function lkiStrip(n) {
    const cells = Array.from({ length: 11 }, (_, i) => {
      const c = D.LKI_CLASSES.find((x) => i + 1 <= x.max);
      return `<span class="cell${i + 1 === n ? " on" : ""}" style="--c:${c.color};--fg:${c.fg || "#fff"}">${i + 1}</span>`;
    }).join("");
    return `<div class="strip lki-strip" aria-hidden="true">${cells}</div>`;
  }

  function gradeStrip(g) {
    return `<div class="strip grade-strip" aria-hidden="true">${D.GRADES.map(
      (x) => `<span class="cell${x.grade === g.grade ? " on" : ""}" style="--c:${x.color};--fg:${x.fg || "#fff"}">${x.grade}</span>`
    ).join("")}</div>`;
  }

  function addressCard(lk, r) {
    const p = lk.place;
    const near = r.near;
    const where = [p.buurt, p.wijk].filter(Boolean).join(", ");
    return `<section class="card kv-card">
      <dl class="kv">
        <dt>${esc(t("Adres", "Address"))}</dt><dd><b>${esc(p.label)}</b></dd>
        <dt>${esc(t("Buurt", "Neighbourhood"))}</dt><dd>${esc(where || "–")}</dd>
        <dt>${esc(t("Meetpunt", "Sensor"))} ${info("ctx-sensor", t("Uitleg over het meetpunt", "About the sensor"))}</dt><dd>${esc(near.s.naam)} <span class="muted">${esc(near.s.id)} · ${esc(near.s.buurt)}</span></dd>
        <dt>${esc(t("Afstand", "Distance"))}</dt><dd>${fmt(near.km)} km</dd>
        <dt>${esc(t("Periode", "Period"))}</dt><dd>${periodSelect()}<div class="muted small">${esc(A.longDate(r.period.start))} – ${esc(A.longDate(r.period.end))}</div></dd>
      </dl>
      ${ctxBox("ctx-sensor", `<p>${t(
        `We zoeken je adres op in de Basisregistratie Adressen (via PDOK) en nemen de sensor die hemelsbreed het dichtstbij hangt. Dat is <b>${esc(near.s.naam)}</b>, op ${fmt(near.km)} km. Fijnstof is over zo’n afstand meestal vergelijkbaar, maar een drukke weg of houtkachel vlak bij je huis zie je hier niet terug.`,
        `We look up your address in the Dutch address register (via PDOK) and take the sensor that is closest in a straight line. That is <b>${esc(near.s.naam)}</b>, ${fmt(near.km)} km away. Particulate matter is usually similar over such a distance, but a busy road or wood stove right next to your home will not show up here.`
      )}</p><p class="muted">${t("In dit prototype zijn de sensoren en metingen verzonnen.", "In this prototype the sensors and measurements are made up.")}</p>`)}
      ${lk.offline ? `<p class="notice">${t("Geen verbinding met PDOK: je adres is bij benadering bepaald op de eerste vier cijfers van je postcode.", "No connection to PDOK: your address was approximated from the first four digits of your postcode.")}</p>` : ""}
    </section>`;
  }

  function scoreCard(r) {
    const ix = r.index;
    const g = r.grade;
    const whoTimes = r.mean / N.who;
    const fill = Math.min(100, (r.mean / N.euNow) * 100);
    const shortPeriod = r.period.key !== "year";
    return `<section class="card score-card">
      <div class="tiles">
        <div class="tile">
          <div class="tile-head">${esc(t("Luchtkwaliteitsindex", "Air quality index"))} ${info("ctx-lki", t("Uitleg over de luchtkwaliteitsindex", "About the air quality index"))}</div>
          ${ix ? `<div class="big-row">
              <span class="big-num" style="--c:${ix.cls.color};--fg:${ix.cls.fg || "#fff"}">${ix.n}</span>
              <div><div class="big-label" style="color:${ix.cls.color}">${esc(clsName(ix.cls))}</div>
              <div class="muted small">${esc(t("schaal 1–11", "scale 1–11"))} · ${esc(A.longDate(r.latest.date))}</div></div>
            </div>${lkiStrip(ix.n)}` : `<p class="muted">${esc(t("Geen recente meting", "No recent measurement"))}</p>`}
        </div>
        <div class="tile">
          <div class="tile-head">${esc(t("Cijfer", "Grade"))} ${info("ctx-grade", t("Uitleg over het cijfer", "About the grade"))}</div>
          <div class="big-row">
            <span class="big-num grade" style="--c:${g.color};--fg:${g.fg || "#fff"}">${g.grade}</span>
            <div><div class="big-label">${esc(gradeText(g))}</div>
            <div class="muted small">${esc(t("gemiddelde", "average"))} ${esc(periodLabel(r.period.key))}</div></div>
          </div>
          ${gradeStrip(g)}
        </div>
      </div>
      ${ctxBox("ctx-lki", `<p>${t(
        "De luchtkwaliteitsindex is de schaal van het RIVM die je ook op luchtmeetnet.nl en in weer-apps ziet. Hij loopt van 1 tot 11: <b>1–3 goed</b>, <b>4–6 matig</b>, <b>7–8 onvoldoende</b>, <b>9–10 slecht</b> en <b>11 zeer slecht</b>. Hoe hoger, hoe groter de kans op klachten op die dag.",
        "The air quality index is the RIVM scale you also see on luchtmeetnet.nl and in weather apps. It runs from 1 to 11: <b>1–3 good</b>, <b>4–6 moderate</b>, <b>7–8 poor</b>, <b>9–10 bad</b> and <b>11 very bad</b>. The higher it is, the more likely you are to notice symptoms that day."
      )}</p><p>${t(
        `We tonen de index voor de laatste dag met een meting (${A.longDate(r.latest ? r.latest.date : M.period.end)}): ${fmt(r.latest ? r.latest.value : null)} µg/m³ fijnstof (PM2.5). Voor PM2.5 hoort index 1 bij minder dan 10 µg/m³, index 3 bij 15–20 en index 11 bij meer dan 140.`,
        `We show the index for the latest day with a measurement (${A.longDate(r.latest ? r.latest.date : M.period.end)}): ${fmt(r.latest ? r.latest.value : null)} µg/m³ of particulate matter (PM2.5). For PM2.5, index 1 means less than 10 µg/m³, index 3 means 15–20 and index 11 more than 140.`
      )}</p><p class="muted">${t("Het RIVM rekent de index per uur; wij gebruiken het daggemiddelde. Een korte piek kan daardoor lager uitvallen.", "RIVM calculates the index per hour; we use the daily average. A short peak can therefore come out lower.")}</p>`)}
      ${ctxBox("ctx-grade", `<p>${t(
        "Het cijfer gaat over de lange termijn: het gemiddelde fijnstof over de gekozen periode, vergeleken met de normen. Net als een energielabel: A is het schoonst.",
        "The grade is about the long term: the average particulate matter over the chosen period, compared with the limits. Like an energy label: A is the cleanest."
      )}</p><ul class="grade-list">${D.GRADES.map((x, i) => {
        const lo = i ? D.GRADES[i - 1].max : 0;
        const range = x.max === Infinity ? `≥ ${lo}` : `${lo}–${x.max}`;
        return `<li><span class="cell" style="--c:${x.color};--fg:${x.fg || "#fff"}">${x.grade}</span> ${range} µg/m³ · ${esc(gradeText(x))}</li>`;
      }).join("")}</ul>${shortPeriod ? `<p class="muted">${t("Normen gaan over een heel jaar. Je hebt een kortere periode gekozen, dus het cijfer is een indicatie.", "Limits apply to a full year. You chose a shorter period, so the grade is only an indication.")}</p>` : ""}`)}
      <dl class="kv compact">
        <dt>${esc(t("Gemiddeld fijnstof", "Average particulate matter"))} ${info("ctx-mean", t("Uitleg over het gemiddelde", "About the average"))}</dt><dd><b>${fmt(r.mean)} µg/m³</b> <span class="muted">PM2.5</span></dd>
        <dt>${esc(t("Ten opzichte van WHO-advies", "Compared with WHO guideline"))}</dt><dd>${fmt(whoTimes)}× ${esc(t("zoveel als de WHO gezond vindt", "what the WHO considers healthy"))}</dd>
        <dt>${esc(t("Wettelijke grens", "Legal limit"))}</dt><dd>
          <div class="quota" role="img" aria-label="${fmt(r.mean)} / ${N.euNow} µg/m³"><span style="width:${fill}%;--c:${g.color}"></span><i style="left:${(N.who / N.euNow) * 100}%"></i><i style="left:${(N.eu2030 / N.euNow) * 100}%"></i></div>
          <div class="muted small">${fmt(r.mean)} ${esc(t("van", "of"))} ${N.euNow} µg/m³ ${esc(t("(grens voor het jaargemiddelde)", "(limit for the annual average)"))}</div>
        </dd>
      </dl>
      ${ctxBox("ctx-mean", `<p>${t(
        `Goedkope sensoren meten fijnstof structureel te hoog. Daarom rekenen we alle sensoren in Haarlem om naar het niveau van het officiële meetstation (in deze periode factor ${fmt(r.k, 2)}). Verschillen tussen plekken blijven zo zichtbaar, maar het getal is vergelijkbaar met de normen.`,
        `Low-cost sensors consistently read particulate matter too high. We therefore scale all sensors in Haarlem to the level of the official monitoring station (factor ${fmt(r.k, 2)} in this period). Differences between places stay visible, but the number becomes comparable with the limits.`
      )}</p>`)}
    </section>`;
  }

  function healthCard(r) {
    const ix = r.index;
    const q = t(`Wat is de gemiddelde luchtkwaliteit in ${r.near.s.buurt}?`, `What is the average air quality in ${r.near.s.buurt}?`);
    const icon = (path) => `<svg viewBox="0 0 48 48" class="icon" aria-hidden="true"><circle cx="24" cy="24" r="20" fill="#EEF4FF"/>${path}<circle cx="38" cy="10" r="3" fill="#F9FF8E" stroke="#202333" stroke-width="1"/></svg>`;
    const today = icon('<path d="M12 26h6l3-8 5 14 3-6h7" fill="none" stroke="#2277FF" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>');
    const longTerm = icon('<rect x="14" y="15" width="20" height="19" rx="3" fill="none" stroke="#2277FF" stroke-width="2.4"/><path d="M14 21h20M19 12v5M29 12v5" stroke="#2277FF" stroke-width="2.4" stroke-linecap="round"/>');
    const act = icon('<path d="M24 35c-7-4-11-8-11-13a5.5 5.5 0 0 1 11-1 5.5 5.5 0 0 1 11 1c0 5-4 9-11 13z" fill="none" stroke="#2277FF" stroke-width="2.4" stroke-linejoin="round"/>');
    return `<section class="card health" id="gezondheid">
      <div class="health-lead">
        <div class="card-head"><h2>${esc(t("Wat betekent dit voor je gezondheid?", "What does this mean for your health?"))}</h2>${explain("ctx-health")}</div>
        <p>${ix ? t(`Vandaag: <b>${esc(clsName(ix.cls).toLowerCase())}</b>. Op de lange termijn: <b>klasse ${r.grade.grade}</b>.`, `Today: <b>${esc(clsName(ix.cls).toLowerCase())}</b>. In the long run: <b>grade ${r.grade.grade}</b>.`) : ""} ${esc(t("Er is geen acuut gevaar.", "There is no acute danger."))}</p>
        <a class="btn-primary" href="index.html?q=${encodeURIComponent(q)}">${esc(t(`Stel een vraag over ${r.near.s.buurt}`, `Ask about ${r.near.s.buurt}`))}</a>
      </div>
      <div class="health-cols">
        <div>${today}<h3>${esc(t("Vandaag", "Today"))}</h3><p>${esc(ix ? todayAdvice(ix.cls) : "–")}</p></div>
        <div>${longTerm}<h3>${esc(t("Op de lange termijn", "In the long run"))}</h3><p>${esc(longTermText(r.grade))}</p></div>
        <div>${act}<h3>${esc(t("Wat kun je zelf doen?", "What can you do?"))}</h3><p>${esc(t(
          "Lokaal zijn houtstook en verkeer de grootste bronnen. Stook liever niet, zeker niet bij windstil weer. Heb je longklachten, sport dan op vieze dagen binnen of in een park, uit de buurt van drukke wegen.",
          "Locally, wood burning and traffic are the biggest sources. Avoid burning wood, especially on still days. If you have lung problems, exercise indoors or in a park on dirty days, away from busy roads."
        ))}</p></div>
      </div>
      ${ctxBox("ctx-health", `<p>${t(
        "Het advies voor <b>vandaag</b> volgt de luchtkwaliteitsindex van het RIVM. Het advies voor de <b>lange termijn</b> volgt de WHO: die raadt een jaargemiddelde van hooguit 5 µg/m³ aan. Bijna nergens in Nederland wordt dat gehaald.",
        "The advice for <b>today</b> follows the RIVM air quality index. The <b>long-term</b> advice follows the WHO, which recommends an annual average of at most 5 µg/m³. Almost nowhere in the Netherlands meets that."
      )}</p><p>${t(
        "Gevoelige groepen zijn mensen met astma, COPD of hart- en vaatziekten, ouderen en jonge kinderen. Twijfel je over klachten, vraag het je huisarts of kijk op de site van de GGD.",
        "Sensitive groups are people with asthma, COPD or heart disease, older people and young children. If you are unsure about symptoms, ask your GP or check the GGD website."
      )}</p>`)}
    </section>`;
  }

  function compareCard(r) {
    const diff = r.mean - r.city;
    const rel = r.city ? Math.round((Math.abs(diff) / r.city) * 100) : 0;
    const same = Math.abs(diff) < 1.5;
    const headline = same
      ? t("Bij jou is de lucht ongeveer even schoon als gemiddeld in Haarlem.", "The air where you live is about as clean as the Haarlem average.")
      : diff > 0
        ? t(`Bij jou is de lucht ${rel}% viezer dan gemiddeld in Haarlem.`, `The air where you live is ${rel}% dirtier than the Haarlem average.`)
        : t(`Bij jou is de lucht ${rel}% schoner dan gemiddeld in Haarlem.`, `The air where you live is ${rel}% cleaner than the Haarlem average.`);
    const detail = same
      ? t(
          `Het verschil is ${fmt(Math.abs(diff))} µg/m³. Dat is kleiner dan wat goedkope sensoren onderling al kunnen afwijken, dus je woont niet op een viezere of schonere plek dan gemiddeld.`,
          `The difference is ${fmt(Math.abs(diff))} µg/m³. That is smaller than how far low-cost sensors already disagree, so you do not live somewhere dirtier or cleaner than average.`
        )
      : t(
          `Het verschil is ${fmt(Math.abs(diff))} µg/m³. Dat kan aan je buurt liggen (verkeer, houtstook), maar ook aan de sensor zelf. Vraag de meetgroep of de sensor goed hangt.`,
          `The difference is ${fmt(Math.abs(diff))} µg/m³. That could be your neighbourhood (traffic, wood burning), but also the sensor itself. Ask the measurement group whether the sensor is mounted properly.`
        );

    const daily = r.period.key !== "year";
    let labels, you, city, tick;
    if (daily) {
      labels = r.dates;
      you = r.est;
      city = r.cityDaily;
      tick = (d, i) => (i % 7 === 0 ? A.shortDate(d) : null);
    } else {
      const byMonth = (vals) => A.groupMean(r.dates, vals, (x) => x.slice(0, 7));
      const ym = byMonth(r.est);
      const cm = byMonth(r.cityDaily);
      labels = [...ym.keys()];
      you = labels.map((k) => ym.get(k));
      city = labels.map((k) => cm.get(k));
      tick = (k) => `${A.monthShort(Number(k.slice(5, 7)) - 1)} '${k.slice(2, 4)}`;
    }
    const youName = t(`Jouw plek (${r.near.s.naam})`, `Your spot (${r.near.s.naam})`);
    const cityName = t("Gemiddelde Haarlem", "Haarlem average");

    const rows = r.perSensor.slice().sort((a, b) => b.mean - a.mean);
    return `<section class="card" id="vergelijking">
      <div class="card-head"><h2>${esc(t("Jouw plek tegenover heel Haarlem", "Your spot compared with all of Haarlem"))}</h2>${explain("ctx-compare")}</div>
      <p class="headline">${esc(headline)}</p>
      <div class="stats">
        <div><span class="muted small">${esc(t("Jouw plek", "Your spot"))}</span><b style="color:${COLORS.you}">${fmt(r.mean)}</b><span class="muted small">µg/m³</span></div>
        <div><span class="muted small">${esc(cityName)}</span><b>${fmt(r.city)}</b><span class="muted small">µg/m³</span></div>
        <div><span class="muted small">${esc(t("Verschil", "Difference"))}</span><b>${diff >= 0 ? "+" : "−"}${fmt(Math.abs(diff))}</b><span class="muted small">${diff >= 0 ? "+" : "−"}${rel}%</span></div>
      </div>
      <p>${esc(detail)}</p>
      ${ctxBox("ctx-compare", `<p>${t(
        `Het gemiddelde van Haarlem is het gemiddelde van alle ${M.sensors.length} sensoren in de stad, op dezelfde manier omgerekend als jouw sensor. Zo vergelijk je appels met appels.`,
        `The Haarlem average is the average of all ${M.sensors.length} sensors in the city, scaled the same way as your sensor. That way you compare like with like.`
      )}</p><p>${t(
        "Een verschil van minder dan 1,5 µg/m³ noemen we ‘ongeveer gelijk’: zoveel verschillen goedkope sensoren op dezelfde plek al van elkaar. Fijnstof waait grotendeels van ver aan, dus grote verschillen binnen één stad zijn zeldzaam.",
        "We call a difference of less than 1.5 µg/m³ ‘about the same’: low-cost sensors at the same spot already differ that much. Most particulate matter blows in from far away, so large differences within one city are rare."
      )}</p>`)}
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
    </section>`;
  }

  function normsCard(r) {
    const status = (ok) => `<span class="pill ${ok ? "ok" : "bad"}">${esc(ok ? t("Gehaald", "Met") : t("Niet gehaald", "Not met"))}</span>`;
    const yearRows = [
      [t("WHO-gezondheidsadvies", "WHO health guideline"), t("advies", "advice"), `${N.who} µg/m³`, r.mean <= N.who],
      [t("EU-grens vanaf 2030", "EU limit from 2030"), t("wet (vanaf 2030)", "law (from 2030)"), `${N.eu2030} µg/m³`, r.mean <= N.eu2030],
      [t("Huidige wettelijke grens", "Current legal limit"), t("wet", "law"), `${N.euNow} µg/m³`, r.mean <= N.euNow],
    ];
    const year = r.period.key === "year";
    const dayRows = year
      ? [
          [t("WHO-advies per dag", "WHO daily guideline"), t("advies", "advice"), t(`${N.whoDay} µg/m³, max. 3–4 dagen per jaar`, `${N.whoDay} µg/m³, at most 3–4 days a year`), r.daysOverWho <= 4, t(`${r.daysOverWho} dagen`, `${r.daysOverWho} days`)],
          [t("EU-daggrens vanaf 2030", "EU daily limit from 2030"), t("wet (vanaf 2030)", "law (from 2030)"), t(`${N.euDay2030} µg/m³, max. 18 dagen per jaar`, `${N.euDay2030} µg/m³, at most 18 days a year`), r.daysOverEu <= 18, t(`${r.daysOverEu} dagen`, `${r.daysOverEu} days`)],
        ]
      : [];
    return `<section class="card" id="normen">
      <div class="card-head"><h2>${esc(t("Wat zegt de overheid?", "What does the government say?"))}</h2>${explain("ctx-norms")}</div>
      <p class="headline">${esc(r.mean <= N.euNow
        ? t(`Je zit onder de wettelijke grens van ${N.euNow} µg/m³${r.mean <= N.eu2030 ? `, en ook onder de strengere grens van ${N.eu2030} die vanaf 2030 geldt` : `, maar boven de strengere grens van ${N.eu2030} die vanaf 2030 geldt`}.`, `You are below the legal limit of ${N.euNow} µg/m³${r.mean <= N.eu2030 ? `, and also below the stricter limit of ${N.eu2030} that applies from 2030` : `, but above the stricter limit of ${N.eu2030} that applies from 2030`}.`)
        : t(`Je zit boven de wettelijke grens van ${N.euNow} µg/m³.`, `You are above the legal limit of ${N.euNow} µg/m³.`))}</p>
      ${C.normScale({ value: r.mean, valueLabel: t(`Jouw plek: ${fmt(r.mean)} µg/m³`, `Your spot: ${fmt(r.mean)} µg/m³`) })}
      <table class="norms"><thead><tr><th>${esc(t("Norm", "Limit"))}</th><th>${esc(t("Soort", "Type"))}</th><th>${esc(t("Grens", "Threshold"))}</th><th>${esc(t("Bij jou", "Where you live"))}</th><th></th></tr></thead><tbody>
        ${yearRows.map(([n, k, v, ok]) => `<tr><td>${esc(n)} <span class="muted small">${esc(t("(jaargemiddelde)", "(annual average)"))}</span></td><td>${esc(k)}</td><td>${esc(v)}</td><td>${fmt(r.mean)} µg/m³</td><td>${status(ok)}</td></tr>`).join("")}
        ${dayRows.map(([n, k, v, ok, val]) => `<tr><td>${esc(n)}</td><td>${esc(k)}</td><td>${esc(v)}</td><td>${esc(val)}</td><td>${status(ok)}</td></tr>`).join("")}
      </tbody></table>
      ${year ? "" : `<p class="muted small">${esc(t("Daggrenzen tellen over een heel jaar; kies ‘Afgelopen 12 maanden’ om ze te zien.", "Daily limits count over a full year; choose ‘Last 12 months’ to see them."))}</p>`}
      ${ctxBox("ctx-norms", `<p>${t(
        "Er zijn twee soorten grenzen. De <b>wettelijke grens</b> (EU, in Nederland vastgelegd in de Omgevingswet) is nu 25 µg/m³ als jaargemiddelde. Vanaf 2030 wordt die 10 µg/m³, en mag het daggemiddelde maximaal 18 dagen per jaar boven 25 µg/m³ komen.",
        "There are two kinds of limits. The <b>legal limit</b> (EU, set in Dutch law through the Environment Act) is currently 25 µg/m³ as an annual average. From 2030 it becomes 10 µg/m³, and the daily average may exceed 25 µg/m³ on at most 18 days a year."
      )}</p><p>${t(
        "Het <b>WHO-advies</b> (2021) is geen wet, maar zegt wat gezond is: een jaargemiddelde van 5 µg/m³ en een daggemiddelde boven 15 µg/m³ op hooguit 3 à 4 dagen per jaar.",
        "The <b>WHO guideline</b> (2021) is not law, but says what is healthy: an annual average of 5 µg/m³, and a daily average above 15 µg/m³ on at most 3 or 4 days a year."
      )}</p><p class="muted">${t("Officieel wordt een norm alleen getoetst met metingen van een officieel meetstation. Onze uitkomst is een schatting op basis van burgersensoren.", "Officially, a limit is only checked with measurements from an official monitoring station. Our result is an estimate based on citizen sensors.")}</p>`)}
    </section>`;
  }

  function params(obj) {
    const label = (k) => k.replace(/_/g, " ");
    return Object.entries(obj || {})
      .map(([k, v]) => `<div><span class="muted">${esc(label(k))}:</span> ${esc(Array.isArray(v) ? v.join(", ") : v)}</div>`)
      .join("");
  }

  function auditCard(audit) {
    return `<section class="card" id="berekening">
      <div class="card-head"><h2>${esc(t("Zo is het berekend", "How it was calculated"))}</h2></div>
      ${audit.beperkingen.length ? `<div class="caveats"><h3>${esc(t("Let op", "Please note"))}</h3><ul>${audit.beperkingen.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
      <details class="audit" id="audit-details">
        <summary>${esc(t(`Bekijk alle ${audit.stappen.length} stappen`, `See all ${audit.stappen.length} steps`))}</summary>
        <p class="muted small">${esc(t(
          "Groen = gevalideerde functie uit Samen Analyseren, oranje = aanvullende eigen berekening.",
          "Green = a validated Samen Analyseren function, orange = an extra calculation of our own."
        ))}</p>
        <div class="table-wrap"><table class="steps"><thead><tr><th>#</th><th>${esc(t("Stap", "Step"))}</th><th>${esc(t("Functie", "Function"))}</th><th>${esc(t("Instellingen", "Settings"))}</th><th>${esc(t("Uitkomst", "Outcome"))}</th></tr></thead><tbody>
        ${audit.stappen.map((s) => `<tr><td>${s.nr}</td><td>${esc(s.stap)}</td>
          <td><span class="badge ${s.bron === "Samen Analyseren" ? "sa" : "own"}">${esc(s.bron === "Samen Analyseren" ? "Samen Analyseren" : s.bron === "PDOK" ? "PDOK" : t("Aanvullend", "Added by us"))}</span><code>${esc(s.functie)}</code></td>
          <td>${params(s.parameters)}</td><td>${esc(s.resultaat)}</td></tr>`).join("")}
        </tbody></table></div>
        <button type="button" class="btn-outline" id="download">${esc(t("Download audit trail (JSON)", "Download audit trail (JSON)"))}</button>
      </details>
    </section>`;
  }

  function periodSelect() {
    const opt = (k, nl, en) => `<option value="${k}"${state.period === k ? " selected" : ""}>${esc(t(nl, en))}</option>`;
    return `<select id="period" class="select" aria-label="${esc(t("Periode", "Period"))}">
      ${opt("year", "Afgelopen 12 maanden", "Last 12 months")}${opt("quarter", "Afgelopen 3 maanden", "Last 3 months")}${opt("month", "Afgelopen maand", "Last month")}
    </select>`;
  }

  function errorCard(html) {
    return `<section class="card empty">${html}</section>`;
  }

  function render() {
    const out = document.getElementById("result");
    const lk = state.lookup;
    if (!lk) {
      out.innerHTML = errorCard(`<p>${esc(t(CHROME.empty[0], CHROME.empty[1]))}</p>`);
      return;
    }
    const input = `${lk.postcode.slice(0, 4)} ${lk.postcode.slice(4)} ${lk.house.number}${lk.house.letter}`;
    const ctx = makeCtx(input);
    ctx.step(
      t("Adres opzoeken", "Look up the address"),
      lk.offline ? t("aanvullend: postcodetabel (offline)", "added: postcode table (offline)") : "PDOK Locatieserver · free",
      { postcode: lk.postcode, huisnummer: `${lk.house.number}${lk.house.letter}` },
      `${lk.place.label} (${lk.place.lat.toFixed(4)}, ${lk.place.lon.toFixed(4)})`,
      lk.offline ? "Aanvullend" : "PDOK"
    );
    const r = D.analyse(lk.place, state.period, ctx);
    ctx.caveat(t(
      "Alle metingen op deze pagina zijn nepdata voor 6 fictieve sensoren in Haarlem. Niet gebruiken voor conclusies over echte luchtkwaliteit.",
      "All measurements on this page are mock data for 6 fictional sensors in Haarlem. Do not use them to draw conclusions about real air quality."
    ));

    if (r.tooFar) {
      out.innerHTML = errorCard(`<h2>${esc(lk.place.label)}</h2><p>${t(
        `Dit prototype heeft alleen sensoren in Haarlem. Het dichtstbijzijnde meetpunt (${esc(r.near.s.naam)}) ligt ${fmt(r.near.km)} km van dit adres; dat is te ver om iets zinnigs over jouw lucht te zeggen.`,
        `This prototype only has sensors in Haarlem. The nearest sensor (${esc(r.near.s.naam)}) is ${fmt(r.near.km)} km from this address; that is too far to say anything meaningful about your air.`
      )}</p><p>${t("Kijk voor de officiële metingen bij jou in de buurt op", "For official measurements near you, see")} <a href="https://www.luchtmeetnet.nl" target="_blank" rel="noopener">luchtmeetnet.nl</a>.</p>`);
      return;
    }

    out.innerHTML =
      `<div class="row" id="overzicht">${addressCard(lk, r)}${scoreCard(r)}</div>` +
      healthCard(r) +
      compareCard(r) +
      normsCard(r) +
      auditCard(ctx.audit);
    bind(ctx.audit);
  }

  function bind(audit) {
    document.querySelectorAll("[data-ctx]").forEach((b) =>
      b.addEventListener("click", () => {
        const box = document.getElementById(b.dataset.ctx);
        const open = box.hidden;
        box.hidden = !open;
        document.querySelectorAll(`[data-ctx="${b.dataset.ctx}"]`).forEach((x) => x.setAttribute("aria-expanded", String(open)));
      })
    );
    document.getElementById("period").addEventListener("change", (e) => {
      state.period = e.target.value;
      const y = window.scrollY;
      render();
      window.scrollTo(0, y);
    });
    document.getElementById("download").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `audit-adres-${audit.tijdstip.slice(0, 19).replace(/[:T]/g, "-")}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  function showError(msg) {
    const el = document.getElementById("form-error");
    el.hidden = !msg;
    el.textContent = msg || "";
  }

  async function submit(postcode, number) {
    showError("");
    const btn = document.getElementById("go");
    btn.disabled = true;
    btn.textContent = t("Bezig met zoeken…", "Searching…");
    const res = await D.lookup(postcode, number);
    btn.disabled = false;
    btn.textContent = t(CHROME["form.submit"][0], CHROME["form.submit"][1]);
    if (res.error) {
      showError({
        postcode: t("Vul een geldige postcode in, bijvoorbeeld 2011 RD.", "Enter a valid postcode, for example 2011 RD."),
        number: t("Vul een huisnummer in, bijvoorbeeld 12 of 12A.", "Enter a house number, for example 12 or 12A."),
        notfound: t("Dit adres kunnen we niet vinden. Klopt de combinatie van postcode en huisnummer?", "We cannot find this address. Is the postcode and house number combination right?"),
        offline: t("Geen verbinding met de adresservice, en zonder verbinding herkennen we alleen Haarlemse postcodes.", "No connection to the address service, and offline we only recognise Haarlem postcodes."),
      }[res.error]);
      return;
    }
    state.lookup = res;
    const url = new URL(window.location.href);
    url.searchParams.set("postcode", res.postcode);
    url.searchParams.set("nr", `${res.house.number}${res.house.letter}`);
    history.replaceState(null, "", url);
    render();
  }

  function applyChrome() {
    document.title = t("Lucht op mijn adres · Hollandse Luchten (prototype)", "Air at my address · Hollandse Luchten (prototype)");
    document.querySelectorAll("[data-i18n]").forEach((el) => {
      const pair = CHROME[el.dataset.i18n];
      if (pair) el.textContent = t(pair[0], pair[1]);
    });
    document.getElementById("foot").textContent = t(
      `Adressen via PDOK (Basisregistratie Adressen). Metingen zijn nepdata voor 6 fictieve sensoren in Haarlem (${A.longDate(M.period.start)} – ${A.longDate(M.period.end)}). Niet gebruiken voor conclusies over echte luchtkwaliteit.`,
      `Addresses via PDOK (Dutch address register). Measurements are mock data for 6 fictional sensors in Haarlem (${A.longDate(M.period.start)} – ${A.longDate(M.period.end)}). Do not use them to draw conclusions about real air quality.`
    );
  }

  document.getElementById("lookup").addEventListener("submit", (e) => {
    e.preventDefault();
    submit(document.getElementById("postcode").value, document.getElementById("number").value);
  });
  document.querySelectorAll("[data-pc]").forEach((b) =>
    b.addEventListener("click", () => {
      document.getElementById("postcode").value = b.dataset.pc;
      document.getElementById("number").value = b.dataset.nr;
      submit(b.dataset.pc, b.dataset.nr);
    })
  );
  document.getElementById("show-audit").addEventListener("click", () => {
    const card = document.getElementById("berekening");
    if (!card) {
      document.getElementById("postcode").focus();
      showError(t("Vul eerst een adres in.", "Enter an address first."));
      return;
    }
    document.getElementById("audit-details").open = true;
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  document.querySelectorAll(".lang-toggle button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.lang !== I.lang) I.set(b.dataset.lang);
    })
  );
  I.onChange(() => {
    applyChrome();
    render();
  });

  applyChrome();
  const params0 = new URLSearchParams(window.location.search);
  if (params0.get("postcode")) {
    document.getElementById("postcode").value = params0.get("postcode");
    document.getElementById("number").value = params0.get("nr") || "";
    submit(params0.get("postcode"), params0.get("nr"));
  }
})();
