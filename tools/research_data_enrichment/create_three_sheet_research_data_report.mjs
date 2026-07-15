import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const [publicationsPath, auditPath, outputPath] = process.argv.slice(2);

if (!publicationsPath || !auditPath || !outputPath) {
  console.error(
    "Usage: node create_three_sheet_research_data_report.mjs <publications.json> <audit.json> <output.xlsx>",
  );
  process.exit(2);
}

const publications = JSON.parse(await fs.readFile(publicationsPath, "utf8"));
const audit = JSON.parse(await fs.readFile(auditPath, "utf8"));
const auditById = new Map(audit.rows.map((row) => [row.pure_id, row]));
const reportDate = audit.generated_at.slice(0, 10);

function text(value) {
  return String(value ?? "").trim();
}

function colName(index) {
  let result = "";
  let value = index + 1;
  while (value > 0) {
    const remainder = (value - 1) % 26;
    result = String.fromCharCode(65 + remainder) + result;
    value = Math.floor((value - 1) / 26);
  }
  return result;
}

function headerStyle(range, color = "#17324D") {
  range.format.fill = { color };
  range.format.font = { color: "#FFFFFF", bold: true };
  range.format.wrapText = true;
  range.format.verticalAlignment = "center";
  range.format.borders = { preset: "outside", style: "thin", color: "#718096" };
}

function bodyStyle(range) {
  range.format.wrapText = true;
  range.format.verticalAlignment = "top";
  range.format.borders = {
    insideHorizontal: { style: "thin", color: "#E2E8F0" },
    bottom: { style: "thin", color: "#CBD5E1" },
  };
}

function accessSummary(links) {
  const statuses = [...new Set(links.map((link) => link.link_audit.access_status))];
  if (!statuses.length) return "kein verifizierter Datenlink";
  return statuses.join("; ");
}

function rejectedSummary(entry) {
  const reasons = [...new Set(entry.rejected_candidates.map((item) => item.decision_reason))];
  return reasons.slice(0, 3).join("; ") || "Keine verifizierten Forschungsdaten gefunden";
}

const records = publications.publications.rows.map((row) => {
  const audited = auditById.get(text(row["PuRe-ID"]));
  const links = audited?.accepted_links ?? [];
  return { row, audited, links };
});
const maxLinks = Math.max(1, ...records.map((record) => record.links.length));

const baseHeaders = [
  "PuRe-ID",
  "Titel",
  "Autor:innen",
  "Genre",
  "Datum",
  "Journal / Quelle",
  "DOI",
  "Status",
  "Forschungsgruppen-Tags",
  "Prime / Target Journal",
  "Forschungsdaten?",
  "Anzahl verifizierte Links",
  "Zugangsstatus gesamt",
];
const linkHeaders = [];
for (let index = 0; index < maxLinks; index += 1) {
  linkHeaders.push(
    `Forschungsdaten-Link ${index + 1}`,
    `Quelle Link ${index + 1}`,
    `Zugang Link ${index + 1}`,
    `Prüfung Link ${index + 1}`,
  );
}
const detailHeaders = [
  ...baseHeaders,
  ...linkHeaders,
  "Geprüft am",
  "Prüfverfahren",
  "Nachweis / Entscheidung",
];
const detailRows = records.map(({ row, audited, links }) => {
  const linkCells = [];
  for (let index = 0; index < maxLinks; index += 1) {
    const link = links[index];
    linkCells.push(
      link?.link_audit.final_url || link?.canonical_url || "",
      link?.source || "",
      link?.link_audit.access_status || "",
      link ? `HTTP ${link.link_audit.http_status ?? "-"}; ${link.link_audit.verification_method}` : "",
    );
  }
  return [
    text(row["PuRe-ID"]),
    text(row.Titel),
    text(row["Autor:innen"]),
    text(row.Genre),
    text(row.Datum),
    text(row["Journal / Quelle"] || row.Verlag),
    text(row.DOI),
    text(row.Status),
    text(row["Forschungsgruppen-Tags"]),
    text(row["Prime / Target Journal"]),
    audited?.research_data ?? "nein",
    links.length,
    accessSummary(links),
    ...linkCells,
    reportDate,
    [...new Set(links.map((link) => link.link_audit.verification_method))].join("; ") || "HTTP + Playwright-Audit",
    links.length
      ? [...new Set(links.map((link) => link.decision_reason))].join("; ")
      : rejectedSummary(audited),
  ];
});

