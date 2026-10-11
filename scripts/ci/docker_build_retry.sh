#!/usr/bin/env bash
# Retry Docker builds only for recognized transient registry/auth/network failures.
# Genuine Dockerfile or application build failures fail immediately.
set -uo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: docker_build_retry.sh <docker-build-args...>" >&2
  exit 2
fi

MAX_ATTEMPTS="${WORKFLO_DOCKER_BUILD_ATTEMPTS:-3}"
if ! [[ "$MAX_ATTEMPTS" =~ ^[1-5]$ ]]; then
  echo "ERROR: WORKFLO_DOCKER_BUILD_ATTEMPTS must be an integer from 1 to 5" >&2
  exit 2
fi

RETRYABLE='429 Too Many Requests|toomanyrequests|unexpected status from (HEAD|POST) request to https://(registry-1\.docker\.io|auth\.docker\.io)|failed to fetch oauth token|TLS handshake timeout|context deadline exceeded|i/o timeout|connection reset by peer|unexpected EOF|temporary failure in name resolution|no such host'

for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  log_file="$(mktemp)"
  echo "==> Docker build attempt $attempt/$MAX_ATTEMPTS"

  docker build "$@" 2>&1 | tee "$log_file"
  pipeline_status=("${PIPESTATUS[@]}")
  build_status="${pipeline_status[0]}"
  tee_status="${pipeline_status[1]:-0}"

  if [[ "$build_status" == "0" && "$tee_status" == "0" ]]; then
    rm -f "$log_file"
    exit 0
  fi
  if [[ "$build_status" == "0" ]]; then
    build_status="$tee_status"
  fi

  if grep -Eiq "$RETRYABLE" "$log_file"; then
    if (( attempt < MAX_ATTEMPTS )); then
      delay=$((attempt * 15))
      echo "::warning::Transient Docker registry/network failure detected; retrying in ${delay}s."
      rm -f "$log_file"
      sleep "$delay"
      continue
    fi
    echo "::error::Docker registry/network failure persisted after $MAX_ATTEMPTS attempts." >&2
  else
    echo "::error::Docker build failed with exit code $build_status; the output did not match a recognized transient registry/network error." >&2
  fi

  rm -f "$log_file"
  exit "$build_status"
done

echo "::error::Docker build retry loop exited unexpectedly." >&2
exit 1
