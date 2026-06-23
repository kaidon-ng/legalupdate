const sourceOrder = ["bailii_uksc", "bailii_comm", "bailii_admlty", "singapore"];
const topicOrder = ["criminal", "family", "employment", "contract", "data-protection", "shipping"];

const sourceMeta = {
  bailii_uksc: {
    label: "UK Supreme Court",
    storageValue: "bailii-uksc",
  },
  bailii_comm: {
    label: "EWHC Commercial Court",
    storageValue: "bailii-ewhc-commercial",
  },
  bailii_admlty: {
    label: "EWHC Admiralty",
    storageValue: "bailii-ewhc-admiralty",
  },
  singapore: {
    label: "Singapore Judiciary",
    storageValue: "elitigation",
  },
};

const topicMeta = {
  criminal: "Criminal",
  family: "Family",
  employment: "Employment",
  contract: "Contract",
  "data-protection": "Data Protection",
  shipping: "Shipping",
};

const sampleData = {
  today_str: "23 June 2026",
  source_warnings: {
    bailii_comm: "",
    singapore: "",
  },
  file_map: {
    "uksc-2026-17": ["summary_pdfs/[2026] UKSC 17 - summary.pdf"],
    "comm-2026-1492": ["summary_pdfs/[2026] EWHC 1492 (Comm) - summary.pdf"],
    "admlty-2026-1211": ["summary_pdfs/[2026] EWHC 1211 (Admlty) - summary.pdf"],
    "sg-2026-sghc-135": ["summary_pdfs/[2026] SGHC 135 - summary.pdf"],
  },
  cases: [
    {
      folder_name: "uksc-2026-17",
      case_name: "Commissioners for His Majesty's Revenue and Customs v HFFX LLP",
      parties: "HMRC; HFFX LLP",
      case_ref: "[2026] UKSC 17",
      date: "17 June 2026",
      court: "UK Supreme Court",
      judgment:
        "The Court considered the tax treatment of partnership arrangements and the legal effect of the relevant statutory scheme.",
      holding:
        "The decision is relevant to tax structuring, partnership disputes, and the limits of contractual form where statutory tax rules apply.",
      source_url: "https://www.bailii.org/uk/cases/UKSC/2026/17.html",
      tags: ["contract"],
    },
    {
      folder_name: "comm-2026-1492",
      case_name: "Petersen Energia Inversora SAU v The Republic of Argentina",
      parties: "Petersen Energia Inversora SAU; The Republic of Argentina",
      case_ref: "[2026] EWHC 1492 (Comm)",
      date: "17 June 2026",
      court: "EWHC Commercial Court",
      judgment:
        "The Commercial Court addressed issues arising from a high-value cross-border commercial dispute.",
      holding:
        "The judgment may matter to parties dealing with sovereign counterparties, enforcement risk, and complex commercial litigation strategy.",
      source_url: "https://www.bailii.org/ew/cases/EWHC/Comm/2026/1492.html",
      tags: ["contract"],
    },
    {
      folder_name: "admlty-2026-1211",
      case_name: 'MS "Solong" Schiffahrtsgesellschaft mbH v Samskip Multimodal BV',
      parties: 'MS "Solong" Schiffahrtsgesellschaft mbH; Samskip Multimodal BV',
      case_ref: "[2026] EWHC 1211 (Admlty)",
      date: "22 May 2026",
      court: "EWHC Admiralty",
      judgment:
        "The Admiralty Court considered claims arising from maritime operations and responsibility between commercial shipping parties.",
      holding:
        "The case is useful for shipping, insurance, and logistics readers tracking how English courts handle maritime disputes.",
      source_url: "https://www.bailii.org/ew/cases/EWHC/Admlty/2026/1211.html",
      tags: ["shipping", "contract"],
    },
    {
      folder_name: "sg-2026-sghc-135",
      case_name: "Management Corporation Strata Title No. 3564 v Edmund Motor Pte. Ltd.",
      parties: "MCST No. 3564; Edmund Motor Pte. Ltd.",
      case_ref: "[2026] SGHC 135",
      date: "22 June 2026",
      court: "Singapore Judiciary",
      judgment:
        "The High Court considered a dispute involving strata management and commercial premises.",
      holding:
        "The judgment may be relevant to management corporations, commercial tenants, and property owners in Singapore.",
      source_url: "https://www.elitigation.sg/gd/s/2026_SGHC_135",
      tags: ["contract"],
    },
  ],
};

