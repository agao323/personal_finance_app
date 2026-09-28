#!/usr/bin/env bash
#
# Fail if a model provider's key could reach anything but the private API.
#
# The advisor's key exists only as a Fly secret on pfa-api (docs/ADVISOR.md#request-path).
# The web app is the public surface, and the demo must be structurally unable to call a
# model (ADR 0014) — so an ANTHROPIC_* name, or the Anthropic SDK, in web/ or in the web or
# demo Fly configs is a key one step from somewhere it must never be.
#
# **Comments are stripped before matching.** The demo guard's own explanation once matched
# its grep; a guard that fires on its rationale gets silenced. Markdown is not scanned for
# the same reason. Matches print as file and line only — never the line, which could be a key.
#
# Usage: check_no_model_key_outside_api.sh [repo root]   (default: .)

set -euo pipefail

root="${1:-.}"
pattern='ANTHROPIC|@anthropic-ai/'

strip_comments() {
  case "$1" in
    *.ts | *.tsx | *.js | *.jsx | *.mjs | *.cjs | *.mts)
      # Block comments, then line comments not preceded by ':' (so https:// survives).
      perl -0pe 's{/\*.*?\*/}{}gs; s{(^|[^:])//[^\n]*}{$1}gm' "$1"
      ;;
    *.toml | *.yml | *.yaml | *.sh | *.env | *.env.* | .env* | Dockerfile*)
      sed -E 's/(^|[[:space:]])#.*$/\1/' "$1"
      ;;
    *)
      cat "$1"
      ;;
  esac
}

files=()
if [[ -d "$root/web" ]]; then
  while IFS= read -r -d '' file; do
    files+=("$file")
  done < <(find "$root/web" \( -name node_modules -o -name .next -o -name coverage \) -prune \
    -o -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
    -o -name '*.mjs' -o -name '*.cjs' -o -name '*.mts' -o -name '*.json' -o -name '*.toml' \
    -o -name '*.yml' -o -name '*.yaml' -o -name '.env*' -o -name 'Dockerfile*' \) -print0)
fi
for config in fly.web.toml fly.demo-api.toml fly.demo-web.toml; do
  [[ -f "$root/$config" ]] && files+=("$root/$config")
done

status=0
for file in "${files[@]}"; do
  if lines=$(strip_comments "$file" | grep -nE "$pattern" | cut -d: -f1 | paste -sd, -); then
    echo "check_no_model_key_outside_api: ${file#"$root"/} line(s) $lines" >&2
    status=1
  fi
done

if [[ $status -ne 0 ]]; then
  echo "" >&2
  echo "A model provider's key or SDK outside the private API. The key lives only as a Fly" >&2
  echo "secret on pfa-api; the web app and the demo must never be able to hold one." >&2
  exit 1
fi

echo "check_no_model_key_outside_api: ok (${#files[@]} files)"
