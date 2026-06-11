const SETTINGS = {
  // Paste the ID from your private Google Sheet URL.
  SPREADSHEET_ID: "PASTE_PRIVATE_SHEET_ID_HERE",

  // Change this to a long random phrase. The local worker uses it to read requests.
  WORKER_SECRET: "CHANGE_ME_TO_A_LONG_RANDOM_SECRET",

  REQUESTS_SHEET: "Requests",
};

const HEADERS = [
  "request_id",
  "timestamp",
  "title",
  "author",
  "isbn",
  "notes",
  "source_url",
  "status",
  "last_checked",
  "drive_link",
  "worker_notes",
];

function doPost(e) {
  const sheet = getRequestsSheet_();
  const params = e.parameter || {};
  const title = clean_(params.title);

  if (clean_(params.website)) {
    return json_({ ok: true, ignored: true });
  }

  if (!title) {
    return json_({ ok: false, error: "Title is required." });
  }

  ensureHeaders_(sheet);
  const requestId = makeRequestId_();
  sheet.appendRow([
    requestId,
    new Date().toISOString(),
    title,
    clean_(params.author),
    clean_(params.isbn),
    clean_(params.notes),
    clean_(params.source_url),
    "received",
    "",
    "",
    "",
  ]);

  return json_({ ok: true, request_id: requestId });
}

function doGet(e) {
  const params = e.parameter || {};
  if (params.secret !== SETTINGS.WORKER_SECRET) {
    return json_({ ok: false, error: "Unauthorized." });
  }

  const action = params.action || "requests";
  if (action === "requests") {
    return json_({ ok: true, requests: getRequests_() });
  }

  return json_({ ok: false, error: "Unknown action." });
}

function getRequests_() {
  const sheet = getRequestsSheet_();
  ensureHeaders_(sheet);
  const values = sheet.getDataRange().getValues();
  const headers = values.shift();
  return values
    .filter(row => row.some(value => String(value).trim() !== ""))
    .map(row => {
      const record = {};
      headers.forEach((header, index) => {
        record[header] = row[index] instanceof Date ? row[index].toISOString() : row[index];
      });
      return record;
    });
}

function getRequestsSheet_() {
  const spreadsheet = SpreadsheetApp.openById(SETTINGS.SPREADSHEET_ID);
  return spreadsheet.getSheetByName(SETTINGS.REQUESTS_SHEET)
    || spreadsheet.insertSheet(SETTINGS.REQUESTS_SHEET);
}

function ensureHeaders_(sheet) {
  const existing = sheet.getRange(1, 1, 1, HEADERS.length).getValues()[0];
  const hasHeaders = existing.some(value => String(value).trim() !== "");
  if (!hasHeaders) {
    sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
    sheet.setFrozenRows(1);
  }
}

function makeRequestId_() {
  const now = new Date();
  const datePart = Utilities.formatDate(now, "UTC", "yyyyMMdd");
  const randomPart = Utilities.getUuid().split("-")[0].toUpperCase();
  return `REQ-${datePart}-${randomPart}`;
}

function clean_(value) {
  return String(value || "").trim();
}

function json_(payload) {
  return ContentService
    .createTextOutput(JSON.stringify(payload))
    .setMimeType(ContentService.MimeType.JSON);
}
