# Step 1 of 3. Run order: 02 (produces the base report from PuRe's own
# research-data tag) -> 01 (cross-checks against external discovery services
# and writes new_confirmed.json) -> 02 again (folds new_confirmed.json in via
# EXTRA_CLASSIFICATION) -> 03 (renders the xlsx). This mirrors how the report
# was actually built: a first pass from PuRe metadata, then a second pass to
# fill PuRe's known gaps.
import json, os, re

SCR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCR, "..", "..", "..", "outputs", "research_data_enrichment")

with open(f"{SCR}/all_publications.json") as f:
    pubs = {p["itemId"]: p for p in json.load(f)}

with open(f"{OUT_DIR}/forschungsdaten_ctx_2213631_2024-heute.json") as f:
    existing = json.load(f)

existing_by_item = {p["itemId"]: p for p in existing["publikationen"]}

def doi_from_url(url):
    m = re.search(r"doi\.org/(.+)$", url or "", re.I)
    return m.group(1).lower().rstrip("/") if m else None

existing_dois_by_item = {}
for item_id, p in existing_by_item.items():
    dois = set()
    for l in p["forschungsdaten"]:
        d = doi_from_url(l["url"])
        if d:
            dois.add(d)
    existing_dois_by_item[item_id] = dois

hits = []
for i in range(6):
    with open(f"{SCR}/discovery_hits/chunk{i}.json") as f:
        hits.extend(json.load(f))

STOP = {"the","a","an","of","in","on","for","and","or","to","with","from","is","are","study",
        "evidence","experiment","experimental","field","data","an","des","im","fur","zur","zum",
        "eine","ein","des","what","how","does","when","why","who"}

def norm_tokens(t):
    if not t:
        return set()
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return {w for w in t.split() if len(w) > 3 and w not in STOP}

EXCLUDE_TITLE_PATTERNS = [
    r"^supplementary material", r"^supplemental material", r"^additional file",
    r"^appendix\b", r"^figure\b", r"^table\b",
]

FIGSHARE_SUBOBJECT_DOI = re.compile(r"\.(g|t)\d{3}(\.|$)", re.I)

def excluded_as_supplement(title, doi):
    tl = (title or "").lower()
    for pat in EXCLUDE_TITLE_PATTERNS:
        if re.search(pat, tl):
            return True
    if FIGSHARE_SUBOBJECT_DOI.search(doi or ""):
        return True
    return False

new_confirmed = {}
for h in hits:
    item_id = h["itemId"]
    pub = pubs.get(item_id)
    if not pub:
        continue
    pub_title = pub["title"]
    pt = norm_tokens(pub_title)
    already = existing_dois_by_item.get(item_id, set())
    kept = []
    for ds in h["datasets"]:
        title = ds.get("title") or ""
        doi = (ds.get("doi") or "").lower()
        if doi in already:
            continue  # already captured via PuRe's own tag
        if excluded_as_supplement(title, doi):
            continue
        ct = norm_tokens(title)
        union = pt | ct
        jaccard = len(pt & ct) / len(union) if union else 0
        strong_title_match = pt and len(pt & ct) >= 4 and jaccard >= 0.4
        relation = ds.get("relation")
        trusted_relation = relation in ("IsSupplementTo", "IsDocumentedBy")
        datacite_or_b2find = "datacite" in ds.get("sources", []) or "b2find" in ds.get("sources", [])
        if strong_title_match or (trusted_relation and datacite_or_b2find):
            confidence = "hoch" if strong_title_match else "mittel"
            kept.append({
                "doi": ds["doi"],
                "url": f"https://doi.org/{ds['doi']}",
                "title": title,
                "publisher": ds.get("publisher"),
                "relation": relation,
                "quelle": ds.get("sources"),
                "konfidenz": confidence,
            })
    if kept:
        new_confirmed[item_id] = kept

print("Publications with NEW externally-discovered research data (beyond PuRe tag):", len(new_confirmed))
for k, v in new_confirmed.items():
    print(" ", k, "|", pubs[k]["title"][:65], "->")
    for x in v:
        print("      ", x["konfidenz"], x["doi"], "|", x["title"][:70])

with open(f"{SCR}/new_confirmed.json", "w") as f:
    json.dump(new_confirmed, f, ensure_ascii=False, indent=2)
