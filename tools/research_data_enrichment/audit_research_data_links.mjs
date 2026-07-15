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
const ACCESS_TERMS =
  /\b(indicate your agreement|I agree|email address\*?|accept (?:the )?terms|terms of use must be accepted)\b/i;
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

function authorSurnames(value) {
  return new Set(
    text(value)
      .split(";")
      .map((name) => normalizedTokens(name).at(-1))
      .filter(Boolean),
  );
}

function samePublicationIdentity(left, right) {
  const leftTitle = normalizedTokens(left.Titel).join(" ");
  const rightTitle = normalizedTokens(right.Titel).join(" ");
  if (!leftTitle || leftTitle !== rightTitle) return false;
  const leftAuthors = authorSurnames(left["Autor:innen"]);
  const rightAuthors = authorSurnames(right["Autor:innen"]);
  const denominator = Math.min(leftAuthors.size, rightAuthors.size);
  if (!denominator) return false;
  const overlap = [...leftAuthors].filter((surname) => rightAuthors.has(surname)).length;
  return overlap >= 2 && overlap / denominator >= 0.5;
}

function isProtocol(title) {
  return /\b(study protocol|protocol for|trial protocol|registered report)\b/i.test(text(title));
}

function semanticCandidate(candidate) {
  if (isProtocol(candidate.publication_title)) {
    return { accepted: false, reason: "Studienprotokoll/Registered Report ohne bereits belegte Datenausgabe" };
  }
  if (/professor-gpt\.coll\.mpg\.de/i.test(candidate.url)) {
    return { accepted: false, reason: "Interaktive Publikationsseite, kein Datensatznachweis" };
  }
  if (/journals?\.sagepub\.com\/doi\/full/i.test(candidate.url)) {
    return { accepted: false, reason: "Verlagsartikel statt eigenständiger Datensatz-Landingpage" };
  }
  if (/\(https?:\/\//i.test(candidate.url)) {
    return { accepted: false, reason: "Fehlerhaft verkettete URL aus PDF-Textextraktion" };
  }
  try {
    const parsed = new URL(candidate.url);
    const viewToken = parsed.searchParams.get("view_only");
    if (viewToken && !/^[a-f0-9]{32}$/i.test(viewToken)) {
      return { accepted: false, reason: "Unvollständiger OSF-View-only-Schlüssel" };
    }
  } catch {
    return { accepted: false, reason: "Ungültige URL" };
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
  if (candidate.provider === "pure-fulltext") {
    return { accepted: true, reason: "Link aus Data-Availability-Abschnitt des öffentlichen PuRe-Volltexts" };
  }
  if (candidate.provider === "pure-file") {
    return { accepted: true, reason: "Öffentliche PuRe-Datei mit Forschungsdaten-Metadaten" };
  }
  if (candidate.provider === "publisher-supplement") {
    return { accepted: true, reason: "Direkt abrufbare strukturierte Supplementdatei des Verlags" };
  }
  if (candidate.provider === "aea") {
    return { accepted: true, reason: "Direkter Data-and-Code-Link auf der AEA-Artikelseite" };
  }
  if (candidate.provider === "github-data") {
    return { accepted: true, reason: "GitHub-README mit exaktem Publikationstitel und geprüften Datendateien" };
  }
  if (candidate.provider === "openalex-fulltext") {
    return { accepted: true, reason: "Link aus Data-Availability-Abschnitt eines offenen Volltexts" };
  }
  if (candidate.provider === "harvard-dataverse") {
    return { accepted: true, reason: "Publizierter Harvard-Dataverse-Datensatz mit Dateien, Titel- und Autor:innen-Match" };
  }
  if (candidate.provider === "github-doi-data") {
    return { accepted: true, reason: "GitHub-README mit Publikations-DOI, Datenkontext, Autor:innenbezug und geprüften Datendateien" };
  }
  if (candidate.provider === "zenodo-replication") {
    return { accepted: true, reason: "Zenodo-Replikationspaket mit Titel-/Autor:innen-Match und geprüften Datendateien" };
  }
  if (candidate.provider === "informs-replication") {
    return { accepted: true, reason: "Offizielles INFORMS-Replikationsarchiv mit geprüften Datendateien" };
  }
  if (candidate.provider === "elife-data-availability") {
    return { accepted: true, reason: "Strukturierte eLife-Data-Availability-Aussage mit öffentlichem Datensatzlink" };
  }
  if (candidate.provider === "pure-duplicate-file") {
    return { accepted: true, reason: "Öffentliche Forschungsdatendatei einer DOI-identischen PuRe-Parallelfassung" };
  }
  if (candidate.provider === "pure-duplicate-fulltext") {
    return { accepted: true, reason: "Datensatzlink aus öffentlichem Volltext einer DOI-identischen PuRe-Parallelfassung" };
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
    const seenNodes = new Set();
    const visitNode = async (id, depth = 0) => {
      if (!id || depth > 5 || seenNodes.has(id)) return;
      seenNodes.add(id);
      const nodeProviders =
        id === nodeId ? providers : await fetchJson(`https://api.osf.io/v2/nodes/${id}/files/`);
      for (const provider of nodeProviders.data ?? []) {
        await visit(provider.relationships?.files?.links?.related?.href);
      }
      const children = await fetchJson(
        `https://api.osf.io/v2/nodes/${id}/children/?page%5Bsize%5D=100`,
      ).catch(() => ({ data: [] }));
      for (const child of children.data ?? []) await visitNode(text(child.id), depth + 1);
    };
    await visitNode(nodeId);
    const dataFiles = names.filter((name) => FILE_DATA_EXTENSIONS.test(name));
    const codeFiles = names.filter((name) => FILE_CODE_EXTENSIONS.test(name));
    return { node_id: nodeId, file_count: names.length, data_files: dataFiles, code_files: codeFiles };
  } catch (error) {
    return { node_id: nodeId, file_count: null, data_files: [], code_files: [], error: text(error.message) };
  }
}

async function inspectGithub(urlValue) {
  try {
    const url = new URL(urlValue);
    if (!/(^|\.)github\.com$/i.test(url.hostname)) return null;
    const [owner, repository] = url.pathname.split("/").filter(Boolean);
    if (!owner || !repository) return null;
    const headers = { "User-Agent": "ResearchDataAudit/1.0 (+link-verification)" };
    if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
    const response = await fetch(
      `https://api.github.com/repos/${owner}/${repository.replace(/\.git$/i, "")}/git/trees/HEAD?recursive=1`,
      { headers, signal: AbortSignal.timeout(30000) },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const payload = await response.json();
    const names = (payload.tree ?? [])
      .filter((entry) => entry.type === "blob")
      .map((entry) => text(entry.path));
    const dataFiles = names.filter((name) => FILE_DATA_EXTENSIONS.test(name));
    return { repository: `${owner}/${repository}`, file_count: names.length, data_files: dataFiles };
  } catch (error) {
    return { file_count: null, data_files: [], error: text(error.message) };
  }
}

function classifyAccess(status, pageText) {
  if (ACCESS_RESTRICTED.test(pageText)) return "zugriffsbeschränkt/embargo";
  if (ACCESS_LOGIN.test(pageText) || status === 401 || status === 402) return "Paywall/Login";
  if (ACCESS_TERMS.test(pageText)) return "Zustimmung/E-Mail erforderlich";
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
    access_status:
      page.ok || [401, 402, 403].includes(page.status)
        ? classifyAccess(page.status, pageText)
        : "nicht erreichbar",
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
    const github = await inspectGithub(audit.final_url || url);
    audits.set(url, { ...audit, osf, github });
    console.log(`[${index + 1}/${urls.length}] ${audit.available ? "OK" : "FAIL"} ${url} -> ${audit.http_status ?? "-"}`);
  }
});
await Promise.all(workers);
await browser.close();

const auditedCandidates = candidates.map((candidate) => {
  const linkAudit = audits.get(candidate.canonical_url) ?? null;
  const authoritativeRestricted =
    [401, 402, 403].includes(linkAudit?.http_status) &&
    (candidate.source === "PuRe" ||
      candidate.provider === "pure-file" ||
      candidate.provider === "datacite" ||
      candidate.provider === "aea");
  let accepted =
    candidate.semantic_precheck.accepted &&
    (Boolean(linkAudit?.available) || authoritativeRestricted);
  let reason = candidate.semantic_precheck.reason;
  if (accepted && authoritativeRestricted) {
    reason = `${reason}; Landingpage antwortet mit HTTP ${linkAudit.http_status} und ist zugriffsgeschützt`;
  } else if (candidate.semantic_precheck.accepted && !linkAudit?.available) {
    reason = "Zielseite nicht erreichbar";
  }
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
  if (accepted && linkAudit?.github) {
    const github = linkAudit.github;
    if (github.file_count !== null && github.data_files.length === 0) {
      accepted = false;
      reason = "GitHub-Repository enthält keine eindeutig als Daten erkennbare Datei";
    } else if (github.data_files.length > 0) {
      reason = `${reason}; ${github.data_files.length} Datendatei(en) über GitHub-API bestätigt`;
    } else {
      accepted = false;
      reason = `GitHub-Dateibaum konnte nicht bestätigt werden: ${github.error || "unbekannter Fehler"}`;
    }
  }
  const repositoryDataConfirmed =
    (linkAudit?.osf?.data_files?.length ?? 0) > 0 ||
    (linkAudit?.github?.data_files?.length ?? 0) > 0;
  if (
    accepted &&
    !repositoryDataConfirmed &&
    linkAudit?.page_has_exclusion_terms &&
    !linkAudit?.page_has_data_terms
  ) {
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

const publicationRows = publications.publications.rows;
const rowById = new Map(publicationRows.map((row) => [text(row["PuRe-ID"]), row]));
const verifiedEntries = [...byPublication.values()].filter((entry) => entry.research_data === "ja");
for (const entry of byPublication.values()) {
  if (entry.research_data === "ja") continue;
  const targetRow = rowById.get(entry.pure_id);
  const source = verifiedEntries.find((candidate) =>
    samePublicationIdentity(targetRow, rowById.get(candidate.pure_id)),
  );
  if (!source) continue;
  entry.accepted_links = source.accepted_links.map((candidate) => ({
    ...candidate,
    pure_id: entry.pure_id,
    source: "PuRe-Parallelfassung",
    decision_reason:
      `Identischer normalisierter Titel und starke Autor:innenüberschneidung mit ${source.pure_id}; ` +
      candidate.decision_reason,
  }));
  entry.research_data = "ja";
  entry.propagated_from = source.pure_id;
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
