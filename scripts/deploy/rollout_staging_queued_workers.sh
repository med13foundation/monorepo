#!/usr/bin/env bash
set -euo pipefail

log() {
  echo "[rollout-staging-queued-workers] $*"
}

fail() {
  echo "[rollout-staging-queued-workers] ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_value() {
  local name="$1"
  local value="$2"
  if [[ -z "${value}" ]]; then
    fail "Missing required value: ${name}"
  fi
}

json_env_value() {
  local snapshot_json="$1"
  local env_name="$2"
  jq -r --arg env_name "${env_name}" '
    [.env[]? | select(.name == $env_name) | .value]
    | map(select(. != null and . != ""))
    | .[0] // ""
  ' <<<"${snapshot_json}"
}

json_secret_name() {
  local snapshot_json="$1"
  local env_name="$2"
  jq -r --arg env_name "${env_name}" '
    [.env[]? | select(.name == $env_name) | .valueFrom.secretKeyRef.name]
    | map(select(. != null and . != ""))
    | .[0] // ""
  ' <<<"${snapshot_json}"
}

capture_service_snapshot() {
  local service_name="$1"
  gcloud run services describe "${service_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format=json | jq '{
      name: .metadata.name,
      latestReadyRevisionName: .status.latestReadyRevisionName,
      traffic: .status.traffic,
      serviceAccount: .spec.template.spec.serviceAccountName,
      cloudsql: .spec.template.metadata.annotations["run.googleapis.com/cloudsql-instances"],
      ingress: .metadata.annotations["run.googleapis.com/ingress"],
      minScale: .spec.template.metadata.annotations["autoscaling.knative.dev/minScale"],
      maxScale: .spec.template.metadata.annotations["autoscaling.knative.dev/maxScale"],
      cpuThrottling: .spec.template.metadata.annotations["run.googleapis.com/cpu-throttling"],
      concurrency: .spec.template.spec.containerConcurrency,
      timeoutSeconds: .spec.template.spec.timeoutSeconds,
      env: [.spec.template.spec.containers[0].env[]? | {name, value, valueFrom}]
    }'
}

capture_sql_snapshot() {
  gcloud sql instances describe "${SQL_INSTANCE}" \
    --project "${PROJECT_ID}" \
    --format=json | jq '{
      name,
      region,
      state,
      connectionName,
      databaseVersion,
      tier: .settings.tier,
      activationPolicy: .settings.activationPolicy
    }'
}

capture_job_snapshot() {
  local job_name="$1"
  if ! gcloud run jobs describe "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" >/dev/null 2>&1; then
    echo "null"
    return
  fi
  gcloud run jobs describe "${job_name}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format=json | jq '{
      name: .metadata.name,
      image: .spec.template.spec.template.spec.containers[0].image,
      serviceAccount: .spec.template.spec.template.spec.serviceAccountName,
      cloudsql: .spec.template.metadata.annotations["run.googleapis.com/cloudsql-instances"],
      env: [.spec.template.spec.template.spec.containers[0].env[]? | {name, value, valueFrom}]
    }'
}

wait_for_sql_tier() {
  local attempts="${1:-40}"
  local sleep_seconds="${2:-15}"

  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    local sql_snapshot
    local current_tier
    local current_state

    sql_snapshot="$(capture_sql_snapshot)"
    current_tier="$(jq -r '.tier // ""' <<<"${sql_snapshot}")"
    current_state="$(jq -r '.state // ""' <<<"${sql_snapshot}")"

    if [[ "${current_tier}" == "${SQL_TIER}" && "${current_state}" == "RUNNABLE" ]]; then
      log "Cloud SQL instance ${SQL_INSTANCE} is RUNNABLE on tier ${SQL_TIER}"
      return 0
    fi

    log "Waiting for Cloud SQL ${SQL_INSTANCE} to reach ${SQL_TIER} (attempt ${attempt}/${attempts}, current tier=${current_tier}, state=${current_state})"
    sleep "${sleep_seconds}"
  done

  fail "Timed out waiting for Cloud SQL ${SQL_INSTANCE} to reach tier ${SQL_TIER}"
}

