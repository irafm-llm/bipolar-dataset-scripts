# Generation and revision log

This document records the principal stages used to construct MIRROR-EN-UA-RU version 1.1. It is a consolidated methodological record, not a turn-by-turn transcript of the original ChatGPT interaction.

## 1. Design and English generation (February 2026)

The event taxonomy was based on the 20 top-level CAMEO categories, the subcategory Accuse (112), and an added Approve category. English scenarios were generated with OpenAI GPT-5.4 through the ChatGPT Projects interface on 22 February 2026. The instructions specified actor roles, positive and negative conduct, past/present/future frames and exact Ukrainian/Russian nationality symmetry.

For each of 22 categories, 100 parameterized templates were expanded over two nationalities, two conduct-valence conditions and three temporal frames. This produced 1,200 rows per category and 26,400 rows overall. Some generated categories were regenerated during preparation when their scenario or actor diversity was insufficient. The retained templates represent 810 distinct scenarios.

## 2. Initial translation and release

Nineteen category files were initially translated with the Microsoft 365 Excel `TRANSLATE` function. Three files completed later in the construction process were translated separately with Claude Opus 5 for the validation material. The initial Zenodo release was published as version 1.0 on 11 June 2026 (10.5281/zenodo.20641322).

## 3. Human validation before revision

Five `pair_id`s were sampled from each category using seed 20260820, yielding 110 templates. Tasks A, B and D assessed all 12 variants of each template (1,320 rows); Task C assessed one representative English sentence per template (110 sentences).

- Task A reviewed English grammar, structure and meaning. After adjudication, 23 of the 110 sampled templates contained a confirmed correctable defect.
- Tasks B and C reproduced all conduct-valence labels (1,320/1,320) and event-category labels (110/110) under blinded conditions.
- Task D compared the initial Russian and Ukrainian translations with their English sources. Rows flagged by at least one reader were 454/1,320 (34.4%) in Russian and 425/1,320 (32.2%) in Ukrainian.

## 4. English revision and final translation

The recurring English problems identified in Task A were screened across the full corpus. Corrections focused on tense, grammar, actor plausibility and attribution of conduct and were applied consistently at template level. Identifiers, labels and nationality contrasts were preserved.

Russian and Ukrainian were then translated anew from the corrected English sources using Claude Opus 5. Translation rules required faithful meaning, preservation of conduct valence and temporal framing, a nationality adjective attached to the actor role, and identical surrounding wording within nationality pairs. Within each target language, the Ukrainian-actor variant was translated first and the Russian-actor variant was derived by controlled substitution of the nationality adjective.

Before final reassessment, corpus-wide checks consolidated recurring terminology, actor-role renderings, temporal openers and scenario predicates and corrected reproducible trilingual defects. The final corpus contains one Russian and one Ukrainian rendering per entity type and temporal opener and one predicate per (`scenario_id`, `timeframe`, `sentiment`) cell.

## 5. Post-revision human reassessments (1.1a2 and 1.1d2)

The English-content reassessment reused the same 1,320 row identities, two native English reviewers and eight criteria as Task A after the corpus-wide corrections. It is reported as **1.1a2** (Task A2). Neither reviewer flagged any row or template on any criterion; raw agreement was 1.000, while Cohen's kappa is not estimable because no problem flags were assigned.

The final translation reassessment reused the same 1,320 row identities, native readers and six criteria as Task D. It is identified in the GitHub repository as **1.1d2**.

- Russian: 36 rows (2.7%) flagged by at least one reader and 30 (2.3%) by both; raw agreement 0.995, Cohen's κ 0.907.
- Ukrainian: 48 rows (3.6%) flagged by at least one reader and 6 (0.5%) by both; raw agreement 0.968, Cohen's κ 0.206.
- No problems were reported for meaning, nationality expression, temporal framing or conduct-valence preservation. Remaining flags concerned naturalness and six Ukrainian grammar instances.

The proposed alternative formulations are retained in the authors' audit records. Neither A2 nor D2 prompted further dataset rewriting.

## 6. Final automated validation and reproducibility material

The final validators check schema, factorial completeness, labels, uniqueness, nationality symmetry, temporal openers, Cyrillic integrity, actor-role terminology, scenario-level translation identity and selected grammatical invariants. All 26,400 rows pass.

The GitHub release provides the annotation protocol, aggregate human-validation results and validation tools. Participant-level sheets and detailed correction records remain in the authors' audit archive. A scripted API generator was developed after the original interactive generation. It supports auditable construction of comparable future datasets and deterministic re-expansion from deposited templates, but it cannot reproduce the original conversational generation exactly because its decoding parameters and platform instructions were not under experimental control.
