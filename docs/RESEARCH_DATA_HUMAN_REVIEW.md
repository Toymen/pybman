# Human review queue for research-data evidence

Status: 2026-07-16

This queue records cases where a specific human action could improve the evidence. An
entry in this document does not change the consolidated `Forschungsdaten?` decision.
Only a reachable, publication-specific dataset or replication package with confirmed
data files may be promoted to `ja`.

## Priority A: may turn a current `nein` into `ja`

| PuRe ID | Current evidence | Useful human action | Acceptance condition |
| --- | --- | --- | --- |
| `item_3656953` | The official APA disclosure form for *What do people want from algorithms?* names `https://osf.io/ax83q/`, but the public OSF project currently contains no files or components. | Ask the corresponding author or OSF project owner whether files are private, withdrawn, or stored in a hidden component, and request a stable public or controlled-access dataset link. | Re-run the OSF file audit and accept only after at least one genuine data file is reachable. |
| `item_3654638` | The publisher data-availability statement for *The illusion of moral superiority* offers data on request, without a stable dataset link. | Request the data from the corresponding author and ask for a citable repository deposit. | Accept only a stable link whose files and publication relationship can be verified. |
| `item_3616083`, `item_3635267` | The publisher statement for *Skewness preferences* offers data on request; these are publication versions of the same work. | Make one author request covering both PuRe versions and ask for a repository link. | Apply the verified result to both versions only after their identity and the deposited data files are confirmed. |
| `item_3559728` | The publisher statement for *Cooperation and norm enforcement differ strongly across adult generations* offers data on request. | Request a repository deposit or controlled-access link from the corresponding author. | Accept only after the exact dataset and at least one data file are verifiable. |
| `item_3628548` | The publisher statement for *Gender differences in wage expectations and negotiation* offers data on request. | Request a repository deposit or controlled-access link from the corresponding author. | Mark access restrictions separately; do not accept an email promise without a working dataset link. |
| `item_3549023` | The publisher statement for *Providing procedural knowledge* announces that data will be made available, but does not prove a current release. | Check the article page again or contact the authors for the promised deposit. | Accept only after the announced release exists and its files pass the normal audit. |

## Priority B: PuRe link maintenance for records already marked `ja`

| PuRe ID | Maintenance issue | Useful human action |
| --- | --- | --- |
| `item_3532287` | An ICPSR version URL returns HTTP 403 to automated access; another independently verified link already supports `ja`. | Open the ICPSR record in an institutional browser session, confirm its files and access conditions, and replace the PuRe URL with the canonical record if appropriate. |
| `item_3570696` | One DataCite-derived target resolves to `about:blank`; another verified link already supports `ja`. | Correct or remove the malformed source link in PuRe/DataCite metadata. |
| `item_3703133` | PuRe full text contains truncated OSF view-only tokens, and one complete OSF link has no identifiable data files; an alternate verified source already supports `ja`. | Repair the truncated tokens in PuRe and ask the project owner whether the file-less node should contain data. |

## Suggested review order

1. Contact authors for Priority A request-only or promised datasets.
2. Re-check `item_3656953` with the OSF owner because the publisher already names a
   specific repository node.
3. Repair Priority B PuRe links so future automated audits no longer encounter broken
   or access-blocked alternatives.
