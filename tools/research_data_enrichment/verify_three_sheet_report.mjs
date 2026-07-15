import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, previewDir] = process.argv.slice(2);
if (!workbookPath || !previewDir) {
  console.error("Usage: node verify_three_sheet_report.mjs <workbook.xlsx> <preview-dir>");
  process.exit(2);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
const structure = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 12000,
  tableMaxRows: 4,
  tableMaxCols: 12,
  tableMaxCellChars: 80,
});
console.log("STRUCTURE");
console.log(structure.ndjson);
const details = await workbook.inspect({
  kind: "table",
  sheetId: "Forschungsdaten",
  range: "A1:AR18",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 44,
  tableMaxCellChars: 100,
  maxChars: 18000,
});
console.log("DETAILS");
console.log(details.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);

await fs.mkdir(previewDir, { recursive: true });
for (const [sheetName, range] of [
  ["Übersicht", "A1:F27"],
  ["Forschungsdaten", "A1:Q18"],
  ["Forschungsgruppen", "A1:G20"],
]) {
  const rendered = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    path.join(previewDir, `${sheetName}.png`),
    new Uint8Array(await rendered.arrayBuffer()),
  );
}
