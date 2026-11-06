"use strict";
const csrf = document.querySelector('meta[name="csrf-token"]').content;

async function api(path, method = "GET", body) {
  const response = await fetch(`/api${path}`, {
    method, credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 204) return null;
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(Array.isArray(detail) ? detail.map(x => x.msg).join(". ") : detail || "Request failed");
  }
  return payload;
}

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

const authForm = document.querySelector("#auth-form");
if (authForm) authForm.addEventListener("submit", async event => {
  event.preventDefault();
  const button = authForm.querySelector("button");
  button.disabled = true;
  const message = document.querySelector("#auth-message");
  message.textContent = "";
  try {
    const fields = new FormData(authForm);
    await api(`/auth/${authForm.dataset.action}`, "POST", {
      email: fields.get("email").trim(), password: fields.get("password"),
    });
    window.location.assign("/settings");
  } catch (error) { message.textContent = error.message; }
  finally { button.disabled = false; }
});

const form = document.querySelector("#destination-form");
if (form) {
  const type = form.querySelector("#type");
  type.addEventListener("change", () => {
    const slack = type.value === "slack";
    document.querySelector("#email-fields").hidden = slack;
    document.querySelector("#slack-fields").hidden = !slack;
    form.elements.email_address.disabled = slack;
    form.elements.email_address.required = !slack;
    form.elements.webhook_url.disabled = !slack;
    form.elements.webhook_url.required = slack;
  });

  async function loadDestinations() {
    const list = document.querySelector("#destination-list");
    const destinations = await api("/destinations");
    list.replaceChildren();
    if (!destinations.length) list.append(node("p", "No destinations yet. Add your first channel.", "muted"));
    for (const destination of destinations) {
      const row = node("div", undefined, "destination");
      const info = node("div");
      info.append(node("strong", destination.type === "email" ? destination.email_address : "Slack webhook"));
      info.append(node("small", `${destination.enabled ? "Enabled" : "Paused"}${destination.type === "slack" ? " · URL hidden" : ""}`));
      const toggle = node("button", destination.enabled ? "Pause" : "Enable", "secondary");
      toggle.setAttribute("aria-label", `${destination.enabled ? "Pause" : "Enable"} ${destination.type} destination ${destination.id}`);
      const test = node("button", "Send test", "secondary");
      test.setAttribute("aria-label", `Send test to ${destination.type} destination ${destination.id}`);
      test.addEventListener("click", async () => {
        test.disabled = true;
        const message = document.querySelector("#destination-message");
        message.textContent = "Sending test…";
        message.dataset.state = "pending";
        try {
          const result = await api(`/destinations/${destination.id}/test`, "POST");
          message.textContent = result.message;
          message.dataset.state = "success";
        } catch (error) { message.textContent = error.message; message.dataset.state = "error"; }
        finally { test.disabled = false; }
      });
      toggle.addEventListener("click", async () => {
        toggle.disabled = true;
        const message = document.querySelector("#destination-message");
        message.textContent = "";
        try {
          await api(`/destinations/${destination.id}`, "PATCH", { enabled: !destination.enabled });
          await loadDestinations();
        } catch (error) { message.textContent = error.message; toggle.disabled = false; }
      });
      const actions = node("div", undefined, "destination-actions");
      actions.append(test, toggle);
      row.append(info, actions);
      list.append(row);
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    const message = document.querySelector("#add-message");
    button.disabled = true;
    message.textContent = "";
    try {
      const body = { type: type.value };
      if (type.value === "email") body.email_address = form.elements.email_address.value.trim();
      else body.webhook_url = form.elements.webhook_url.value.trim();
      await api("/destinations", "POST", body);
      form.elements.email_address.value = "";
      form.elements.webhook_url.value = "";
      await loadDestinations();
    } catch (error) { message.textContent = error.message; }
    finally { button.disabled = false; }
  });

  document.querySelector("#logout").addEventListener("click", async () => {
    try { await api("/auth/logout", "POST"); window.location.assign("/login"); }
    catch (error) { document.querySelector("#destination-message").textContent = error.message; }
  });

  let historyOffset = 0;
  async function loadHistory() {
    const button = document.querySelector("#history-more");
    button.disabled = true;
    try {
      const deliveries = await api(`/deliveries?limit=50&offset=${historyOffset}`);
      const list = document.querySelector("#delivery-list");
      for (const delivery of deliveries) {
        const row = node("tr");
        for (const value of [delivery.headline, delivery.destination_type, delivery.status,
          delivery.attempts, new Date(delivery.created_at).toLocaleString()]) row.append(node("td", value));
        if (delivery.error) row.children[2].append(node("small", delivery.error));
        list.append(row);
      }
      historyOffset += deliveries.length;
      document.querySelector("#history-message").textContent = historyOffset ? "" : "No notifications yet.";
      button.hidden = deliveries.length < 50;
    } catch (error) { document.querySelector("#history-message").textContent = error.message; }
    finally { button.disabled = false; }
  }
  document.querySelector("#history-more").addEventListener("click", loadHistory);
  loadDestinations().catch(error => { document.querySelector("#destination-message").textContent = error.message; });
  loadHistory();
}

// Admin actions (select / drop): POST with the CSRF header, then reload to show the new state.
for (const actionForm of document.querySelectorAll("form[data-admin-action]")) {
  actionForm.addEventListener("submit", async event => {
    event.preventDefault();
    const button = actionForm.querySelector("button");
    button.disabled = true;
    const message = document.querySelector("#admin-message");
    try {
      const response = await fetch(actionForm.action, {
        method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf },
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "Request failed");
      window.location.reload();
    } catch (error) {
      if (message) message.textContent = error.message;
      button.disabled = false;
    }
  });
}
