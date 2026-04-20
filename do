#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cmd_help() {
  cat <<EOF
Usage: ./do <command>

Commands:
  help            Show this help
  dev             Start the backend API server (port 8200)
  frontend-dev    Start Next.js dev server (port 3000, proxies to 8200)
  frontend-build  Build Next.js static export to frontend/out/
  demo            Open the demo (http://localhost:8200 if backend running)
  load-data       Upload sample data to Aito
  reset-data      Drop and reload all Aito tables
  screenshots     Capture screenshots of all views (needs running server)
  test            Run the unit test suite
  book            Run book tests (Aito examination notebooks)
  book-update     Update book test snapshots after review
  fmt             Format code
  check           Run all pre-merge checks (test + fmt)

EOF
}

cmd_dev() {
  echo "Starting Ledger Pro API on http://localhost:8200"
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
    echo "Or open the static HTML: ledger-pro-demo.html"
  fi
}

cmd_load_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader
}

cmd_reset_data() {
  cd "$SCRIPT_DIR"
  uv run python -m src.data_loader --reset
}

cmd_test() {
  cd "$SCRIPT_DIR"
  uv run pytest tests/ -v
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
  screenshots)     cmd_screenshots ;;
  test)            cmd_test ;;
  book)            cmd_book ;;
  book-update)     cmd_book_update ;;
  fmt)             cmd_fmt ;;
  check)           cmd_check ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
