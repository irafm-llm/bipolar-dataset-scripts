# Changelog

## 1.1 (September 2026) — peer-review revision and final quality consolidation

Version 1.1 is the current public release. All `pair_id`, category, timeframe, side and sentiment labels remain compatible with version 1.0.

### English sources

- Human Task A identified recurring problems involving verb tense, grammar, actor plausibility and attribution of the described conduct.
- The complete English corpus was screened for those patterns and corrected at template level while preserving identifiers and the factorial minimal-pair design.
- Subsequent trilingual quality checks resolved remaining reproducible source, actor-role and cross-language consistency problems before the final human reassessment.
- `templates.csv` and `entity_inventory.csv` were rebuilt from the final data. The release contains 2,200 templates, 810 scenarios, 1,304 category/entity combinations and 410 distinct entity types.

### Russian and Ukrainian

- The initial Microsoft Translator output was superseded.
- Final Russian and Ukrainian translations were produced from the corrected English sources using Claude Opus 5 under fixed rules for meaning, temporal framing, conduct valence, nationality expression and nationality-pair symmetry.
- Corpus-wide consistency checks established one canonical rendering per temporal opener and entity type and one Russian/Ukrainian predicate per scenario cell. All 13,200 nationality pairs are identical within each language apart from the nationality expression.
- The final native-speaker reassessment is deposited as annotation round **1.1d2**. Rows flagged by at least one reader were 36/1,320 (2.7%) for Russian and 48/1,320 (3.6%) for Ukrainian. No meaning, nationality, temporal or conduct-valence problems were reported. No changes were made to the dataset after 1.1d2.

### Documentation and validation

- Added `templates.csv`, `data_dictionary.csv`, `data_dictionary.json`, `GENERATION_LOG.md`, `validation_report.md`, `checksums.sha256`, `LICENSE.txt`, `CITATION.cff` and this README/changelog package.
- Automated validation now covers all 26,400 rows and the documented between-row consistency rules. The final release reports zero failures and no exact or normalized duplicate sentences.
- Validation code, the annotation protocol and aggregate human-validation results are maintained in the matching GitHub release. Participant-level working records and detailed correction files are retained by the authors rather than published in the compact repository.

## 1.0 (11 June 2026) — initial release

The initial Zenodo release contained the 22 category files, `entity_inventory.csv` and `prompts.txt`. Nineteen files used Microsoft Translator; three later-generated category files did not have complete released translations. DOI: 10.5281/zenodo.20641322.
