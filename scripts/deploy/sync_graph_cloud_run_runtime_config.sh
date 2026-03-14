#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[sync-graph-runtime] $*"
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

require_distinct_if_present() {
  local left_name="$1"
  local right_name="$2"
  local message="$3"
  local left_value="${!left_name:-}"
  local right_value="${!right_name:-}"

  if [[ -z "${left_value}" || -z "${right_value}" ]]; then
    return
  fi

  if [[ "${left_value}" == "${right_value}" ]]; then
    echo "${message}" >&2
    exit 1
  fi
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
require_var "GRAPH_SERVICE"
require_var "GRAPH_DATABASE_URL_SECRET_NAME"
require_var "GRAPH_JWT_SECRET_NAME"
require_distinct_if_present \
  "GRAPH_DATABASE_URL_SECRET_NAME" \
  "DATABASE_URL_SECRET_NAME" \
  "GRAPH_DATABASE_URL_SECRET_NAME must differ from DATABASE_URL_SECRET_NAME in deployed environments"

log "Syncing graph runtime config for project=${PROJECT_ID} region=${REGION}"

declare -a graph_update_args=()
if [[ -n "${GRAPH_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
  graph_update_args+=(--set-cloudsql-instances "${GRAPH_CLOUDSQL_CONNECTION_NAME}")
fi
if [[ -n "${GRAPH_MIN_INSTANCES:-}" ]]; then
  graph_update_args+=(--min-instances "${GRAPH_MIN_INSTANCES}")
fi

declare -a graph_secret_pairs=()
if [[ -n "${GRAPH_DATABASE_URL_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("GRAPH_DATABASE_URL=${GRAPH_DATABASE_URL_SECRET_NAME}:latest")
fi
if [[ -n "${GRAPH_JWT_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("GRAPH_JWT_SECRET=${GRAPH_JWT_SECRET_NAME}:latest")
fi
if [[ -n "${OPENAI_API_KEY_SECRET_NAME:-}" ]]; then
  graph_secret_pairs+=("OPENAI_API_KEY=${OPENAI_API_KEY_SECRET_NAME}:latest")
fi

if ((${#graph_secret_pairs[@]} > 0)); then
  graph_update_secrets="$(IFS=,; echo "${graph_secret_pairs[*]}")"
  graph_update_args+=(--update-secrets "${graph_update_secrets}")
fi

declare -a graph_env_pairs=(
  "GRAPH_SERVICE_HOST=0.0.0.0"
  "GRAPH_SERVICE_PORT=8080"
  "GRAPH_SERVICE_RELOAD=0"
)
if [[ -n "${GRAPH_SERVICE_NAME:-}" ]]; then
  graph_env_pairs+=("GRAPH_SERVICE_NAME=${GRAPH_SERVICE_NAME}")
fi
if [[ -n "${GRAPH_DB_POOL_SIZE:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_POOL_SIZE=${GRAPH_DB_POOL_SIZE}")
fi
if [[ -n "${GRAPH_DB_MAX_OVERFLOW:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_MAX_OVERFLOW=${GRAPH_DB_MAX_OVERFLOW}")
fi
if [[ -n "${GRAPH_DB_POOL_TIMEOUT_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_DB_POOL_TIMEOUT_SECONDS=${GRAPH_DB_POOL_TIMEOUT_SECONDS}"
  )
fi
if [[ -n "${GRAPH_DB_POOL_RECYCLE_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_DB_POOL_RECYCLE_SECONDS=${GRAPH_DB_POOL_RECYCLE_SECONDS}"
  )
fi
if [[ -n "${GRAPH_DB_POOL_USE_LIFO:-}" ]]; then
  graph_env_pairs+=("GRAPH_DB_POOL_USE_LIFO=${GRAPH_DB_POOL_USE_LIFO}")
fi
if [[ -n "${GRAPH_ENABLE_ENTITY_EMBEDDINGS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_ENTITY_EMBEDDINGS=${GRAPH_ENABLE_ENTITY_EMBEDDINGS}"
  )
fi
if [[ -n "${GRAPH_ENABLE_SEARCH_AGENT:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_SEARCH_AGENT=${GRAPH_ENABLE_SEARCH_AGENT}"
  )
fi
if [[ -n "${GRAPH_ENABLE_RELATION_SUGGESTIONS:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_RELATION_SUGGESTIONS=${GRAPH_ENABLE_RELATION_SUGGESTIONS}"
  )
fi
if [[ -n "${GRAPH_ENABLE_HYPOTHESIS_GENERATION:-}" ]]; then
  graph_env_pairs+=(
    "GRAPH_ENABLE_HYPOTHESIS_GENERATION=${GRAPH_ENABLE_HYPOTHESIS_GENERATION}"
  )
fi
if [[ -n "${MED13_ARTANA_POOL_MIN_SIZE:-}" ]]; then
  graph_env_pairs+=(
    "MED13_ARTANA_POOL_MIN_SIZE=${MED13_ARTANA_POOL_MIN_SIZE}"
  )
fi
if [[ -n "${MED13_ARTANA_POOL_MAX_SIZE:-}" ]]; then
  graph_env_pairs+=(
    "MED13_ARTANA_POOL_MAX_SIZE=${MED13_ARTANA_POOL_MAX_SIZE}"
  )
fi
if [[ -n "${MED13_ARTANA_COMMAND_TIMEOUT_SECONDS:-}" ]]; then
  graph_env_pairs+=(
    "MED13_ARTANA_COMMAND_TIMEOUT_SECONDS=${MED13_ARTANA_COMMAND_TIMEOUT_SECONDS}"
  )
fi

if ((${#graph_env_pairs[@]} > 0)); then
  graph_update_envs="$(IFS=@; echo "${graph_env_pairs[*]}")"
  graph_update_args+=(--update-env-vars "^@^${graph_update_envs}")
fi

update_service_if_needed "${GRAPH_SERVICE}" "${graph_update_args[@]}"
set_public_access "${GRAPH_SERVICE}" "${GRAPH_PUBLIC:-}"

if [[ -n "${GRAPH_MIGRATION_JOB_NAME:-}" ]]; then
  if ! gcloud run jobs describe "${GRAPH_MIGRATION_JOB_NAME}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" >/dev/null 2>&1; then
    echo "Configured graph migration job does not exist: ${GRAPH_MIGRATION_JOB_NAME}" >&2
    exit 1
  fi

  declare -a migration_job_update_args=()
  if [[ -n "${GRAPH_CLOUDSQL_CONNECTION_NAME:-}" ]]; then
    migration_job_update_args+=(
      --set-cloudsql-instances
      "${GRAPH_CLOUDSQL_CONNECTION_NAME}"
    )
  fi

  if [[ -n "${GRAPH_DATABASE_URL_SECRET_NAME:-}" ]]; then
    migration_job_update_args+=(
      --update-secrets
      "GRAPH_DATABASE_URL=${GRAPH_DATABASE_URL_SECRET_NAME}:latest"
    )
  fi

  update_job_if_needed "${GRAPH_MIGRATION_JOB_NAME}" "${migration_job_update_args[@]}"
fi

log "Graph runtime sync completed"
