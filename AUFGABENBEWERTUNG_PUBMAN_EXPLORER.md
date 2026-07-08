# Aufgabenbewertung: Publikationen, Tags, Forschungsdaten und Excel-Export

## Kurzfazit

Ja, die Page kann diese Aufgabe grundsätzlich vernünftig unterstützen und eine
brauchbare Excel-Datei daraus erzeugen.

Die vorhandene Webapp ist bereits auf genau die relevanten Datenachsen
ausgelegt:

- Publikationen aus einem konfigurierbaren PuRe-Kontext oder einer PuRe-Query
- lokale Tags wie `prime`, `Sutter`, `Engel`, `Oggenfels` und weitere Tags
- gesonderte Spalten für Prime/Target-Journal-Markierung und Forschungsgruppen
- Forschungsdaten-Erkennung mit Flag, Links und Evidenztext
- Filterung in der Page
- Excel-Export des gefilterten Result Sets
- zusätzlicher Export aller indexierten JSON-Pfade und des Roh-JSONs

Damit ist die Aufgabe nicht nur visuell auf der Page bearbeitbar, sondern auch
als tabellarischer Datensatz in Excel nachvollziehbar.

## Abbildung der Aufgabe in der Page

### 1. Publikationen in Target Journals / Prime

Die Page bildet den vorhandenen `prime`-Tag als eigene Spalte ab:

- Spalte: `Prime / Target Journal`
- technisches Feld: `prime_tag`
- Wert: `yes`, wenn ein lokaler Tag `prime` enthält
- Filter: über `Local Tag = prime` oder über das Dropdown `Prime / Target Journal`

Das reicht, wenn die Vorarbeit bereits korrekt in PuRe als lokaler Tag
gespeichert wurde. Die Page entscheidet nicht selbst, ob ein Journal ein Target
Journal ist; sie wertet nur den vorhandenen Tag aus.

### 2. Aufsplittung nach Forschungsgruppen

Die Page zeigt lokale Tags zusätzlich als Forschungsgruppen-Tags:

- Spalte: `Group Tags`
- technisches Feld: `research_group_tags`
- Filter: `Research group tag`
- Vorschlagsliste: alle lokalen Tags außer Prime-Tags

Damit lassen sich Gruppen wie `Sutter`, `Engel` oder `Oggenfels` filtern und
exportieren. Falls weitere Gruppentags existieren, werden sie ebenfalls aus den
gespeicherten PuRe-Tags gelesen und müssen nicht vorher hart codiert werden.

Wichtig: Die Logik behandelt alle Nicht-Prime-Tags als mögliche Gruppen- oder
Kategorietags. Falls es lokale Tags gibt, die keine Forschungsgruppe meinen,
würden diese ebenfalls in `Group Tags` erscheinen.

### 3. Alle Publikationen im PuRe-Kontext

Der Sync kann über Umgebungsvariablen eingeschränkt werden:

- `SYNC_CONTEXT_ID` für einen konkreten PuRe-Kontext
- `SYNC_OU_ID` für eine Organisationseinheit
- `SYNC_QUERY` für eine eigene PuRe/Elasticsearch-Query
- ohne Einschränkung: alle Items

Für die beschriebene Aufgabe sollte die App mit dem passenden
`SYNC_CONTEXT_ID` oder einer passenden `SYNC_QUERY` laufen. Dann bezieht sich
die Page auf genau den gewünschten PuRe-Kontext.

### 4. Forschungsdaten-Links je Publikation

Die Page hat eigene Forschungsdaten-Spalten:

- `Research Data?`
- `Research Data Links`
- `Research Data Evidence`

Die Erkennung basiert auf Signalen in den Dateien einer Publikation:

- Datei-Kategorie `research-data`
- Datei-Kategorie `code`
- bekannte Repositories wie Zenodo, Edmond, GitHub, GitLab, Figshare, Dryad,
  OSF, Dataverse, PANGAEA und weitere
- Textsignale wie `research data`, `dataset`, `data availability`,
  `Forschungsdaten`, `raw data`, `replication data`

