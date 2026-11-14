// Tweetalige teksten. Nederlands is de standaard; t(nl, en) kiest op het moment van tonen.
(function () {
  "use strict";

  // Voorbeeldvragen die de backend kan beantwoorden: een plek (of adres) met een datum of periode.
  // Tools: pm25 (dag), pm25_timeseries, pm25_compare (WHO/EU), pm25_weekday, pm25_trend, pm25_events.
  const EXAMPLES = [
    { nl: "Hoe was de luchtkwaliteit in Haarlem op 2025-05-01?", en: "How was the air quality in Haarlem on 2025-05-01?" },
    { nl: "Hoe verhield de lucht in Amsterdam in 2025 zich tot de WHO-richtlijn?", en: "How did the air in Amsterdam in 2025 compare with the WHO guideline?" },
    { nl: "Is de lucht in Utrecht in 2025 beter of slechter geworden?", en: "Did the air in Utrecht get better or worse in 2025?" },
    { nl: "Is de lucht in Rotterdam in het weekend schoner dan doordeweeks (2025)?", en: "Is the air in Rotterdam cleaner at weekends than on weekdays (2025)?" },
    { nl: "Op welke dagen in mei 2025 was het fijnstof in Eindhoven boven 15 µg/m³?", en: "On which days in May 2025 was particulate matter in Eindhoven above 15 µg/m³?" },
  ];

  const I18N = {
    lang: "nl",
    listeners: [],
    examples: EXAMPLES,
    t(nl, en) {
      return this.lang === "en" ? en : nl;
    },
    refName() {
      return this.t("Referentiestation Haarlem (mock)", "Haarlem reference station (mock)");
    },
    onChange(fn) {
      this.listeners.push(fn);
    },
    set(lang) {
      this.lang = lang === "en" ? "en" : "nl";
      document.documentElement.lang = this.lang;
      document.querySelectorAll(".lang-toggle button").forEach((b) => b.classList.toggle("on", b.dataset.lang === this.lang));
      this.listeners.forEach((fn) => fn());
    },
  };

  window.I18N = I18N;
})();
