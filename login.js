const authForm = document.querySelector("#authForm");
const authEmail = document.querySelector("#authEmail");
const authPassword = document.querySelector("#authPassword");
const authStatus = document.querySelector("#authStatus");
const registerButton = document.querySelector("#registerButton");
const logoutButton = document.querySelector("#logoutButton");

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

function setAuthState(user) {
  if (user) {
    authStatus.textContent = `Signed in as ${user.email}.`;
    authEmail.value = user.email;
    authPassword.value = "";
    logoutButton.hidden = false;
    return;
  }

  logoutButton.hidden = true;
  authStatus.textContent = "Sign in to save preferences to the database.";
}

async function loadAccount() {
  try {
    const payload = await apiFetch("/api/auth/me");
    setAuthState(payload.authenticated ? payload.user : null);
  } catch {
    authStatus.textContent = "Backend is offline. Start server.py to log in.";
  }
}

async function submitAuth(action) {
  const email = authEmail.value.trim();
  const password = authPassword.value;

  try {
    const payload = await apiFetch(`/api/auth/${action}`, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setAuthState(payload.user);
  } catch (error) {
    authStatus.textContent = error.message;
  }
}

authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  submitAuth("login");
});

registerButton.addEventListener("click", () => {
  submitAuth("register");
});

logoutButton.addEventListener("click", async () => {
  try {
    await apiFetch("/api/auth/logout", { method: "POST" });
  } catch {
    // UI still resets if the backend disappears after page load.
  }

  setAuthState(null);
});

loadAccount();