Das ist für eine erste Auswertung sinnvoll, aber nicht perfekt. Die Page kann
verlinkte Forschungsdaten gut finden, wenn sie in den PuRe-Dateimetadaten,
Dateilinks, Beschreibungen oder bekannten Repository-URLs auftauchen. Sie kann
Forschungsdaten übersehen, wenn die Information nur indirekt im Volltext,
in einem externen Artikel, in einer nicht erkannten URL oder in uneinheitlichen
Metadaten steht.

## Excel-Tauglichkeit

Der Excel-Export ist für diese Aufgabe grundsätzlich geeignet.

Die Datei `publications.xlsx` enthält:

- alle Standardspalten der Page
- Prime-/Target-Journal-Spalte
- Forschungsgruppen-Spalte
- Forschungsdaten-Flag
- Forschungsdaten-Links
- Forschungsdaten-Evidenz
- alle zusätzlich indexierten JSON-Pfade
- das komplette Roh-JSON pro Publikation

Der Export übernimmt dieselben Filter wie die Page. Dadurch kann man zum
Beispiel direkt exportieren:

- alle Publikationen mit `Research Data? = yes`
- alle Publikationen einer Gruppe, z. B. `Sutter`
- alle Prime-Publikationen einer Gruppe
- alle Publikationen im PuRe-Kontext mit oder ohne Forschungsdaten-Link

Für Excel ist besonders hilfreich, dass neben den zusammengefassten Spalten auch
das Roh-JSON und alle flachen JSON-Pfade exportiert werden. So kann eine Person
später nachvollziehen, warum ein Datensatz markiert wurde, oder weitere Spalten
in Excel/Pivot-Tabellen nachbauen.

## Empfohlene Auswertung

Für die genannte Aufgabe wäre ein sinnvoller Ablauf:

1. App mit dem richtigen PuRe-Kontext synchronisieren.
2. In der Page prüfen, ob die Gesamtzahl plausibel ist.
3. Nach `Research Data? = yes` filtern.
4. Optional zusätzlich nach `Research group tag` filtern, z. B. `Sutter`,
   `Engel`, `Oggenfels`.
5. Gefilterte Ansicht als Excel exportieren.
6. In Excel mit Pivot-Tabellen zählen:
   - Publikationen je Forschungsgruppe
   - Publikationen mit Forschungsdaten je Forschungsgruppe
   - Prime vs. Nicht-Prime
   - Forschungsdaten-Link vorhanden vs. nicht vorhanden

## Offene Punkte und Risiken

- Die Page erkennt Target Journals nicht selbst. Sie verlässt sich auf den
  vorhandenen `prime`-Tag.
- Die Forschungsgruppen-Zuordnung verlässt sich auf lokale Tags. Unbekannte oder
  falsch geschriebene Tags werden nicht normalisiert.
- Alle Nicht-Prime-Tags werden als mögliche Gruppentags angezeigt. Das kann
  zusätzliche, fachfremde Tags in die Gruppen-Spalte bringen.
- Die Forschungsdaten-Erkennung ist heuristisch. Für eine finale belastbare
  Auswertung sollte eine manuelle Stichprobe oder Prüfung der Treffer ohne
  Forschungsdaten-Flag erfolgen.
- Der Export ist aktuell auf maximal 50.000 Treffer pro Export begrenzt. Für
  sehr große Kontexte müsste das Limit geprüft oder angepasst werden.

## Gesamtbewertung

Die Page ist für die Aufgabe gut geeignet, wenn die relevanten Informationen in
PuRe als lokale Tags und Datei-/Linkmetadaten vorhanden sind. Sie kann die Daten
übersichtlich ausgeben, nach Forschungsgruppen und Prime-Status filtern und
eine Excel-Datei erzeugen, die für Nacharbeit, Pivot-Auswertungen und
Qualitätssicherung brauchbar ist.

Für eine wissenschaftlich oder administrativ finale Auswertung sollte die
automatische Forschungsdaten-Erkennung aber als Vorselektion verstanden werden,
nicht als unfehlbare Entscheidung.
