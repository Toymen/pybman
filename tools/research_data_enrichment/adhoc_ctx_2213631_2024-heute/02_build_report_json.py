# Step 2 of 3 (run twice, see 01_merge_external_discovery.py for the order).
import json, os

SCR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(SCR, "..", "..", "..", "outputs", "research_data_enrichment")
os.makedirs(OUT_DIR, exist_ok=True)

with open(f"{SCR}/all_publications.json") as f:
    pubs = json.load(f)

try:
    with open(f"{SCR}/new_confirmed.json") as f:
        new_confirmed = json.load(f)
except FileNotFoundError:
    new_confirmed = {}  # first run: 01_merge_external_discovery.py hasn't produced it yet

# Second pass: cross-check every publication that HAS a DOI against external
# discovery services (ScholeXplorer, DataCite, B2FIND, Crossref, Zenodo,
# Figshare, Dryad) via pybman's research-data discovery tooling, because
# PuRe's own contentCategory=="research-data" tagging is not exhaustive
# (confirmed: it misses at least one publication's dataset entirely). Hits
# were deduplicated against already-known PuRe DOIs, filtered to drop
# citation noise (relation "References"/"IsRelatedTo" to a different paper's
# dataset) and generic article supplements/figures/appendices (which map to
# the excluded "Supplement Seiten" category), and kept only when either the
# dataset title strongly matches the publication title or the relation is a
# high-precision Scholix/DataCite relation type (IsSupplementTo/IsDocumentedBy).
EXTRA_CLASSIFICATION = {
    "item_3670247": [
        {
            "url": "https://doi.org/10.23668/psycharchives.16435",
            "kategorie": "Datensatz/Replication Package mit Daten",
            "anmerkung": "PsychArchives: \"Datasets and codebook for: ...\" — exakter Titelmatch zur Publikation; via externe Discovery (B2FIND) gefunden, in PuRe NICHT als research-data getaggt.",
            "manuelle_pruefung_empfohlen": False,
            "quelle": "extern (b2find), nicht in PuRe getaggt",
        }
    ],
    "item_3497021": [
        {
            "url": "https://doi.org/10.25384/sage.c.6447082.v1",
            "kategorie": "Daten",
            "anmerkung": "SAGE/JCR-Datenrepositorium: exakter Titelmatch zur Publikation; zusätzliche Quelle neben dem bereits in PuRe getaggten OSF-Link.",
            "manuelle_pruefung_empfohlen": False,
            "quelle": "extern (scholexplorer), zusätzlich zum PuRe-Tag",
        }
    ],
}

