# Automated validation report for MIRROR-EN-UA-RU version 1.1

Files: 22  Rows: 26400  Failures: 0

| File | Rows | pair_ids | Complete pairs (12/12) | Side-sym. EN pairs | Side-sym. RU/UK pairs | Unique EN | Unique RU | Unique UK | Failures |
|---|---|---|---|---|---|---|---|---|---|
| 01-make_statement.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 02-appeal.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 03-cooperate.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 04-consult.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 05-engage_in_diplomatic_cooperation.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 06-engage_in_material_cooperation.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 07-provide_aid.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 08-yield.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 09-investigate.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 10-demand.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 11-approve.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 11-disapprove.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 112-accuse.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 12-reject.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 13-threaten.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 14-protest.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 15-exhibit_force.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 16-reduce_relations.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 17-coerce.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 18-assault.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 19-fight.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |
| 20-mass_violence.csv | 1200 | 100 | 100/100 | 600/600 | 600/600 | 1200/1200 | 1200/1200 | 1200/1200 | 0 |

## Between-row checks

| check | result |
|---|---|
| one Russian and one Ukrainian predicate per (`scenario_id`, `timeframe`, `sentiment`) | pass (4,860 cells) |
| RU/UK future aspect parallel | pass (8,800 Future rows) |
| past-tense verb agrees with the actor's gender and number | pass |
| single apostrophe codepoint in `uk` (U+0027) | pass |
| one Cyrillic rendering per English temporal opener, all 30 distinct per language | pass |
| one Russian and one Ukrainian rendering per `entity_type` | pass |
| no comma between the temporal opener and the nationality adjective | pass |
| `NGO` rendered as RU `НПО` / UK `НУО` | pass |
| `19-fight` main verb uniform across the file | pass |

From the root of the matching GitHub release, reproduce this report with
`scripts/run_all.sh /path/to/zenodo-download /tmp/mirror-validation`. The validator includes
the within-row, mirror, scenario-cell, tense, terminology and agreement checks used for this
release.
