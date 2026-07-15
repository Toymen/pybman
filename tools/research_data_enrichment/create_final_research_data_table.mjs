import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, outputPath] = process.argv.slice(2);

if (!inputPath || !outputPath) {
  console.error("Usage: node create_final_research_data_table.mjs <input.xlsx> <output.xlsx>");
  process.exit(2);
}

const FINAL_SHEET = "Forschungsdaten final";
const URL_RE = /\bhttps?:\/\/[^\s;"'<>)\]]+/gi;

function text(value) {
  return String(value ?? "").trim();
}

function table(sheet) {
  const values = sheet.getUsedRange().values;
  const headers = values[0].map((value) => text(value));
  return values.slice(1).map((row) => {
    const item = {};
    headers.forEach((header, index) => {
      item[header] = row[index] ?? null;
    });
    return item;
  });
}

function cleanUrl(url) {
  return text(url)
    .replace(/&amp;/g, "&")
    .replace(/[.,;:]+$/g, "")
    .replace(/&#xA;?/g, "")
    .trim();
}

function extractUrls(...values) {
  const urls = [];
  for (const value of values) {
    for (const match of text(value).matchAll(URL_RE)) {
      const cleaned = cleanUrl(match[0]);
      if (
        cleaned &&
        !cleaned.includes("datasetsearch.research.google.com") &&
        !urls.some((url) => url.toLowerCase() === cleaned.toLowerCase())
      ) {
        urls.push(cleaned);
      }
    }
  }
  return urls;
}

function isFutureProtocol(row) {
  return /study protocol|protocol for a/i.test(text(row["Titel"]));
}

function sourceList(row) {
  const sources = [];
  if (extractUrls(row["Forschungsdaten-Links"]).length) sources.push("PuRe");
  if (!isFutureProtocol(row) && extractUrls(row["Verlag: Datenlink(s)"]).length) {
    sources.push("Verlagsseite");
  }
  if (extractUrls(row["Provider: Datenlinks"]).length) sources.push("Provider");
  return sources.join("; ");
}

function evidence(row) {
  return [
    text(row["Forschungsdaten-Nachweis"]) && `PuRe: ${text(row["Forschungsdaten-Nachweis"])}`,
    text(row["Verlag: Fundstelle / Nachweis"]) &&
      `Verlag: ${text(row["Verlag: Fundstelle / Nachweis"])}`,
    text(row["Provider: Nachweis"]) && `Provider: ${text(row["Provider: Nachweis"])}`,
    text(row["Merge-Kommentar"]) && `Kommentar: ${text(row["Merge-Kommentar"])}`,
    isFutureProtocol(row) && "Qualitätsregel: Studienprotokoll mit angekündigter künftiger Datenfreigabe wird nicht als verfügbar gezählt",
  ]
    .filter(Boolean)
    .join(" || ");
}

function colName(index) {
  let name = "";
  let n = index + 1;
  while (n > 0) {
    const rem = (n - 1) % 26;
    name = String.fromCharCode(65 + rem) + name;
    n = Math.floor((n - 1) / 26);
  }
  return name;
}

function applyHeaderStyle(range) {
  range.format.fill = { color: "#17324D" };
  range.format.font = { color: "#FFFFFF", bold: true };
  range.format.wrapText = true;
  range.format.borders = { preset: "outside", style: "thin", color: "#718096" };
}

function applyBodyStyle(range) {
  range.format.borders = {
    insideHorizontal: { style: "thin", color: "#E2E8F0" },
    top: { style: "thin", color: "#CBD5E1" },
    bottom: { style: "thin", color: "#CBD5E1" },
  };
  range.format.wrapText = true;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const mergedRows = table(workbook.worksheets.getItem("Merged Details"));

const records = mergedRows.map((row) => {
  const links = extractUrls(
    row["Forschungsdaten-Links"],
    isFutureProtocol(row) ? "" : row["Verlag: Datenlink(s)"],
    row["Provider: Datenlinks"],
  );
  return {
    base: row,
    links,
    available: links.length > 0,
    sources: sourceList(row),
    evidence: evidence(row),
  };
});

const maxLinks = Math.max(1, ...records.map((record) => record.links.length));
const headers = [
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
  "Forschungsdaten verfügbar?",
  "Forschungsdaten-Quelle(n)",
  "Anzahl Links",
  ...Array.from({ length: maxLinks }, (_, index) => `Forschungsdaten-Link ${index + 1}`),
  "Nachweis / Kommentar",
];

const rows = records.map((record) => [
  text(record.base["PuRe-ID"]),
  text(record.base["Titel"]),
  text(record.base["Autor:innen"]),
  text(record.base["Genre"]),
  text(record.base["Datum"]),
  text(record.base["Journal / Quelle"]),
  text(record.base["DOI"]),
  text(record.base["Status"]),
  text(record.base["Forschungsgruppen-Tags"]),
  text(record.base["Prime / Target Journal"]),
  record.available ? "ja" : "nein",
  record.sources,
  record.links.length,
  ...Array.from({ length: maxLinks }, (_, index) => record.links[index] ?? null),
  record.evidence,
]);

const finalSheet = workbook.worksheets.getOrAdd(FINAL_SHEET);
const used = finalSheet.getUsedRange();
if (used) used.clear({ applyTo: "all" });
finalSheet.showGridLines = false;

finalSheet.getRangeByIndexes(0, 0, 1, headers.length).values = [headers];
finalSheet.getRangeByIndexes(1, 0, rows.length, headers.length).values = rows;

const lastCol = colName(headers.length - 1);
const lastRow = rows.length + 1;
const fullRange = `A1:${lastCol}${lastRow}`;
const bodyRange = finalSheet.getRangeByIndexes(1, 0, rows.length, headers.length);
applyHeaderStyle(finalSheet.getRangeByIndexes(0, 0, 1, headers.length));
applyBodyStyle(bodyRange);

finalSheet.tables.deleteAll();
const dataTable = finalSheet.tables.add(fullRange, true);
dataTable.name = "tbl_Forschungsdaten_final";

finalSheet.freezePanes.freezeRows(1);
finalSheet.freezePanes.freezeColumns(2);
finalSheet.getRange("A1:A1").format.columnWidth = 15;
finalSheet.getRange("B:B").format.columnWidth = 46;
finalSheet.getRange("C:C").format.columnWidth = 34;
finalSheet.getRange("D:E").format.columnWidth = 12;
finalSheet.getRange("F:F").format.columnWidth = 28;
finalSheet.getRange("G:G").format.columnWidth = 24;
finalSheet.getRange("H:J").format.columnWidth = 16;
finalSheet.getRange("K:K").format.columnWidth = 18;
finalSheet.getRange("L:L").format.columnWidth = 22;
finalSheet.getRange("M:M").format.columnWidth = 12;

const firstLinkColIndex = headers.indexOf("Forschungsdaten-Link 1");
const lastLinkColIndex = firstLinkColIndex + maxLinks - 1;
const notesColIndex = headers.length - 1;
finalSheet
  .getRangeByIndexes(0, firstLinkColIndex, rows.length + 1, maxLinks)
  .format.columnWidth = 34;
finalSheet.getRangeByIndexes(0, notesColIndex, rows.length + 1, 1).format.columnWidth = 54;
finalSheet.getRangeByIndexes(1, firstLinkColIndex, rows.length, maxLinks).format.wrapText = false;

const availableCol = headers.indexOf("Forschungsdaten verfügbar?");
for (let i = 0; i < rows.length; i += 1) {
  const rowRange = finalSheet.getRangeByIndexes(i + 1, 0, 1, headers.length);
  const availabilityCell = finalSheet.getRangeByIndexes(i + 1, availableCol, 1, 1);
  const countCell = finalSheet.getRangeByIndexes(i + 1, headers.indexOf("Anzahl Links"), 1, 1);
  if (rows[i][availableCol] === "ja") {
    rowRange.format.fill = { color: i % 2 === 0 ? "#F6FFED" : "#EFFBE8" };
    availabilityCell.format.fill = { color: "#C6EFCE" };
    availabilityCell.format.font = { color: "#006100", bold: true };
    countCell.format.fill = { color: "#D9EAF7" };
  } else {
    rowRange.format.fill = { color: i % 2 === 0 ? "#FFF8F0" : "#FFF2E5" };
    availabilityCell.format.fill = { color: "#F4CCCC" };
    availabilityCell.format.font = { color: "#9C0006", bold: true };
  }
}

finalSheet.getRangeByIndexes(0, firstLinkColIndex, rows.length + 1, maxLinks).format.fill = {
  color: "#EAF4FF",
};
finalSheet.getRangeByIndexes(0, firstLinkColIndex, 1, maxLinks).format.fill = {
  color: "#17324D",
};
finalSheet.getRangeByIndexes(0, firstLinkColIndex, 1, maxLinks).format.font = {
  color: "#FFFFFF",
  bold: true,
};
finalSheet.getRangeByIndexes(1, firstLinkColIndex, rows.length, maxLinks).format.font = {
  color: "#1155CC",
};
finalSheet.getRangeByIndexes(0, availableCol, rows.length + 1, 1).format.horizontalAlignment =
  "center";
finalSheet.getRangeByIndexes(0, headers.indexOf("Anzahl Links"), rows.length + 1, 1).format
  .horizontalAlignment = "center";
finalSheet.getRange(`A1:${lastCol}1`).format.rowHeight = 44;
finalSheet.getRangeByIndexes(1, 0, rows.length, headers.length).format.rowHeight = 30;

const overview = workbook.worksheets.getItem("Übersicht");
const availableCount = records.filter((record) => record.available).length;
const targetCount = Math.ceil(records.length * 0.5);
overview.getRange("A30:B38").clear({ applyTo: "all" });
overview.getRange("A30:B38").values = [
  ["Finale Forschungsdaten-Tabelle", ""],
  ["Filterbares Blatt", FINAL_SHEET],
  ["Publikationen mit Forschungsdaten-Link", availableCount],
  ["Publikationen ohne Forschungsdaten-Link", records.filter((record) => !record.available).length],
  ["Abdeckungsquote", availableCount / records.length],
  ["50%-Zielmarke (Publikationen)", targetCount],
  ["Noch fehlend bis 50%", Math.max(0, targetCount - availableCount)],
  ["Maximale Link-Spalten", maxLinks],
  ["Regel", "Nur konkrete, belegte Forschungsdaten-Links; Suchseiten und bloß angekündigte künftige Freigaben zählen nicht"],
];
overview.getRange("A30:B30").format.fill = { color: "#D9EAF7" };
overview.getRange("A30:B30").format.font = { color: "#102A43", bold: true };
overview.getRange("A30:B38").format.wrapText = true;
overview.getRange("B34").format.numberFormat = "0.0%";
overview.getRange("A:B").format.autofitColumns();

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);
console.log(
  JSON.stringify({
    rows: rows.length,
    available: records.filter((record) => record.available).length,
    unavailable: records.filter((record) => !record.available).length,
    maxLinks,
    range: fullRange,
  }),
);

await fs.mkdir(path.dirname(outputPath), { recursive: true });
const exported = await SpreadsheetFile.exportXlsx(workbook);
await exported.save(outputPath);
