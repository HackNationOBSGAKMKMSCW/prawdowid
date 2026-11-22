#!/usr/bin/env bash
# Buduje stronę i panel admina do /opt/prawdowid/dist (serwuje je Caddy).
#   dist/         strona (tryb live: woła /api na tym samym adresie)
#   dist/admin/   panel admina (base /admin/, woła /api/admin)
# Uruchamiaj jako użytkownik prawdowid z katalogu repo: sudo -u prawdowid deploy/build-frontend.sh
set -euo pipefail
cd "$(dirname "$0")/.."

# Zmienne procesu mają pierwszeństwo przed .env (Vite czyta .env z katalogu głównego).
export VITE_API_MODE=live
export VITE_API_BASE_URL=/api
export VITE_CHECK_TIMEOUT_MS="${VITE_CHECK_TIMEOUT_MS:-310000}"

npm ci --prefix frontend --no-audit --no-fund
npm ci --prefix admin_panel/frontend --no-audit --no-fund
npm run build:live --prefix frontend
npm run build --prefix admin_panel/frontend -- --base=/admin/

rm -rf dist.new
cp -r frontend/dist dist.new
cp -r admin_panel/frontend/dist dist.new/admin
rm -rf dist
mv dist.new dist
echo "Zbudowano: $(pwd)/dist"
