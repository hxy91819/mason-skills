#!/bin/sh
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
output_dir=${1:-"$source_dir/dist"}
mkdir -p "$output_dir"
"${CC:-cc}" -std=c11 -O2 -fPIC -fvisibility=hidden -Wall -Wextra -Werror \
  -shared "$source_dir/plugin.c" -o "$output_dir/cpa-muse-full-models.so"
printf '%s\n' "$output_dir/cpa-muse-full-models.so"