const filterStorageKey = "law-digest-source-filters";
const topicFilterStorageKey = "law-digest-topic-filters";
const oldPreferencesKey = "law-digest-preferences";
const preferenceSourceMap = {
  elitigation: "singapore",
  "bailii-uksc": "bailii_uksc",
  "bailii-ewhc-commercial": "bailii_comm",
  "bailii-ewhc-admiralty": "bailii_admlty",
};

const state = {
  cases: [],
  fileMap: {},
  today: "",
  warnings: {},
  enabledSources: new Set(sourceOrder),
  enabledTopics: new Set(topicOrder),
  readerType: "regular",
  currentCaseId: null,
};

const els = {
  topDate: document.querySelector("#topDate"),
  topCaseCount: document.querySelector("#topCaseCount"),
  sourceNav: document.querySelector("#sourceNav"),
  mainContent: document.querySelector("#mainContent"),
  warningSection: document.querySelector("#warningSection"),
  warningList: document.querySelector("#warningList"),
  menuButton: document.querySelector("#menuButton"),
  sidebarBackdrop: document.querySelector("#sidebarBackdrop"),
  overviewLink: document.querySelector("#overviewLink"),
  pdfPanel: document.querySelector("#pdfPanel"),
  pdfBackdrop: document.querySelector("#pdfBackdrop"),
  pdfFrame: document.querySelector("#pdfFrame"),
  pdfTitle: document.querySelector("#pdfTitle"),
  closePdfButton: document.querySelector("#closePdfButton"),
};

function normaliseDigestData(payload) {
  return {
    cases: Array.isArray(payload?.cases) ? payload.cases : [],
    fileMap: payload?.file_map || payload?.fileMap || {},
    today: payload?.today_str || payload?.today || new Date().toLocaleDateString("en-GB"),
    warnings: normaliseWarnings(payload?.source_warnings || payload?.sourceWarnings || {}),
    preferences: payload?.preferences || null,
  };
}

function normaliseWarnings(rawWarnings) {
  if (Array.isArray(rawWarnings)) {
    return rawWarnings.reduce((warnings, item) => {
      const sourceId = item.source_id || item.source || item.id;

      if (sourceId) {
        warnings[sourceId] = item.message || item.warning || item.status || String(item);
      }

      return warnings;
    }, {});
  }

  if (rawWarnings.scrapers && typeof rawWarnings.scrapers === "object") {
    return Object.entries(rawWarnings.scrapers).reduce((warnings, [sourceId, status]) => {
      const scraperStatus = status.status;

      if (scraperStatus && !["ok", "pending"].includes(scraperStatus)) {
        warnings[sourceId] = status.last_error || `Scraper status: ${scraperStatus}`;
      }

      return warnings;
    }, {});
  }

  return rawWarnings || {};
}

function getCaseId(caseItem) {
  const raw = caseItem.folder_name || caseItem.case_ref || caseItem.case_name;
  return String(raw || "case").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function inferSourceId(caseItem) {
  const court = String(caseItem.court || "").toLowerCase();
  const ref = String(caseItem.case_ref || "").toLowerCase();
  const folder = String(caseItem.folder_name || "").toLowerCase();

  if (court.includes("supreme") || ref.includes("uksc") || folder.includes("uksc")) {
    return "bailii_uksc";
  }

  if (court.includes("commercial") || ref.includes("(comm)") || folder.includes("comm")) {
    return "bailii_comm";
  }

  if (court.includes("admiralty") || ref.includes("admlty") || folder.includes("admlty")) {
    return "bailii_admlty";
  }

  return "singapore";
}

function normaliseTags(tags) {
  if (typeof tags === "string") {
    tags = tags.split(/[,;/\n]+/);
  }

  if (!Array.isArray(tags)) {
    return [];
  }

  return tags
    .map((tag) => String(tag).trim().toLowerCase().replaceAll("_", "-"))
    .filter((tag, index, allTags) => topicOrder.includes(tag) && allTags.indexOf(tag) === index);
}

function enrichCases(cases) {
  return cases.map((caseItem, index) => ({
    ...caseItem,
    id: getCaseId(caseItem),
    source_id: caseItem.source_id || inferSourceId(caseItem),
    tags: normaliseTags(caseItem.tags),
    order: index + 1,
  }));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function loadEnabledSources() {
  const saved = localStorage.getItem(filterStorageKey);

  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      return new Set(parsed.filter((sourceId) => sourceOrder.includes(sourceId)));
    } catch {
      localStorage.removeItem(filterStorageKey);
    }
  }

  const oldPreferences = localStorage.getItem(oldPreferencesKey);

  if (oldPreferences) {
    try {
      const parsed = JSON.parse(oldPreferences);
      const enabled = new Set();

      for (const sourceId of sourceOrder) {
        if (parsed.sources?.includes(sourceMeta[sourceId].storageValue)) {
          enabled.add(sourceId);
        }
      }

      return enabled.size > 0 ? enabled : new Set(sourceOrder);
    } catch {
      localStorage.removeItem(oldPreferencesKey);
    }
  }

  return new Set(sourceOrder);
}

