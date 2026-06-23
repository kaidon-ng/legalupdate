const form = document.querySelector("#preferencesForm");
const sourceCount = document.querySelector("#sourceCount");
const profilePreview = document.querySelector("#profilePreview");
const stylePreview = document.querySelector("#stylePreview");
const resetButton = document.querySelector("#resetButton");

const storageKey = "law-digest-preferences";
const digestFilterStorageKey = "law-digest-source-filters";
const digestTopicFilterStorageKey = "law-digest-topic-filters";
const digestSourceMap = {
  elitigation: "singapore",
  "bailii-uksc": "bailii_uksc",
  "bailii-ewhc-commercial": "bailii_comm",
  "bailii-ewhc-admiralty": "bailii_admlty",
};
const defaultState = {
  readerType: "regular",
  sources: ["elitigation", "bailii-uksc", "bailii-ewhc-commercial", "bailii-ewhc-admiralty"],
  topics: ["criminal", "family", "employment", "contract", "data-protection", "shipping"],
};

let currentUser = null;
let apiAvailable = true;

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || "Request failed.");
  }

  return payload;
}

function getFormState() {
  const data = new FormData(form);

  return {
    readerType: data.get("readerType") || "regular",
    sources: data.getAll("source"),
    topics: data.getAll("topic"),
  };
}

function setCheckboxGroup(name, selectedValues) {
  form.querySelectorAll(`input[name="${name}"]`).forEach((input) => {
    input.checked = selectedValues.includes(input.value);
  });
}

function applyState(state) {
  const readerInput = form.querySelector(
    `input[name="readerType"][value="${state.readerType}"]`,
  );

  if (readerInput) {
    readerInput.checked = true;
  }

  setCheckboxGroup("source", state.sources || []);
  setCheckboxGroup("topic", state.topics || []);
  updatePreview();
}

function updatePreview() {
  const state = getFormState();
  const isLawyer = state.readerType === "lawyer";

  profilePreview.textContent = isLawyer ? "Lawyer" : "Regular reader";
  stylePreview.textContent = isLawyer ? "Legal analysis" : "Plain English";
  sourceCount.textContent = String(state.sources.length);
}

function saveLocalState(state = getFormState()) {
  const digestSources = state.sources
    .map((source) => digestSourceMap[source])
    .filter(Boolean);

  localStorage.setItem(storageKey, JSON.stringify(state));
  localStorage.setItem(digestFilterStorageKey, JSON.stringify(digestSources));
  localStorage.setItem(digestTopicFilterStorageKey, JSON.stringify(state.topics));
}

function loadLocalState() {
  const savedState = localStorage.getItem(storageKey);

  if (!savedState) {
    applyState(defaultState);
    return;
  }

  try {
    applyState(JSON.parse(savedState));
  } catch {
    localStorage.removeItem(storageKey);
    applyState(defaultState);
  }
}

async function loadRemotePreferences() {
  const preferences = await apiFetch("/api/preferences");
  applyState(preferences);
  saveLocalState(preferences);
}

async function saveRemotePreferences() {
  if (!currentUser) {
    return;
  }

  const state = getFormState();
  const saved = await apiFetch("/api/preferences", {
    method: "PUT",
    body: JSON.stringify(state),
  });
  applyState(saved);
  saveLocalState(saved);
}

async function loadAccount() {
  try {
    const payload = await apiFetch("/api/auth/me");
    apiAvailable = true;

    if (payload.authenticated) {
      currentUser = payload.user;
      await loadRemotePreferences();
    } else {
      currentUser = null;
      loadLocalState();
    }
  } catch {
    apiAvailable = false;
    currentUser = null;
    loadLocalState();
  }
}

form.addEventListener("input", () => {
  updatePreview();
  saveLocalState();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveLocalState();

  if (apiAvailable && currentUser) {
    try {
      await saveRemotePreferences();
    } catch {
      // Local preferences still update immediately for static demos.
    }
  }
});

resetButton.addEventListener("click", async () => {
  localStorage.removeItem(storageKey);
  localStorage.removeItem(digestFilterStorageKey);
  localStorage.removeItem(digestTopicFilterStorageKey);
  applyState(defaultState);
  saveLocalState(defaultState);

  if (apiAvailable && currentUser) {
    try {
      await saveRemotePreferences();
    } catch {
      // Local fallback remains usable.
    }
  }
});

loadAccount();
