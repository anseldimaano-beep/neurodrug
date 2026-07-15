# Round 2 Fixes — Drug Prediction & Gene Graph Issues

Applied 2026-06-30, in response to: "only 11 drugs rank, where are the
others" and "genes always show 0". Verified by reading source end-to-end
(not by running the app — see Verification Method below).

## C7 — CRITICAL: drug prediction scores were misattributed to the wrong drug

**File:** `backend/app/services/repurposing.py`

`run_inference()` builds the full knowledge graph, then filters the Drug
node list down to only chembl-tagged drugs (to exclude ClinicalTrials junk
interventions like "Questionnaire"). It then built `drug_nodes` as
`torch.arange(len(filtered_list))` — i.e. positions 0..n-1 *within the
filtered list* — and used that directly as the row index into
`emb_dict["Drug"]`, which is ordered by the *original, unfiltered* graph
node list (same order `nx_to_heterodata` used to build
`hetero_data['Drug'].x`).

The moment the filter dropped even one earlier non-drug entry, every drug
after it in the list was scored using a different node's embedding.

**Effect:** every prediction score in the system — both the high ones and
the suspicious flat 0.0000 ones — was at least partially misattributed.
The 0.0000 cluster (Pyrazinamide, Dasatinib, Imatinib, Bevacizumab,
Sunitinib, Aspirin) wasn't "no connectivity" — some of those drugs (e.g.
Bevacizumab) have real graph edges. They were being scored against
whatever unrelated node's embedding happened to land at their filtered
position.

**Fix:** capture each filtered drug's original index in the unfiltered
list (`_orig_index` dict) and pass those as `drug_nodes` instead of a
fresh `arange`.

**You must re-run inference for every disease after deploying this fix.**
Old `Prediction` rows in the database still reflect the old (wrong)
scores — fixing the code doesn't retroactively correct stored rows.

## C8 — `/etl/ingest/all_diseases` never triggered STRING or DGIdb

**File:** `backend/app/api/v1/endpoints/etl.py`

Docstring claimed this was "the one-shot fix for diseases showing 1 node,
0 edges," but it only queued OpenTargets + ClinicalTrials. Gene nodes
require STRING (Gene-Gene) and/or DGIdb (Drug-Gene) edges to exist at all
— this endpoint never touched either source, so `Genes (0)` was
guaranteed regardless of whether OpenTargets itself worked.

**Fix:** the endpoint now also queues one STRING job and one DGIdb job
over the shared cancer-gene panel (`_CANCER_GENES`) after looping the
per-disease jobs.

**Retracted from Round 1:** the MONDO-vs-EFO theory for why OpenTargets
returns empty associations does not hold up — Open Targets' GraphQL API
accepts MONDO-format IDs as `efoId` directly (confirmed against their own
community docs / example queries). The `opentargets.py` client code reads
correctly. If genes are still empty after this fix, check that the Celery
worker is actually running and consuming the queue
(`docker-compose logs worker`), and check `GET /etl/jobs` for
`records_processed` on the opentargets/string/dgidb jobs — that's an
operational question this sandbox can't verify without a live instance.

## C9 — Temozolomide had the wrong ChEMBL ID

**Files:** `backend/scripts/seed_initial_data.py`,
`backend/app/api/v1/endpoints/etl.py`

Seed data had Temozolomide's `chembl_id` set to `CHEMBL614`. Verified
against ChEMBL's own compound records: `CHEMBL614` is **Pyrazinamide** (a
tuberculosis drug). Temozolomide's real ID is `CHEMBL810`.

This collided with the hardcoded `_CANCER_CHEMBL_IDS` default list in
`etl.py`, which also included `CHEMBL614`. Any time the ChEMBL ETL ran
with default args, it matched the existing Temozolomide row by
`chembl_id` and silently renamed it to "PYRAZINAMIDE" — explaining why a
real glioblastoma standard-of-care drug vanished and a TB drug appeared
in its place.

**Fix:** corrected the seed `chembl_id` to `CHEMBL810`; removed `CHEMBL614`
from the default ETL list.

**Action needed on an already-seeded database:** `seed_initial_data.py` is
idempotent by `chembl_id` lookup, so re-running it will NOT retroactively
fix an existing mis-named row. Run this once against your current DB:

```sql
UPDATE drugs SET name = 'Temozolomide', chembl_id = 'CHEMBL810'
WHERE chembl_id = 'CHEMBL614';
```

(Left `CHEMBL25` / Aspirin and `CHEMBL1421` / Dasatinib in the default
list — those look like intentional negative-control / off-label
candidates rather than a data bug. Pull them out if that wasn't the
intent.)

## C10 — latent crash in the zero-embedding fallback

**File:** `backend/app/ml/predictor.py`

`predict_all_pairs()`'s Drug-embedding fallback had a literal `...`
(Ellipsis) where `device=self.device` should be — `torch.zeros(n_drug,
hidden, ...)`. This branch only fires if HGTConv produces no Drug
embeddings at all (currently doesn't happen, thanks to the reverse-edge
fix in `graph_convert.py`), so it's never been hit — but if it ever is,
it would crash with a `TypeError` instead of degrading gracefully. Fixed
to match the parallel (correct) Disease fallback on the next line.

## Still open — needs real ETL data, not a code fix

Four seeded drugs have **zero Interaction rows anywhere in the database**
(Erdafitinib, Dactinomycin, Doxorubicin, Ifosfamide), so per
`KnowledgeGraphBuilder.build_from_database()` they never become graph
nodes and can't be candidates for any disease. This isn't a bug to patch
— it's missing data. Pull real interaction evidence in for them, e.g.:

```bash
curl -X POST "http://localhost:8000/api/v1/etl/ingest/clinicaltrials" \
  -H "Authorization: Bearer $TOKEN" \
  -G --data-urlencode "condition=ewing sarcoma" \
     --data-urlencode "intervention=Ifosfamide"
```

Repeat per drug/disease pair where real-world usage exists. Fabricating
synthetic interaction edges instead would quietly corrupt the training
set, so that's left to you rather than auto-generated here.

## Verification method

These fixes were verified by static code reading (cross-referencing
`builder.py`, `graph_convert.py`, `repurposing.py`, and `predictor.py`
line-by-line) plus external verification of ChEMBL IDs and the Open
Targets API contract. All edited files pass `python -m py_compile`. This
sandbox has no Docker/network access, so none of this was exercised
against a live running instance — re-run the full pipeline (ETL →
training → inference) on your machine and treat this as a strong,
evidence-based patch rather than a tested one.
