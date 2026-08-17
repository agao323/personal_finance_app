#!/usr/bin/env bash
#
# Fail if the browser is given a way to address the API directly.
#
# The browser talks only to the Next.js origin, which proxies over the private
# network. That is what makes the origin lock structural, removes CORS entirely, and
# keeps Cloudflare Access to a single application. A NEXT_PUBLIC_API_URL — or any
# hardcoded API origin in client code — silently undoes all three.
#
# See docs/ARCHITECTURE.md#request-path.
#
# Usage: check_no_public_api_url.sh [directory]   (default: web)

set -euo pipefail

target="${1:-web}"

if [[ ! -d "$target" ]]; then
  echo "check_no_public_api_url: no such directory: $target" >&2
  exit 2
fi

status=0

# 1. Any *use* of the env var — read in code, or assigned in config.
#
# Deliberately not a bare name match: the doc comments in api.ts and this script
# name the variable in order to explain why it must not exist. A guard that fires on
# its own rationale gets silenced, so it matches the two forms that could actually
# introduce it instead.
if matches=$(grep -rEn \
  --include='*.ts' --include='*.tsx' --include='*.js' --include='*.mjs' \
  --include='*.json' --include='*.yaml' --include='*.yml' --include='*.env*' \
  --exclude-dir=node_modules --exclude-dir=.next \
  '(process\.env\.|env\.)NEXT_PUBLIC_API_URL|^[[:space:]]*(-[[:space:]]*)?NEXT_PUBLIC_API_URL[[:space:]]*[:=]' \
  "$target" 2>/dev/null); then
  echo "check_no_public_api_url: NEXT_PUBLIC_API_URL found." >&2
  echo "$matches" >&2
  status=1
fi

# 2. A hardcoded API origin in application code.
#
# Test files are excluded on purpose: api.test.ts asserts that apiFetch *rejects*
# absolute URLs, so it necessarily contains some. Excluding them keeps the guard
# honest rather than forcing the test to obfuscate its own fixture.
if matches=$(grep -rEn \
  --include='*.ts' --include='*.tsx' \
  --exclude='*.test.ts' --exclude='*.test.tsx' \
  --exclude-dir=node_modules --exclude-dir=.next \
  'https?://[a-z0-9._-]*(api|localhost|127\.0\.0\.1)[a-z0-9._-]*(:[0-9]+)?' \
  "$target/src" 2>/dev/null); then
  echo "check_no_public_api_url: hardcoded API origin in client code." >&2
  echo "$matches" >&2
  status=1
fi

if [[ $status -ne 0 ]]; then
  echo "" >&2
  echo "The browser must never address the API directly." >&2
  echo "See docs/ARCHITECTURE.md#request-path." >&2
  exit 1
fi

echo "check_no_public_api_url: ok ($target)"
