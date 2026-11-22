#!/usr/bin/env bash
# Instalacja i aktualizacja Prawdowida na jednym serwerze (Ubuntu/Debian).
# Strona, panel admina i backend za Caddy; baza PostgreSQL już stoi na tym serwerze.
#
# Uruchamiaj jako root, z repo w /opt/prawdowid (instrukcja: deploy/README.md):
#   sudo deploy/setup.sh :80                  # http://<IP-serwera>
#   sudo deploy/setup.sh 203-0-113-5.sslip.io # https://203-0-113-5.sslip.io (IP z kreskami)
#   sudo deploy/setup.sh                      # ponownie z poprzednim adresem (aktualizacja)
#
# Skrypt można uruchamiać wiele razy: robi tylko to, czego brakuje, i restartuje usługi.
set -euo pipefail

APP_DIR=/opt/prawdowid
APP_USER=prawdowid
SITE_FILE=/etc/prawdowid/site

die() { echo "BŁĄD: $*" >&2; exit 1; }
step() { echo; echo "==> $*"; }
as_app() { sudo -u "$APP_USER" -H env "$@"; }

[ "$(id -u)" = 0 ] || die "uruchom jako root: sudo deploy/setup.sh ..."
[ "$(cd "$(dirname "$0")/.." && pwd -P)" = "$APP_DIR" ] || die "repo musi leżeć w $APP_DIR"
cd "$APP_DIR"

SITE="${1:-$(cat "$SITE_FILE" 2>/dev/null || true)}"
[ -n "$SITE" ] || die "podaj adres: ':80' (samo IP, HTTP) albo '<ip-z-kreskami>.sslip.io' (HTTPS)"

[ -f .env ] || die "brak .env: cp deploy/server.env.example .env i uzupełnij wartości <...>"
if grep -nE '^[A-Z_]+=.*<[^>]*>' .env; then
  die "uzupełnij w .env wartości w <...> (linie wyżej)"
fi

# Pamięci podręczne narzędzi w katalogu aplikacji (użytkownik systemowy nie ma katalogu domowego).
APP_ENV=(
  HOME="$APP_DIR"
  UV_CACHE_DIR="$APP_DIR/.cache/uv"
  UV_PYTHON_INSTALL_DIR="$APP_DIR/.cache/uv-python"
  npm_config_cache="$APP_DIR/.cache/npm"
  PATH="/usr/local/bin:/usr/bin:/bin:$(dirname "$(command -v node 2>/dev/null || echo /usr/bin/node)")"
)

step "Użytkownik $APP_USER"
id "$APP_USER" >/dev/null 2>&1 \
  || useradd --system --home-dir "$APP_DIR" --no-create-home --shell /usr/sbin/nologin "$APP_USER"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 755 "$APP_DIR"
chmod 600 .env

step "Pakiety: Caddy, Node.js, uv"
command -v caddy >/dev/null || { apt-get update && apt-get install -y caddy; } \
  || die "nie udało się zainstalować Caddy z apt; instrukcja: https://caddyserver.com/docs/install#debian-ubuntu-raspbian"
command -v node >/dev/null || die "brak Node.js 22: https://nodejs.org (np. NodeSource: setup_22.x)"
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$node_major" -ge 20 ] || die "Node.js $node_major jest za stary, potrzebny 22 LTS (albo 20.19+)"
# uv w /usr/local/bin: ten z katalogu domowego roota jest niedostępny dla użytkownika aplikacji.
UV=/usr/local/bin/uv
[ -x "$UV" ] \
  || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
[ -x "$UV" ] || die "nie udało się zainstalować uv w /usr/local/bin"

step "Python 3.13 i zależności backendu"
[ -x .venv/bin/python ] || as_app "${APP_ENV[@]}" "$UV" venv --python 3.13 .venv
as_app "${APP_ENV[@]}" "$UV" pip install --python .venv/bin/python -r requirements.txt

step "Baza: migracje (dokładają tylko brakujące tabele)"
(cd backend && as_app "${APP_ENV[@]}" ../.venv/bin/python -m database migrate) \
  || die "migracja nie przeszła: sprawdź DATABASE_URL w .env i deploy/README.md (krok 2)"

step "Strona i panel admina → $APP_DIR/dist"
as_app "${APP_ENV[@]}" deploy/build-frontend.sh

step "Backend (systemd)"
install -m 644 deploy/prawdowid-backend.service /etc/systemd/system/prawdowid-backend.service
systemctl daemon-reload
systemctl enable --quiet prawdowid-backend
systemctl restart prawdowid-backend
for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && break
  sleep 1
done
curl -fsS http://127.0.0.1:8000/api/health >/dev/null \
  || die "backend nie odpowiada; logi: journalctl -u prawdowid-backend -n 50"

step "Caddy: $SITE"
mkdir -p "$(dirname "$SITE_FILE")" /var/log/caddy
echo "$SITE" > "$SITE_FILE"
if [ -f /etc/caddy/Caddyfile ] && ! grep -q "prawdowid" /etc/caddy/Caddyfile; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.przed-prawdowid
fi
sed "s|__SITE__|$SITE|" deploy/Caddyfile > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
chown -R caddy:caddy /var/log/caddy
systemctl enable --quiet caddy
systemctl reload caddy 2>/dev/null || systemctl restart caddy

if [ "$SITE" = ":80" ]; then
  url="http://$(curl -4 -fsS --max-time 10 https://ifconfig.me 2>/dev/null || echo '<IP-serwera>')"
else
  url="https://$SITE"
fi
cat <<INFO

Gotowe.
  Strona:        $url
  Panel admina:  $url/admin/
  Stan:          $url/api/health
Sprawdź adres spoza sieci domowej (np. telefon na LTE). Jeśli nie działa: przekierowanie
portów na routerze i zapora (deploy/README.md, krok 1).
Logi: journalctl -u prawdowid-backend -f   oraz   /var/log/caddy/prawdowid.log
INFO
