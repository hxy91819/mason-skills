#!/usr/bin/env bash
set -euo pipefail

expected='hello from orchestrated worker'
actual=$(cat greeting.txt)
[[ "$actual" == "$expected" ]]
printf '%s\n' 'greeting check passed'
