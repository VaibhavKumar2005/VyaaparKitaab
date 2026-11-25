#!/usr/bin/env bash
# End-to-end Azure deployment helper for VyaparKitaab:
#   1. Verifies Azure CLI login & active subscription.
#   2. Provisions core infra via Terraform (infra/bootstrap -> infra/terraform) OR updates Container App.
#   3. Builds the Docker image directly in Azure Container Registry (`az acr build`) with tesseract-ocr-hin + poppler-utils.
#   4. Updates the Container App to the newly built ACR image.
#   5. Builds frontend/ with VITE_API_URL=<Container App HTTPS URL> and deploys to Azure Static Web Apps.
#
# Required env vars before running (never commit secrets):
#   export TF_VAR_postgres_admin_password="YourStrongPgPassword!23"
#   export TF_VAR_secret_key="$(openssl rand -hex 32)"
# Optional live integration env vars:
#   export TF_VAR_encryption_key="$(openssl rand -hex 32)"
#   export TF_VAR_smtp_user="you@gmail.com"
#   export TF_VAR_smtp_from_email="you@gmail.com"
#   export TF_VAR_smtp_password="your-16-char-gmail-app-password"
#   export TF_VAR_payment_gateway="razorpay"
#   export TF_VAR_payment_key_id="rzp_test_..."
#   export TF_VAR_payment_key_secret="..."
#   export TF_VAR_payment_webhook_secret="..."
#   export TF_VAR_gemini_api_key="..."

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOOTSTRAP_DIR="$ROOT/infra/bootstrap"
TF_DIR="$ROOT/infra/terraform"

command -v az >/dev/null || { echo "ERROR: Azure CLI (az) not found."; exit 1; }
command -v terraform >/dev/null || { echo "ERROR: Terraform not found."; exit 1; }

echo "==> Checking Azure login..."
az account show --query "{name:name, id:id, tenantId:tenantId}" -o table

if [ -z "${TF_VAR_postgres_admin_password:-}" ] || [ -z "${TF_VAR_secret_key:-}" ]; then
  echo "ERROR: Export TF_VAR_postgres_admin_password and TF_VAR_secret_key before running."
  exit 1
fi

echo "==> Step 1: Bootstrapping remote Terraform state storage in Azure..."
(
  cd "$BOOTSTRAP_DIR"
  terraform init -input=false
  terraform apply -auto-approve -input=false
)

STATE_RG=$(terraform -chdir="$BOOTSTRAP_DIR" output -raw resource_group_name)
STATE_SA=$(terraform -chdir="$BOOTSTRAP_DIR" output -raw storage_account_name)
STATE_CONTAINER=$(terraform -chdir="$BOOTSTRAP_DIR" output -raw container_name)
STATE_KEY=$(terraform -chdir="$BOOTSTRAP_DIR" output -raw state_key)

echo "==> Step 2: Initializing main Azure infrastructure stack..."
(
  cd "$TF_DIR"
  terraform init -input=false -reconfigure \
    -backend-config="resource_group_name=$STATE_RG" \
    -backend-config="storage_account_name=$STATE_SA" \
    -backend-config="container_name=$STATE_CONTAINER" \
    -backend-config="key=$STATE_KEY"

  # Create ACR first so we can build & push our production Docker image before starting the Container App
  terraform apply -auto-approve -input=false \
    -target=azurerm_resource_group.main \
    -target=azurerm_container_registry.main
)

ACR_NAME=$(terraform -chdir="$TF_DIR" output -raw container_registry_name 2>/dev/null || \
  az acr list --resource-group "rg-vyaaparkitaab-${TF_VAR_environment:-prod}" --query "[0].name" -o tsv)
ACR_LOGIN=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)}"
FULL_IMAGE="$ACR_LOGIN/vyaaparkitaab-backend:$IMAGE_TAG"

echo "==> Step 3: Building Docker image in Azure Container Registry ($FULL_IMAGE)..."
az acr build \
  --registry "$ACR_NAME" \
  --image "vyaaparkitaab-backend:$IMAGE_TAG" \
  --image "vyaaparkitaab-backend:latest" \
  --file "$ROOT/docker/Dockerfile" \
  "$ROOT"

echo "==> Step 4: Applying complete Terraform stack (Postgres 16, Key Vault, Container App, Static Web App, Monitoring)..."
export TF_VAR_backend_image="$FULL_IMAGE"
(
  cd "$TF_DIR"
  terraform apply -auto-approve -input=false
)

API_URL=$(terraform -chdir="$TF_DIR" output -raw container_app_url)
FRONTEND_URL=$(terraform -chdir="$TF_DIR" output -raw frontend_url)
SWA_TOKEN=$(terraform -chdir="$TF_DIR" output -raw static_web_app_api_key)

echo "==> Step 5: Building React frontend with VITE_API_URL=$API_URL..."
(
  cd "$ROOT/frontend"
  npm ci
  VITE_API_URL="$API_URL" npm run build
)

echo "==> Step 6: Deploying frontend/dist to Azure Static Web Apps ($FRONTEND_URL)..."
npx --yes @azure/static-web-apps-cli deploy "$ROOT/frontend/dist" \
  --deployment-token "$SWA_TOKEN" \
  --env production

echo ""
echo "=== Azure Deployment Complete ==="
echo "Frontend (HTTPS): $FRONTEND_URL"
echo "Backend  (HTTPS): $API_URL"
echo "Health Check:     $API_URL/api/v1/health"
