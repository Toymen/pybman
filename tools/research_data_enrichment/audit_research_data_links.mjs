import fs from "node:fs/promises";
import { chromium } from "playwright";

const [publicationsPath, discoveryPath, outputPath] = process.argv.slice(2);

if (!publicationsPath || !discoveryPath || !outputPath) {
  console.error(
    "Usage: node audit_research_data_links.mjs <publications.json> <discovery.json> <output.json>",
  );
  process.exit(2);
}

const URL_RE = /https?:\/\/[^\s;"'<>)\]]+/gi;
const DATA_WORDS =
  /\b(dataset|data set|research data|raw data|processed data|replication data|replication package|data and code|daten|datensatz|forschungsdaten|codebook)\b/i;
const EXCLUDED_ONLY =
  /\b(study protocol|protocol for|preregistration|pre-registration|registered report|registration|software|source code only|code only)\b/i;
const ACCESS_RESTRICTED =
  /\b(restricted access|controlled access|request access|access request|files? (?:is|are) under embargo|access is restricted|zugriffsbeschr[aä]nkt)\b/i;
const ACCESS_LOGIN =
  /\b(login required|sign in to access|log in to access|institutional access required|purchase access|subscribe to access|behind (?:a )?paywall)\b/i;
const FILE_DATA_EXTENSIONS =
  /\.(csv|tsv|sav|dta|rds|rdata|xlsx?|json|parquet|feather|zip|7z|tar|gz|txt|mat|h5|hdf5|sql|sqlite|por|sas7bdat)$/i;
const FILE_CODE_EXTENSIONS = /\.(r|rmd|py|ipynb|do|m|jl|js|ts|html?|pdf|docx?)$/i;
const STOP_WORDS = new Set([
  "a", "an", "and", "are", "as", "at", "be", "by", "der", "die", "das", "ein", "eine",
  "for", "from", "how", "in", "is", "it", "of", "on", "or", "the", "to", "und", "von",
  "was", "when", "with", "zu",
]);

function text(value) {
  return String(value ?? "").trim();
}

function cleanUrl(url) {
  return text(url)
    .replace(/&amp;/gi, "&")
    .replace(/&#xA;?/gi, "")
    .replace(/[.,;:]+$/g, "")
    .trim();
}

function extractUrls(...values) {
  const urls = [];
  for (const value of values) {
    for (const match of text(value).matchAll(URL_RE)) {
      const url = cleanUrl(match[0]);
      if (url && !urls.some((item) => item.toLowerCase() === url.toLowerCase())) urls.push(url);
    }
  }
  return urls;
}

function canonicalUrl(value) {
  try {
    const url = new URL(cleanUrl(value));
    url.hash = "";
    if (url.hostname === "www.doi.org") url.hostname = "doi.org";
    if (url.hostname === "doi.org") url.pathname = url.pathname.toLowerCase();
    if (url.hostname.endsWith("osf.io")) {
      url.pathname = url.pathname.replace(/\/+$/, "/");
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    return cleanUrl(value);
  }
}

function normalizedTokens(value) {
  return text(value)
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/^(replication (data|package) for|data and code for|datasets? and codebook for)\s*[:\-]?\s*/i, "")
    .replace(/[^a-z0-9]+/g, " ")
    .split(/\s+/)
    .filter((token) => token.length > 2 && !STOP_WORDS.has(token));
}

function titleSimilarity(left, right) {
  const a = new Set(normalizedTokens(left));
  const b = new Set(normalizedTokens(right));
  if (!a.size || !b.size) return 0;
  const overlap = [...a].filter((token) => b.has(token)).length;
  return overlap / Math.min(a.size, b.size);
}

function isProtocol(title) {
  return /\b(study protocol|protocol for|trial protocol|registered report)\b/i.test(text(title));
}

function semanticCandidate(candidate) {
  if (isProtocol(candidate.publication_title)) {
    return { accepted: false, reason: "Studienprotokoll/Registered Report ohne bereits belegte Datenausgabe" };
  }
  if (candidate.source === "PuRe") {
    if (/professor-gpt\.coll\.mpg\.de/i.test(candidate.url)) {
      return { accepted: false, reason: "Interaktive Publikationsseite, kein Datensatznachweis" };
    }
    return { accepted: true, reason: "Kuratiertes PuRe-Forschungsdatenfeld" };
  }
  if (candidate.source === "Verlagsseite") {
    const evidence = `${candidate.evidence} ${candidate.dataset_title}`;
    const urlMentioned = evidence.toLowerCase().includes(cleanUrl(candidate.url).toLowerCase());
    const repositoryTarget =
      /osf\.io\/(?!preprints)|doi\.org\/(10\.17605|10\.17617|10\.5281|10\.5525|10\.6084|10\.7910|10\.3886)|dataverse|figshare\.com\/articles\/dataset|zenodo\.org\/records?/i.test(
        candidate.url,
      );
    if (/\bdata availability\b/i.test(evidence) && DATA_WORDS.test(evidence) && urlMentioned && repositoryTarget) {
      return { accepted: true, reason: "Explizite Data-Availability-Aussage der Verlagsseite" };
    }
    if (
      /\b(raw data|processed data|replication data|replication package|data and code)\b/i.test(evidence) &&
      urlMentioned &&
      repositoryTarget
    ) {
      return { accepted: true, reason: "Verlagsnachweis nennt konkrete Datenartefakte" };
    }
    return { accepted: false, reason: "Verlagsseite nennt keine eindeutige vorhandene Datenausgabe" };
  }
  if (candidate.provider === "europepmc") {
    return { accepted: true, reason: "Link aus expliziter Data-Availability-Statement" };
  }
  if (candidate.provider === "datacite" || candidate.provider === "osf" || candidate.provider === "b2find") {
    const similarity = titleSimilarity(candidate.publication_title, candidate.dataset_title);
    if (similarity >= 0.55 || /verified-title-author-match/i.test(candidate.relation)) {
      return { accepted: true, reason: `Titel-/Autor:innen-Match (${similarity.toFixed(2)})` };
    }
  }
  if (/DataCite resourceTypeGeneral=Dataset/i.test(candidate.source_validation)) {
    const similarity = titleSimilarity(candidate.publication_title, candidate.dataset_title);
    const directlyNamed = /\b(replication data|replication package|data and code)\b/i.test(
      candidate.dataset_title,
    );
    if (similarity >= 0.72 && directlyNamed) {
      return { accepted: true, reason: `DataCite-Dataset mit engem Titelbezug (${similarity.toFixed(2)})` };
    }
    return {
      accepted: false,
      reason: `Dataset-Treffer ohne hinreichend engen Publikationsbezug (${similarity.toFixed(2)})`,
    };
  }
  return { accepted: false, reason: "Datencharakter oder Publikationsbezug nicht eindeutig" };
}

function collectCandidates(publications, discovery) {
  const byId = new Map(publications.publications.rows.map((row) => [text(row["PuRe-ID"]), row]));
  const candidates = [];
  for (const row of publications.publications.rows) {
    for (const url of extractUrls(row["Forschungsdaten-Links"])) {
      candidates.push({
        pure_id: text(row["PuRe-ID"]),
        publication_title: text(row.Titel),
        url,
        source: "PuRe",
        evidence: text(row["Forschungsdaten-Nachweis"]),
        dataset_title: "",
        provider: "",
        relation: "curated-research-data-field",
        source_validation: "PuRe",
      });
    }
  }
  for (const row of publications.publisher.rows) {
    const publication = byId.get(text(row["PuRe-ID"]));
    if (!publication) continue;
    for (const url of extractUrls(row["Datenlink(s) laut Verlagsseite"])) {
      candidates.push({
        pure_id: text(row["PuRe-ID"]),
        publication_title: text(publication.Titel),
        url,
        source: "Verlagsseite",
        evidence: `${text(row["Fundstelle / Nachweis"])} ${text(row["Abruf-Hinweis"])}`,
        dataset_title: "",
        provider: "",
        relation: "publisher-page",
        source_validation: "Verlagsseite",
      });
    }
  }
  for (const result of discovery.results) {
    const publication = byId.get(text(result["PuRe-ID"]));
    if (!publication) continue;
    for (const hit of result.hits ?? []) {
      candidates.push({
        pure_id: text(result["PuRe-ID"]),
        publication_title: text(publication.Titel),
        url: cleanUrl(hit.url),
        source: "Provider",
        evidence: `${text(hit.source_validation)} ${text(hit.relation)}`,
        dataset_title: text(hit.title),
        provider: text(hit.provider),
        relation: text(hit.relation),
        source_validation: text(hit.source_validation),
      });
    }
  }
  return candidates;
}

function osfNodeId(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!/(^|\.)osf\.io$/i.test(url.hostname)) return "";
    return url.pathname.split("/").filter(Boolean)[0] ?? "";
  } catch {
    return "";
  }
}

