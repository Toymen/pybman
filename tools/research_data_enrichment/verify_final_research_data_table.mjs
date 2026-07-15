import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, previewDir] = process.argv.slice(2);

if (!workbookPath || !previewDir) {
  console.error("Usage: node verify_final_research_data_table.mjs <workbook.xlsx> <preview-dir>");
  process.exit(2);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));

const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 10000,
  tableMaxRows: 3,
  tableMaxCols: 10,
  tableMaxCellChars: 60,
});
console.log("OVERVIEW");
console.log(overview.ndjson);

const finalTable = await workbook.inspect({
  kind: "table",
  sheetId: "Forschungsdaten final",
  range: "A1:AH20",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 34,
  tableMaxCellChars: 90,
  maxChars: 18000,
});
console.log("FINAL");
console.log(finalTable.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range] of [
  ["Übersicht", "A1:B38"],
  ["Publikationen", "A1:O20"],
  ["Forschungsdaten laut Verlag", "A1:I20"],
  ["Provider-Recherche", "A1:T20"],
  ["Forschungsgruppen", "A1:H20"],
  ["Merged Details", "A1:AD20"],
  ["Forschungsdaten final", "A1:AH20"],
]) {
  const rendered = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}.png`),
    new Uint8Array(await rendered.arrayBuffer()),
  );
}