deploy_service_from_source() {
  local service_name="$1"
  local source_path="$2"
  local service_account="$3"
  local cloudsql_instance="$4"
  local min_scale="$5"
  local max_scale="$6"
  local concurrency="$7"
  local timeout_seconds="$8"

  local -a args=(
    run deploy "${service_name}"
    --project "${PROJECT_ID}"
    --region "${REGION}"
    --source "${source_path}"
    --no-allow-unauthenticated
    --service-account "${service_account}"
    --set-cloudsql-instances "${cloudsql_instance}"
    --min-instances "${min_scale}"
    --max-instances "${max_scale}"
    --timeout "${timeout_seconds}"
    --quiet
  )

  if [[ -n "${concurrency}" && "${concurrency}" != "null" ]]; then
    args+=(--concurrency "${concurrency}")
  fi

  log "Deploying ${service_name} from ${source_path}"
  gcloud "${args[@]}"
}

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
API_SERVICE="${API_SERVICE:-med13-resource-library-staging}"
ADMIN_SERVICE="${ADMIN_SERVICE:-med13-admin-staging}"
SCHEDULER_SERVICE="${SCHEDULER_SERVICE:-med13-resource-library-staging-scheduler}"
SQL_INSTANCE="${SQL_INSTANCE:-med13-pg-staging}"
SQL_TIER="${SQL_TIER:-db-g1-small}"
MIGRATION_JOB_NAME="${MIGRATION_JOB_NAME:-med13-alembic-migrate}"
MED13_ENV="${MED13_ENV:-staging}"
BACKEND_SOURCE="${BACKEND_SOURCE:-.}"
ADMIN_SOURCE="${ADMIN_SOURCE:-src/web}"

require_cmd gcloud
require_cmd jq
require_value "PROJECT_ID" "${PROJECT_ID}"
require_value "REGION" "${REGION}"

api_snapshot="$(capture_service_snapshot "${API_SERVICE}")"
admin_snapshot="$(capture_service_snapshot "${ADMIN_SERVICE}")"
sql_snapshot="$(capture_sql_snapshot)"
migration_job_snapshot="$(capture_job_snapshot "${MIGRATION_JOB_NAME}")"

api_service_account="$(jq -r '.serviceAccount // ""' <<<"${api_snapshot}")"
api_cloudsql="$(jq -r '.cloudsql // ""' <<<"${api_snapshot}")"
api_min_scale="$(jq -r '.minScale // "1"' <<<"${api_snapshot}")"
api_max_scale="$(jq -r '.maxScale // "2"' <<<"${api_snapshot}")"
api_concurrency="$(jq -r '.concurrency // ""' <<<"${api_snapshot}")"
api_timeout_seconds="$(jq -r '.timeoutSeconds // "300"' <<<"${api_snapshot}")"

admin_service_account="$(jq -r '.serviceAccount // ""' <<<"${admin_snapshot}")"
admin_min_scale="$(jq -r '.minScale // "1"' <<<"${admin_snapshot}")"
admin_max_scale="$(jq -r '.maxScale // "20"' <<<"${admin_snapshot}")"
admin_concurrency="$(jq -r '.concurrency // ""' <<<"${admin_snapshot}")"
admin_timeout_seconds="$(jq -r '.timeoutSeconds // "300"' <<<"${admin_snapshot}")"

require_value "API service account" "${api_service_account}"
require_value "Admin service account" "${admin_service_account}"
require_value "API Cloud SQL connection" "${api_cloudsql}"

MED13_ALLOWED_ORIGINS="${MED13_ALLOWED_ORIGINS:-$(json_env_value "${api_snapshot}" "MED13_ALLOWED_ORIGINS")}"
DATABASE_URL_SECRET_NAME="${DATABASE_URL_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "DATABASE_URL")}"
MED13_DEV_JWT_SECRET_NAME="${MED13_DEV_JWT_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "MED13_DEV_JWT_SECRET")}"
ADMIN_API_KEY_SECRET_NAME="${ADMIN_API_KEY_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "ADMIN_API_KEY")}"
WRITE_API_KEY_SECRET_NAME="${WRITE_API_KEY_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "WRITE_API_KEY")}"
READ_API_KEY_SECRET_NAME="${READ_API_KEY_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "READ_API_KEY")}"
OPENAI_API_KEY_SECRET_NAME="${OPENAI_API_KEY_SECRET_NAME:-$(json_secret_name "${api_snapshot}" "OPENAI_API_KEY")}"
NEXTAUTH_SECRET_SECRET_NAME="${NEXTAUTH_SECRET_SECRET_NAME:-$(json_secret_name "${admin_snapshot}" "NEXTAUTH_SECRET")}"

require_value "DATABASE_URL secret" "${DATABASE_URL_SECRET_NAME}"
require_value "MED13_DEV_JWT_SECRET secret" "${MED13_DEV_JWT_SECRET_NAME}"
require_value "ADMIN_API_KEY secret" "${ADMIN_API_KEY_SECRET_NAME}"
require_value "WRITE_API_KEY secret" "${WRITE_API_KEY_SECRET_NAME}"
require_value "READ_API_KEY secret" "${READ_API_KEY_SECRET_NAME}"
require_value "OPENAI_API_KEY secret" "${OPENAI_API_KEY_SECRET_NAME}"
require_value "NEXTAUTH_SECRET secret" "${NEXTAUTH_SECRET_SECRET_NAME}"
require_value "MED13_ALLOWED_ORIGINS" "${MED13_ALLOWED_ORIGINS}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
ROLLBACK_ARTIFACT="${ROLLBACK_ARTIFACT:-/tmp/${API_SERVICE}-queued-rollout-${timestamp}.json}"

