(function () {
  "use strict";
  const M = window.MOCK;
  const A = window.A;
  const I = window.I18N;
  const { esc } = window.Charts;
  const t = (nl, en) => I.t(nl, en);

  const state = { question: "", overrides: {}, allExamples: false, chatHistory: [], chatRes: null, coverage: null };
  const FEATURED = 5;

  function apiBase() {
    const param = new URLSearchParams(window.location.search).get("api");
    return (param || window.HL_API_URL || "http://localhost:8000").replace(/\/+$/, "");
  }

  async function checkCoverage() {
    const badge = document.getElementById("badge");
    try {
      const res = await fetch(`${apiBase()}/coverage`, { signal: AbortSignal.timeout(1500) });
      if (res.ok) {
        state.coverage = await res.json();
        if (badge) {
          badge.textContent = t("Live REST API · localhost:8000", "Live REST API · localhost:8000");
          badge.style.background = "#e9f6ef";
          badge.style.color = "#258758";
          badge.style.borderColor = "#b7e1cd";
        }
        fetch(`${apiBase()}/guidelines`, { signal: AbortSignal.timeout(1500) })
          .then((r) => r.ok ? r.json() : null)
          .then((norms) => { if (norms) document.dispatchEvent(new CustomEvent("hl:norms", { detail: norms })); })
          .catch(() => {});
        return;
      }
    } catch (_) {
      // Backend offline; use embedded real Parquet dataset
    }
    if (window.REAL_DATA && badge) {
      badge.textContent = t("Luchtmeetnet Parquet-data (2025–2026)", "Luchtmeetnet Parquet data (2025–2026)");
      badge.style.background = "#eef4ff";
      badge.style.color = "#2277ff";
      badge.style.borderColor = "#c3d9ff";
    }
  }

  async function callBackendChat(message) {
    try {
      const res = await fetch(`${apiBase()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, history: state.chatHistory }),
        signal: AbortSignal.timeout(12000),
      });
      if (!res.ok) return null;
      const data = await res.json();
      if (data.history) state.chatHistory = data.history;
      return data;
    } catch (_) {
      return null;
    }
  }

  const AUDIT_KEYS = {
    vraag: ["vraag", "question"],
    tijdstip: ["tijdstip", "time"],
    versie: ["versie", "version"],
    let_op: ["let op", "note"],
    interpretatie: ["interpretatie", "interpretation"],
    methode: ["methode", "method"],
    soort_vraag: ["soort vraag", "question type"],
    herkend_op: ["herkend op", "matched on"],
    status: ["status", "status"],
    data: ["data", "data"],
    bron: ["bron", "source"],
    meetwaarde: ["meetwaarde", "measurement"],
    resolutie: ["resolutie", "resolution"],
    tijdzone: ["tijdzone", "time zone"],
    wijk: ["wijk", "neighbourhood"],
    sensoren: ["sensoren", "sensors"],
    referentiestation: ["referentiestation", "reference station"],
    periode: ["periode", "period"],
    keuzes: ["keuzes", "choices"],
    filters: ["filters", "filters"],
    grenswaarde: ["grenswaarde", "limit"],
    aannames: ["aannames", "assumptions"],
    wijzigingen_door_gebruiker: ["wijzigingen door gebruiker", "changes by the user"],
    stappen: ["stappen", "steps"],
    nr: ["nr", "no."],
    stap: ["stap", "step"],
    functie: ["functie", "function"],
    parameters: ["parameters", "parameters"],
    resultaat: ["resultaat", "result"],
    beperkingen: ["beperkingen", "limitations"],
    kort_antwoord: ["kort antwoord", "short answer"],
    sensoren_key: ["sensoren", "sensors"],
    van: ["van", "from"],
    tot: ["tot", "to"],
    bovengrens: ["bovengrens", "upper limit"],
    vastgelopen_sensor: ["vastgelopen sensor", "stuck sensor"],
    filter: ["filter", "filter"],
    minimale_dekking: ["minimale dekking", "minimum coverage"],
    perioden: ["perioden", "periods"],
    groepen: ["groepen", "groups"],
    groepering: ["groepering", "grouping"],
    regel: ["regel", "rule"],
    regionaal: ["regionaal", "regional"],
    vocht: ["vocht", "humidity"],
    aggregatie: ["aggregatie", "aggregation"],
    reeksen: ["reeksen", "series"],
    eerste_3_maanden: ["eerste 3 maanden", "first 3 months"],
    laatste_3_maanden: ["laatste 3 maanden", "last 3 months"],
    soort: ["soort", "type"],
    herkend: ["herkend", "recognised"],
    enabled: ["aan", "on"],
    cutoff: ["bovengrens", "upper limit"],
    stuckDays: ["vastgelopen na dagen", "stuck after days"],
  };

  function keyLabel(k) {
    const pair = AUDIT_KEYS[k];
    return pair ? t(pair[0], pair[1]) : k.replace(/_/g, " ");
  }

  function localize(value) {
    if (Array.isArray(value)) return value.map(localize);
    if (value && typeof value === "object") {
      const out = {};
      Object.entries(value).forEach(([k, v]) => {
        out[keyLabel(k)] = localize(v);
      });
      return out;
    }
    return value;
  }

  function makeCtx(plan) {
    const audit = {
      vraag: plan.question,
      tijdstip: new Date().toISOString(),
      versie: "prototype-0.1",
      let_op: t(
        "Prototype op nepdata. De functienamen tonen welke Samen Analyseren-module in de echte versie wordt aangeroepen; de berekening hier is JavaScript.",
        "Prototype on mock data. The function names show which Samen Analyseren module the real version would call; the calculation here is JavaScript."
      ),
      interpretatie: {
        methode: t("regelgebaseerd (plek voor een LLM in de echte versie)", "rule-based (a placeholder for an LLM in the real version)"),
        soort_vraag: plan.label,
        herkend_op: plan.matchedOn,
        status: plan.status,
      },
      data: plan.sensors
        ? {
            bron: t("MOCK: nepdata, geen echte metingen", "MOCK: mock data, not real measurements"),
            meetwaarde: plan.component,
            resolutie: t("daggemiddelden", "daily averages"),
            tijdzone: t("UTC (sensoren en referentie gelijkgetrokken)", "UTC (sensors and reference aligned)"),
            wijk: plan.buurt || t("alle wijken", "all neighbourhoods"),
            sensoren: plan.sensors,
            referentiestation: M.reference.id,
            periode: plan.periods ? plan.periods.map((p) => `${p.start} ${t("t/m", "to")} ${p.end}`) : `${plan.period.start} ${t("t/m", "to")} ${plan.period.end}`,
          }
        : null,
      keuzes: plan.sensors ? { filters: plan.filters, ...(plan.intent === "threshold" ? { grenswaarde: plan.threshold } : {}) } : null,
      aannames: plan.assumptions,
      wijzigingen_door_gebruiker: plan.userChanges,
      stappen: [],
      beperkingen: [],
      resultaat: null,
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

  function run() {
    const plan = window.Planner.plan(state.question, state.overrides);
    const ctx = makeCtx(plan);
    const handler = window.Intents[plan.status === "clarify" ? "clarify" : plan.intent];
    const res = handler(plan, ctx);
    if (state.chatRes && Array.isArray(state.chatRes.results)) {
      state.chatRes.results.forEach((env) => {
        if (Array.isArray(env.audit)) {
          env.audit.forEach((a) => {
            const { step, action, functions, result, ...rest } = a;
            ctx.step(
              `REST API: ${action || "stap"}`,
              Array.isArray(functions) ? functions.join(" · ") : env.reproduce || "POST /chat",
              rest,
              result != null ? `${result} µg/m³` : "OK",
              Array.isArray(functions) ? "Samen Analyseren" : "REST API"
            );
          });
        }
      });
    }
    ctx.audit.resultaat = { kort_antwoord: res.short, backend_chat: state.chatRes ? state.chatRes.answer : null };
    render(plan, res, ctx.audit);
  }

  async function ask(question) {
    state.question = question.trim();
    state.overrides = {};
    state.chatRes = null;
    document.getElementById("q").value = state.question;
    if (!state.question) return;
    run();
    const chatRes = await callBackendChat(state.question);
    if (chatRes) {
      state.chatRes = chatRes;
      run();
    }
  }

  function planCard(plan) {
    const understood = t("Zo heb ik je vraag begrepen", "How I understood your question");
    if (plan.status !== "ok" || plan.intent === "education") {
      const note = plan.status === "reject"
        ? t("Deze vraag valt buiten wat ik betrouwbaar kan analyseren. Hieronder leg ik uit waarom, en wat wel kan.", "This question is outside what I can analyse reliably. Below I explain why, and what I can do instead.")
        : plan.status === "clarify"
          ? t("Ik herken geen soort analyse in je vraag.", "I do not recognise a type of analysis in your question.")
          : t("Hier is geen data-analyse voor nodig.", "This does not need a data analysis.");
      return `<section class="card" id="begrepen"><h2><span class="num">1</span>${esc(understood)}</h2>
        <dl class="plan"><dt>${esc(t("Soort vraag", "Type of question"))}</dt><dd>${esc(plan.label)}${plan.matchedOn ? ` <span class="muted">(${esc(t("herkend op", "matched on"))} “${esc(plan.matchedOn)}”)</span>` : ""}</dd></dl>
        <p class="muted">${esc(note)}</p></section>`;
    }

    const names = plan.sensors.map((id) => {
      const s = M.sensors.find((x) => x.id === id);
      return `${esc(s.naam)} <span class="muted">${s.id}</span>`;
    });
    const f = plan.filters;
    const filters = f.enabled
      ? t(
          `Waarden boven ${f.cutoff} µg/m³ en sensoren die ${f.stuckDays}+ dagen hetzelfde meten, tellen als ontbrekend`,
          `Values above ${f.cutoff} µg/m³, and sensors that read the same value for ${f.stuckDays}+ days, count as missing`
        )
      : t("Uit: alle waarden tellen mee", "Off: every value counts");
    const buurten = [...new Set(M.sensors.map((s) => s.buurt))];
    const p = plan.period;

    return `<section class="card" id="begrepen"><h2><span class="num">1</span>${esc(understood)}</h2>
      <dl class="plan">
        <dt>${esc(t("Soort vraag", "Type of question"))}</dt><dd>${esc(plan.label)} <span class="muted">(${esc(t("herkend op", "matched on"))} “${esc(plan.matchedOn)}”)</span></dd>
        <dt>${esc(t("Waar", "Where"))}</dt><dd>${esc(plan.buurt || t("Heel Haarlem", "All of Haarlem"))}: ${names.join(", ")}</dd>
        <dt>${esc(t("Vergeleken met", "Compared with"))}</dt><dd>${esc(I.refName())}</dd>
        <dt>${esc(t("Periode", "Period"))}</dt><dd>${esc(p.label)}</dd>
        <dt>${esc(t("Meetwaarde", "Measurement"))}</dt><dd>${esc(plan.component)}, ${esc(t("daggemiddelden", "daily averages"))}</dd>
        <dt>${esc(t("Uitschieters", "Outliers"))}</dt><dd>${esc(filters)}</dd>
        ${plan.intent === "threshold" ? `<dt>${esc(t("Grenswaarde", "Limit"))}</dt><dd>${plan.threshold} µg/m³ (${esc(t("daggemiddelde", "daily average"))})</dd>` : ""}
      </dl>
      ${plan.assumptions.length ? `<ul class="notes assumptions">${plan.assumptions.map((a) => `<li><b>${esc(t("Aanname:", "Assumption:"))}</b> ${esc(a)}</li>`).join("")}</ul>` : ""}
      ${plan.userChanges.length ? `<ul class="notes changes">${plan.userChanges.map((a) => `<li><b>${esc(t("Door jou aangepast:", "Changed by you:"))}</b> ${esc(a)}</li>`).join("")}</ul>` : ""}
      <details class="adjust"${plan.userChanges.length ? " open" : ""}>
        <summary>${esc(t("Keuzes aanpassen", "Adjust the choices"))}</summary>
        <form id="adjust">
          <label>${esc(t("Wijk", "Neighbourhood"))}
            <select name="buurt"><option value="">${esc(t("Alle wijken", "All neighbourhoods"))}</option>${buurten
              .map((b) => `<option${b === plan.buurt ? " selected" : ""}>${esc(b)}</option>`)
              .join("")}</select>
          </label>
          ${
            plan.periods
              ? ""
              : `<label>${esc(t("Van", "From"))} <input type="date" name="start" value="${p.start}" min="${M.period.start}" max="${M.period.end}"></label>
                 <label>${esc(t("Tot", "To"))} <input type="date" name="end" value="${p.end}" min="${M.period.start}" max="${M.period.end}"></label>`
          }
          <label class="check"><input type="checkbox" name="filtersEnabled"${f.enabled ? " checked" : ""}> ${esc(t("Uitschieters filteren", "Filter outliers"))}</label>
          <label>${esc(t("Bovengrens (µg/m³)", "Upper limit (µg/m³)"))} <input type="number" name="cutoff" value="${f.cutoff}" min="20" max="500" step="5"></label>
          <label>${esc(t("Vastgelopen na (dagen)", "Stuck after (days)"))} <input type="number" name="stuckDays" value="${f.stuckDays}" min="2" max="60"></label>
          ${plan.intent === "threshold" ? `<label>${esc(t("Grenswaarde (µg/m³)", "Limit (µg/m³)"))} <input type="number" name="threshold" value="${plan.threshold}" min="1" max="100"></label>` : ""}
          <button type="submit" class="btn-primary">${esc(t("Opnieuw analyseren", "Analyse again"))}</button>
        </form>
      </details>
    </section>`;
  }

  function answerCard(res, audit) {
    const saCount = (audit.stappen || []).filter((s) => s.bron === "Samen Analyseren").length;
    const saBadge = saCount > 0
      ? `<div class="sa-inline"><span class="badge sa">Samen Analyseren</span> ${saCount} ${esc(t("gevalideerde functies gebruikt", "validated function(s) used"))} · <a href="#audit">${esc(t("bekijk audit trail ↓", "see audit trail ↓"))}</a></div>`
      : "";
    return `<section class="card answer" id="antwoord"><h2><span class="num">2</span>${esc(t("Antwoord", "Answer"))}</h2>
      <p class="short">${esc(res.short)}</p>
      ${res.meaning ? `<div class="meaning"><h3>${esc(t("Wat betekent dit voor jou?", "What does this mean for you?"))}</h3>${res.meaning}</div>` : `<div>${res.body}</div>`}
      ${
        res.followups && res.followups.length
          ? `<div class="followups"><h3>${esc(t("Vervolgvragen", "Follow-up questions"))}</h3><div class="chips">${res.followups
              .map((q) => `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`)
              .join("")}</div></div>`
          : ""
      }
      ${saBadge}
    </section>
    ${
      res.meaning
        ? `<details class="card drawer-card">
            <summary>${esc(t("Bekijk de cijfers, grafiek en kanttekeningen", "See the numbers, chart, and caveats"))}</summary>
            <div class="drawer-inner">
              ${res.body}
              ${res.chart || ""}
              ${audit.beperkingen.length ? `<div class="caveats"><h3>${esc(t("Let op", "Please note"))}</h3><ul>${audit.beperkingen.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>` : ""}
            </div>
          </details>`
        : ""
    }`;
  }

  function params(obj) {
    return Object.entries(obj || {})
      .map(([k, v]) => `<div><span class="muted">${esc(keyLabel(k))}:</span> ${esc(Array.isArray(v) ? v.join(", ") : v)}</div>`)
      .join("");
  }

  function auditCard(audit) {
    return `<section class="card" id="audit"><h2><span class="num">3</span>${esc(t("Audit trail", "Audit trail"))}</h2>
      <p class="muted">${esc(t(
        "Elke stap die tot dit antwoord leidde. Groen = gevalideerde functie uit Samen Analyseren, oranje = aanvullende eigen berekening.",
        "Every step that led to this answer. Green = a validated Samen Analyseren function, orange = an extra calculation of our own."
      ))}</p>
      <details class="audit"><summary>${esc(t(`Bekijk alle ${audit.stappen.length} stappen`, `See all ${audit.stappen.length} steps`))}</summary>
      <div class="table-wrap"><table class="steps"><thead><tr><th>#</th><th>${esc(t("Stap", "Step"))}</th><th>${esc(t("Functie", "Function"))}</th><th>${esc(t("Instellingen", "Settings"))}</th><th>${esc(t("Uitkomst", "Outcome"))}</th></tr></thead><tbody>
      ${audit.stappen
        .map((s) => `<tr><td>${s.nr}</td><td>${esc(s.stap)}</td>
            <td><span class="badge ${s.bron === "Samen Analyseren" ? "sa" : "own"}">${esc(s.bron === "Samen Analyseren" ? "Samen Analyseren" : t("Aanvullend", "Added by us"))}</span><code>${esc(s.functie)}</code></td>
            <td>${params(s.parameters)}</td><td>${esc(s.resultaat)}</td></tr>`)
        .join("")}
      </tbody></table></div>
      <details class="json"><summary>${esc(t("Volledige audit trail (JSON)", "Full audit trail (JSON)"))}</summary><pre>${esc(JSON.stringify(localize(audit), null, 2))}</pre></details>
      </details>
      <button type="button" id="download" class="btn-outline">${esc(t("Download audit trail (JSON)", "Download audit trail (JSON)"))}</button>
    </section>`;
  }

  function backendChatCard(chatRes) {
    if (!chatRes || (!chatRes.results?.length && !chatRes.interpretation?.length)) return "";
    const base = apiBase();
    const calls = (chatRes.interpretation || [])
      .map((c) => {
        const link = c.reproduce ? `<a href="${esc(base + c.reproduce)}" target="_blank" rel="noopener"><code>${esc(c.reproduce)}</code></a>` : `<code>${esc(JSON.stringify(c.input))}</code>`;
        return `<li><b>${esc(c.tool)}</b> → ${link}${c.error ? ` <span class="pill bad">${esc(c.error)}</span>` : ""}</li>`;
      })
      .join("");
    return `<section class="card" style="border-left:4px solid var(--blue)">
      <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:8px">
        <h2 style="margin:0">${esc(t("Live REST API Antwoord (POST /chat)", "Live REST API Answer (POST /chat)"))}</h2>
        <span class="pill ok">${esc(chatRes.llm || "REST API")}</span>
      </div>
      <p class="short" style="font-family:var(--serif);font-size:1.25rem;margin:0 0 10px">${esc(chatRes.answer)}</p>
      ${calls ? `<div class="muted small"><b>${esc(t("Aangeroepen backend-tools:", "Backend tools called:"))}</b><ul style="margin:4px 0 0;padding-left:18px">${calls}</ul></div>` : ""}
    </section>`;
  }

  function render(plan, res, audit) {
    const out = document.getElementById("result");
    const planHtml = planCard(plan).replace(
      /^<section class="card" id="begrepen"><h2><span class="num">1<\/span>([^<]+)<\/h2>/,
      `<details class="card drawer-card" id="begrepen"${plan.userChanges.length ? " open" : ""}><summary>$1 (${esc(t("gebruikte sensoren, periode & filters aanpassen", "sensors used, period & adjust filters"))})</summary><div class="drawer-inner">`
    ).replace(/<\/section>$/, "</div></details>");
    out.innerHTML = backendChatCard(state.chatRes) + answerCard(res, audit) + planHtml + auditCard(audit);

    out.querySelectorAll("[data-q]").forEach((b) => b.addEventListener("click", () => {
      ask(b.dataset.q);
      document.getElementById("begrepen").scrollIntoView({ behavior: "smooth", block: "start" });
    }));

    const form = document.getElementById("adjust");
    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        const fd = new FormData(form);
        state.overrides = {
          buurt: fd.get("buurt") || null,
          filtersEnabled: fd.get("filtersEnabled") === "on",
          cutoff: Number(fd.get("cutoff")),
          stuckDays: Number(fd.get("stuckDays")),
        };
        if (fd.has("start")) {
          state.overrides.start = fd.get("start");
          state.overrides.end = fd.get("end");
        }
        if (fd.has("threshold")) state.overrides.threshold = Number(fd.get("threshold"));
        run();
      });
    }

    document.getElementById("download").addEventListener("click", () => {
      const blob = new Blob([JSON.stringify(localize(audit), null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `audit-${audit.tijdstip.slice(0, 19).replace(/[:T]/g, "-")}.json`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  const CHROME = {
    "nav-address": ["Check mijn plek", "Check my spot"],
    "nav-ask": ["Stel een vraag", "Ask a question"],
    "side-tools": ["Luchtkwaliteit", "Air quality"],
    "side-address": ["Check mijn plek", "Check my spot"],
    "side-ask": ["Stel een vraag", "Ask a question"],
    "side-page": ["Op deze pagina", "On this page"],
    "side-question": ["Je vraag", "Your question"],
    "side-plan": ["Zo heb ik het begrepen", "How I understood it"],
    "side-answer": ["Antwoord", "Answer"],
    "side-audit": ["Audit trail", "Audit trail"],
    badge: ["Prototype · nepdata", "Prototype · mock data"],
  };

  function renderExamples() {
    const list = state.allExamples ? I.examples : I.examples.slice(0, FEATURED);
    document.getElementById("examples").innerHTML = list
      .map((ex) => {
        const q = t(ex.nl, ex.en);
        return `<button type="button" class="chip" data-example="${esc(q)}">${esc(q)}</button>`;
      })
      .join("");
    document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => ask(b.dataset.example)));
    const more = document.getElementById("more");
    more.textContent = state.allExamples
      ? t("Minder voorbeelden", "Fewer examples")
      : t(`Meer voorbeelden (${I.examples.length - FEATURED})`, `More examples (${I.examples.length - FEATURED})`);
    more.setAttribute("aria-expanded", String(state.allExamples));
  }

  function applyChrome() {
    document.title = t("Stel een vraag · Hollandse Luchten (prototype)", "Ask a question · Hollandse Luchten (prototype)");
    Object.entries(CHROME).forEach(([id, [nl, en]]) => (document.getElementById(id).textContent = t(nl, en)));
    document.getElementById("title").textContent = t("Stel je vraag over de luchtkwaliteit", "Ask your question about air quality");
    document.getElementById("lead").textContent = t(
      "Ik zet je vraag om in een analyse met de functies van Samen Analyseren, laat zien welke keuzes ik maak, en leg uit wat je wel en niet uit de uitkomst kunt concluderen.",
      "I turn your question into an analysis with the Samen Analyseren functions, show the choices I make, and explain what you can and cannot conclude."
    );
    document.getElementById("q").placeholder = t(
      "Bijvoorbeeld: is de lucht in het weekend beter dan doordeweeks?",
      "For example: is the air better at the weekend than on weekdays?"
    );
    document.getElementById("submit").textContent = t("Analyseer", "Analyse");
    document.getElementById("q").setAttribute("aria-label", t("Je vraag", "Your question"));
    document.getElementById("try").textContent = t("Probeer:", "Try:");
    renderExamples();
    document.getElementById("foot").innerHTML = `${esc(t(
      "Alle cijfers zijn nepdata voor 6 fictieve sensoren in Haarlem en één fictief referentiestation",
      "All figures are mock data for 6 fictional sensors in Haarlem and one fictional reference station"
    ))} (<span id="data-range"></span>). ${esc(t(
      "Niet gebruiken voor conclusies over echte luchtkwaliteit.",
      "Do not use them to draw conclusions about real air quality."
    ))}`;
    document.getElementById("data-range").textContent = `${A.longDate(M.period.start)} – ${A.longDate(M.period.end)}`;
  }

  document.querySelectorAll(".lang-toggle button").forEach((b) => {
    b.addEventListener("click", () => {
      if (b.dataset.lang === I.lang) return;
      I.set(b.dataset.lang);
    });
  });

  I.onChange(() => {
    applyChrome();
    if (!state.question) return;
    const translated = I.exampleIn(state.question, I.lang);
    if (translated) {
      state.question = translated;
      document.getElementById("q").value = translated;
    }
    run();
  });

  document.getElementById("more").addEventListener("click", () => {
    state.allExamples = !state.allExamples;
    renderExamples();
  });

  document.getElementById("ask").addEventListener("submit", (e) => {
    e.preventDefault();
    ask(document.getElementById("q").value);
  });

  applyChrome();
  checkCoverage();
  const initial = new URLSearchParams(window.location.search).get("q");
  if (initial) ask(initial);
})();