const workbook = Workbook.create();
const overview = workbook.worksheets.add("Übersicht");
const details = workbook.worksheets.add("Forschungsdaten");
const groups = workbook.worksheets.add("Forschungsgruppen");

for (const sheet of [overview, details, groups]) sheet.showGridLines = false;

// Übersicht
overview.getRange("A1").values = [["Forschungsdatenbericht 2024 bis heute"]];
overview.getRange("A1:F1").format.font = { color: "#17324D", bold: true, size: 18 };
overview.getRange("A1:F1").format.borders = { bottom: { style: "thick", color: "#17324D" } };
overview.getRange("A1:F1").format.rowHeight = 34;
overview.getRange("A3:B3").values = [["Berichtsstatus", "Wert"]];
headerStyle(overview.getRange("A3:B3"));
overview.getRange("A3:B3").format.font = { color: "#17324D", bold: true };
overview.getRange("A4:B9").values = [
  ["Publikationen gesamt", records.length],
  ["Forschungsdaten: ja", audit.metrics.publications_yes],
  ["Forschungsdaten: nein", audit.metrics.publications_no],
  ["Abdeckungsquote", audit.metrics.publications_yes / records.length],
  ["Verifizierte Forschungsdatenlinks", audit.metrics.accepted_links],
  ["Prüfdatum", reportDate],
];
overview.getRange("B7").format.numberFormat = "0.0%";
overview.getRange("A4:A9").format.font = { bold: true, color: "#17324D" };
overview.getRange("A4:B9").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };

overview.getRange("A11").values = [["Berichtsfähige Definition"]];
headerStyle(overview.getRange("A11:F11"), "#245B45");
overview.getRange("A11:F11").format.font = { color: "#245B45", bold: true };
overview.getRange("A12:F14").values = [
  ["Eingeschlossen", audit.definition.included, "", "", "", ""],
  ["Ausgeschlossen", audit.definition.excluded, "", "", "", ""],
  ["Zugangsregel", audit.definition.access_rule, "", "", "", ""],
];
for (const row of [12, 13, 14]) overview.getRange(`B${row}:F${row}`).merge();
overview.getRange("A12:A14").format.font = { bold: true, color: "#17324D" };
overview.getRange("A12:F14").format.wrapText = true;
overview.getRange("A12:F14").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };
overview.getRange("A12:F14").format.rowHeight = 48;

overview.getRange("A16").values = [["Qualitätssicherung"]];
headerStyle(overview.getRange("A16:F16"), "#245B45");
overview.getRange("A16:F16").format.font = { color: "#245B45", bold: true };
overview.getRange("A17:F21").values = [
  ["Quellenpriorität", "1. gepflegte PuRe-Links; 2. explizite Data-Availability-Aussagen; 3. Repositorien mit engem Titel-/Autor:innenbezug und geprüften Datendateien", "", "", "", ""],
  ["Linkprüfung", "HTTP-Status und Weiterleitungsziel; Playwright als Fallback bei JavaScript oder Zugriffsschutz", "", "", "", ""],
  ["Dateiprüfung", "OSF- und GitHub-Dateibäume rekursiv über die jeweilige API; Zenodo-Archive werden bis auf Dateiebene geprüft", "", "", "", ""],
  ["Konservative Regel", "Nicht erreichbare, mehrdeutige oder nur indirekt referenzierte Treffer werden als nein geführt", "", "", "", ""],
  ["Zugang", "Paywall, Login, Embargo, Zustimmungspflichten und View-only-Zugänge erscheinen je Link in einer eigenen Spalte", "", "", "", ""],
];
for (let row = 17; row <= 21; row += 1) overview.getRange(`B${row}:F${row}`).merge();
overview.getRange("A17:A21").format.font = { bold: true, color: "#17324D" };
overview.getRange("A17:F21").format.wrapText = true;
overview.getRange("A17:F21").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };
overview.getRange("A17:F21").format.rowHeight = 42;

overview.getRange("A23:B23").values = [["Farblegende", "Bedeutung"]];
headerStyle(overview.getRange("A23:B23"));
overview.getRange("A23:B23").format.font = { color: "#17324D", bold: true };
overview.getRange("A24:B27").values = [
  ["Grün", "Forschungsdaten ja / Link offen"],
  ["Rot", "Forschungsdaten nein"],
  ["Gelb", "Paywall, Login, Embargo, Zustimmungspflicht oder View-only-Zugang"],
  ["Blau", "Verifizierter Forschungsdatenlink"],
];
overview.getRange("A24").format.fill = { color: "#C6EFCE" };
overview.getRange("A25").format.fill = { color: "#F4CCCC" };
overview.getRange("A26").format.fill = { color: "#FFE699" };
overview.getRange("A27").format.fill = { color: "#D9EAF7" };
overview.getRange("A24:B27").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };
overview.getRange("A:A").format.columnWidth = 24;
overview.getRange("B:F").format.columnWidth = 24;
overview.freezePanes.freezeRows(1);

