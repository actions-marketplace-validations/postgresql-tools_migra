#!/usr/bin/env bash
set -euo pipefail

# Direct invocation mode (docker run <image> postgres://...)
if [[ -z "${GITHUB_OUTPUT:-}" ]] && [[ -z "${MIGRA_BASE_URL:-}" ]] && [[ -z "${MIGRA_BASE_FILE:-}" ]]; then
  exec migra "$@"
fi

# GitHub Actions mode
ARGS=()

if [[ -n "${MIGRA_BASE_FILE:-}" && -n "${MIGRA_HEAD_FILE:-}" ]]; then
  ARGS+=(--from-file "$MIGRA_BASE_FILE" "$MIGRA_HEAD_FILE")
elif [[ -n "${MIGRA_BASE_URL:-}" ]]; then
  ARGS+=("${MIGRA_BASE_URL}" "${MIGRA_HEAD_URL:-}")
else
  echo "::error::Either base_url+head_url or base_file+head_file must be set."
  exit 1
fi

[[ -n "${MIGRA_SCHEMA:-}" ]] && ARGS+=(--schema "$MIGRA_SCHEMA")
[[ "${MIGRA_OUTPUT_FORMAT:-sql}" == "json" ]] && ARGS+=(--output json)

OUTPUT=$(migra "${ARGS[@]}" 2>/dev/null || true)

if [[ -z "$OUTPUT" ]]; then
  echo "has_changes=false" >> "$GITHUB_OUTPUT"
  echo "has_destructive_operations=false" >> "$GITHUB_OUTPUT"
else
  echo "has_changes=true" >> "$GITHUB_OUTPUT"
  if echo "$OUTPUT" | grep -qiE '^\s*(DROP TABLE|DROP COLUMN|TRUNCATE)'; then
    echo "has_destructive_operations=true" >> "$GITHUB_OUTPUT"
    if [[ "${MIGRA_FAIL_ON_DESTRUCTIVE:-false}" == "true" ]]; then
      echo "::error::Destructive schema operations detected. Review the diff before merging."
      exit 1
    fi
  else
    echo "has_destructive_operations=false" >> "$GITHUB_OUTPUT"
  fi
  echo "diff_sql=$(echo "$OUTPUT" | head -c 65535)" >> "$GITHUB_OUTPUT"
fi
