# Demo kit — known-answer files for the TrialNexus demo video

All files are synthetic and clearly labeled DEMO-. Expected outputs were
verified against the app on 2026-11-02; the runbook quotes them.

| File | What it proves |
|---|---|
| `protocol_demo.pdf` | Upload → 4 INC + 3 EXC coded, fragility + exposure scored. Regenerate with `python demo/make_protocol_pdf.py` (stdlib only). |
| `sites.json` | Score → DEMO-GO **GO (90.0)**, DEMO-MID **CONDITIONAL (57.7)**, DEMO-WEAK **NO-GO (27.2)** with manual counts. Toggle live CT.gov afterwards to show real competitors moving the numbers. |
| `ae_records.json` | Triage → DEMO-SAE-1 flagged **SAE, Grade 4** with clock + drafted query; other two routine. The osimertinib SAE also fires the live FAERS reality check. |
| `visits.json` | Screen → s-01 out-of-window major (10d), s-02 missing assessment major, s-03 consent-violation critical; clean s-04 silent. Both sites tiered **100% critical fields**. |
| `queries.json` | Route → DEMO-Q-OLD **critical** (site coordinator, months overdue), DEMO-Q-NEW on-track, DEMO-Q-DONE excluded. The old query stays critical forever, so this demo never expires. |
| `ecrf_fields.txt` | Trace → 1 covered / 8 missing against PROT-TNX-001. Every missing row is a data point the CRF never captures. |
| Seed FHIR bundles (`data/fhir/synthea/`) | Worklist → REVIEW_REQUIRED, REVIEW_REQUIRED, ELIGIBLE in that order; the known-ineligible bundle is correctly excluded. |
