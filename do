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
  test            Run the test suite
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
  test)            cmd_test ;;
  fmt)             cmd_fmt ;;
  check)           cmd_check ;;
  *)
    echo "Unknown command: $1" >&2
    cmd_help
    exit 1
    ;;
esac