# Manual classification of each research-data link, based on repository semantics
# (PuRe's own contentCategory=="research-data" tag identifies the link; the
# category below sub-classifies it per the requested taxonomy). Where the
# nature of an OSF node (data vs. bare registration) could not be verified
# because this environment has no live web access to osf.io, this is flagged.
CLASSIFICATION = {
    "https://osf.io/k493y/": ("Datensatz/Replication Package mit Daten", "OSF-Projekt (Titel/Kontext deutet auf Daten hin); Inhalt nicht browser-verifizierbar", True),
    "https://osf.io/mf2rk": ("Datensatz/Replication Package mit Daten", "OSF-Projekt; Inhalt nicht browser-verifizierbar", True),
    "https://doi.org/10.3886/E193522V4": ("Datensatz/Replication Package mit Daten", "openICPSR \"Replication data for...\" (laut ScholeXplorer-Metadaten)", False),
    "https://www.doi.org/10.17605/OSF.IO/5BJQW": ("Datensatz/Replication Package mit Daten", "OSF-DOI; Inhalt nicht browser-verifizierbar", True),
    "https://osf.io/6jp9q": ("Datensatz/Replication Package mit Daten", "OSF-Projekt; Inhalt nicht browser-verifizierbar", True),
    "https://osf.io/4n8hy/?view_only=fb104cd14ba548e0b01b997908fdbeb8": ("Datensatz/Replication Package mit Daten", "OSF-Projekt (view-only Link); Inhalt nicht browser-verifizierbar", True),
    "https://osf.io/j8mds/": ("Datensatz/Replication Package mit Daten", "OSF-Projekt; Inhalt nicht browser-verifizierbar", True),
    "https://osf.io/b8zp4/?view_only=f331e7a632e54a6fbaf5763175393150": ("Datensatz/Replication Package mit Daten", "OSF-Projekt (view-only Link); Inhalt nicht browser-verifizierbar", True),
    "https://www.openicpsr.org/openicpsr/project/184701/version/V1/view": ("Datensatz/Replication Package mit Daten", "openICPSR-Projekt (Data & Code)", False),
    "https://osf.io/2gf8k/": ("Datensatz/Replication Package mit Daten", "OSF-Projekt; Inhalt nicht browser-verifizierbar", True),
    "https://doi.org/10.5525/gla.researchdata.1661": ("Daten", "University of Glasgow Research Data Repository (Simulationsdaten)", False),
    "https://doi.org/10.7910/DVN/DCSR0N": ("Datensatz/Replication Package mit Daten", "Harvard Dataverse", False),
    "https://osf.io/sqcrm/": ("Datensatz/Replication Package mit Daten", "OSF-Projekt, Titel nennt explizit \"multi-lab replication\"", True),
    "https://professor-gpt.coll.mpg.de/html/overview.html": ("reine Software", "institutseigene Projekt-/Demo-Webseite eines LLM-Tools, keine Datendateien", False),
    "https://doi.org/10.17617/3.1H6QYT": ("Daten", "Edmond (Max Planck Digital Library Datenrepositorium)", False),
    "https://osf.io/sdbgf": ("Datensatz/Replication Package mit Daten", "OSF-Projekt zu Meta-Analyse; Inhalt nicht browser-verifizierbar", True),
    "https://doi.org/10.17617/3.LPX8BT": ("Daten", "Edmond (Max Planck Digital Library Datenrepositorium)", False),
    "https://doi.org/10.17632/p29n4ft8pz.1": ("Daten", "Mendeley Data", False),
    "https://osf.io/d2fex/?view_only=daca41c653574a8aa1fb40d6b6a7f46c": ("Datensatz/Replication Package mit Daten", "OSF-Projekt (view-only Link); Inhalt nicht browser-verifizierbar", True),
}

CATEGORIES = [
    "Daten",
    "Datensatz/Replication Package mit Daten",
    "Protokolle",
    "reine Software",
    "Registrierungen",
]

out_pubs = []
category_counts = {c: 0 for c in CATEGORIES}
n_with_data = 0

n_new_from_discovery = 0
for p in pubs:
    links = []
    for url in p["researchDataFiles"]:
        cat, note, needs_review = CLASSIFICATION.get(
            url, ("Datensatz/Replication Package mit Daten", "nicht manuell klassifiziert", True)
        )
        links.append({
            "url": url,
            "kategorie": cat,
            "anmerkung": note,
            "manuelle_pruefung_empfohlen": needs_review,
            "quelle": "PuRe (contentCategory=research-data)",
        })
        category_counts[cat] += 1
    for extra in EXTRA_CLASSIFICATION.get(p["itemId"], []):
        links.append(extra)
        category_counts[extra["kategorie"]] += 1
        n_new_from_discovery += 1
    if links:
        n_with_data += 1
    out_pubs.append({
        "itemId": p["itemId"],
        "pureUrl": f"https://pure.mpg.de/pubman/faces/ViewItemOverviewPage.jsp?itemId={p['itemId']}",
        "title": p["title"],
        "doi": p["doi"],
        "datePublished": p["datePublished"],
        "genre": p["genre"],
        "publicState": p["publicState"],
        "forschungsgruppen_tags": p["localTags"],
        "hatVerlinkteForschungsdaten": bool(links),
        "forschungsdaten": links,
    })

