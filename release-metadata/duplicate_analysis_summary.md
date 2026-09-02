# Duplicate-analysis summary

The released version 1.1 was screened across all 26,400 rows in each of its three language columns.

| Check | English | Russian | Ukrainian |
|---|---:|---:|---:|
| Exact duplicate surplus rows, within files | 0 | 0 | 0 |
| Exact duplicate surplus rows, full corpus | 0 | 0 | 0 |
| Normalized duplicate surplus rows, within files | 0 | 0 | 0 |
| Normalized duplicate surplus rows, full corpus | 0 | 0 | 0 |

After the temporal opener, nationality expression and entity type were masked, 2,463 frames were shared by different `pair_id` values. This is expected from the design: 2,200 templates instantiate 810 underlying scenarios using different entities and openers. Frame reuse is therefore reported as a structural property, not counted as duplicate released sentences.

No near-duplicate frame pairs were found at token-set Jaccard similarity of 0.9 or higher within the comparison blocks used by the checker. The complete row-level listing is omitted because it is large and can be regenerated with:

```bash
python3 scripts/tools/check_duplicates.py \
  --dir /path/to/zenodo-download \
  --out /tmp/mirror-duplicates
```
