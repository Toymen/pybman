import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);

if (!inputPath || !outputPath) {
  console.error("Usage: node merge_detail_sheets.mjs <input.xlsx> <output.xlsx>");
  process.exit(2);
}

const MERGED_SHEET = "Merged Details";

function text(value) {
  return String(value ?? "").trim();
}

function table(sheet) {
  const values = sheet.getUsedRange().values;
  const headers = values[0].map((value) => text(value));
  const rows = values.slice(1).map((row) => {
    const item = {};
    headers.forEach((header, index) => {
      item[header] = row[index] ?? null;
    });
    return item;
  });
  return { headers, rows };
}

function byPureId(rows) {
  return new Map(rows.map((row) => [text(row["PuRe-ID"]), row]));
}

function applyHeaderStyle(range) {
  range.format.fill = { color: "#D9EAF7" };
  range.format.font = { color: "#102A43", bold: true };
  range.format.wrapText = true;
  range.format.borders = { preset: "outside", style: "thin", color: "#AAB7C4" };
}

function applyBodyStyle(range) {
  range.format.wrapText = true;
  range.format.borders = {
    insideHorizontal: { style: "thin", color: "#E2E8F0" },
    top: { style: "thin", color: "#CBD5E1" },
    bottom: { style: "thin", color: "#CBD5E1" },
  };
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const publications = table(workbook.worksheets.getItem("Publikationen"));
const publisher = table(workbook.worksheets.getItem("Forschungsdaten laut Verlag"));
const provider = table(workbook.worksheets.getItem("Provider-Recherche"));

const publisherById = byPureId(publisher.rows);
const providerById = byPureId(provider.rows);

const publicationHeaders = publications.headers;
const mergedHeaders = [
  ...publicationHeaders,
  "Verlag: Forschungsdaten?",
  "Verlag: Datenlink(s)",
  "Verlag: Fundstelle / Nachweis",
  "Verlag: Abruf-Hinweis",
  "Provider: Forschungsdaten?",
  "Provider",
  "Provider: Dataset-PIDs",
  "Provider: Dataset-Titel",
  "Provider: Datenlinks",
  "Provider: Nachweis",
  "Provider: Fehler",
  "Google Dataset Search",
  "Kombinierter Befund",
  "Kombinierte Datenlinks",
  "Merge-Kommentar",
];

const mergedRows = publications.rows.map((pub) => {
  const id = text(pub["PuRe-ID"]);
  const pubPage = publisherById.get(id) ?? {};
  const prov = providerById.get(id) ?? {};
  return [
    ...publicationHeaders.map((header) => pub[header] ?? null),
    pubPage["Forschungsdaten laut Verlagsseite"] ?? null,
    pubPage["Datenlink(s) laut Verlagsseite"] ?? null,
    pubPage["Fundstelle / Nachweis"] ?? null,
    pubPage["Abruf-Hinweis"] ?? null,
    prov["Provider-Forschungsdaten?"] ?? null,
    prov["Provider"] ?? null,
    prov["Dataset-PIDs"] ?? null,
    prov["Dataset-Titel"] ?? null,
    prov["Provider-Datenlinks"] ?? null,
    prov["Provider-Nachweis"] ?? null,
    prov["Provider-Fehler"] ?? null,
    prov["Google Dataset Search"] ?? null,
    prov["Kombinierter Befund"] ?? null,
    prov["Kombinierte Datenlinks"] ?? null,
    prov["Kommentar"] ?? null,
  ];
});

const sheet = workbook.worksheets.getOrAdd(MERGED_SHEET);
const used = sheet.getUsedRange();
if (used) used.clear({ applyTo: "all" });
sheet.showGridLines = false;

sheet.getRangeByIndexes(0, 0, 1, mergedHeaders.length).values = [mergedHeaders];
sheet.getRangeByIndexes(1, 0, mergedRows.length, mergedHeaders.length).values = mergedRows;
applyHeaderStyle(sheet.getRangeByIndexes(0, 0, 1, mergedHeaders.length));
applyBodyStyle(sheet.getRangeByIndexes(1, 0, mergedRows.length, mergedHeaders.length));

sheet.freezePanes.freezeRows(1);
sheet.getRange("A1:AD1").format.rowHeight = 44;
sheet.getRangeByIndexes(1, 0, mergedRows.length, mergedHeaders.length).format.rowHeight = 34;
sheet.getRange("A:A").format.columnWidth = 15;
sheet.getRange("B:B").format.columnWidth = 48;
sheet.getRange("C:C").format.columnWidth = 36;
sheet.getRange("D:E").format.columnWidth = 13;
sheet.getRange("F:H").format.columnWidth = 24;
sheet.getRange("I:J").format.columnWidth = 14;
sheet.getRange("K:L").format.columnWidth = 38;
sheet.getRange("M:O").format.columnWidth = 22;
sheet.getRange("P:AD").format.columnWidth = 34;
sheet.getRange("K:L").format.wrapText = false;
sheet.getRange("Q:R").format.wrapText = false;
sheet.getRange("X:AC").format.wrapText = false;

const overview = workbook.worksheets.getItem("Übersicht");
overview.getRange("A26:B28").clear({ applyTo: "all" });
overview.getRange("A26:B28").values = [
  ["Merge-Status", ""],
  ["Zusammengeführte Blätter", "Publikationen; Forschungsdaten laut Verlag; Provider-Recherche"],
  ["Merge-Detailblatt", MERGED_SHEET],
];
overview.getRange("A26:B26").format.fill = { color: "#D9EAF7" };
overview.getRange("A26:B26").format.font = { color: "#102A43", bold: true };
overview.getRange("A26:B28").format.wrapText = true;

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
