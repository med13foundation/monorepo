#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-runtime] $*"
}

is_true() {
  local value="${1:-}"
  case "${value,,}" in
    1|true|yes|y|on) return 0 ;;
    *) return 1 ;;
  esac
}

require_var() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: ${name}" >&2
    exit 1
  fi
}

get_service_status_url() {
  local service_name="$1"
  gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(status.url)'
}

get_service_primary_url() {
  local service_name="$1"
  local urls_json=""

  urls_json="$(gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(metadata.annotations."run.googleapis.com/urls")' 2>/dev/null || true)"

  if [[ "${urls_json}" =~ ^\[[[:space:]]*\"([^\"]+)\" ]]; then
    echo "${BASH_REMATCH[1]}"
    return 0
  fi

  get_service_status_url "${service_name}"
}

to_websocket_url() {
  local http_url="$1"
  case "${http_url}" in
    https://*)
      echo "wss://${http_url#https://}"
      ;;
    http://*)
      echo "ws://${http_url#http://}"
      ;;
    *)
      echo "${http_url}"
      ;;
  esac
}

set_public_access() {
  local service_name="$1"
  local public_flag="$2"

  if [[ -z "${public_flag}" ]]; then
    return
  fi

  if is_true "${public_flag}"; then
    log "Ensuring public access for ${service_name}"
    gcloud run services add-iam-policy-binding "${service_name}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --member="allUsers" \
      --role="roles/run.invoker" \
      --quiet >/dev/null
    return
  fi

  log "Ensuring private access for ${service_name}"
  gcloud run services remove-iam-policy-binding "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet >/dev/null || true
}

require_var "PROJECT_ID"
require_var "REGION"
require_var "API_SERVICE"
require_var "ADMIN_SERVICE"

log "Syncing runtime config for project=${PROJECT_ID} region=${REGION}"

# Keep API service connected to the intended Cloud SQL instance.
if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  log "Setting Cloud SQL connection for ${API_SERVICE}"
  gcloud run services update "${API_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}" \
    --quiet >/dev/null
fi

# Build backend secret updates (applied in a single revision).
declare -a backend_secret_pairs=()
if [[ -n "${DATABASE_URL_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest")
fi
if [[ -n "${MED13_DEV_JWT_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("MED13_DEV_JWT_SECRET=${MED13_DEV_JWT_SECRET_NAME}:latest")
fi
if [[ -n "${ADMIN_API_KEY_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("ADMIN_API_KEY=${ADMIN_API_KEY_SECRET_NAME}:latest")
fi
if [[ -n "${WRITE_API_KEY_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("WRITE_API_KEY=${WRITE_API_KEY_SECRET_NAME}:latest")
fi
if [[ -n "${READ_API_KEY_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("READ_API_KEY=${READ_API_KEY_SECRET_NAME}:latest")
fi

if ((${#backend_secret_pairs[@]} > 0)); then
  backend_update_secrets="$(IFS=,; echo "${backend_secret_pairs[*]}")"
  log "Updating backend secrets for ${API_SERVICE}"
  gcloud run services update "${API_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-secrets "${backend_update_secrets}" \
    --quiet >/dev/null
fi

if [[ -n "${MED13_ALLOWED_ORIGINS:-}" ]]; then
  log "Updating MED13_ALLOWED_ORIGINS for ${API_SERVICE}"
  gcloud run services update "${API_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-env-vars "^@^MED13_ALLOWED_ORIGINS=${MED13_ALLOWED_ORIGINS}" \
    --quiet >/dev/null
fi

# Optionally sync admin runtime wiring to the API URL.
if [[ -z "${ADMIN_PUBLIC_URL:-}" ]]; then
  ADMIN_PUBLIC_URL="$(get_service_primary_url "${ADMIN_SERVICE}")"
fi

if [[ -z "${API_PUBLIC_URL:-}" ]]; then
  API_PUBLIC_URL="$(get_service_primary_url "${API_SERVICE}")"
fi

if [[ -z "${API_PUBLIC_WS_URL:-}" ]]; then
  API_PUBLIC_WS_URL="$(to_websocket_url "${API_PUBLIC_URL}")"
fi

if is_true "${SYNC_ADMIN_URLS:-}"; then
  log "Updating admin API/WS/NEXTAUTH URLs for ${ADMIN_SERVICE}"
  gcloud run services update "${ADMIN_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-env-vars "^@^NEXT_PUBLIC_API_URL=${API_PUBLIC_URL}@NEXT_PUBLIC_WS_URL=${API_PUBLIC_WS_URL}@NEXTAUTH_URL=${ADMIN_PUBLIC_URL}" \
    --quiet >/dev/null
fi

if [[ -n "${NEXTAUTH_SECRET_SECRET_NAME:-}" ]]; then
  log "Updating NEXTAUTH_SECRET for ${ADMIN_SERVICE}"
  gcloud run services update "${ADMIN_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --update-secrets "NEXTAUTH_SECRET=${NEXTAUTH_SECRET_SECRET_NAME}:latest" \
    --quiet >/dev/null
fi

set_public_access "${API_SERVICE}" "${API_PUBLIC:-}"
set_public_access "${ADMIN_SERVICE}" "${ADMIN_PUBLIC:-}"

# Optional: keep migration job aligned to database runtime config.
if [[ -n "${MIGRATION_JOB_NAME:-}" ]] && gcloud run jobs describe "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" >/dev/null 2>&1; then
  if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    log "Setting Cloud SQL connection for job ${MIGRATION_JOB_NAME}"
    gcloud run jobs update "${MIGRATION_JOB_NAME}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}" \
      --quiet >/dev/null
  fi

  if [[ -n "${DATABASE_URL_SECRET_NAME:-}" ]]; then
    log "Updating DATABASE_URL secret for job ${MIGRATION_JOB_NAME}"
    gcloud run jobs update "${MIGRATION_JOB_NAME}" \
      --project "${PROJECT_ID}" \
      --region "${REGION}" \
      --update-secrets "DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest" \
      --quiet >/dev/null
  fi
fi

log "Runtime sync completed"
