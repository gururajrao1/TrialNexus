# Credibility dossiers — TrialNexus OS panels

One card per panel, following the FDA January-2025 draft credibility
framework skeleton (question of interest, context of use, risk, validation,
adequacy verdict) as **non-binding guidance applied to deterministic
rules-based tooling** — not a compliance claim, not a clearance, not an
ML validation package.

Codebase: TrialNexus OS `main` (re-validate on any code, weight, or
seed-data change). Seed data: `demo/` + `data/fhir/synthea/` + seeded DB.
No real PHI ships with the product. Live sources (CT.gov, PubMed, openFDA)
degrade live → cache → offline-fallback and always carry a source chip.

## Cards

- [01 audit](01-audit-protocol.md) · [02 sites](02-site-feasibility.md) ·
  [03 cohort](03-cohort-matching.md) · [04 safety](04-safety-triage.md) ·
  [05 diversity](05-diversity-plan.md) · [06 history](06-history-export.md) ·
  [07 startup](07-study-startup.md) · [08 monitoring](08-monitoring.md) ·
  [09 finder](09-find-trials.md) · [10 external](10-external-control.md) ·
  [11 twins](11-synthetic-twins.md) · [12 mcode](12-mcode-summary.md) ·
  [13 validity](13-model-validity.md) · [14 llm-rationale](14-llm-rationale.md)

## Never-claims (apply to every card)

1. Twins, forecasts, fragility/exposure dollars, and PRR/ROR screens are
   planning math, never clinical evidence of efficacy, safety, or
   approvability.
2. Matcher/finder output is prescreen triage, never an enrollment or
   eligibility decision — a clinician signs every decision.
3. SAE flags never replace expedited-reporting judgment or regulatory
   filing — the tool clocks and drafts, a human files.
4. Synthetic seeds prove plumbing, never real-patient validation — the
   n2c2 fixture plus the DUA full-data path is the external benchmark.
5. Live CT.gov/PubMed/openFDA outputs are never claimed current or
   complete — every live number carries its source chip.
6. No EU AI Act conformity, FDA endorsement, or validated-SaMD status is
   claimed — cited frameworks are draft or non-binding guidance.
7. No air-gap claim while live lookups are enabled — the network
   exception is stated on every live panel.
