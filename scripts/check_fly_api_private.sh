#!/usr/bin/env bash
#
# Fail if the API's Fly config would make it publicly addressable.
#
# The origin lock in this project is structural, not configural: the API has no
# public address, so there is nothing for Cloudflare Access to sit in front of and
# nothing to leave unprotected. A Fly app becomes public when it declares an
# [http_service] or [[services]] block and receives an IP. This guard makes adding
# one a failed build rather than a quiet change in blast radius.
#
# See docs/ARCHITECTURE.md#request-path and docs/adr/0001-hosting.md.
#
# Usage: check_fly_api_private.sh [fly.api.toml]

set -euo pipefail

config="${1:-fly.api.toml}"

if [[ ! -f "$config" ]]; then
  echo "check_fly_api_private: no such file: $config" >&2
  exit 2
fi

# Strip comments so the explanation above a rule never trips the rule.
body=$(sed 's/#.*//' "$config")

status=0

if grep -qE '^[[:space:]]*\[\[services\]\]' <<<"$body"; then
  echo "check_fly_api_private: [[services]] block found in $config" >&2
  status=1
fi

if grep -qE '^[[:space:]]*\[http_service' <<<"$body"; then
  echo "check_fly_api_private: [http_service] block found in $config" >&2
  status=1
fi

if grep -qE '^[[:space:]]*ports[[:space:]]*=' <<<"$body"; then
  echo "check_fly_api_private: a ports declaration found in $config" >&2
  status=1
fi

if [[ $status -ne 0 ]]; then
  echo "" >&2
  echo "The API must be reachable only over Fly's private network." >&2
  echo "See docs/ARCHITECTURE.md#request-path." >&2
  exit 1
fi

echo "check_fly_api_private: ok ($config declares no public service)"
