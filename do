#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd_help() {
  cat <<EOF
Usage: ./do <command>

Commands:
  help            Show this help

  Data pipeline:
    fetch-companies   Download Finnish companies from PRH YTJ API
    generate-data     Generate fixture data (--small / --medium / default 1M)
    load-data         Upload fixture data to Aito (and optimize tables)
    reset-data        Drop all tables and reload from fixtures
    optimize          Optimize Aito tables for faster queries
    warm-cache        Pre-warm API cache for top customers
    precompute        Pre-compute predictions for demo views

  Development:
    dev               Start the backend API server (port 8200)
    frontend-dev      Start Next.js dev server (port 3000)
    frontend-build    Build Next.js static export
    demo              Open the demo in browser

  Testing:
    test              Run unit tests (pytest)
    book              Run book tests (Aito examination notebooks)
    book-update       Update book test snapshots
    book-capture      Capture fresh snapshots from live Aito

  Deployment:
    docker-build      Build the Docker image (frontend + API + precomputed)
    docker-run        Run the image locally on http://localhost:8200
    azure-deploy      Push image + deploy to Azure (see docs/deploy-azure.md)

  Other:
    screenshots       Capture screenshots of all views
    fmt               Format code
    check             Run all checks (test + fmt)

EOF
}

cmd_dev() {
  echo "Starting Predictive Ledger API on http://localhost:8200"
  if [[ -d "$SCRIPT_DIR/frontend/out" ]]; then
    echo "  Frontend: serving Next.js build from frontend/out/"
  else
    echo "  Frontend: not built. Run ./do frontend-build first."
  fi
  cd "$SCRIPT_DIR"
  uv run uvicorn src.app:app --reload --port 8200
}

cmd_frontend_dev() {
  echo "Starting Next.js dev server on http://localhost:3000"
  echo "  API proxy → http://localhost:8200 (start ./do dev in another terminal)"
  cd "$SCRIPT_DIR/frontend"
  npx next dev -p 3000
}

cmd_frontend_build() {
  echo "Building Next.js static export..."
  cd "$SCRIPT_DIR/frontend"
  npx next build
  echo "Built to frontend/out/ — ./do dev will serve it."
}

cmd_demo() {
  if curl -s -o /dev/null http://localhost:8200/api/health 2>/dev/null; then
    echo "Opening http://localhost:8200"
    if command -v xdg-open &>/dev/null; then
      xdg-open "http://localhost:8200"
    elif command -v open &>/dev/null; then
      open "http://localhost:8200"
    else
      echo "Open manually: http://localhost:8200"
    fi
  else
    echo "Backend not running. Start with: ./do dev"
    echo "Start with: ./do dev"
  fi
}

cmd_fetch_companies() {
  echo "Downloading Finnish companies from PRH YTJ API..."
  cd "$SCRIPT_DIR"
  uv run python data/fetch_companies.py
}

cmd_optimize() {
  echo "Optimizing Aito tables..."
  cd "$SCRIPT_DIR"
  uv run python -c "
from src.config import load_config
from src.aito_client import AitoClient
from src.data_loader import optimize_table, SCHEMAS
client = AitoClient(load_config())
for table_name in SCHEMAS:
    optimize_table(client, table_name)
print('Done.')
"
}

cmd_warm_cache() {
  cd "$SCRIPT_DIR"
  uv run python scripts/warm_cache.py "$@"
}

cmd_load_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader
}

cmd_reset_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader --reset
}

cmd_generate_data() {
  cd "$SCRIPT_DIR"
  uv run python data/generate_fixtures.py "$@"
}

cmd_precompute() {
  cd "$SCRIPT_DIR"
  echo "Pre-computing predictions for all customers..."
  echo "  (~3min/customer sequentially; pass --workers 4 for ~4x speedup)"
  uv run python data/precompute_predictions.py "$@"
}

cmd_test() {
  cd "$SCRIPT_DIR"
  uv run pytest tests/ -v
}

# ── Deployment ────────────────────────────────────────────────────

DOCKER_IMAGE="${DOCKER_IMAGE:-predictive-ledger}"
DOCKER_TAG="${DOCKER_TAG:-latest}"

cmd_docker_build() {
  cd "$SCRIPT_DIR"
  if [ ! -d "data/precomputed" ] || [ -z "$(ls -A data/precomputed 2>/dev/null)" ]; then
    echo "Warning: data/precomputed/ is empty. Run ./do precompute first," >&2
    echo "or the image will fall back to live Aito calls on every request." >&2
  fi
  docker build -t "${DOCKER_IMAGE}:${DOCKER_TAG}" .
  echo
  echo "Built ${DOCKER_IMAGE}:${DOCKER_TAG}"
  echo "Run with: ./do docker-run"
}

cmd_docker_run() {
  cd "$SCRIPT_DIR"
  if [ ! -f .env ]; then
    echo "Error: .env file not found. Aito credentials must be in .env." >&2
    exit 1
  fi
  docker run --rm -it \
    --env-file .env \
    -p 8200:8200 \
    "${DOCKER_IMAGE}:${DOCKER_TAG}"
}

