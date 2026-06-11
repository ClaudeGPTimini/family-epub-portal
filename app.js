const config = window.PORTAL_CONFIG || {};
const requestFormUrl = config.requestFormUrl || "#";

const latestBooksEl = document.querySelector("#latestBooks");
const statusRowsEl = document.querySelector("#statusRows");
const searchInput = document.querySelector("#statusSearch");
const latestCountEl = document.querySelector("#latestCount");
const openCountEl = document.querySelector("#openCount");
const uploadedCountEl = document.querySelector("#uploadedCount");

let allStatuses = [];

for (const id of ["heroRequestLink", "navRequestLink", "latestRequestLink"]) {
  const link = document.querySelector(`#${id}`);
  if (link) {
    link.href = requestFormUrl;
  }
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Could not load ${path}`);
  }
  return response.json();
}

function statusLabel(status) {
  return String(status || "received")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function renderLatest(books) {
  latestCountEl.textContent = books.length;
  if (!books.length) {
    latestBooksEl.innerHTML = '<div class="empty-state">No books have been added yet.</div>';
    return;
  }

  latestBooksEl.innerHTML = books
    .map(
      (book) => `
        <article class="book-card">
          <h3>${escapeHtml(book.title)}</h3>
          <p>${escapeHtml(book.author || "Unknown author")}</p>
          <div class="book-meta">
            <i data-lucide="calendar-check" aria-hidden="true"></i>
            <span>${escapeHtml(book.added || "Recently added")}</span>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderStatuses(statuses) {
  allStatuses = statuses;
  const uploadedCount = statuses.filter((item) => item.status === "uploaded").length;
  const openCount = statuses.filter(
    (item) => !["uploaded", "found"].includes(item.status),
  ).length;
  uploadedCountEl.textContent = uploadedCount;
  openCountEl.textContent = openCount;
  renderFilteredStatuses(searchInput.value);
}

function renderFilteredStatuses(query) {
  const needle = query.trim().toLowerCase();
  const visible = allStatuses.filter((item) => {
    const haystack = `${item.request_id} ${item.title} ${item.author}`.toLowerCase();
    return haystack.includes(needle);
  });

  if (!visible.length) {
    statusRowsEl.innerHTML = `
      <tr>
        <td colspan="4">No matching requests.</td>
      </tr>
    `;
    return;
  }

  statusRowsEl.innerHTML = visible
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.request_id || "")}</td>
          <td>
            <span class="book-title">${escapeHtml(item.title || "")}</span>
            <span class="book-author">${escapeHtml(item.author || "Unknown author")}</span>
          </td>
          <td>
            <span class="status-pill status-${escapeHtml(item.status || "received")}">
              ${escapeHtml(statusLabel(item.status))}
            </span>
          </td>
          <td>${escapeHtml(item.last_checked || "")}</td>
        </tr>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

searchInput.addEventListener("input", () => renderFilteredStatuses(searchInput.value));

Promise.all([
  loadJson("data/latest-books.json"),
  loadJson("data/request-status.json"),
])
  .then(([books, statuses]) => {
    renderLatest(books);
    renderStatuses(statuses);
    if (window.lucide) {
      window.lucide.createIcons();
    }
  })
  .catch(() => {
    latestBooksEl.innerHTML =
      '<div class="empty-state">Library data could not be loaded.</div>';
    statusRowsEl.innerHTML = `
      <tr>
        <td colspan="4">Request status could not be loaded.</td>
      </tr>
    `;
  });
