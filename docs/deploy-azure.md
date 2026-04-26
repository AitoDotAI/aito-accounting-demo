# Deploying the Predictive Ledger demo to Azure

Target: a single public URL serving the same demo `./do dev` runs
locally. We deploy the Docker image (`Dockerfile` at the repo root)
to **Azure Container Apps**. This gives us scale-to-zero pricing,
HTTPS + custom domains out of the box, and one-command redeploys.

## What's in the image

- The FastAPI backend (`src/`)
- The Next.js static export (built into `frontend/out/` during the
  Docker build)
- Pre-computed prediction JSON (`data/precomputed/`) — the **read**
  endpoints serve these directly. Only Form Fill calls Aito at
  runtime.
- The fixture JSON (`data/*.json`) — the API does not need them
  once predictions are precomputed, but they're tiny and ship inside
  the image for now.

## One-time setup

Assumes Azure CLI is logged in (`az login`).

```bash
# Pick names — these become DNS-visible later
RG=predictive-ledger-rg            # resource group
LOCATION=northeurope               # closest to Helsinki / Aito
ACR=predictiveledgerregistry       # must be globally unique
ENV_NAME=predictive-ledger-env     # Container Apps environment
APP_NAME=predictive-ledger         # the app itself
```

### 1. Resource group + Container Registry

```bash
az group create --name $RG --location $LOCATION

az acr create \
  --resource-group $RG \
  --name $ACR \
  --sku Basic \
  --admin-enabled true
```

### 2. Container Apps environment

```bash
az extension add --name containerapp --upgrade

az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights

az containerapp env create \
  --name $ENV_NAME \
  --resource-group $RG \
  --location $LOCATION
```

### 3. First deploy (creates the app + secrets)

```bash
# Aito credentials — these match what's in your local .env
AITO_INSTANCE_NAME=...     # e.g. my-instance.aito.app
AITO_API_KEY=...           # full read/write key

# Build + push first image so the create command has something to point at
az acr login --name $ACR
docker build -t $ACR.azurecr.io/predictive-ledger:latest .
docker push $ACR.azurecr.io/predictive-ledger:latest

az containerapp create \
  --name $APP_NAME \
  --resource-group $RG \
  --environment $ENV_NAME \
  --image $ACR.azurecr.io/predictive-ledger:latest \
  --target-port 8200 \
  --ingress external \
  --registry-server $ACR.azurecr.io \
  --secrets aito-api-key=$AITO_API_KEY \
  --env-vars \
      AITO_INSTANCE_NAME=$AITO_INSTANCE_NAME \
      AITO_API_KEY=secretref:aito-api-key \
      DEMO_MODE=true \
      DEMO_MAX_REQUESTS=30 \
  --min-replicas 0 \
  --max-replicas 2

# Note the public URL it prints
az containerapp show -n $APP_NAME -g $RG --query properties.configuration.ingress.fqdn -o tsv
```

### 4. Re-deploys

After the one-time setup, every redeploy goes through `./do
azure-deploy`. Required env vars (set them once in your shell):

```bash
export AZURE_RESOURCE_GROUP=$RG
export AZURE_REGISTRY=$ACR
export AZURE_APP_NAME=$APP_NAME
```

Then:

```bash
./do precompute --workers 4   # regenerate predictions if data changed
./do azure-deploy             # build → push → containerapp update
```

`./do azure-deploy` does:

1. `docker build` → `$ACR.azurecr.io/predictive-ledger:latest`
2. `az acr login` + `docker push`
3. `az containerapp update --image …`

## Rate limiting

The container respects two env vars set above:
- **`DEMO_MAX_REQUESTS=30`** — drops the per-IP cap from the default
  60/min. Behind Container Apps the remote IP is the ingress proxy,
  so this is effectively a global cap. Form Fill is the only live
  Aito-calling endpoint; everything else serves precomputed JSON, so
  30/min is comfortable headroom for one CTO clicking around.
- **`DEMO_MODE=true`** — surfaced via `/api/health` so a future
  client banner ("Demo instance — predictions on a fixed dataset")
  can render without a hardcoded check.

## Custom domain (optional)

```bash
az containerapp hostname add --hostname demo.your-domain.com \
  --name $APP_NAME --resource-group $RG

# Add the CNAME record they print to your DNS

az containerapp hostname bind --hostname demo.your-domain.com \
  --name $APP_NAME --resource-group $RG --validation-method CNAME
```

## Logs

```bash
az containerapp logs show -n $APP_NAME -g $RG --follow
```

## Cost estimate

Container Apps with `min-replicas=0` is effectively free at low
traffic — you pay per request + per second of CPU/RAM, with a
180,000 req/month free tier. For a demo a CTO opens a few times,
this typically lands at $0–5/month. ACR Basic is ~$5/month.
