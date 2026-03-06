#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-runtime] $*"
}

update_service_if_needed() {
  local service_name="$1"
  shift

  if (($# == 0)); then
    log "No runtime changes requested for ${service_name}"
    return
  fi

  log "Applying runtime updates for ${service_name} in a single revision"
  gcloud run services update "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    "$@" \
    --quiet >/dev/null
}

update_job_if_needed() {
  local job_name="$1"
  shift

  if (($# == 0)); then
    log "No runtime changes requested for job ${job_name}"
    return
  fi

  log "Applying runtime updates for job ${job_name}"
  gcloud run jobs update "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    "$@" \
    --quiet >/dev/null
}

is_true() {
  local value="${1:-}"
  local normalized
  normalized="$(printf '%s' "${value}" | tr '[:upper:]' '[:lower:]')"
  case "${normalized}" in
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

get_service_account_email() {
  local service_name="$1"
  local service_account=""

  service_account="$(gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(spec.template.spec.serviceAccountName)' 2>/dev/null || true)"

  if [[ -n "${service_account}" ]]; then
    echo "${service_account}"
    return 0
  fi

  service_account="$(gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format='value(template.serviceAccount)' 2>/dev/null || true)"

  echo "${service_account}"
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

grant_service_invoker_access() {
  local service_name="$1"
  local invoker_service_account="$2"

  if [[ -z "${invoker_service_account}" ]]; then
    log "No invoker service account resolved for ${service_name}; skipping service-to-service IAM binding"
    return
  fi

  log "Granting ${invoker_service_account} Cloud Run invoker access on ${service_name}"
  gcloud run services add-iam-policy-binding "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --member="serviceAccount:${invoker_service_account}" \
    --role="roles/run.invoker" \
    --quiet >/dev/null
}

require_var "PROJECT_ID"
require_var "REGION"
require_var "API_SERVICE"
require_var "ADMIN_SERVICE"

log "Syncing runtime config for project=${PROJECT_ID} region=${REGION}"

# Build API runtime updates (applied in a single revision).
declare -a api_update_args=()
if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  api_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
fi

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
if [[ -n "${OPENAI_API_KEY_SECRET_NAME:-}" ]]; then
  backend_secret_pairs+=("OPENAI_API_KEY=${OPENAI_API_KEY_SECRET_NAME}:latest")
fi

if ((${#backend_secret_pairs[@]} > 0)); then
  backend_update_secrets="$(IFS=,; echo "${backend_secret_pairs[*]}")"
  api_update_args+=(--update-secrets "${backend_update_secrets}")
fi

declare -a backend_env_pairs=()
if [[ -n "${MED13_ALLOWED_ORIGINS:-}" ]]; then
  backend_env_pairs+=("MED13_ALLOWED_ORIGINS=${MED13_ALLOWED_ORIGINS}")
fi
if [[ -n "${MED13_DB_POOL_SIZE:-}" ]]; then
  backend_env_pairs+=("MED13_DB_POOL_SIZE=${MED13_DB_POOL_SIZE}")
fi
if [[ -n "${MED13_DB_MAX_OVERFLOW:-}" ]]; then
  backend_env_pairs+=("MED13_DB_MAX_OVERFLOW=${MED13_DB_MAX_OVERFLOW}")
fi
if [[ -n "${MED13_DB_POOL_TIMEOUT_SECONDS:-}" ]]; then
  backend_env_pairs+=(
    "MED13_DB_POOL_TIMEOUT_SECONDS=${MED13_DB_POOL_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${MED13_DB_POOL_RECYCLE_SECONDS:-}" ]]; then
  backend_env_pairs+=(
    "MED13_DB_POOL_RECYCLE_SECONDS=${MED13_DB_POOL_RECYCLE_SECONDS}"
  )
fi
if [[ -n "${MED13_DB_POOL_USE_LIFO:-}" ]]; then
  backend_env_pairs+=("MED13_DB_POOL_USE_LIFO=${MED13_DB_POOL_USE_LIFO}")
fi

if ((${#backend_env_pairs[@]} > 0)); then
  backend_update_envs="$(IFS=@; echo "${backend_env_pairs[*]}")"
  api_update_args+=(--update-env-vars "^@^${backend_update_envs}")
fi

update_service_if_needed "${API_SERVICE}" "${api_update_args[@]}"

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

declare -a admin_update_args=()
if is_true "${SYNC_ADMIN_URLS:-}"; then
  admin_update_args+=(
    --update-env-vars
    "^@^NEXT_PUBLIC_API_URL=${API_PUBLIC_URL}@NEXT_PUBLIC_WS_URL=${API_PUBLIC_WS_URL}@NEXTAUTH_URL=${ADMIN_PUBLIC_URL}@API_BASE_URL=${API_PUBLIC_URL}"
  )
fi

if [[ -n "${NEXTAUTH_SECRET_SECRET_NAME:-}" ]]; then
  admin_update_args+=(--update-secrets "NEXTAUTH_SECRET=${NEXTAUTH_SECRET_SECRET_NAME}:latest")
fi

update_service_if_needed "${ADMIN_SERVICE}" "${admin_update_args[@]}"

API_INVOKER_SERVICE_ACCOUNT="${API_INVOKER_SERVICE_ACCOUNT:-$(get_service_account_email "${ADMIN_SERVICE}")}"
grant_service_invoker_access "${API_SERVICE}" "${API_INVOKER_SERVICE_ACCOUNT}"

set_public_access "${API_SERVICE}" "${API_PUBLIC:-}"
set_public_access "${ADMIN_SERVICE}" "${ADMIN_PUBLIC:-}"

# Optional: keep migration job aligned to database runtime config.
if [[ -n "${MIGRATION_JOB_NAME:-}" ]] && gcloud run jobs describe "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" >/dev/null 2>&1; then
  declare -a migration_job_update_args=()
  if [[ -n "${CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(--set-cloudsql-instances "${CLOUDSQL_CONNECTION_NAME}")
  fi

  if [[ -n "${DATABASE_URL_SECRET_NAME:-}" ]]; then
    migration_job_update_args+=(--update-secrets "DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest")
  fi

  update_job_if_needed "${MIGRATION_JOB_NAME}" "${migration_job_update_args[@]}"
fi

log "Runtime sync completed"
