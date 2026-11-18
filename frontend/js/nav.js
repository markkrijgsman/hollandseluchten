// Shared LuchtZorg AppBar & Modal <dialog> Navigation Drawer.
// AppBar holds ONLY brand + 2 primary mode tabs (Check my spot / Ask a question) + Hamburger button.
// All secondary pages (About, Hollandse Luchten, Other apps, Presentation, Contact) + Language toggle live strictly inside the Hamburger Drawer.
(function () {
  "use strict";

  const logoSvg = (size) => `<svg width="${size}" height="${size}" viewBox="0 0 36 36" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M5 13H19.5A3.5 3.5 0 1 0 16 9.5" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M3 18H28.5A3.5 3.5 0 1 0 25 14.5" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M7 23H22A3.5 3.5 0 1 1 18.5 26.5" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;

  function activeKey() {
    const p = window.location.pathname.replace(/\/index\.html$/, "/");
    if (p.startsWith("/gesprek")) return "ask";
    if (p.startsWith("/over")) return "about";
    if (p.startsWith("/hollandse-luchten")) return "hl";
    if (p.startsWith("/tools")) return "tools";
    if (p.startsWith("/contact")) return "contact";
    if (p.endsWith("presentation.html")) return "presentation";
    return "address";
  }

  function buildHeaderAndDrawer() {
    const header = document.querySelector("header.topbar");
    if (!header) return;
    const cur = activeKey();
    const curAttr = (k) => (cur === k ? ' aria-current="page"' : "");
    const curCls = (k) => (cur === k ? ' class="on" aria-current="page"' : "");

    header.innerHTML = `
      <a class="logo" href="/" aria-label="LuchtZorg">
        <span class="logo-mark" aria-hidden="true">${logoSvg(30)}</span>
        <span class="logo-titles">
          <span class="logo-text" translate="no">LuchtZorg</span>
          <span class="logo-sub" data-lz-i18n="brandSub"></span>
        </span>
      </a>

      <nav class="topnav" aria-label="Primary">
        <a href="/"${curCls("address")}>
          <svg class="tab-ic" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7Z"/><circle cx="12" cy="9" r="2.5"/></svg>
          <span data-lz-i18n="navAddress"></span>
        </a>
        <a href="/gesprek/"${curCls("ask")}>
          <svg class="tab-ic" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          <span data-lz-i18n="navAsk"></span>
        </a>
      </nav>

      <div class="top-actions">
        <button
          type="button"
          class="menu-btn"
          id="drawer-open"
          aria-label="Menu"
          aria-expanded="false"
          aria-controls="lz-drawer"
        >
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
            <path d="M4 7h16M4 12h16M4 17h16"/>
          </svg>
        </button>
      </div>
    `;

    let drawer = document.getElementById("lz-drawer");
    if (drawer) drawer.remove();
    drawer = document.createElement("dialog");
    drawer.className = "lz-drawer";
    drawer.id = "lz-drawer";
    drawer.setAttribute("aria-label", "LuchtZorg menu");
    drawer.innerHTML = `
      <div class="lz-drawer-scroller">
        <div class="lz-drawer-sheet">
          <div class="drawer-top-row">
            <div class="menu-brand-row">
              <span class="menu-brand-icon" aria-hidden="true">${logoSvg(30)}</span>
              <div>
                <strong translate="no">LuchtZorg</strong>
                <span class="menu-brand-tag" data-lz-i18n="brandSub"></span>
              </div>
            </div>
            <button type="button" class="drawer-close-btn" id="drawer-close" aria-label="Close menu" autofocus>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18"/>
              </svg>
            </button>
          </div>

          <div class="menu-brand-box">
            <span class="menu-proto-pill" data-lz-i18n="protoBadge"></span>
            <p class="menu-brand-desc" data-lz-i18n="menuDesc"></p>
            <p class="menu-proto-note" data-lz-i18n="menuDisclaimer"></p>
          </div>

          <div class="menu-section-label" data-lz-i18n="secApp"></div>
          <nav class="menu-links" aria-label="Primary">
            <a href="/"${curAttr("address")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7Z"/><circle cx="12" cy="9" r="2.5"/></svg>
              <span data-lz-i18n="navAddress"></span>
            </a>
            <a href="/gesprek/"${curAttr("ask")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
              <span data-lz-i18n="navAsk"></span>
            </a>
          </nav>

          <hr />

          <div class="menu-section-label" data-lz-i18n="secMore"></div>
          <nav class="menu-links" aria-label="Information">
            <a href="/over/"${curAttr("about")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>
              <span data-lz-i18n="navAbout"></span>
            </a>
            <a href="/hollandse-luchten/"${curAttr("hl")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"/></svg>
              <span data-lz-i18n="navHl"></span>
            </a>
            <a href="/tools/"${curAttr("tools")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>
              <span data-lz-i18n="navTools"></span>
            </a>
            <a href="/presentation.html"${curAttr("presentation")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg>
              <span data-lz-i18n="navPresentation"></span>
            </a>
            <a href="/contact/"${curAttr("contact")}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>
              <span data-lz-i18n="navContact"></span>
            </a>
          </nav>

          <div class="menu-lang-row">
            <span class="menu-section-label" data-lz-i18n="secLang"></span>
            <div class="lang-toggle menu-lang-toggle" role="group" aria-label="Language" translate="no">
              <button type="button" data-lang="nl" aria-label="Nederlands">NL · Nederlands</button>
              <button type="button" data-lang="en" aria-label="English">EN · English</button>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(drawer);

    const openBtn = document.getElementById("drawer-open");
    const closeBtn = document.getElementById("drawer-close");
    const scroller = drawer.querySelector(".lz-drawer-scroller");
    const sheet = drawer.querySelector(".lz-drawer-sheet");
    let hasOpened = false;

    async function openDrawer() {
      hasOpened = false;
      drawer.showModal();
      if (!CSS.supports("scroll-initial-target", "nearest")) {
        scroller.scrollTo({ left: 0, behavior: "instant" });
        await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
      }
      if (!CSS.supports("animation-timeline: scroll()")) {
        drawer.style.setProperty("--drawer-backdrop", "1");
      }
      scroller.scrollTo({ left: scroller.scrollWidth, behavior: "auto" });
      openBtn.setAttribute("aria-expanded", "true");
    }

    function closeDrawer() {
      if (!drawer.open) return;
      if (!hasOpened) {
        drawer.close();
        openBtn.setAttribute("aria-expanded", "false");
        return;
      }
      scroller.scrollTo({ left: 0, behavior: "auto" });
    }

    if (!CSS.supports("animation-timeline: scroll()")) {
      scroller.addEventListener("scroll", () => {
        const w = sheet.offsetWidth || 1;
        const ratio = Math.max(0, Math.min(1, scroller.scrollLeft / w));
        drawer.style.setProperty("--drawer-backdrop", String(ratio));
      });
    }

    const visibleThreshold = 1 / Math.max(window.innerWidth, 320);
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[entries.length - 1];
        if (!entry) return;
        if (entry.intersectionRatio >= 0.2) {
          hasOpened = true;
          openBtn.setAttribute("aria-expanded", "true");
        } else if (hasOpened && entry.intersectionRatio < visibleThreshold) {
          hasOpened = false;
          if (drawer.open) drawer.close();
          openBtn.setAttribute("aria-expanded", "false");
        }
      },
      { root: drawer, threshold: [0, visibleThreshold, 0.2, 1] }
    );
    observer.observe(sheet);

    openBtn.addEventListener("click", openDrawer);
    closeBtn.addEventListener("click", closeDrawer);
    drawer.addEventListener("click", (e) => {
      if (!sheet.contains(e.target)) closeDrawer();
    });
    drawer.addEventListener("cancel", (e) => {
      if (e.cancelable && hasOpened) {
        e.preventDefault();
        closeDrawer();
      } else {
        openBtn.setAttribute("aria-expanded", "false");
      }
    });

    drawer.querySelectorAll(".lang-toggle button").forEach((b) =>
      b.addEventListener("click", () => {
        if (window.I18N && b.dataset.lang !== window.I18N.lang) {
          window.I18N.set(b.dataset.lang);
        }
      })
    );

    if (new URLSearchParams(window.location.search).get("menu") === "1") {
      requestAnimationFrame(() => openDrawer());
    }

    let foot = document.querySelector("footer.foot");
    if (!foot) {
      foot = document.createElement("footer");
      foot.className = "foot muted small";
      document.body.appendChild(foot);
    }
    foot.removeAttribute("data-nl");
    foot.removeAttribute("data-en");
    foot.innerHTML = `
      <div class="app-disclaimer" role="note">
        <strong data-lz-i18n="discTitle"></strong>
        <span data-lz-i18n="discBody"></span>
      </div>
    `;
  }

  const STRINGS = {
    brandSub: ["Voor mensen die om hun lucht geven", "For people who care for their air"],
    protoBadge: ["Hackathon-prototype", "Hackathon prototype"],
    menuDesc: [
      "Lokale fijnstofinzichten (PM2.5) in begrijpelijke taal, gebouwd op open burgersensoren van Hollandse Luchten, Luchtmeetnet en de Samen Analyseren R-tools van het RIVM.",
      "Local PM2.5 insights in plain language, built on open Hollandse Luchten citizen sensors, Luchtmeetnet, and RIVM’s Samen Analyseren R tools.",
    ],
    menuDisclaimer: [
      "Indicatieve metingen · geen medisch advies of wettelijke toetsing.",
      "Indicative data · not medical advice or statutory compliance.",
    ],
    discTitle: [
      "Disclaimer (Hackathon-prototype): ",
      "Disclaimer (Hackathon prototype): ",
    ],
    discBody: [
      "LuchtZorg is een experimenteel open-source prototype uit de Hollandse Luchten Hackathon. Burgersensoren bieden waardevol lokaal inzicht naast officiële Luchtmeetnet-stations, maar kennen een hogere meetonzekerheid. Alle uitkomsten zijn indicatief en vormen geen medisch advies of formele wettelijke beoordeling.",
      "LuchtZorg is an experimental open-source prototype created at the Hollandse Luchten Hackathon. Citizen sensors provide valuable local context alongside official Luchtmeetnet stations, but carry higher measurement uncertainty. All results are indicative and do not constitute medical advice or statutory legal assessment.",
    ],
    secApp: ["Ontdek jouw lucht", "Explore your air"],
    secMore: ["Over & Ecosysteem", "About & Ecosystem"],
    secLang: ["Taal / Language", "Language / Taal"],
    navAddress: ["Check mijn plek", "Check my spot"],
    navAsk: ["Stel een vraag", "Ask a question"],
    navAbout: ["Over LuchtZorg", "About LuchtZorg"],
    navHl: ["Over Hollandse Luchten", "About Hollandse Luchten"],
    navTools: ["Andere lucht-apps & tools", "Other air-quality apps"],
    navPresentation: ["Presentatie (Pitch Deck)", "Presentation (Pitch Deck)"],
    navContact: ["Contact", "Contact us"],
  };

  function translateNav() {
    if (!window.I18N) return;
    const t = (nl, en) => window.I18N.t(nl, en);
    document.querySelectorAll("[data-lz-i18n]").forEach((el) => {
      const pair = STRINGS[el.dataset.lzI18n];
      if (pair) el.textContent = t(pair[0], pair[1]);
    });
    document.querySelectorAll("[data-nl][data-en]").forEach((el) => {
      el.textContent = window.I18N.lang === "en" ? el.dataset.en : el.dataset.nl;
    });
    const pageTitleEl = document.querySelector("[data-title-nl][data-title-en]");
    if (pageTitleEl) {
      document.title = window.I18N.lang === "en" ? pageTitleEl.dataset.titleEn : pageTitleEl.dataset.titleNl;
    }
  }

  buildHeaderAndDrawer();
  translateNav();
  if (window.I18N) {
    window.I18N.sync();
    window.I18N.onChange(() => translateNav());
  }
})();
