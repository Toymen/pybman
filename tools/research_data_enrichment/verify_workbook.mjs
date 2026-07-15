import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const workbookPath = process.argv[2];
const previewDir = process.argv[3];

if (!workbookPath || !previewDir) {
  console.error("Usage: node verify_workbook.mjs <workbook.xlsx> <preview-dir>");
  process.exit(2);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));

for (const [sheetName, range] of [
  ["Übersicht", "A1:B38"],
  ["Provider-Recherche", "A1:T18"],
  ["Forschungsgruppen", "A1:H20"],
]) {
  const inspected = await workbook.inspect({
    kind: "table",
    sheetId: sheetName,
    range,
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 20,
    tableMaxCellChars: 100,
    maxChars: 12000,
  });
  console.log(`INSPECT ${sheetName}`);
  console.log(inspected.ndjson);

  const rendered = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  await fs.mkdir(previewDir, { recursive: true });
  const bytes = new Uint8Array(await rendered.arrayBuffer());
  await fs.writeFile(path.join(previewDir, `${sheetName}.png`), bytes);
}

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);
