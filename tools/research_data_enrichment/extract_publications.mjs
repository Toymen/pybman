import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const inputPath = process.argv[2];
const outputPath = process.argv[3];

if (!inputPath || !outputPath) {
  console.error("Usage: node extract_publications.mjs <input.xlsx> <output.json>");
  process.exit(2);
}

const input = await FileBlob.load(inputPath);
const workbook = await SpreadsheetFile.importXlsx(input);
function tableFromSheet(sheetName) {
  const sheet = workbook.worksheets.getItem(sheetName);
  const values = sheet.getUsedRange().values;
  const headers = values[0].map((value) => String(value ?? ""));
  const rows = values.slice(1).map((row, index) => {
    const item = { excelRow: index + 2 };
    headers.forEach((header, colIndex) => {
      item[header] = row[colIndex] ?? null;
    });
    return item;
  });
  return { headers, rows };
}

await fs.writeFile(
  outputPath,
  JSON.stringify(
    {
      publications: tableFromSheet("Publikationen"),
      publisher: tableFromSheet("Forschungsdaten laut Verlag"),
    },
    null,
    2,
  ),
  "utf8",
);
