import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const [workbookPath, previewDir] = process.argv.slice(2);

if (!workbookPath || !previewDir) {
  console.error("Usage: node verify_merged_workbook.mjs <workbook.xlsx> <preview-dir>");
  process.exit(2);
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));

const sheets = await workbook.inspect({ kind: "sheet", include: "id,name" });
console.log("SHEETS");
console.log(sheets.ndjson);

const check = await workbook.inspect({
  kind: "table",
  sheetId: "Merged Details",
  range: "A1:AD18",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 30,
  tableMaxCellChars: 100,
  maxChars: 18000,
});
console.log("MERGED");
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log("ERRORS");
console.log(errors.ndjson);

const rendered = await workbook.render({
  sheetName: "Merged Details",
  range: "A1:AD18",
  scale: 1,
  format: "png",
});
await fs.mkdir(previewDir, { recursive: true });
await fs.writeFile(
  path.join(previewDir, "Merged Details.png"),
  new Uint8Array(await rendered.arrayBuffer()),
);
