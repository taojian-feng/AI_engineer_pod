#!/usr/bin/env bash
# Deploy Pod Simulator to Azure Container Apps (consumption plan, scales to zero)
# plus a Python dynamic-sessions pool for the coding labs.
#
# Secrets are read from your shell environment and stored as Container App
# secrets. They are never written to disk or committed.
#
#   export ANTHROPIC_API_KEY=sk-ant-...      # required
#   export ACCESS_CODE=some-shared-code      # required: applicants type this to get in
#   export IMAGE=ghcr.io/<owner>/ai_engineer_pod:latest
#   ./infra/deploy.sh
set -euo pipefail

: "${ANTHROPIC_API_KEY:?Set ANTHROPIC_API_KEY in your shell}"
: "${ACCESS_CODE:?Set ACCESS_CODE in your shell}"
: "${IMAGE:?Set IMAGE, e.g. ghcr.io/<owner>/ai_engineer_pod:latest}"

RG="${RG:-rg-podsim}"
LOCATION="${LOCATION:-eastus}"          # must be a region that supports session pools
ENV_NAME="${ENV_NAME:-podsim-env}"
APP="${APP:-podsim}"
POOL="${POOL:-podsim-sandbox}"
MODEL="${MODEL:-claude-opus-5-5}"
EFFORT="${EFFORT:-low}"
SESSION_TOKEN_BUDGET="${SESSION_TOKEN_BUDGET:-400000}"
DAILY_TOKEN_BUDGET="${DAILY_TOKEN_BUDGET:-5000000}"

az extension add --name containerapp --upgrade --only-show-errors
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

echo "==> Resource group"
az group create -n "$RG" -l "$LOCATION" -o none

echo "==> Container Apps environment (no Log Analytics, to stay near \$0)"
az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null || \
  az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" --logs-destination none -o none

echo "==> Python code-interpreter session pool (egress disabled)"
az containerapp sessionpool show -n "$POOL" -g "$RG" -o none 2>/dev/null || \
  az containerapp sessionpool create -n "$POOL" -g "$RG" -l "$LOCATION" \
    --container-type PythonLTS --max-sessions 20 --cooldown-period 300 --network-status EgressDisabled -o none
POOL_ID=$(az containerapp sessionpool show -n "$POOL" -g "$RG" --query id -o tsv)
POOL_ENDPOINT=$(az containerapp sessionpool show -n "$POOL" -g "$RG" --query properties.poolManagementEndpoint -o tsv)

REGISTRY_ARGS=()
if [[ -n "${GHCR_USER:-}" && -n "${GHCR_TOKEN:-}" ]]; then
  REGISTRY_ARGS=(--registry-server ghcr.io --registry-username "$GHCR_USER" --registry-password "$GHCR_TOKEN")
fi

ENV_VARS=(ANTHROPIC_API_KEY=secretref:anthropic-key ACCESS_CODE=secretref:access-code
  LLM_PROVIDER=anthropic MODEL="$MODEL" EFFORT="$EFFORT" SANDBOX=azure
  AZURE_SESSION_POOL_ENDPOINT="$POOL_ENDPOINT"
  SESSION_TOKEN_BUDGET="$SESSION_TOKEN_BUDGET" DAILY_TOKEN_BUDGET="$DAILY_TOKEN_BUDGET")

echo "==> Container App"
if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp secret set -n "$APP" -g "$RG" -o none \
    --secrets anthropic-key="$ANTHROPIC_API_KEY" access-code="$ACCESS_CODE"
  az containerapp update -n "$APP" -g "$RG" --image "$IMAGE" --set-env-vars "${ENV_VARS[@]}" -o none
else
  az containerapp create -n "$APP" -g "$RG" --environment "$ENV_NAME" --image "$IMAGE" "${REGISTRY_ARGS[@]}" \
    --ingress external --target-port 8000 --min-replicas 0 --max-replicas 1 --cpu 0.5 --memory 1.0Gi \
    --system-assigned \
    --secrets anthropic-key="$ANTHROPIC_API_KEY" access-code="$ACCESS_CODE" \
    --env-vars "${ENV_VARS[@]}" -o none
fi

echo "==> Let the app's managed identity run code in the pool (and nothing else)"
PRINCIPAL=$(az containerapp show -n "$APP" -g "$RG" --query identity.principalId -o tsv)
for ROLE in "Azure ContainerApps Session Executor" "Contributor"; do
  az role assignment create --assignee-object-id "$PRINCIPAL" --assignee-principal-type ServicePrincipal \
    --role "$ROLE" --scope "$POOL_ID" -o none 2>/dev/null || true
done

URL=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo
echo "Done. Open https://$URL and sign in with your ACCESS_CODE."
echo "Role assignments can take a few minutes to apply before the coding lab works."
