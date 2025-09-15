#!/usr/bin/env bash
set -Eeuo pipefail
trap 'echo "[ERROR] línea $LINENO: $BASH_COMMAND" >&2' ERR

# ================== CONFIG ==================
BASE_URL="http://awx.example.com"   # <--- cambia
TOKEN="oFIdEnnpCzHTJ4iED9csm9ND0peXxo"                 # <--- cambia
PAGE_SIZE=200
VALIDATE_CERTS=false                 # true si tu CA es válida
OUT_JT_JSON="job_templates.json"
OUT_WF_JSON="workflow_job_templates.json"
OUT_JT_YAML="job_templates.yaml"
OUT_WF_YAML="workflow_job_templates.yaml"
# ============================================

h(){ echo "[$(date +%H:%M:%S)] $*"; }

curl_auth() {
  local kargs=()
  [[ "${VALIDATE_CERTS}" == "false" ]] && kargs+=(-k)
  curl -sS "${kargs[@]}" \
       -H "Authorization: Bearer $TOKEN" \
       -H "Content-Type: application/json" \
       "$@"
}

# Paginación segura
get_all_results() {
  local next="$1"
  local tmpdir idx page n
  tmpdir="$(mktemp -d)"
  idx=0
  while [[ -n "$next" && "$next" != "null" ]]; do
    page="$(curl_auth "$next")"
    echo "$page" | jq '.results // []' > "$tmpdir/$idx.json"
    n="$(echo "$page" | jq -r '.next')"
    if [[ -z "$n" || "$n" == "null" ]]; then
      next=""
    else
      if [[ "$n" =~ ^/ ]]; then next="$BASE_URL$n"; else next="$n"; fi
    fi
    idx=$((idx+1))
  done
  if ls "$tmpdir"/*.json >/dev/null 2>&1; then
    jq -s 'add' "$tmpdir"/*.json
  else
    echo '[]'
  fi
  rm -rf "$tmpdir"
}

h "Probando API y token…"
if curl_auth "$BASE_URL/api/v2/job_templates/?page_size=1" | jq -e '.results | type=="array"' >/dev/null; then
  h "OK: token válido (job_templates accesible)"
else
  echo "[ERROR] Token inválido o sin permisos para job_templates"; exit 1
fi


# ============= 1) JOB TEMPLATES =============
h "Exportando Job Templates…"
JT_URL="$BASE_URL/api/v2/job_templates/?page_size=$PAGE_SIZE"
JT_RESULTS="$(get_all_results "$JT_URL")"

echo "$JT_RESULTS" \
| jq 'map({
    id, name, description, job_type, playbook, limit, verbosity, scm_branch, timeout,
    project: (.summary_fields.project.name // null),
    inventory: (.summary_fields.inventory.name // null),
    execution_environment: (.summary_fields.execution_environment.name // null),
    credentials: ((.summary_fields.credentials // []) | map(.name)),
    ask_limit_on_launch, ask_variables_on_launch, ask_inventory_on_launch, ask_credential_on_launch,
    survey_enabled, extra_vars
  })' > "$OUT_JT_JSON"

h "Job Templates guardados en $OUT_JT_JSON (total: $(jq 'length' "$OUT_JT_JSON"))"

# ====== 2) WORKFLOW JOB TEMPLATES + NODOS ======

h "¡Export terminado!"