function enabledSourcesFromPreferences(preferences) {
  if (!preferences?.sources) {
    return null;
  }

  const selected = preferences.sources
    .map((source) => preferenceSourceMap[source])
    .filter((sourceId) => sourceOrder.includes(sourceId));

  return selected.length > 0 ? new Set(selected) : new Set(sourceOrder);
}

function loadEnabledTopics() {
  const saved = localStorage.getItem(topicFilterStorageKey);

  if (saved) {
    try {
      const parsed = JSON.parse(saved);
      const selected = parsed.filter((topic) => topicOrder.includes(topic));
      return selected.length > 0 ? new Set(selected) : new Set(topicOrder);
    } catch {
      localStorage.removeItem(topicFilterStorageKey);
    }
  }

  const oldPreferences = localStorage.getItem(oldPreferencesKey);

  if (oldPreferences) {
    try {
      const parsed = JSON.parse(oldPreferences);
      const selected = (parsed.topics || []).filter((topic) => topicOrder.includes(topic));
      return selected.length > 0 ? new Set(selected) : new Set(topicOrder);
    } catch {
      localStorage.removeItem(oldPreferencesKey);
    }
  }

  return new Set(topicOrder);
}

function loadReaderType() {
  const oldPreferences = localStorage.getItem(oldPreferencesKey);

  if (oldPreferences) {
    try {
      const parsed = JSON.parse(oldPreferences);
      return parsed.readerType === "lawyer" ? "lawyer" : "regular";
    } catch {
      localStorage.removeItem(oldPreferencesKey);
    }
  }

  return "regular";
}

function enabledTopicsFromPreferences(preferences) {
  if (!preferences?.topics) {
    return null;
  }

  const selected = preferences.topics.filter((topic) => topicOrder.includes(topic));
  return selected.length > 0 ? new Set(selected) : new Set(topicOrder);
}

function saveEnabledSources() {
  localStorage.setItem(filterStorageKey, JSON.stringify([...state.enabledSources]));
}

function caseMatchesFilters(caseItem) {
  if (!state.enabledSources.has(caseItem.source_id)) {
    return false;
  }

  if (state.enabledTopics.size === topicOrder.length) {
    return true;
  }

  return caseItem.tags.some((tag) => state.enabledTopics.has(tag));
}

function filteredCases() {
  return state.cases.filter(caseMatchesFilters);
}

function groupCases(cases) {
  const groups = new Map(sourceOrder.map((sourceId) => [sourceId, []]));

  for (const caseItem of cases) {
    if (!groups.has(caseItem.source_id)) {
      groups.set(caseItem.source_id, []);
    }

    groups.get(caseItem.source_id).push(caseItem);
  }

  return groups;
}

function pdfFilesForCase(caseItem) {
  const files = state.fileMap[caseItem.folder_name] || state.fileMap[caseItem.id] || [];
  return Array.isArray(files) ? files : [files];
}

function normalisePdfFile(file) {
  if (typeof file === "string") {
    const parts = file.split(/[\\/]/);
    return { name: parts[parts.length - 1] || "Summary PDF", url: file };
  }

  return {
    name: file?.name || file?.filename || file?.url || file?.path || "Summary PDF",
    url: file?.url || file?.path || file?.href || "",
  };
}

function warningTextForSource(sourceId) {
  const warning = state.warnings?.[sourceId];

  if (!warning) {
    return "";
  }

  if (typeof warning === "string") {
    return warning;
  }

  return warning.message || warning.status || JSON.stringify(warning);
}

