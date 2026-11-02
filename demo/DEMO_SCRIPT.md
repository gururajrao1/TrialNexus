# TrialNexus demo video — shot list (~7 minutes)

Open `http://127.0.0.1:8000`, hard-refresh (`Ctrl+F5`), hit **Run full workup**.
Say: *"TrialNexus is a clinical-trial operations workspace that runs entirely
on our machines — protocol, sites, patients, safety — with live registry,
genomic, and regulatory data piped in, and everything cited."*

## Shot 1 — Protocol audit (60s)

*Do:* 01 Protocol audit → **Audit PDF** → upload `demo/protocol_demo.pdf` → Run.
*Say:* "A real protocol document in — coded rules out."
*Proof on screen:* 4 INC + 3 EXC as tables, fragility index, amendment
exposure dollars, burden matrix. Point at one clash if shown.

## Shot 2 — Site feasibility (75s)

*Do:* 04 Site feasibility → **Site file** → upload `demo/sites.json` →
target 450 → run with live CT.gov **off**.
*Say:* "Three invented sites, three verdicts."
*Proof:* DEMO-GO **GO (90.0)**, DEMO-MID **CONDITIONAL (57.7)**,
DEMO-WEAK **NO-GO (27.2)**, each with the 35/25/20/20 math.
*Then:* tick live CT.gov on, re-run.
*Say:* "And now the same math against the real registry — live competitor
counts, cached for offline." Scroll to the recruiting-studies box with
cities.

## Shot 3 — Cohort + worklist (90s)

*Do:* 07 Cohort matching → tick all bundles → Match. Then scroll to the
**prescreen workup queue** → Run worklist.
*Say:* "Matching tells us who is eligible. The worklist tells the coordinator
what to do Monday morning."
*Proof:* REVIEW_REQUIRED, REVIEW_REQUIRED, ELIGIBLE in that order; the
known-ineligible bundle correctly excluded. Click an EGFR gene chip.
*Say:* "Every biomarker carries its live evidence — function, curation,
variants."

## Shot 4 — Safety (90s)

*Do:* 12 Safety triage → **Safety file** → upload `demo/ae_records.json` → Triage.
*Say:* "Three reports in — one serious event, two routine."
*Proof:* DEMO-SAE-1 stamped **SAE, Grade 4** with expedited clock and drafted
query; the other two routine. Run signal screen → point at the FAERS
reality-check line with live report counts.
*Then:* **Query file** → upload `demo/queries.json` → Route queries.
*Proof:* DEMO-Q-OLD stamped **critical**, months overdue, owner-assigned;
the resolved query correctly excluded.

## Shot 5 — Deviation watch (45s)

*Do:* 06 Monitoring → **Visit file** → upload `demo/visits.json` → Screen.
*Say:* "Four visits, three findings the listing review would catch weeks late."
*Proof:* out-of-window major, missing-assessment major, consent-violation
critical, both sites tiered **100% critical fields**.

## Shot 6 — CRF trace (30s)

*Do:* Safety tab → **CRF coverage trace** → paste `demo/ecrf_fields.txt` → Trace.
*Say:* "Three fields against nine criteria — the missing rows are data we
would never capture."
*Proof:* 1 covered / 8 missing matrix.

## Close (20s)

*Say:* "Every number on screen is deterministic and cited — same input, same
result. Live sources are badged live, cache, or fallback, so you can always
see what is real. The seeds are placeholders; your protocol, your sites,
your patients slot straight into the same boxes."
