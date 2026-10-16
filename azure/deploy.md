# Deploy DataPilot to Azure

Two routes. **App Service** is the simplest and the one most enterprise
IT teams already operate. The container route is there if your team
standardizes on images.

Everything below assumes the [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
is installed and you're signed in (`az login`).

## 0. One-time: create the Azure OpenAI resource (the LLM)

DataPilot's full natural-language mode needs an Azure OpenAI deployment.
Skip this if you're staying on `LLM_MODE=demo` for now.

```bash
az group create --name datapilot-rg --location centralus

az cognitiveservices account create \
  --name datapilot-openai \
  --resource-group datapilot-rg \
  --location centralus \
  --kind OpenAI \
  --sku S0

az cognitiveservices account deployment create \
  --name datapilot-openai \
  --resource-group datapilot-rg \
  --deployment-name gpt-4o-mini \
  --model-name gpt-4o-mini \
  --model-version "2024-07-18" \
  --model-format OpenAI \
  --sku-capacity 10 --sku-name Standard
```

Grab the endpoint + key:

```bash
az cognitiveservices account show --name datapilot-openai \
  --resource-group datapilot-rg --query properties.endpoint -o tsv

az cognitiveservices account keys list --name datapilot-openai \
  --resource-group datapilot-rg --query key1 -o tsv
```

## 1. Secrets in Key Vault (do this before the app)

```bash
az keyvault create --name datapilot-kv --resource-group datapilot-rg \
  --location centralus

for s in DATABRICKS_HOST DATABRICKS_HTTP_PATH DATABRICKS_TOKEN \
         AZURE_OPENAI_ENDPOINT AZURE_OPENAI_KEY DATAPILOT_API_KEY; do
  read -s -p "$s: " val; echo
  az keyvault secret set --vault-name datapilot-kv --name $s --value "$val" > /dev/null
done
```

## 2. Route A — App Service (recommended)

```bash
az appservice plan create --name datapilot-plan \
  --resource-group datapilot-rg --sku B1 --is-linux

az webapp create --name datapilot-app \
  --resource-group datapilot-rg --plan datapilot-plan \
  --runtime "PYTHON:3.12"
```

Give the app a managed identity and Key Vault access (no secrets in config):

```bash
az webapp identity assign --name datapilot-app --resource-group datapilot-rg

PRINCIPAL=$(az webapp identity show --name datapilot-app \
  --resource-group datapilot-rg --query principalId -o tsv)

az keyvault set-policy --name datapilot-kv --object-id $PRINCIPAL \
  --secret-permissions get
```

Point the app at the secrets and set the startup command:

```bash
KV=https://datapilot-kv.vault.azure.net
az webapp config appsettings set --name datapilot-app \
  --resource-group datapilot-rg --settings \
  LLM_MODE=azure \
  AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini \
  DATABRICKS_HOST="@Microsoft.KeyVault(SecretUri=$KV/secrets/DATABRICKS_HOST/)" \
  DATABRICKS_HTTP_PATH="@Microsoft.KeyVault(SecretUri=$KV/secrets/DATABRICKS_HTTP_PATH/)" \
  DATABRICKS_TOKEN="@Microsoft.KeyVault(SecretUri=$KV/secrets/DATABRICKS_TOKEN/)" \
  AZURE_OPENAI_ENDPOINT="@Microsoft.KeyVault(SecretUri=$KV/secrets/AZURE_OPENAI_ENDPOINT/)" \
  AZURE_OPENAI_KEY="@Microsoft.KeyVault(SecretUri=$KV/secrets/AZURE_OPENAI_KEY/)" \
  DATAPILOT_API_KEY="@Microsoft.KeyVault(SecretUri=$KV/secrets/DATAPILOT_API_KEY/)" \
  SCM_DO_BUILD_DURING_DEPLOYMENT=true

az webapp config set --name datapilot-app --resource-group datapilot-rg \
  --startup-file "uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

Deploy from this folder:

```bash
cd ~/workspace/datapilot   # or wherever the repo lives
az webapp up --name datapilot-app --resource-group datapilot-rg \
  --runtime "PYTHON:3.12"
```

Open `https://datapilot-app.azurewebsites.net` — the health endpoint
`…/api/health` should report `"warehouse": "databricks"`.

## 3. Route B — Container (Container Apps)

```bash
az acr create --name datapilotacr --resource-group datapilot-rg --sku Basic
az acr build --registry datapilotacr --image datapilot:latest ./azure/..
# (Dockerfile is in azure/; build context is the repo root)

az containerapp env create --name datapilot-env --resource-group datapilot-rg
az containerapp create --name datapilot --resource-group datapilot-rg \
  --environment datapilot-env \
  --image datapilotacr.azurecr.io/datapilot:latest \
  --target-port 8000 --ingress external \
  --env-vars LLM_MODE=azure AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini \
  --secrets dbr-host=... dbr-path=...  # or Key Vault refs
```

## 4. After deploy — verify

```bash
curl https://datapilot-app.azurewebsites.net/api/health

curl -s -H "X-API-Key: <your key>" -H "Content-Type: application/json" \
  -d '{"question":"What tables can I use?"}' \
  https://datapilot-app.azurewebsites.net/api/ask
```

The first question to ask in production: **"What tables can I use?"** —
the app inventories Unity Catalog by itself.

## Notes for the enterprise-applications conversation

- The API key in this repo is a placeholder. The production move is
  Entra ID (OAuth2) — `app/auth.py` is the only file that changes.
- The demo SQLite (`data/datapilot.db`) is local throwaway state for
  dashboards/history. On Azure, mount Azure Files or move those two
  tables to Postgres — the warehouse data itself stays in Databricks.
- Databricks token here is a PAT for dev speed. Production uses a
  Databricks service principal with least-privilege grants on exactly
  the schemas the copilot may read.
