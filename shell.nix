{ pkgs ? import <nixpkgs> {} }:

let
  python = pkgs.python312;
  pythonPackages = python.pkgs;
in
pkgs.mkShell {
  name = "aito-accounting-poc";

  buildInputs = [
    # Python backend
    python
    pythonPackages.pip
    pythonPackages.virtualenv

    # Node / Next.js frontend
    pkgs.nodejs_20
    pkgs.corepack # enables pnpm/yarn via packageManager field

    # Playwright system dependencies
    pkgs.playwright-driver.browsers

    # Dev tools
    pkgs.jq
    pkgs.curl
    pkgs.httpie # nicer than curl for API testing
    pkgs.watchexec # file watcher for ./do dev
  ];

  shellHook = ''
    # Python virtualenv (keeps nix shell pure, pip installs isolated)
    if [ ! -d .venv ]; then
      echo "Creating Python virtualenv..."
      python -m venv .venv
    fi
    source .venv/bin/activate

    # Install Python deps if requirements.txt exists and changed
    if [ -f requirements.txt ]; then
      pip install -q -r requirements.txt
    fi

    # Install Node deps if package.json exists
    if [ -f frontend/package.json ] && [ ! -d frontend/node_modules ]; then
      echo "Installing frontend dependencies..."
      (cd frontend && npm install)
    fi

    # Playwright browser path (use nix-managed browsers)
    export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1

    # Project env
    export AITO_API_URL="''${AITO_API_URL:-http://localhost:8002}"
    export AITO_API_KEY="''${AITO_API_KEY:-}"
    export PYTHONDONTWRITEBYTECODE=1
    export PYTHONUNBUFFERED=1

    # Remind if Aito key is missing
    if [ -z "$AITO_API_KEY" ]; then
      echo ""
      echo "⚠  AITO_API_KEY not set. Export it or add to .env"
      echo "   export AITO_API_KEY=your-key-here"
      echo ""
    fi

    echo ""
    echo "Aito Accounting PoC — run ./do help for available commands"
    echo ""
  '';
}