function renderSourceNav() {
  const allCasesBySource = groupCases(state.cases);
  const filteredBySource = groupCases(filteredCases());
  const isCaseRoute = Boolean(state.currentCaseId);

  els.sourceNav.innerHTML = sourceOrder
    .map((sourceId) => {
      const casesForSource = allCasesBySource.get(sourceId) || [];
      const filteredCount = (filteredBySource.get(sourceId) || []).length;
      const checked = state.enabledSources.has(sourceId) ? "checked" : "";
      const citationLinks = isCaseRoute
        ? `<div class="citation-list">${casesForSource
            .map((caseItem) => {
              const active = caseItem.id === state.currentCaseId ? " active" : "";
              return `<a class="citation-link${active}" href="#case/${encodeURIComponent(caseItem.id)}">${escapeHtml(
                caseItem.case_ref || caseItem.case_name,
              )}</a>`;
            })
            .join("")}</div>`
        : "";

      return `
        <section class="source-group">
          <label class="source-row">
            <input type="checkbox" data-source-toggle="${sourceId}" ${checked} />
            <span class="source-title">${sourceMeta[sourceId].label}</span>
            <span class="source-count">${filteredCount}</span>
          </label>
          ${citationLinks}
        </section>
      `;
    })
    .join("");

  els.sourceNav.querySelectorAll("[data-source-toggle]").forEach((input) => {
    input.addEventListener("change", () => {
      const sourceId = input.dataset.sourceToggle;

      if (input.checked) {
        state.enabledSources.add(sourceId);
      } else {
        state.enabledSources.delete(sourceId);
      }

      saveEnabledSources();
      render();
    });
  });
}

function renderWarnings() {
  const warningItems = sourceOrder
    .map((sourceId) => {
      const text = warningTextForSource(sourceId);
      return text ? { sourceId, text } : null;
    })
    .filter(Boolean);

  els.warningSection.hidden = warningItems.length === 0;
  els.warningList.innerHTML = warningItems
    .map(
      (item) =>
        `<div class="warning-item"><strong>${sourceMeta[item.sourceId].label}</strong><br />${escapeHtml(
          item.text,
        )}</div>`,
    )
    .join("");

  return warningItems;
}

function renderTopBar() {
  const count = filteredCases().length;
  els.topDate.textContent = state.today;
  els.topCaseCount.textContent = `${count} ${count === 1 ? "case" : "cases"}`;
}

function caseSummary(caseItem) {
  if (state.readerType === "lawyer") {
    return (
      caseItem.lawyer_summary ||
      caseItem.holding ||
      caseItem.short_summary ||
      caseItem.judgment ||
      "No summary available yet."
    );
  }

  return (
    caseItem.regular_summary ||
    caseItem.short_summary ||
    caseItem.judgment ||
    caseItem.holding ||
    "No summary available yet."
  );
}

function renderTags(caseItem) {
  if (!caseItem.tags.length) {
    return "";
  }

  return `<div class="tag-row">${caseItem.tags
    .map((tag) => `<span class="tag-pill">${escapeHtml(topicMeta[tag] || tag)}</span>`)
    .join("")}</div>`;
}