cmd_azure_deploy() {
  cd "$SCRIPT_DIR"
  if [ ! -f docs/deploy-azure.md ]; then
    echo "See docs/deploy-azure.md for one-time Azure setup." >&2
    exit 1
  fi
  : "${AZURE_RESOURCE_GROUP:?set AZURE_RESOURCE_GROUP (e.g. predictive-ledger-rg)}"
  : "${AZURE_REGISTRY:?set AZURE_REGISTRY (your ACR name, no .azurecr.io suffix)}"
  : "${AZURE_APP_NAME:?set AZURE_APP_NAME (e.g. predictive-ledger)}"

  local full="${AZURE_REGISTRY}.azurecr.io/${DOCKER_IMAGE}:${DOCKER_TAG}"

  echo "→ Building image"
  docker build -t "$full" .

  echo "→ Pushing to ${AZURE_REGISTRY}.azurecr.io"
  az acr login --name "$AZURE_REGISTRY"
  docker push "$full"

  echo "→ Updating Container App ${AZURE_APP_NAME}"
  az containerapp update \
    --name "$AZURE_APP_NAME" \
    --resource-group "$AZURE_RESOURCE_GROUP" \
    --image "$full"

  echo
  echo "Deployed. Tail logs with:"
  echo "  az containerapp logs show -n $AZURE_APP_NAME -g $AZURE_RESOURCE_GROUP --follow"
}

cmd_fmt() {
  echo "No formatter configured yet."
}

cmd_screenshots() {
  echo "Capturing screenshots of all views..."
  echo "  Waiting for API and cache warmup..."
  mkdir -p "$SCRIPT_DIR/screenshots"

  # Wait for server + full cache warmup by polling the slowest endpoints
  for ep in /api/invoices/pending /api/matching/pairs /api/rules/candidates /api/anomalies/scan /api/quality/overview; do
    for i in $(seq 1 60); do
      result=$(curl -s http://localhost:8200${ep} 2>/dev/null)
      if [ -n "$result" ] && echo "$result" | grep -qv '"Loading"'; then
        break
      fi
      sleep 2
    done
  done
  echo "  All endpoints ready."

  # Ensure playwright-core is available
  if [ ! -d "$SCRIPT_DIR/frontend/node_modules/playwright-core" ]; then
    (cd "$SCRIPT_DIR/frontend" && npm install --save-dev playwright-core@1.52.0 --silent)
  fi

  # Find chromium binary from nix
  local chrome="${PLAYWRIGHT_BROWSERS_PATH}/chromium-1169/chrome-linux/chrome"
  if [ ! -x "$chrome" ]; then
    echo "Error: chromium not found at $chrome" >&2
    echo "Set PLAYWRIGHT_BROWSERS_PATH or enter the nix shell." >&2
    exit 1
  fi

  node -e "
    const { chromium } = require('$SCRIPT_DIR/frontend/node_modules/playwright-core');
    (async () => {
      const browser = await chromium.launch({ executablePath: '$chrome', headless: true });
      const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
      const routes = [
        ['01-invoices','/invoices/'],
        ['02-formfill','/formfill/'],
        ['03-matching','/matching/'],
        ['04-rulemining','/rulemining/'],
        ['05-anomalies','/anomalies/'],
        ['06-quality-overview','/quality/overview/'],
        ['07-quality-rules','/quality/rules/'],
        ['08-quality-predictions','/quality/predictions/'],
        ['09-quality-overrides','/quality/overrides/'],
      ];
      for (const [name, path] of routes) {
        await page.goto('http://localhost:8200' + path);
        await page.waitForTimeout(2500);
        await page.screenshot({ path: '$SCRIPT_DIR/screenshots/' + name + '.png' });
        console.log('  captured ' + name);
      }
      await browser.close();
    })();
  "
  echo "Done. Screenshots in screenshots/"
}

cmd_book() {
  echo "Running book tests..."
  cd "$SCRIPT_DIR"
  uv run booktest -v book/ "$@"
}

cmd_book_update() {
  echo "Updating book test snapshots..."
  cd "$SCRIPT_DIR"
  uv run booktest -v -u book/ "$@"
}

cmd_book_capture() {
  echo "Capturing fresh snapshots from live Aito..."
  cd "$SCRIPT_DIR"
  uv run booktest -v -u -s book/ "$@"
}

cmd_check() {
  cmd_test
  cmd_fmt
}

case "${1:-help}" in
  help)            cmd_help ;;
  dev)             cmd_dev ;;
  frontend-dev)    cmd_frontend_dev ;;
  frontend-build)  cmd_frontend_build ;;
  demo)            cmd_demo ;;
  load-data)       cmd_load_data ;;
  reset-data)      cmd_reset_data ;;
  generate-data)   cmd_generate_data "${@:2}" ;;
  precompute)      cmd_precompute "${@:2}" ;;
  screenshots)     cmd_screenshots ;;
  test)            cmd_test ;;
  fetch-companies) cmd_fetch_companies ;;
  optimize)        cmd_optimize ;;
  warm-cache)      cmd_warm_cache "${@:2}" ;;
  book)            cmd_book ;;
  book-update)     cmd_book_update ;;
  book-capture)    cmd_book_capture ;;
  docker-build)    cmd_docker_build ;;
  docker-run)      cmd_docker_run ;;
  azure-deploy)    cmd_azure_deploy ;;
  fmt)             cmd_fmt ;;
  check)           cmd_check ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
