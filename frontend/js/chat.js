(function () {
  "use strict";

  const I = window.I18N;
  const t = (nl, en) => I.t(nl, en);

  const state = { history: [], loading: false };

  function apiBase() {
    const param = new URLSearchParams(window.location.search).get("api");
    return (param || window.HL_API_URL || "http://localhost:8000").replace(/\/+$/, "");
  }

  async function checkCoverage() {
    const badge = document.getElementById("badge");
    try {
      const res = await fetch(`${apiBase()}/coverage`, { signal: AbortSignal.timeout(1500) });
      if (res.ok && badge) {
        badge.textContent = "Live REST API · localhost:8000";
        badge.style.background = "#e9f6ef";
        badge.style.color = "#258758";
        badge.style.borderColor = "#b7e1cd";
      }
    } catch (_) {}
  }

  function esc(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function appendUserMessage(text) {
    const thread = document.getElementById("chat-thread");
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg--user";
    div.innerHTML = `<div class="chat-bubble">${esc(text)}</div>`;
    thread.appendChild(div);
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function appendAssistantMessage(data) {
    const thread = document.getElementById("chat-thread");
    const div = document.createElement("div");
    div.className = "chat-msg chat-msg--ai";

    const answer = data.answer || t("(geen antwoord ontvangen)", "(no answer received)");
    const suggestions = Array.isArray(data.suggestions) ? data.suggestions : [];
    const interpretation = Array.isArray(data.interpretation) ? data.interpretation : [];
    const llm = data.llm;

    let suggestionsHtml = "";
    if (suggestions.length) {
      suggestionsHtml = `<div class="chat-suggestions">${suggestions
        .map((s) => `<button type="button" class="chip chat-suggestion" data-q="${esc(s)}">${esc(s)}</button>`)
        .join("")}</div>`;
    }

    let detailsHtml = "";
    if (interpretation.length) {
      const calls = interpretation
        .map(
          (c) =>
            `<li><b>${esc(c.tool)}</b>${c.reproduce ? ` → <code>${esc(c.reproduce)}</code>` : ""}${c.error ? ` <span class="chat-pill bad">${esc(c.error)}</span>` : ""}</li>`
        )
        .join("");
      detailsHtml = `<details class="chat-details"><summary>${esc(t("API-aanroepen bekijken", "View API calls"))}</summary><ul>${calls}</ul></details>`;
    }

    const llmBadge = llm
      ? `<span class="chat-pill ok">${esc(llm)}</span>`
      : "";

    div.innerHTML = `
      <div class="chat-bubble">
        <div class="chat-answer">${esc(answer)}</div>
        ${detailsHtml}
        ${llmBadge}
      </div>
      ${suggestionsHtml}`;

    thread.appendChild(div);
    div.querySelectorAll(".chat-suggestion").forEach((btn) =>
      btn.addEventListener("click", () => sendMessage(btn.dataset.q))
    );
    div.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  let typingEl = null;

  function showTyping() {
    const thread = document.getElementById("chat-thread");
    typingEl = document.createElement("div");
    typingEl.className = "chat-msg chat-msg--ai";
    typingEl.innerHTML =
      `<div class="chat-bubble chat-typing"><span></span><span></span><span></span></div>`;
    thread.appendChild(typingEl);
    typingEl.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function hideTyping() {
    if (typingEl) { typingEl.remove(); typingEl = null; }
  }

  async function sendMessage(text) {
    text = text.trim();
    if (!text || state.loading) return;

    const emptyEl = document.getElementById("chat-empty");
    if (emptyEl) emptyEl.style.display = "none";

    state.loading = true;
    document.getElementById("chat-submit").disabled = true;
    document.getElementById("chat-input").value = "";

    appendUserMessage(text);
    showTyping();

    try {
      const res = await fetch(`${apiBase()}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: state.history }),
        signal: AbortSignal.timeout(60000),
      });
      hideTyping();
      if (!res.ok) {
        appendAssistantMessage({
          answer: t(
            `Er is iets misgegaan (HTTP ${res.status}). Probeer het opnieuw.`,
            `Something went wrong (HTTP ${res.status}). Please try again.`
          ),
        });
      } else {
        const data = await res.json();
        if (data.history) state.history = data.history;
        appendAssistantMessage(data);
      }
    } catch (err) {
      hideTyping();
      const msg =
        err.name === "TimeoutError"
          ? t(
              "Geen antwoord van de server (time-out). Is de backend actief?",
              "No response from server (timeout). Is the backend running?"
            )
          : t(
              "Verbindingsfout. Is de backend actief op localhost:8000?",
              "Connection error. Is the backend running on localhost:8000?"
            );
      appendAssistantMessage({ answer: msg });
    } finally {
      state.loading = false;
      document.getElementById("chat-submit").disabled = false;
      document.getElementById("chat-input").focus();
    }
  }

  function renderExamples() {
    const chips = document.getElementById("example-chips");
    if (!chips) return;
    chips.innerHTML = I.examples
      .slice(0, 5)
      .map((ex) => {
        const q = t(ex.nl, ex.en);
        return `<button type="button" class="chip" data-q="${esc(q)}">${esc(q)}</button>`;
      })
      .join("");
    chips.querySelectorAll("[data-q]").forEach((b) =>
      b.addEventListener("click", () => sendMessage(b.dataset.q))
    );
  }

  function applyChrome() {
    document.title = t(
      "Stel een vraag · Hollandse Luchten",
      "Ask a question · Hollandse Luchten"
    );
    const labels = {
      "nav-address": ["Mijn adres", "My address"],
      "nav-ask": ["Stel een vraag", "Ask a question"],
      "side-tools": ["Luchtkwaliteit", "Air quality"],
      "side-address": ["Mijn adres", "My address"],
      "side-ask": ["Stel een vraag", "Ask a question"],
      "chat-title": ["Stel je vraag over de luchtkwaliteit", "Ask your question about air quality"],
      "chat-lead": [
        "Stel een vraag in gewone taal en ik analyseer de luchtkwaliteitsdata voor je.",
        "Ask a question in plain language and I will analyse the air quality data for you.",
      ],
      "chat-new": ["Nieuw gesprek", "New conversation"],
    };
    Object.entries(labels).forEach(([id, [nl, en]]) => {
      const el = document.getElementById(id);
      if (el) el.textContent = t(nl, en);
    });
    document.getElementById("chat-submit").textContent = t("Verstuur", "Send");
    document.getElementById("chat-input").placeholder = t(
      "Typ je vraag hier…",
      "Type your question here…"
    );
    document.getElementById("chat-input").setAttribute(
      "aria-label",
      t("Je vraag", "Your question")
    );
    document.getElementById("example-label").textContent = t(
      "Probeer een van deze vragen:",
      "Try one of these questions:"
    );
    renderExamples();
  }

  document.querySelectorAll(".lang-toggle button").forEach((b) =>
    b.addEventListener("click", () => {
      if (b.dataset.lang !== I.lang) I.set(b.dataset.lang);
    })
  );

  I.onChange(() => applyChrome());

  document.getElementById("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(document.getElementById("chat-input").value);
  });

  document.getElementById("chat-new").addEventListener("click", () => {
    state.history = [];
    document.getElementById("chat-thread").innerHTML = "";
    const emptyEl = document.getElementById("chat-empty");
    if (emptyEl) emptyEl.style.display = "";
    renderExamples();
    document.getElementById("chat-input").focus();
  });

  applyChrome();
  checkCoverage();

  const initial = new URLSearchParams(window.location.search).get("q");
  if (initial) sendMessage(initial);
})();
