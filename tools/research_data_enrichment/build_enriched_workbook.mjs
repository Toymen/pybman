import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [inputPath, publicationsJsonPath, discoveryJsonPath, outputPath] = process.argv.slice(2);

if (!inputPath || !publicationsJsonPath || !discoveryJsonPath || !outputPath) {
  console.error(
    "Usage: node build_enriched_workbook.mjs <input.xlsx> <publications.json> <discovery_results.json> <output.xlsx>",
  );
  process.exit(2);
}

const RESEARCH_SHEET = "Provider-Recherche";
const GROUP_SHEET = "Forschungsgruppen";

function yes(value) {
  return String(value ?? "").trim().toLowerCase() === "yes";
}

function text(value) {
  return String(value ?? "").trim();
}

function splitTags(value) {
  return text(value)
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean);
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function join(values) {
  return unique(values).join("; ");
}

function safeLinksFromHits(hits) {
  return join(
    hits.flatMap((hit) => {
      const links = [];
      if (hit.url) links.push(hit.url);
      if (hit.pid_type === "doi" && hit.pid) links.push(`https://doi.org/${hit.pid}`);
      return links;
    }),
  );
}

function providerNames(hits) {
  return join(hits.map((hit) => hit.provider));
}

function providerTitles(hits) {
  return join(hits.map((hit) => hit.title || hit.pid));
}