result = {
    "meta": {
        "kontext": "ctx_2213631",
        "kontextName": "_Publications of the MPI for Research on Collective Goods",
        "zeitraum": {"von": "2024-01-01", "bis": "2026-07-16"},
        "erzeugtAm": "2026-07-16",
        "quelle": "PuRe (pure.mpg.de) REST API, Feld files[].metadata.contentCategory == 'research-data'",
        "methodik": (
            "Alle Publikationen im angegebenen Kontext und Zeitraum wurden über die "
            "PuRe-Suche geladen. Als 'Forschungsdaten verlinkt' gelten ausschliesslich "
            "Dateien/Links, die in PuRe selbst mit der institutionell gepflegten "
            "Content-Kategorie 'research-data' getaggt sind (nicht 'supplementary-material', "
            "'any-fulltext', 'pre-print', 'post-print' oder 'publisher-version'). "
            "Die Kategorie 'supplementary-material' entspricht den ausgeschlossenen "
            "'Supplement Seiten' und wurde nicht berücksichtigt. Innerhalb der so "
            "gefundenen Links wurde jeder einzelne anhand von Repository/DOI-Präfix "
            "und Publikationskontext einer der fünf angeforderten Unterkategorien "
            "zugeordnet (Daten, Datensatz/Replication Package mit Daten, Protokolle, "
            "reine Software, Registrierungen). Kein Link mit Ziel-Domain, die auf "
            "Preregistration-Ankündigung, Suchseite oder eine rein angekündigte "
            "künftige Freigabe hindeutet, wurde in diesem Kontext gefunden."
        ),
        "methodik_zweiter_durchgang": (
            "PuRe selbst ist nicht vollständig: nicht jede Publikation, für die "
            "tatsächlich Forschungsdaten existieren, ist in PuRe mit "
            "contentCategory=='research-data' getaggt. Deshalb wurden zusätzlich alle "
            "151 Publikationen mit DOI im Kontext gegen externe Discovery-Dienste "
            "abgeglichen (ScholeXplorer, DataCite, B2FIND, Crossref, Zenodo, Figshare, "
            "Dryad — dieselben Dienste, die pybman.discovery/tools/research_data_enrichment "
            "in diesem Repository für die Forschungsdaten-Recherche nutzt). Treffer wurden "
            "gegen die bereits per PuRe-Tag bekannten DOIs dedupliziert, generische "
            "Artikel-Supplements/Abbildungen/Appendizes (== 'Supplement Seiten') und reine "
            "Zitations-Rauschen ('References'/'IsRelatedTo' auf eine erkennbar andere "
            "Publikation) wurden verworfen. Nur Treffer mit exaktem Titelmatch zur "
            "Publikation oder einer hochpräzisen Scholix/DataCite-Relation "
            "(IsSupplementTo/IsDocumentedBy) wurden übernommen. Ergebnis: 1 Publikation "
            "(item_3670247) hat ein PsychArchives-Datenset, das in PuRe GAR NICHT getaggt "
            "war; 1 weitere Publikation (item_3497021) hat eine zusätzliche Datenquelle "
            "neben dem bereits bekannten PuRe-Link."
        ),
        "einschraenkung": (
            "In dieser Ausführungsumgebung besteht kein Live-Browserzugriff auf externe "
            "Repositorien (osf.io, openicpsr.org, doi.org, ...); die Feineinordnung "
            "einzelner OSF-Links (Datensatz vs. reine Registrierung) beruht auf "
            "Titel/Kontext der Publikation, nicht auf Sichtung des tatsächlichen "
            "Datei-Inhalts. Diese Fälle sind mit 'manuelle_pruefung_empfohlen': true "
            "markiert. Der zweite Durchgang (externe Discovery) konnte nur für die 151 "
            "von 280 Publikationen mit DOI laufen; für die 129 Publikationen ohne DOI "
            "(Working Papers, Buchkapitel u.ä.) ist nur der PuRe-eigene Tag verfügbar — "
            "hier bleibt eine Lücke, die nur durch manuelle Recherche (z.B. Google Dataset "
            "Search, direkte Anfrage bei den Autor:innen) geschlossen werden kann."
        ),
        "kategorien_forschungsdaten": CATEGORIES,
        "ausgeschlossene_kategorien": [
            "Supplement Seiten", "Prereregistrierung (Ankündigung)", "Suchseiten", "Angekündigte Freigaben"
        ],
    },
    "zusammenfassung": {
        "publikationenGesamt": len(pubs),
        "publikationenMitDOI": sum(1 for p in pubs if p["doi"]),
        "publikationenMitVerlinktenForschungsdaten": n_with_data,
        "davonNeuDurchExterneDiscoveryGefunden": n_new_from_discovery,
        "anzahlLinksProKategorie": category_counts,
    },
    "publikationen": out_pubs,
}

out_path = f"{OUT_DIR}/forschungsdaten_ctx_2213631_2024-heute.json"
with open(out_path, "w") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("wrote", out_path)
print("total pubs", len(pubs), "with data", n_with_data)
print(category_counts)