async function fetchJson(url, timeoutMs = 20000) {
  const response = await fetch(url, {
    headers: { "User-Agent": "ResearchDataAudit/1.0 (+link-verification)" },
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

async function inspectOsf(url) {
  const nodeId = osfNodeId(url);
  if (!nodeId) return null;
  try {
    const providers = await fetchJson(`https://api.osf.io/v2/nodes/${nodeId}/files/`);
    const names = [];
    const visit = async (listingUrl, depth = 0) => {
      if (!listingUrl || depth > 5) return;
      let nextUrl = listingUrl;
      while (nextUrl) {
        const listing = await fetchJson(nextUrl);
        for (const entry of listing.data ?? []) {
          const name = text(entry.attributes?.name);
          if (entry.attributes?.kind === "folder") {
            await visit(entry.relationships?.files?.links?.related?.href, depth + 1);
          } else if (name) {
            names.push(name);
          }
        }
        nextUrl = listing.links?.next ?? null;
      }
    };
    for (const provider of providers.data ?? []) {
      const rootUrl = provider.relationships?.files?.links?.related?.href;
      await visit(rootUrl);
    }
    const dataFiles = names.filter((name) => FILE_DATA_EXTENSIONS.test(name));
    const codeFiles = names.filter((name) => FILE_CODE_EXTENSIONS.test(name));
    return { node_id: nodeId, file_count: names.length, data_files: dataFiles, code_files: codeFiles };
  } catch (error) {
    return { node_id: nodeId, file_count: null, data_files: [], code_files: [], error: text(error.message) };
  }
}

function classifyAccess(status, pageText) {
  if (ACCESS_RESTRICTED.test(pageText)) return "zugriffsbeschränkt/embargo";
  if (ACCESS_LOGIN.test(pageText) || status === 401 || status === 402) return "Paywall/Login";
  if (status === 403) return "Paywall/Login oder Zugriffsschutz";
  return "offen";
}

async function fetchPage(url) {
  try {
    const response = await fetch(url, {
      redirect: "follow",
      headers: {
        Accept: "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (compatible; ResearchDataAudit/1.0)",
      },
      signal: AbortSignal.timeout(30000),
    });
    const body = (await response.text()).slice(0, 250000);
    const title = body.match(/<title[^>]*>([\s\S]*?)<\/title>/i)?.[1]?.replace(/<[^>]+>/g, " ") ?? "";
    return {
      ok: response.status >= 200 && response.status < 400,
      status: response.status,
      final_url: response.url,
      title: text(title).replace(/\s+/g, " "),
      body,
      method: "HTTP",
    };
  } catch (error) {
    return { ok: false, status: null, final_url: url, title: "", body: "", method: "HTTP", error: text(error.message) };
  }
}

async function browserPage(browser, url) {
  const page = await browser.newPage();
  try {
    const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 40000 });
    await page.waitForTimeout(800);
    const body = (await page.locator("body").innerText({ timeout: 5000 }).catch(() => "")).slice(0, 100000);
    return {
      ok: Boolean(response && response.status() >= 200 && response.status() < 400),
      status: response?.status() ?? null,
      final_url: page.url(),
      title: await page.title(),
      body,
      method: "Playwright",
    };
  } catch (error) {
    return { ok: false, status: null, final_url: page.url() || url, title: "", body: "", method: "Playwright", error: text(error.message) };
  } finally {
    await page.close();
  }
}

async function auditUrl(browser, url) {
  const http = await fetchPage(url);
  let page = http;
  if (!http.ok || !http.title || /just a moment|enable javascript|access denied/i.test(`${http.title} ${http.body.slice(0, 2000)}`)) {
    page = await browserPage(browser, url);
  }
  const pageText = `${page.title} ${page.body}`;
  return {
    requested_url: url,
    final_url: page.final_url,
    available: page.ok,
    http_status: page.status,
    page_title: text(page.title).replace(/\s+/g, " ").slice(0, 500),
    access_status: page.ok ? classifyAccess(page.status, pageText) : "nicht erreichbar",
    verification_method: page.method,
    error: page.error ?? "",
    page_has_data_terms: DATA_WORDS.test(pageText),
    page_has_exclusion_terms: EXCLUDED_ONLY.test(pageText),
  };
}

const publications = JSON.parse(await fs.readFile(publicationsPath, "utf8"));
const discovery = JSON.parse(await fs.readFile(discoveryPath, "utf8"));
const rawCandidates = collectCandidates(publications, discovery);
const candidates = rawCandidates.map((candidate) => ({
  ...candidate,
  canonical_url: canonicalUrl(candidate.url),
  semantic_precheck: semanticCandidate(candidate),
}));
const urls = [...new Set(candidates.filter((item) => item.semantic_precheck.accepted).map((item) => item.canonical_url))];
const browser = await chromium.launch({ headless: true });
const audits = new Map();
let cursor = 0;
const workers = Array.from({ length: 5 }, async () => {
  while (cursor < urls.length) {
    const index = cursor;
    cursor += 1;
    const url = urls[index];
    const audit = await auditUrl(browser, url);
    const osf = await inspectOsf(audit.final_url || url);
    audits.set(url, { ...audit, osf });
    console.log(`[${index + 1}/${urls.length}] ${audit.available ? "OK" : "FAIL"} ${url} -> ${audit.http_status ?? "-"}`);
  }
});
await Promise.all(workers);
await browser.close();

const auditedCandidates = candidates.map((candidate) => {
  const linkAudit = audits.get(candidate.canonical_url) ?? null;
  let accepted = candidate.semantic_precheck.accepted && Boolean(linkAudit?.available);
  let reason = candidate.semantic_precheck.reason;
  if (candidate.semantic_precheck.accepted && !linkAudit?.available) reason = "Zielseite nicht erreichbar";
  if (accepted && linkAudit?.osf) {
    const osf = linkAudit.osf;
    if (osf.file_count === 0) {
      accepted = false;
      reason = "OSF-Projekt ist erreichbar, enthält aber keine Dateien";
    } else if (osf.file_count !== null && osf.data_files.length === 0) {
      accepted = false;
      reason = "OSF-Projekt enthält keine eindeutig als Daten erkennbare Datei";
    } else if (osf.data_files.length > 0) {
      reason = `${reason}; ${osf.data_files.length} Datendatei(en) über OSF-API bestätigt`;
    }
  }
  if (accepted && linkAudit?.page_has_exclusion_terms && !linkAudit?.page_has_data_terms) {
    accepted = false;
    reason = "Zielseite weist nur Protokoll/Präregistrierung/Software, aber keine Daten aus";
  }
  return { ...candidate, link_audit: linkAudit, accepted, decision_reason: reason };
});

const byPublication = new Map();
for (const row of publications.publications.rows) {
  byPublication.set(text(row["PuRe-ID"]), {
    pure_id: text(row["PuRe-ID"]),
    title: text(row.Titel),
    accepted_links: [],
    rejected_candidates: [],
  });
}
for (const candidate of auditedCandidates) {
  const entry = byPublication.get(candidate.pure_id);
  if (candidate.accepted) entry.accepted_links.push(candidate);
  else entry.rejected_candidates.push(candidate);
}
for (const entry of byPublication.values()) {
  const seen = new Set();
  entry.accepted_links = entry.accepted_links.filter((candidate) => {
    const key = canonicalUrl(candidate.link_audit?.final_url || candidate.canonical_url).toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
  entry.research_data = entry.accepted_links.length ? "ja" : "nein";
}

const rows = [...byPublication.values()];
const output = {
  generated_at: new Date().toISOString(),
  definition: {
    included: "Vorhandene Roh-/Prozessdaten, Datensätze oder Replikationspakete mit Datendateien und eindeutigem Publikationsbezug.",
    excluded: "Studienprotokolle, Präregistrierungen ohne Daten, Software/Code-only, Registrierungen, Such-/Bibliografieseiten, bloße Supplement-Seiten ohne Datennachweis und nur angekündigte Freigaben.",
    access_rule: "Ein Datensatz kann offen oder zugriffsbeschränkt sein; Paywall, Login, Embargo oder Zugriffsschutz werden separat ausgewiesen. Nicht erreichbare Links zählen nicht.",
  },
  metrics: {
    publications: rows.length,
    candidate_records: auditedCandidates.length,
    audited_unique_urls: urls.length,
    publications_yes: rows.filter((row) => row.research_data === "ja").length,
    publications_no: rows.filter((row) => row.research_data === "nein").length,
    accepted_links: rows.reduce((sum, row) => sum + row.accepted_links.length, 0),
    rejected_candidates: rows.reduce((sum, row) => sum + row.rejected_candidates.length, 0),
  },
  rows,
};
await fs.writeFile(outputPath, `${JSON.stringify(output, null, 2)}\n`);
console.log(JSON.stringify(output.metrics));
