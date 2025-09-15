#!/usr/bin/env bash
set -Eeuo pipefail

# ============== CONFIG ==============
BASE_URL="http://awx.example.com"   # <-- pon tu URL (http o https)
TOKEN="TU_TOKEN_AQUI"               # <-- tu PAT de AWX
PAGE_SIZE=200
VALIDATE_CERTS=false                # true si usas HTTPS con CA válida
OUT_JSON="workflow_configs.json"
OUT_CSV="workflow_configs.csv"
# ====================================

h(){ echo "[$(date +%H:%M:%S)] $*"; }

curl_auth() {
  local kargs=()
  [[ "${VALIDATE_CERTS}" == "false" ]] && kargs+=(-k)
  curl -sS "${kargs[@]}" \
       -H "Authorization: Bearer $TOKEN" \
       -H "Content-Type: application/json" \
       "$@"
}

# Paginador que devuelve SIEMPRE un array (concatena .results)
get_all_results() {
  local next="$1"
  local tmpdir; tmpdir="$(mktemp -d)"
  local idx=0
  while [[ -n "$next" && "$next" != "null" ]]; do
    local page; page="$(curl_auth "$next")"
    echo "$page" | jq '.results // []' > "$tmpdir/$idx.json"
    local n; n="$(echo "$page" | jq -r '.next')"
    if [[ -z "$n" || "$n" == "null" ]]; then next=""; else
      if [[ "$n" =~ ^/ ]]; then next="$BASE_URL$n"; else next="$n"; fi
    fi
    idx=$((idx+1))
  done
  if ls "$tmpdir"/*.json >/dev/null 2>&1; then jq -s 'add' "$tmpdir"/*.json; else echo '[]'; fi
  rm -rf "$tmpdir"
}

h "Probando acceso…"
if curl_auth "$BASE_URL/api/v2/workflow_job_templates/?page_size=1" | jq -e '.results | type=="array"' >/dev/null; then
  h "OK: acceso a workflow_job_templates"
else
  echo "[ERROR] No se pudo acceder a workflow_job_templates. Revisa BASE_URL/TOKEN."; exit 1
fi

h "Listando Workflows (solo configuración, sin nodos)…"
WF_URL="$BASE_URL/api/v2/workflow_job_templates/?page_size=$PAGE_SIZE"
WF_ALL="$(get_all_results "$WF_URL")"

# JSON “bonito” con campos de configuración útiles
echo "$WF_ALL" | jq 'map({
  id, name, description,
  organization: (.summary_fields.organization.name // null),
  inventory: (.summary_fields.inventory.name // null),
  allow_simultaneous, survey_enabled, ask_variables_on_launch,
  # lanzadores/asks comunes:
  ask_inventory_on_launch, ask_scm_branch_on_launch, ask_limit_on_launch,
  ask_labels_on_launch, ask_skip_tags_on_launch,
  # scm/limit/vars:
  scm_branch, limit, extra_vars,
  # webhooks/labels:
  webhook_service,
  webhook_credential: (.summary_fields.webhook_credential.name // null),
  labels: ((.summary_fields.labels.results // []) | map(.name)),
  # metadata
  created, modified
})' > "$OUT_JSON"

h "Configuraciones guardadas en $OUT_JSON (total: $(jq 'length' "$OUT_JSON"))"

# CSV rápido y útil
jq -r '
  (["id","name","organization","inventory","allow_simultaneous","survey_enabled",
    "ask_variables_on_launch","scm_branch","limit","webhook_service","webhook_credential",
    "labels","created","modified"] | @csv),
  (.[] | [
    .id,
    (.name // ""),
    (.organization // ""),
    (.inventory // ""),
    (.allow_simultaneous // false),
    (.survey_enabled // false),
    (.ask_variables_on_launch // false),
    (.scm_branch // ""),
    (.limit // ""),
    (.webhook_service // ""),
    (.webhook_credential // ""),
    ((.labels // []) | join("|")),
    (.created // ""),
    (.modified // "")
  ] | @csv)
' "$OUT_JSON" > "$OUT_CSV"

h "CSV guardado en $OUT_CSV"
h "Hecho."