function renderOverview() {
  state.currentCaseId = null;
  closePdfPanel();
  els.overviewLink.classList.add("active");

  const cases = filteredCases();
  const totalCount = state.cases.length;
  const warnings = renderWarnings();
  const grouped = groupCases(cases);
  let caseNumber = 1;

  const warningMarkup = warnings.length
    ? `<section class="warning-banner">${warnings
        .map(
          (item) =>
            `<div class="warning-item"><strong>${sourceMeta[item.sourceId].label}</strong>: ${escapeHtml(
              item.text,
            )}</div>`,
        )
        .join("")}</section>`
    : "";

  const groupedMarkup = sourceOrder
    .map((sourceId) => {
      const sourceCases = grouped.get(sourceId) || [];

      if (sourceCases.length === 0) {
        return "";
      }

      return `
        <section class="source-section">
          <div class="source-heading">
            <h3>${sourceMeta[sourceId].label}</h3>
            <span>${sourceCases.length} ${sourceCases.length === 1 ? "case" : "cases"}</span>
          </div>
          <div class="case-list">
            ${sourceCases
              .map((caseItem) => {
                const number = caseNumber++;
                return `
                  <article class="case-block">
                    <div class="case-number">${number}</div>
                    <div class="case-body">
                      <h4 class="case-title">${escapeHtml(caseItem.case_name || "Untitled case")}</h4>
                      <div class="meta-line">
                        <strong>${escapeHtml(caseItem.parties || "Parties not stated")}</strong>
                        <span>${escapeHtml(caseItem.case_ref || "No citation")}</span>
                        <span>${escapeHtml(caseItem.date || "")}</span>
                      </div>
                      <p class="summary-text">${escapeHtml(caseSummary(caseItem))}</p>
                      ${renderTags(caseItem)}
                      <div class="link-row">
                        <a class="text-link" href="#case/${encodeURIComponent(caseItem.id)}">View summary</a>
                        ${
                          caseItem.source_url
                            ? `<a class="external-link" href="${escapeHtml(
                                caseItem.source_url,
                              )}" target="_blank" rel="noreferrer">Read full judgment</a>`
                            : ""
                        }
                      </div>
                    </div>
                  </article>
                `;
              })
              .join("")}
          </div>
        </section>
      `;
    })
    .join("");

  els.mainContent.innerHTML = `
    <header class="page-header">
      <h2>Legal Updates - ${escapeHtml(state.today)}</h2>
      <p>${cases.length} of ${totalCount} ${totalCount === 1 ? "case" : "cases"} match the selected sources and topics. These updates are generated from the weekly scrape and filtered in the browser.</p>
    </header>
    ${warningMarkup}
    ${
      groupedMarkup ||
      `<div class="empty-state">No cases match the selected sources and topics. Adjust your preferences on the configuration page.</div>`
    }
  `;
}