function providerPids(hits) {
  return join(hits.map((hit) => hit.pid));
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

function getOrResetSheet(workbook, sheetName) {
  const sheet = workbook.worksheets.getOrAdd(sheetName);
  const used = sheet.getUsedRange();
  if (used) {
    used.clear({ applyTo: "all" });
  }
  sheet.showGridLines = false;
  return sheet;
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const extracted = JSON.parse(await fs.readFile(publicationsJsonPath, "utf8"));
const discovery = JSON.parse(await fs.readFile(discoveryJsonPath, "utf8"));

const publications = extracted.publications.rows;
const publisherById = new Map(
  extracted.publisher.rows.map((row) => [text(row["PuRe-ID"]), row]),
);
const discoveryById = new Map(
  discovery.results.map((row) => [text(row["PuRe-ID"]), row]),
);

const researchHeaders = [
  "PuRe-ID",
  "Titel",
  "Datum",
  "DOI",
  "Forschungsgruppen-Tags",
  "PuRe-Forschungsdaten?",
  "PuRe-Forschungsdaten-Links",
  "Verlagsseite-Forschungsdaten?",
  "Verlagsseite-Links",
  "Provider-Forschungsdaten?",
  "Provider",
  "Dataset-PIDs",
  "Dataset-Titel",
  "Provider-Datenlinks",
  "Provider-Nachweis",
  "Provider-Fehler",
  "Google Dataset Search",
  "Kombinierter Befund",
  "Kombinierte Datenlinks",
  "Kommentar",
];

const researchRows = publications.map((pub) => {
  const itemId = text(pub["PuRe-ID"]);
  const publisher = publisherById.get(itemId) ?? {};
  const result = discoveryById.get(itemId) ?? { hits: [], found: false };
  const hits = result.hits ?? [];
  const pureLinks = text(pub["Forschungsdaten-Links"]);
  const publisherLinks = text(publisher["Datenlink(s) laut Verlagsseite"]);
  const providerLinks = safeLinksFromHits(hits);
  const pureFound = yes(pub["Forschungsdaten verlinkt?"]);
  const publisherReported = yes(publisher["Forschungsdaten laut Verlagsseite"]);
  const providerFound = Boolean(result.found);
  const futureProtocol =
    /study protocol|protocol for a/i.test(text(pub["Titel"])) &&
    publisherReported &&
    !pureFound &&
    !providerFound;
  const publisherFound = publisherReported && !futureProtocol;
  const combinedFound = pureFound || publisherFound || providerFound;
  const comments = [];
  if (!text(pub["DOI"])) {
    comments.push("Keine DOI; automatisierte Recherche per Titel und Autor:innen durchgeführt.");
  }
  if (String(result.status ?? "").startsWith("checked") && !providerFound) {
    comments.push("Keine belegte Dataset-Beziehung in DOI-, Titel- oder Volltextquellen gefunden.");
  }
  if (result.provider_errors) comments.push(`Provider-Hinweis: ${result.provider_errors}`);
  if (result.validation_summary) comments.push(`Quellenvalidierung: ${result.validation_summary}`);
  if (futureProtocol) {
    comments.push("Studienprotokoll: Verlagslink beschreibt eine künftige Datenfreigabe und zählt nicht als aktuell verfügbare Forschungsdaten.");
  }
  return [
    itemId,
    text(pub["Titel"]),
    text(pub["Datum"]),
    text(result.DOI || pub["DOI"]),
    text(pub["Forschungsgruppen-Tags"]),
    pureFound ? "yes" : "no",
    pureLinks,
    futureProtocol ? "planned" : publisherFound ? "yes" : "no",
    publisherLinks,
    providerFound ? "yes" : "no",
    providerNames(hits),
    providerPids(hits),
    providerTitles(hits),
    providerLinks,
    text(result.provider_summary),
    text(result.provider_errors),
    text(result.google_dataset_search),
    combinedFound ? "yes" : "no",
    join([pureLinks, publisherFound ? publisherLinks : "", providerLinks]),
    comments.join(" "),
  ];
});

const researchSheet = getOrResetSheet(workbook, RESEARCH_SHEET);
researchSheet.getRangeByIndexes(0, 0, 1, researchHeaders.length).values = [researchHeaders];
researchSheet.getRangeByIndexes(1, 0, researchRows.length, researchHeaders.length).values = researchRows;
applyHeaderStyle(researchSheet.getRangeByIndexes(0, 0, 1, researchHeaders.length));
applyBodyStyle(researchSheet.getRangeByIndexes(1, 0, researchRows.length, researchHeaders.length));
researchSheet.freezePanes.freezeRows(1);
researchSheet.getRange("A1:T1").format.rowHeight = 42;
researchSheet.getRangeByIndexes(1, 0, researchRows.length, researchHeaders.length).format.rowHeight = 34;
researchSheet.getRange("G:G").format.wrapText = false;
researchSheet.getRange("I:I").format.wrapText = false;
researchSheet.getRange("N:Q").format.wrapText = false;
researchSheet.getRange("S:S").format.wrapText = false;
researchSheet.getRange("A:A").format.columnWidth = 15;
researchSheet.getRange("B:B").format.columnWidth = 48;
researchSheet.getRange("C:C").format.columnWidth = 12;
researchSheet.getRange("D:D").format.columnWidth = 24;
researchSheet.getRange("E:E").format.columnWidth = 22;
researchSheet.getRange("F:J").format.columnWidth = 14;
researchSheet.getRange("K:M").format.columnWidth = 26;
researchSheet.getRange("N:Q").format.columnWidth = 42;
researchSheet.getRange("R:R").format.columnWidth = 16;
researchSheet.getRange("S:S").format.columnWidth = 42;
researchSheet.getRange("T:T").format.columnWidth = 46;

const groupStats = new Map();
for (const row of researchRows) {
  const tags = splitTags(row[4]);
  for (const tag of tags.length ? tags : ["ohne Tag"]) {
    if (!groupStats.has(tag)) {
      groupStats.set(tag, {
        group: tag,
        total: 0,
        withDoi: 0,
        pure: 0,
        publisher: 0,
        provider: 0,
        combined: 0,
        providerLinks: 0,
      });
    }
    const stat = groupStats.get(tag);
    stat.total += 1;
    if (row[3]) stat.withDoi += 1;
    if (row[5] === "yes") stat.pure += 1;
    if (row[7] === "yes") stat.publisher += 1;
    if (row[9] === "yes") stat.provider += 1;
    if (row[17] === "yes") stat.combined += 1;
    if (row[13]) stat.providerLinks += 1;
  }
}

const groupHeaders = [
  "Forschungsgruppe",
  "Publikationen",
  "mit DOI",
  "PuRe-Forschungsdaten",
  "Verlagsseite-Forschungsdaten",
  "Provider-Forschungsdaten",
  "kombiniert mit Forschungsdaten-Hinweis",
  "Anteil kombiniert",
];
const groupRows = [...groupStats.values()]
  .sort((a, b) => b.combined - a.combined || b.total - a.total || a.group.localeCompare(b.group, "de"))
  .map((stat) => [
    stat.group,
    stat.total,
    stat.withDoi,
    stat.pure,
    stat.publisher,
    stat.provider,
    stat.combined,
    stat.total ? stat.combined / stat.total : 0,
  ]);

const groupSheet = getOrResetSheet(workbook, GROUP_SHEET);
groupSheet.getRangeByIndexes(0, 0, 1, groupHeaders.length).values = [groupHeaders];
groupSheet.getRangeByIndexes(1, 0, groupRows.length, groupHeaders.length).values = groupRows;
applyHeaderStyle(groupSheet.getRangeByIndexes(0, 0, 1, groupHeaders.length));
applyBodyStyle(groupSheet.getRangeByIndexes(1, 0, groupRows.length, groupHeaders.length));
groupSheet.getRange("A1:H1").format.rowHeight = 58;
groupSheet.getRangeByIndexes(1, 0, groupRows.length, groupHeaders.length).format.rowHeight = 24;
groupSheet.getRangeByIndexes(1, 1, groupRows.length, 6).format.numberFormat = [["0"]];
groupSheet.getRangeByIndexes(1, 7, groupRows.length, 1).format.numberFormat = [["0.0%"]];
groupSheet.freezePanes.freezeRows(1);
groupSheet.getRange("A:A").format.columnWidth = 24;
groupSheet.getRange("B:C").format.columnWidth = 18;
groupSheet.getRange("D:G").format.columnWidth = 24;
groupSheet.getRange("H:H").format.columnWidth = 16;

const overview = workbook.worksheets.getItem("Übersicht");
overview.getRange("A16:B26").clear({ applyTo: "all" });
overview.getRange("A16:B26").values = [
  ["Erweiterung Provider-Recherche", ""],
  ["DOI-Zeilen automatisiert geprüft", discovery.doi_rows],
  ["Titel automatisiert geprüft", discovery.title_rows],
  ["Publikationen mit Provider-Treffern", discovery.provider_found_rows],
  ["davon mit verifiziertem Titel-/Autoren-Treffer", discovery.title_found_rows],
  ["Publikationen mit kombiniertem Forschungsdaten-Hinweis", researchRows.filter((row) => row[17] === "yes").length],
  ["davon nur Provider-Treffer (nicht PuRe/Verlag)", researchRows.filter((row) => row[9] === "yes" && row[5] !== "yes" && row[7] !== "yes").length],
  ["DOI-lose Publikationen", researchRows.filter((row) => !row[3]).length],
  ["Automatisierte Quellen", "DataCite; OSF; Europe PMC Volltext; OpenAIRE; ScholeXplorer; B2FIND; Crossref"],
  ["Detailblatt", RESEARCH_SHEET],
  ["Forschungsgruppenblatt", GROUP_SHEET],
];
overview.getRange("A16:B16").format.fill = { color: "#D9EAF7" };
overview.getRange("A16:B16").format.font = { color: "#102A43", bold: true };
overview.getRange("A16:B26").format.wrapText = true;
overview.getRange("A:B").format.autofitColumns();

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