// Publikationsdetails
details.getRangeByIndexes(0, 0, 1, detailHeaders.length).values = [detailHeaders];
details.getRangeByIndexes(1, 0, detailRows.length, detailHeaders.length).values = detailRows;
const detailLastCol = colName(detailHeaders.length - 1);
const detailLastRow = detailRows.length + 1;
headerStyle(details.getRange(`A1:${detailLastCol}1`));
bodyStyle(details.getRange(`A2:${detailLastCol}${detailLastRow}`));
details.tables.add(`A1:${detailLastCol}${detailLastRow}`, true).name = "tbl_Forschungsdaten";
details.freezePanes.freezeRows(1);
details.freezePanes.freezeColumns(2);
details.getRange("A:A").format.columnWidth = 15;
details.getRange("B:B").format.columnWidth = 46;
details.getRange("C:C").format.columnWidth = 32;
details.getRange("D:E").format.columnWidth = 12;
details.getRange("F:F").format.columnWidth = 28;
details.getRange("G:G").format.columnWidth = 23;
details.getRange("H:J").format.columnWidth = 17;
details.getRange("K:M").format.columnWidth = 18;
details.getRange(`${detailLastCol}:${detailLastCol}`).format.columnWidth = 52;
details.getRange(`${colName(detailHeaders.length - 3)}:${colName(detailHeaders.length - 2)}`).format.columnWidth = 18;
details.getRange(`A1:${detailLastCol}1`).format.rowHeight = 44;
details.getRange(`A2:${detailLastCol}${detailLastRow}`).format.rowHeight = 34;

const yesCol = detailHeaders.indexOf("Forschungsdaten?");
for (let rowIndex = 0; rowIndex < detailRows.length; rowIndex += 1) {
  const excelRow = rowIndex + 2;
  const yes = detailRows[rowIndex][yesCol] === "ja";
  const fill = yes
    ? rowIndex % 2 === 0 ? "#F6FFED" : "#EFFBE8"
    : rowIndex % 2 === 0 ? "#FFF8F0" : "#FFF2E5";
  details.getRange(`A${excelRow}:${detailLastCol}${excelRow}`).format.fill = { color: fill };
  const yesCell = details.getRangeByIndexes(rowIndex + 1, yesCol, 1, 1);
  yesCell.format.fill = { color: yes ? "#C6EFCE" : "#F4CCCC" };
  yesCell.format.font = { color: yes ? "#006100" : "#9C0006", bold: true };
}
for (let index = 0; index < maxLinks; index += 1) {
  const linkCol = baseHeaders.length + index * 4;
  const sourceCol = linkCol + 1;
  const accessCol = linkCol + 2;
  const checkCol = linkCol + 3;
  details.getRangeByIndexes(0, linkCol, detailRows.length + 1, 1).format.columnWidth = 38;
  details.getRangeByIndexes(1, linkCol, detailRows.length, 1).format.font = { color: "#1155CC" };
  details.getRangeByIndexes(1, linkCol, detailRows.length, 1).format.fill = { color: "#EAF4FF" };
  details.getRangeByIndexes(0, sourceCol, detailRows.length + 1, 1).format.columnWidth = 15;
  details.getRangeByIndexes(0, accessCol, detailRows.length + 1, 1).format.columnWidth = 23;
  details.getRangeByIndexes(0, checkCol, detailRows.length + 1, 1).format.columnWidth = 19;
  for (let rowIndex = 0; rowIndex < detailRows.length; rowIndex += 1) {
    const status = text(detailRows[rowIndex][accessCol]);
    if (status && status !== "offen") {
      details.getRangeByIndexes(rowIndex + 1, accessCol, 1, 1).format.fill = { color: "#FFE699" };
      details.getRangeByIndexes(rowIndex + 1, accessCol, 1, 1).format.font = { color: "#7F6000", bold: true };
    }
  }
}
details.getRangeByIndexes(1, detailHeaders.indexOf("Anzahl verifizierte Links"), detailRows.length, 1).format.numberFormat = "0";

