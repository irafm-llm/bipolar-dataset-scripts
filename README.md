# MIRROR-EN-UA-RU — GitHub companion for dataset version 1.2

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20641321.svg)](https://doi.org/10.5281/zenodo.20641321)

This is the compact code and documentation companion to **MIRROR-EN-UA-RU: Synthetic trilingual minimal-pair sentences for nationality and language bias evaluation in large language models**. The canonical dataset is the Zenodo record at [10.5281/zenodo.20641321](https://doi.org/10.5281/zenodo.20641321). The repository is [irafm-llm/bipolar-dataset-scripts](https://github.com/irafm-llm/bipolar-dataset-scripts), and the Git tag for this release is `dataset-v1.2`.

The 35 files of the Zenodo record (22 category CSV files and 13 supporting files) are deliberately not duplicated here. Download them from Zenodo; the SHA-256 values of all files except the checksum file itself (34 entries) are recorded in [`release-metadata/dataset_checksums.sha256`](release-metadata/dataset_checksums.sha256). The label `1.1d2` refers only to the final human reassessment, not to another dataset version.

## Contents

```text
README.md                  this guide
CITATION.cff               citation metadata
LICENSE                    MIT licence for the code
MANIFEST.sha256            checksums for this compact companion
release-metadata/          release provenance, data dictionary and concise reports
scripts/tools/             structural, duplicate, template and entity checks
scripts/validation/        independent full-corpus validation
scripts/generator/         generator for candidate future versions
scripts/run_all.sh         one-command validation of a downloaded release
```

The companion is intentionally small. It excludes the dataset CSV files already archived on Zenodo, raw annotator sheets, participant-level records, pilot material, historical repair scripts, raw model transcripts and regenerable row-level reports. The human-validation protocol and the aggregate results needed to assess the claims are retained in [`release-metadata/HUMAN_VALIDATION.md`](release-metadata/HUMAN_VALIDATION.md).

## Released data

Version 1.2 (data identical to version 1.1) contains 22 category CSV files, 26,400 rows and 79,200 sentences across English, Russian and Ukrainian. The design has 2,200 `pair_id` templates grouped into 810 scenarios, with 415 distinct entity types and 1,308 category–entity combinations. Each template expands to 12 rows: three timeframes, two nationality sides and two conduct-valence labels. The Zenodo record also contains the entity inventory, templates, data dictionary, provenance documents, aggregate human-validation results, checksums and validation report.

All CSV files are UTF-8 without a byte-order mark. The released version uses CRLF line endings. If Excel does not detect Cyrillic correctly, import the file through *Data → From Text/CSV* and select UTF-8.

## Versions

| Version | Released | DOI | Notes |
|---|---|---|---|
| 1.2 (current) | October 2026 | [10.5281/zenodo.23655445](https://doi.org/10.5281/zenodo.23655445) | Documentation update; all data files byte-identical to version 1.1 |
| 1.1 | 1 September 2026 | [10.5281/zenodo.22125432](https://doi.org/10.5281/zenodo.22125432) | English revised after human review; all Russian and Ukrainian sentences translated anew with Claude Opus 5 from the corrected English sources |
| 1.0 | 11 June 2026 | [10.5281/zenodo.20641322](https://doi.org/10.5281/zenodo.20641322) | Initial release; Microsoft Translator for 19 files, no Russian and Ukrainian columns in `112-accuse`, `16-reduce_relations` and `19-fight` |

The concept DOI [10.5281/zenodo.20641321](https://doi.org/10.5281/zenodo.20641321) always resolves to the latest version. All `pair_id`s and labels are stable across versions, but the English text changed in 1,247 of the 2,200 templates between versions 1.0 and 1.1 (not counting letter-case-only changes), so results obtained with version 1.0 are not directly reproducible from later versions. The experiments reported in the BIPOLAR research article (https://doi.org/10.1016/j.tcs.2026.116117) used dataset version 1.0 (English sentences, present temporal frame, 18 categories; 7,200 statements), available in [irafm-llm/bipolar](https://github.com/irafm-llm/bipolar).

## Verify and validate

Requirements are Python 3.10 or later and standard Unix checksum utilities. The validation code uses only the Python standard library.

After downloading and unpacking all 35 Zenodo files into one directory, run:

```bash
cd /path/to/zenodo-download
sha256sum -c /path/to/this-repository/release-metadata/dataset_checksums.sha256

/path/to/this-repository/scripts/run_all.sh \
  /path/to/zenodo-download \
  /tmp/mirror-validation
```

To verify the GitHub companion itself, run `sha256sum -c MANIFEST.sha256` from its root. The first command above verifies byte identity with the canonical dataset release. The second runs the two validators, duplicate analysis, template reconstruction, entity statistics and temporal-opener checks. It also compares the reconstructed templates with the archived `templates.csv`. Any failed check terminates the run with a non-zero exit status.

The compact reports supplied with this repository describe the already validated release:

- [`validation_report.md`](release-metadata/validation_report.md): complete factorial, symmetry, uniqueness and translation-integrity checks;
- [`duplicate_analysis_summary.md`](release-metadata/duplicate_analysis_summary.md): exact, normalized and near-duplicate findings;
- [`templates_summary.md`](release-metadata/templates_summary.md): template and scenario counts;
- [`entity_statistics_summary.md`](release-metadata/entity_statistics_summary.md): entity distribution and concentration;
- [`HUMAN_VALIDATION.md`](release-metadata/HUMAN_VALIDATION.md): protocol and aggregate A–D, A2 (1.1a2) and D2 (1.1d2) results.

## Generator scope

[`scripts/generator/generate_dataset.py`](scripts/generator/generate_dataset.py) is the scripted and logged workflow created for reproducible generation of candidate future versions. It proposes entities and templates through an OpenRouter-compatible model, performs deterministic factorial expansion, optionally translates the expanded material and runs the release checks. Its prompts and configuration are included beside the script.

The released data (version 1.1, unchanged in version 1.2) were not produced by this script. Their English material originated in an interactive ChatGPT session, was revised after human review, and their Russian and Ukrainian columns were translated anew from the corrected English sources with Claude Opus 5. That history is documented in [`GENERATION_LOG.md`](release-metadata/GENERATION_LOG.md) and [`CHANGELOG.md`](release-metadata/CHANGELOG.md). The generator is provided to make future construction auditable, not to imply exact regeneration of the released data.

To reproduce the released data (versions 1.1 and 1.2) from the archived templates without an API call:

```bash
python3 scripts/generator/generate_dataset.py \
  --out /tmp/mirror-reexpanded \
  --from-templates /path/to/zenodo-download/templates.csv \
  --release /path/to/zenodo-download
```

For a new model-generated candidate, set `OPENROUTER_API_KEY` and consult `--help`. Model snapshots and routing can change, so exact replay requires the cache and manifest produced by that run.

## Human validation

Six validation tasks used a fixed stratified sample of 110 templates. Tasks A–C and the post-correction English reassessment A2 (1.1a2) were performed independently by two native English speakers who were not members of the author team. Task D and the final translation reassessment D2 (1.1d2) were performed independently by two native readers per language. The final round reused the same item identities and readers as initial Task D, allowing a direct before-and-after comparison after the English revision and complete retranslation.

Raw sheets are not part of this compact public companion. The public record instead gives the sample design, criteria, counts and agreement statistics needed to assess the reported validation; excluding row-level sheets avoids publishing participant-level working records. The authors retain the source annotation records. See [`HUMAN_VALIDATION.md`](release-metadata/HUMAN_VALIDATION.md) for the complete public summary.

## Provenance, limitations and contamination

The data are fully synthetic and fictional. They reflect the styles and scenario choices of the generating models and should not be treated as naturally occurring language. The repository documents the generator history, translation protocol, revision history and automated checks, but semantic and naturalness judgements remain human assessments.

Because public benchmark material can enter future training corpora, report the evaluated model's training cut-off and consider scenario-disjoint evaluation. The release canary is `MIRROR-EN-UA-RU-CANARY-7f3a9c2e`.

## Licences and citation

The scripts are released under the MIT Licence in [`LICENSE`](LICENSE). The dataset is released under CC BY 4.0; see [`release-metadata/DATA_LICENSE.txt`](release-metadata/DATA_LICENSE.txt) and the Zenodo record.

Please cite both the dataset DOI and the accompanying data article. Machine-readable metadata are provided in [`CITATION.cff`](CITATION.cff).