log "Capturing rollback preflight to ${ROLLBACK_ARTIFACT}"
jq -n \
  --arg captured_at "${timestamp}" \
  --arg project_id "${PROJECT_ID}" \
  --arg region "${REGION}" \
  --arg api_service "${API_SERVICE}" \
  --arg admin_service "${ADMIN_SERVICE}" \
  --arg scheduler_service "${SCHEDULER_SERVICE}" \
  --arg sql_instance "${SQL_INSTANCE}" \
  --arg sql_target_tier "${SQL_TIER}" \
  --arg migration_job_name "${MIGRATION_JOB_NAME}" \
  --argjson api "${api_snapshot}" \
  --argjson admin "${admin_snapshot}" \
  --argjson sql "${sql_snapshot}" \
  --argjson migration_job "${migration_job_snapshot}" \
  '{
    captured_at: $captured_at,
    project_id: $project_id,
    region: $region,
    api_service: $api_service,
    admin_service: $admin_service,
    scheduler_service: $scheduler_service,
    sql_instance: $sql_instance,
    sql_target_tier: $sql_target_tier,
    migration_job_name: $migration_job_name,
    rollback: {
      api: $api,
      admin: $admin,
      sql: $sql,
      migration_job: $migration_job
    }
  }' >"${ROLLBACK_ARTIFACT}"

log "Manual staging-pipeline pause is not automated; ensure no ad hoc runs are started during this rollout window."

current_sql_tier="$(jq -r '.tier // ""' <<<"${sql_snapshot}")"
if [[ "${current_sql_tier}" != "${SQL_TIER}" ]]; then
  log "Resizing Cloud SQL ${SQL_INSTANCE} from ${current_sql_tier} to ${SQL_TIER}"
  gcloud sql instances patch "${SQL_INSTANCE}" \
    --project "${PROJECT_ID}" \
    --tier "${SQL_TIER}" \
    --quiet
else
  log "Cloud SQL ${SQL_INSTANCE} already on tier ${SQL_TIER}"
fi
wait_for_sql_tier

deploy_service_from_source \
  "${API_SERVICE}" \
  "${BACKEND_SOURCE}" \
  "${api_service_account}" \
  "${api_cloudsql}" \
  "${api_min_scale}" \
  "${api_max_scale}" \
  "${api_concurrency}" \
  "${api_timeout_seconds}"

api_image="$(
  gcloud run services describe "${API_SERVICE}" \
    --project "${PROJECT_ID}" \
    --region "${REGION}" \
    --format=json | jq -r '.spec.template.spec.containers[0].image // ""'
)"
require_value "API image" "${api_image}"

log "Updating and executing migration job ${MIGRATION_JOB_NAME}"
gcloud run jobs update "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${api_image}" \
  --service-account "${api_service_account}" \
  --set-cloudsql-instances "${api_cloudsql}" \
  --set-secrets "DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest" \
  --quiet
gcloud run jobs execute "${MIGRATION_JOB_NAME}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --wait

deploy_service_from_source \
  "${ADMIN_SERVICE}" \
  "${ADMIN_SOURCE}" \
  "${admin_service_account}" \
  "${api_cloudsql}" \
  "${admin_min_scale}" \
  "${admin_max_scale}" \
  "${admin_concurrency}" \
  "${admin_timeout_seconds}"

