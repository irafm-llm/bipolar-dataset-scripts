# Human-validation protocol and aggregate results

This document provides the public evidence for the human-validation claims associated with dataset version 1.1. It reports the sampling design, reviewer setup, criteria, item counts and aggregate outcomes. Raw annotation sheets and participant-level working records are retained by the authors and are not included in this compact GitHub companion.

## Design

A stratified random sample was drawn with fixed seed `20260820`: five `pair_id` values from each of the 22 categories. This produced 110 sampled templates representing 105 distinct scenarios.

Tasks A, A2, B, D and 1.1d2 assessed all 12 variants of every sampled template, or 1,320 rows per task. Task C assessed one representative `Past/ua/pos` English sentence per sampled template, or 110 sentences. Tasks A–C and A2 were completed independently by two native English speakers who were not members of the author team. Tasks D and 1.1d2 were completed independently by two native readers of Russian and two native readers of Ukrainian. A2 repeated the English-content assessment after correction; both reassessments used the same row identities and readers as their corresponding initial task.

## Tasks

| Task | Material | Items per reviewer | Judgement |
|---|---|---:|---|
| A | English content, all variants | 1,320 | Grammar/idiomaticity, symmetry, tense/opener, plausibility, category, valence, real names and offensive wording |
| A2 (`1.1a2`) | Corrected English content, all variants | 1,320 | The same eight criteria as Task A |
| B | English conduct-valence label, label hidden | 1,320 | `pos` or `neg` |
| C | English event category, label hidden | 110 | One of the 22 categories |
| D | Initial Russian or Ukrainian translation | 1,320 per language | Meaning, grammar, naturalness, nationality expression, temporal framing and valence preservation |
| 1.1d2 | Revised Russian or Ukrainian translation | 1,320 per language | The same six criteria as Task D |

Reviewers worked on separate copies and did not see each other's decisions. Agreement was calculated after joining their decisions by item identifier, never by sheet order. Raw agreement is the proportion of identical binary judgements; Cohen's kappa adjusts this value for agreement expected from the reviewers' marginal rates. For Tasks A, A2, D and 1.1d2, `ANY` means that at least one criterion was flagged for a row. Template-level counts treat a template as flagged if any of its 12 correlated rows was flagged.

## Aggregate results

| Stage | Task | Main result | Raw agreement / Cohen's kappa |
|---|---|---|---|
| Initial | A — English | 278/1,320 rows flagged by at least one reviewer and 222 by both; after template-level adjudication, 23/110 templates were confirmed for revision | 0.958 / 0.862 |
| Initial | B — valence | Both reviewers recovered 1,320/1,320 labels | 1.000 / 1.000 |
| Initial | C — category | Both reviewers recovered 110/110 labels | 1.000 / 1.000 |
| Initial | D — Russian | 454/1,320 rows (34.4%) flagged by at least one reader and 320 (24.2%) by both | 0.898 / 0.755 |
| Initial | D — Ukrainian | 425/1,320 rows (32.2%) flagged by at least one reader and 331 (25.1%) by both | 0.929 / 0.826 |
| Post-revision | A2 (`1.1a2`) — English | Neither reviewer flagged any row (0/1,320) or template (0/110) on any criterion | 1.000 / not estimable |
| Final | 1.1d2 — Russian | 36/1,320 rows (2.7%) flagged by at least one reader and 30 (2.3%) by both; all concerned naturalness | 0.995 / 0.907 |
| Final | 1.1d2 — Ukrainian | 48/1,320 rows (3.6%) flagged by at least one reader and 6 (0.5%) by both; flags concerned naturalness and six grammar judgements from one reader | 0.968 / 0.206 |

In A2, both English reviewers assigned zero problem flags across all eight criteria (0/1,320 rows; 95% CI 0.0%–0.3% for each reviewer), and no sampled template was flagged (0/110; 95% CI 0.0%–3.4%). Cohen's kappa is not estimable because neither reviewer used the problem category.

In the final translation reassessment, neither reader identified a meaning, nationality-expression, temporal-marker or conduct-valence error in either language. The lower Ukrainian kappa is a sparse-flag effect combined with different wording preferences: the reviewers agreed on 96.8% of rows but overlapped on only six rows when `ANY` criterion was considered.

At template level, final Russian text was flagged by at least one reader for 6/110 templates and by both for 5/110. Final Ukrainian text was flagged by at least one reader for 8/110 templates and by both for 1/110.

Across the six tasks, 18,700 row-level reviewer judgements were collected. Neither A2 nor 1.1d2 prompted further dataset edits.

## Interpretation

The initial results were diagnostic: confirmed English issues were addressed at template level, and the earlier translations were replaced by a complete Claude Opus 5 retranslation rather than repaired row by row. A2 found no residual English-content problem in the reviewed sample. The final translation reassessment quantifies the residual issues on the same stratified material. Its remaining flags chiefly represent preferences for alternative phrasing, while the controlled meaning, nationality, temporal and valence contrasts were preserved in the reviewed sample.

The 1,320 rows within each language task are not statistically independent because each group of 12 derives from one template. For claims about scenario-level quality, the template-level counts above are the more conservative summary. The results describe a stratified sample rather than a full semantic review of all 26,400 rows; complete-corpus claims are limited to the structural properties covered by the automated validators.
