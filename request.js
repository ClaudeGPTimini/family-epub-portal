const form = document.querySelector("#bookRequestForm");
const alertBox = document.querySelector("#requestAlert");
const frame = document.querySelector("#requestFrame");
const endpoint = (window.PORTAL_CONFIG && window.PORTAL_CONFIG.requestEndpoint) || "";
let submitted = false;

function setAlert(message, tone = "info") {
  alertBox.textContent = message;
  alertBox.dataset.tone = tone;
  alertBox.hidden = !message;
}

function submitRequest(event) {
  if (!endpoint) {
    event.preventDefault();
    setAlert("Request intake is not connected yet. Ask the library owner to finish the private backend setup.", "error");
    return;
  }

  const title = String(new FormData(form).get("title") || "").trim();
  if (!title) {
    event.preventDefault();
    setAlert("Add a title before sending.", "error");
    return;
  }

  form.action = endpoint;
  submitted = true;
  setAlert("Sending request...");
}

form.addEventListener("submit", submitRequest);
frame.addEventListener("load", () => {
  if (!submitted) {
    return;
  }
  submitted = false;
  form.reset();
  setAlert("Request sent. It will appear in the queue after the next library sync.", "success");
});

if (!endpoint) {
  setAlert("Private request backend is not connected yet.", "error");
}

if (window.lucide) {
  window.lucide.createIcons();
}
