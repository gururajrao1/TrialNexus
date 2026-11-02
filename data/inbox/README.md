# Your inbox — the app's memory of your files

The internet gives TrialNexus registries, genes, drugs, and literature.
**You** give it your study. Drop files here once; every panel offers a
**Load my …** button that pulls them in. Nothing here is ever uploaded
anywhere, and nothing here touches the database — files are read on demand.

## What goes where

| File | Panel that reads it | Format |
|---|---|---|
| `bundles/*.json` | 07 Cohort matching (ticked like seeds) + 08 Find trials + 10 External control | FHIR Bundle JSON, one per file, named `inbox/<file>` |
| `sites.json` | 04 Site feasibility | JSON list: id, name, country, historical_activation_days, regulatory_tier, active_competing_trials, past_accrual_per_month, staff_capacity_score |
| `ae_records.json` | 12 Safety triage | JSON list: discrepancy_id, patient_id, reported_term, description, severity (MILD/MODERATE/SEVERE), suspect_drug |
| `visits.json` | 06 Monitoring → deviation watch | JSON list: site_id, subject, visit, planned_day, actual_day, assessments_required[], assessments_done[], consent_date, visit_date (YYYY-MM-DD) |
| `queries.json` | 12 Safety → query aging | JSON list: id, created_at (`YYYY-MM-DD HH:MM:SS`), resolution_status (OPEN/RESOLVED), is_sae |
| `ecrf_fields.txt` | 12 Safety → CRF trace | One field name per line |

Copy the shapes from `demo/` — same columns, your data.

## Privacy rules (enforced, not suggested)

- Everything under this folder is **git-ignored**. It can never be committed
  or pushed. De-identified data only, regardless.
- The app never sends inbox contents anywhere: all analysis is local
  functions plus the same public lookups (CT.gov, ClinVar, OpenFDA) the
  demo uses. Uploaded FHIR bundles live in page memory and die on refresh.
- Protocols stay yours: pick the PDF from disk each time in 01 Protocol
  audit. Nothing is stored.
