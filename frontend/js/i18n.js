// Bilingual NL/EN state. Auto-detects browser language (persisted in localStorage) so English browsers
// render clean native English instead of invoking browser auto-translate (which turns Dutch 'EN' into 'AND').
(function () {
  "use strict";

  const EXAMPLES = [
    { nl: "Hoe was de luchtkwaliteit in Haarlem op 2025-05-01?", en: "How was the air quality in Haarlem on 2025-05-01?" },
    { nl: "Hoe verhield het fijnstof rond de Zaanse Schans in 2025 zich tot de WHO-richtlijn?", en: "How did PM2.5 around Zaanse Schans in 2025 compare with the WHO guideline?" },
    { nl: "Is de lucht in Zaandam in 2025 beter of slechter geworden?", en: "Did the air in Zaandam get better or worse in 2025?" },
    { nl: "Is de lucht in Amsterdam in het weekend schoner dan doordeweeks (2025)?", en: "Is the air in Amsterdam cleaner on weekends than on weekdays (2025)?" },
    { nl: "Op welke dagen in mei 2025 was het fijnstof in IJmuiden boven 15 µg/m³?", en: "On which days in May 2025 was PM2.5 in IJmuiden above 15 µg/m³?" },
  ];

  function detectLang() {
    const param = new URLSearchParams(window.location.search).get("lang");
    if (param === "nl" || param === "en") return param;
    try {
      const saved = window.localStorage.getItem("lz_lang");
      if (saved === "nl" || saved === "en") return saved;
    } catch (_) {}
    const nav = (navigator.language || navigator.userLanguage || "nl").toLowerCase();
    return nav.startsWith("nl") ? "nl" : "en";
  }

  function syncButtons(lang) {
    document.documentElement.lang = lang;
    document.querySelectorAll(".lang-toggle button").forEach((b) => {
      const active = b.dataset.lang === lang;
      b.classList.toggle("on", active);
      b.setAttribute("aria-pressed", String(active));
    });
  }

  const initialLang = detectLang();

  const I18N = {
    lang: initialLang,
    listeners: [],
    examples: EXAMPLES,
    t(nl, en) {
      return this.lang === "en" ? en : nl;
    },
    refName() {
      return this.t("Referentiestation Haarlem", "Haarlem reference station");
    },
    onChange(fn) {
      this.listeners.push(fn);
    },
    set(lang) {
      this.lang = lang === "en" ? "en" : "nl";
      try {
        window.localStorage.setItem("lz_lang", this.lang);
      } catch (_) {}
      syncButtons(this.lang);
      this.listeners.forEach((fn) => fn());
    },
    sync() {
      syncButtons(this.lang);
    },
  };

  syncButtons(initialLang);
  window.I18N = I18N;
})();