log "Syncing API and admin runtime envs"
env \
  PROJECT_ID="${PROJECT_ID}" \
  REGION="${REGION}" \
  API_SERVICE="${API_SERVICE}" \
  ADMIN_SERVICE="${ADMIN_SERVICE}" \
  CLOUDSQL_CONNECTION_NAME="${api_cloudsql}" \
  API_MIN_INSTANCES="${api_min_scale}" \
  ADMIN_MIN_INSTANCES="${admin_min_scale}" \
  DATABASE_URL_SECRET_NAME="${DATABASE_URL_SECRET_NAME}" \
  MED13_DEV_JWT_SECRET_NAME="${MED13_DEV_JWT_SECRET_NAME}" \
  ADMIN_API_KEY_SECRET_NAME="${ADMIN_API_KEY_SECRET_NAME}" \
  WRITE_API_KEY_SECRET_NAME="${WRITE_API_KEY_SECRET_NAME}" \
  READ_API_KEY_SECRET_NAME="${READ_API_KEY_SECRET_NAME}" \
  OPENAI_API_KEY_SECRET_NAME="${OPENAI_API_KEY_SECRET_NAME}" \
  NEXTAUTH_SECRET_SECRET_NAME="${NEXTAUTH_SECRET_SECRET_NAME}" \
  MED13_ENV="${MED13_ENV}" \
  MED13_ALLOWED_ORIGINS="${MED13_ALLOWED_ORIGINS}" \
  MED13_RUNTIME_ROLE="api" \
  MED13_DISABLE_INGESTION_SCHEDULER="1" \
  MED13_DISABLE_PIPELINE_WORKER="1" \
  MED13_DB_POOL_SIZE="4" \
  MED13_DB_MAX_OVERFLOW="0" \
  MED13_ARTANA_POOL_MIN_SIZE="1" \
  MED13_ARTANA_POOL_MAX_SIZE="1" \
  MED13_ARTANA_COMMAND_TIMEOUT_SECONDS="30" \
  MED13_ENABLE_WORKFLOW_SSE="true" \
  MED13_PIPELINE_QUEUE_MAX_SIZE="100" \
  MED13_PIPELINE_QUEUE_RETRY_AFTER_SECONDS="30" \
  MED13_PIPELINE_RETRY_MAX_ATTEMPTS="5" \
  MED13_PIPELINE_RETRY_BASE_DELAY_SECONDS="30" \
  NEXT_PUBLIC_WORKFLOW_SSE_ENABLED="true" \
  SYNC_ADMIN_URLS="true" \
  /bin/bash scripts/deploy/sync_cloud_run_runtime_config.sh

scheduler_envs=(
  "MED13_ENV=${MED13_ENV}"
  "MED13_RUNTIME_ROLE=scheduler"
  "MED13_DISABLE_INGESTION_SCHEDULER=0"
  "MED13_DISABLE_PIPELINE_WORKER=0"
  "MED13_DB_POOL_SIZE=2"
  "MED13_DB_MAX_OVERFLOW=0"
  "MED13_ARTANA_POOL_MIN_SIZE=1"
  "MED13_ARTANA_POOL_MAX_SIZE=2"
  "MED13_ARTANA_COMMAND_TIMEOUT_SECONDS=30"
  "MED13_PIPELINE_WORKER_MAX_CONCURRENCY=1"
  "MED13_PIPELINE_WORKER_POLL_INTERVAL_SECONDS=5"
  "MED13_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS=15"
  "MED13_PIPELINE_QUEUE_MAX_SIZE=100"
  "MED13_PIPELINE_QUEUE_RETRY_AFTER_SECONDS=30"
  "MED13_PIPELINE_RETRY_MAX_ATTEMPTS=5"
  "MED13_PIPELINE_RETRY_BASE_DELAY_SECONDS=30"
  "MED13_ALLOWED_ORIGINS=${MED13_ALLOWED_ORIGINS}"
)

scheduler_secrets=(
  "DATABASE_URL=${DATABASE_URL_SECRET_NAME}:latest"
  "MED13_DEV_JWT_SECRET=${MED13_DEV_JWT_SECRET_NAME}:latest"
  "ADMIN_API_KEY=${ADMIN_API_KEY_SECRET_NAME}:latest"
  "WRITE_API_KEY=${WRITE_API_KEY_SECRET_NAME}:latest"
  "READ_API_KEY=${READ_API_KEY_SECRET_NAME}:latest"
  "OPENAI_API_KEY=${OPENAI_API_KEY_SECRET_NAME}:latest"
)

# Use a custom delimiter because MED13_ALLOWED_ORIGINS contains commas.
scheduler_env_flag="^|^$(IFS='|'; echo "${scheduler_envs[*]}")"
scheduler_secrets_flag="^|^$(IFS='|'; echo "${scheduler_secrets[*]}")"

log "Deploying dedicated scheduler service ${SCHEDULER_SERVICE}"
gcloud run deploy "${SCHEDULER_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --image "${api_image}" \
  --no-allow-unauthenticated \
  --no-default-url \
  --service-account "${api_service_account}" \
  --set-cloudsql-instances "${api_cloudsql}" \
  --min-instances 1 \
  --max-instances 1 \
  --concurrency 1 \
  --timeout 300 \
  --no-cpu-throttling \
  --set-env-vars "${scheduler_env_flag}" \
  --set-secrets "${scheduler_secrets_flag}" \
  --quiet

log "Capturing post-deploy service summary"
gcloud run services describe "${API_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)'
gcloud run services describe "${ADMIN_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)'
gcloud run services describe "${SCHEDULER_SERVICE}" \
  --project "${PROJECT_ID}" \
  --region "${REGION}" \
  --format='value(status.latestReadyRevisionName)'

log "Rollout completed. Manual authenticated smoke tests are still required for the pipeline endpoint and UI workflow."
log "Rollback preflight artifact: ${ROLLBACK_ARTIFACT}"