function renderCaseDetail(caseId) {
  const caseItem = state.cases.find((item) => item.id === caseId);
  state.currentCaseId = caseId;
  els.overviewLink.classList.remove("active");

  if (!caseItem || !caseMatchesFilters(caseItem)) {
    els.mainContent.innerHTML = `
      <div class="empty-state">
        Case not found in the selected sources and topics. <a class="text-link" href="#overview">Return to overview</a>
      </div>
    `;
    return;
  }

  const pdfFiles = pdfFilesForCase(caseItem).map(normalisePdfFile).filter((file) => file.url);
  const pdfMarkup = pdfFiles.length
    ? pdfFiles
        .map(
          (file) => `
            <button class="pdf-button" type="button" data-pdf-url="${escapeHtml(
              file.url,
            )}" data-pdf-name="${escapeHtml(file.name)}">
              <span>${escapeHtml(file.name)}</span>
              <em>PDF</em>
            </button>
          `,
        )
        .join("")
    : `<p class="summary-text">No generated summary PDFs are available for this case yet.</p>`;

  els.mainContent.innerHTML = `
    <nav class="breadcrumb" aria-label="Breadcrumb">
      <a href="#overview">Overview</a>
      <span>/</span>
      <span>${escapeHtml(caseItem.case_ref || caseItem.case_name)}</span>
    </nav>

    <div class="detail-layout">
      <article class="detail-card">
        <h2 class="detail-title">${escapeHtml(caseItem.case_name || "Untitled case")}</h2>
        <div class="case-ref">${escapeHtml(caseItem.case_ref || "No citation")}</div>

        <div class="metadata-grid">
          <div class="metadata-item">
            <span>Parties</span>
            <strong>${escapeHtml(caseItem.parties || "Not stated")}</strong>
          </div>
          <div class="metadata-item">
            <span>Date</span>
            <strong>${escapeHtml(caseItem.date || "Not stated")}</strong>
          </div>
          <div class="metadata-item">
            <span>Court</span>
            <strong>${escapeHtml(caseItem.court || sourceMeta[caseItem.source_id]?.label || "Not stated")}</strong>
          </div>
        </div>

        <section class="judgment-section">
          ${
            caseItem.tags.length
              ? `<div>
                  <h3>Tags</h3>
                  ${renderTags(caseItem)}
                </div>`
              : ""
          }
          <div>
            <h3>${state.readerType === "lawyer" ? "Legal Summary" : "Plain English Summary"}</h3>
            <p>${escapeHtml(caseSummary(caseItem))}</p>
          </div>
          <div>
            <h3>Holding</h3>
            <p>${escapeHtml(caseItem.holding || "No holding summary available yet.")}</p>
          </div>
        </section>
      </article>

      <section class="detail-card">
        <h3>Generated Summary PDFs</h3>
        <div class="pdf-list">${pdfMarkup}</div>
      </section>

      ${
        caseItem.source_url
          ? `<a class="external-link" href="${escapeHtml(
              caseItem.source_url,
            )}" target="_blank" rel="noreferrer">Read the full judgment on the court website</a>`
          : ""
      }
    </div>
  `;

  els.mainContent.querySelectorAll("[data-pdf-url]").forEach((button) => {
    button.addEventListener("click", () => {
      openPdf(button.dataset.pdfUrl, button.dataset.pdfName);
    });
  });
}

function currentRoute() {
  const hash = window.location.hash || "#overview";

  if (hash.startsWith("#case/")) {
    return {
      type: "case",
      caseId: decodeURIComponent(hash.slice("#case/".length)),
    };
  }

  return { type: "overview" };
}

function openPdf(url, title) {
  if (window.matchMedia("(max-width: 1050px)").matches) {
    window.open(url, "_blank", "noopener,noreferrer");
    return;
  }

  els.pdfTitle.textContent = title || "Summary PDF";
  els.pdfFrame.src = url;
  els.pdfPanel.hidden = false;
  document.body.classList.add("pdf-modal-open");
  els.closePdfButton.focus({ preventScroll: true });
}

function closePdfPanel() {
  els.pdfPanel.hidden = true;
  els.pdfFrame.src = "about:blank";
  document.body.classList.remove("pdf-modal-open");
}

function closeMobileSidebar() {
  document.body.classList.remove("sidebar-open");
  els.sidebarBackdrop.hidden = true;
  els.menuButton.setAttribute("aria-expanded", "false");
}

function render() {
  renderTopBar();
  renderWarnings();

  const route = currentRoute();

  if (route.type === "case") {
    renderCaseDetail(route.caseId);
  } else {
    renderOverview();
  }

  renderSourceNav();
  els.mainContent.focus({ preventScroll: true });
}

function renderLegalDigest(payload) {
  const data = normaliseDigestData(payload);
  state.cases = enrichCases(data.cases);
  state.fileMap = data.fileMap;
  state.today = data.today;
  state.warnings = data.warnings;
  state.enabledSources = enabledSourcesFromPreferences(data.preferences) || loadEnabledSources();
  state.enabledTopics = enabledTopicsFromPreferences(data.preferences) || loadEnabledTopics();
  state.readerType = data.preferences?.readerType === "lawyer" ? "lawyer" : loadReaderType();
  render();
}

async function loadInitialDigest() {
  try {
    const response = await fetch("/api/digest", { credentials: "same-origin" });
    const payload = await response.json().catch(() => ({}));

    if (response.status === 401) {
      renderLegalDigest({
        today_str: new Date().toLocaleDateString("en-GB"),
        source_warnings: {},
        file_map: {},
        cases: [],
      });
      els.mainContent.innerHTML = `
        <div class="empty-state">
          Sign in on the preferences page to view your account-filtered digest.
          <a class="text-link" href="./index.html">Open preferences</a>
        </div>
      `;
      return;
    }

    if (!response.ok) {
      throw new Error(payload.error || "Digest API failed.");
    }

    renderLegalDigest(payload);
  } catch {
    renderLegalDigest(window.LEGAL_DIGEST_DATA || sampleData);
  }
}

els.menuButton.addEventListener("click", () => {
  document.body.classList.add("sidebar-open");
  els.sidebarBackdrop.hidden = false;
  els.menuButton.setAttribute("aria-expanded", "true");
});

els.sidebarBackdrop.addEventListener("click", closeMobileSidebar);

els.closePdfButton.addEventListener("click", closePdfPanel);
els.pdfBackdrop.addEventListener("click", closePdfPanel);

window.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.pdfPanel.hidden) {
    closePdfPanel();
  }
});

window.addEventListener("hashchange", () => {
  closeMobileSidebar();
  render();
});

window.addEventListener("resize", () => {
  if (window.matchMedia("(max-width: 1050px)").matches) {
    closePdfPanel();
  }
});

window.renderLegalDigest = renderLegalDigest;

loadInitialDigest();