// Forschungsgruppen
const ADMIN_TAGS = new Set(["dp", "externdp", "preprint"]);
const TAG_ALIASES = new Map([
  ["gloeckner", "glöckner"],
  ["glöckner", "glöckner"],
  ["gueth", "güth"],
  ["güth", "güth"],
]);
function researchGroupTags(value) {
  return [...new Set(
    text(value)
      .split(";")
      .map((item) => item.trim())
      .filter(Boolean)
      .filter((item) => !ADMIN_TAGS.has(item.toLowerCase()))
      .map((item) => TAG_ALIASES.get(item.toLowerCase()) ?? item.toLowerCase()),
  )];
}
const tags = new Set();
for (const record of records) {
  for (const tag of researchGroupTags(record.row["Forschungsgruppen-Tags"])) {
    tags.add(tag);
  }
}
const sortedTags = [...tags].sort((a, b) => a.localeCompare(b, "de"));
const groupHeaders = [
  "Forschungsgruppe",
  "Publikationen",
  "Forschungsdaten ja",
  "Forschungsdaten nein",
  "Quote Forschungsdaten",
  "Target-Journal-Publikationen",
  "Davon Forschungsdaten ja",
];
const groupRows = sortedTags.map((tag) => {
  const matching = records.filter((record) =>
    researchGroupTags(record.row["Forschungsgruppen-Tags"]).includes(tag),
  );
  const yes = matching.filter((record) => record.audited?.research_data === "ja").length;
  const target = matching.filter((record) => text(record.row["Prime / Target Journal"]).toLowerCase() === "yes").length;
  const targetYes = matching.filter(
    (record) => text(record.row["Prime / Target Journal"]).toLowerCase() === "yes" && record.audited?.research_data === "ja",
  ).length;
  return [tag, matching.length, yes, matching.length - yes, matching.length ? yes / matching.length : 0, target, targetYes];
});
groups.getRange("A1").values = [["Forschungsdaten nach Forschungsgruppen"]];
groups.getRange("A1:G1").format.font = { color: "#17324D", bold: true, size: 16 };
groups.getRange("A1:G1").format.borders = { bottom: { style: "thick", color: "#17324D" } };
groups.getRange("A3:G3").values = [groupHeaders];
groups.getRangeByIndexes(3, 0, groupRows.length, groupHeaders.length).values = groupRows;
headerStyle(groups.getRange("A3:G3"));
bodyStyle(groups.getRange(`A4:G${groupRows.length + 3}`));
groups.tables.add(`A3:G${groupRows.length + 3}`, true).name = "tbl_Forschungsgruppen";
groups.getRange(`E4:E${groupRows.length + 3}`).format.numberFormat = "0.0%";
groups.getRange(`A4:G${groupRows.length + 3}`).format.rowHeight = 28;
for (let index = 0; index < groupRows.length; index += 1) {
  groups.getRange(`A${index + 4}:G${index + 4}`).format.fill = {
    color: index % 2 === 0 ? "#F7FAFC" : "#EDF2F7",
  };
  groups.getRange(`C${index + 4}`).format.fill = { color: "#C6EFCE" };
  groups.getRange(`D${index + 4}`).format.fill = { color: "#FCE8E6" };
}
groups.getRange("A:A").format.columnWidth = 24;
groups.getRange("B:G").format.columnWidth = 22;
const notesRow = groupRows.length + 6;
groups.getRange(`A${notesRow}:G${notesRow + 1}`).values = [
  ["Hinweis", "Publikationen mit mehreren Forschungsgruppen-Tags werden jeder genannten Gruppe zugerechnet.", "", "", "", "", ""],
  ["Definition", "Die Ja/Nein-Entscheidung entspricht vollständig dem konsolidierten Blatt Forschungsdaten.", "", "", "", "", ""],
];
groups.getRange(`B${notesRow}:G${notesRow}`).merge();
groups.getRange(`B${notesRow + 1}:G${notesRow + 1}`).merge();
groups.getRange(`A${notesRow}:A${notesRow + 1}`).format.font = { bold: true, color: "#17324D" };
groups.getRange(`A${notesRow}:G${notesRow + 1}`).format.wrapText = true;
groups.freezePanes.freezeRows(3);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log(errors.ndjson);
await fs.mkdir(path.dirname(outputPath), { recursive: true });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ sheets: 3, rows: records.length, yes: audit.metrics.publications_yes, maxLinks, outputPath }));
