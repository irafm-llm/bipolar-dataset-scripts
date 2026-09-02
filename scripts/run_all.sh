#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 DATA_DIRECTORY [OUTPUT_DIRECTORY]" >&2
    exit 2
fi

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
data_dir=$(CDPATH= cd -- "$1" && pwd)
output_arg=${2:-validation-output}
mkdir -p "$output_arg"
output_dir=$(CDPATH= cd -- "$output_arg" && pwd)

export PYTHONDONTWRITEBYTECODE=1

python3 "$script_dir/validation/validate_all.py" "$data_dir" \
    | tee "$output_dir/validation_full.txt"

python3 "$script_dir/tools/validate_dataset.py" \
    --dir "$data_dir" \
    --version v1.1 \
    --report "$output_dir/validation_report.md"

python3 "$script_dir/tools/check_duplicates.py" \
    --dir "$data_dir" \
    --out "$output_dir"

python3 "$script_dir/tools/extract_templates.py" \
    --dir "$data_dir" \
    --out "$output_dir/templates.csv"

cmp "$output_dir/templates.csv" "$data_dir/templates.csv"

python3 "$script_dir/tools/entity_statistics.py" \
    --dir "$data_dir" \
    --out "$output_dir"

python3 "$script_dir/tools/check_openers.py" \
    --dir "$data_dir" \
    > "$output_dir/opener_check.txt"

(
    cd "$data_dir"
    sha256sum -c "$repo_dir/release-metadata/dataset_checksums.sha256"
) | tee "$output_dir/checksums.txt"

echo "All checks passed. Reports: $output_dir"
