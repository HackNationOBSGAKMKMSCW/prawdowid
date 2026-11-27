# Wdrożenie na jednym serwerze (strona + panel + backend + baza, model z API OpenAI)

```
Użytkownik ─> http://<IP-serwera>  albo  https://<ip-z-kreskami>.sslip.io
                 └── Caddy (porty 80/443)
                       ├── /          strona            (/opt/prawdowid/dist)
                       ├── /admin/    panel admina      (/opt/prawdowid/dist/admin)
                       └── /api/*  ─> backend FastAPI   127.0.0.1:8000 (systemd)
                                        ├── PostgreSQL  127.0.0.1:5432 (już jest na serwerze)
                                        └── API OpenAI  (gpt-6.2-sol)
```

Wszystko jest pod jednym adresem, więc CORS i przekierowania nie są potrzebne. Z internetu
otwarte są tylko porty 80 (i 443 przy HTTPS). Bazy (5432) i backendu (8000) nie otwieraj.

## Co się zmienia względem wersji lokalnej

Tylko konfiguracja w `/opt/prawdowid/.env` (wzór: `deploy/server.env.example`):

| Zmienna | Lokalnie było | Na serwerze |
|---|---|---|
| `FREELLM_BASE_URL` | Ollama w Tailscale | `https://api.openai.com/v1` |
| `FREELLM_API_KEY` | `ollama` | klucz OpenAI |
| `FREELLM_MODEL` | `gemma4:26b-a4b` | `gpt-6.2-sol` |
| `LLM_REASONING_EFFORT` | (brak) | `low` (gpt-6.2-sol odrzuca `none`) |
| `KNOWN_DISINFO_REASONING_EFFORT`, `LLM_TEMPERATURE` | `none`, `0.1` | usuń |
| `DATABASE_URL` | adres w Tailscale `100.115...` | `...@127.0.0.1:5432/prawdowid` |
| `CORS_ORIGINS` | puste | puste (jeden adres) |
| `VITE_*` | `mock` itd. | niepotrzebne: `deploy/build-frontend.sh` ustawia tryb `live` i `/api` |

Kod nie wymaga zmian: strona i panel wołają `/api` względnie, a w kodzie nie ma zaszytych
adresów serwerów.

## Krok 1. Router i zapora

1. Na routerze przekieruj **TCP 80** (i **TCP 443**, jeśli chcesz HTTPS) na adres serwera w
   sieci lokalnej. Nic więcej.
2. Na serwerze:
   ```bash
   sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
   sudo ufw allow in on tailscale0      # SSH i baza nadal tylko przez Tailscale
   sudo ufw enable
   ```
3. Publiczne IP: `curl -4 ifconfig.me` na serwerze ma dać ten sam adres co WAN w routerze
   (nie `100.x.x.x` z Tailscale).

## Krok 2. Baza (już działa na serwerze)

Backend łączy się przez `127.0.0.1`, więc Postgres musi słuchać też na localhost. W
`/etc/postgresql/<wersja>/main/postgresql.conf`:

```
listen_addresses = 'localhost,100.115.139.118'
```

`sudo systemctl restart postgresql`. Hasło użytkownika `prawdowid` było w rozmowie i w starym
`.env`, więc je zmień:

```bash
sudo -u postgres psql -c "ALTER ROLE prawdowid PASSWORD '<nowe-haslo>';"
```

## Krok 3. Kod i `.env`

```bash
sudo git clone -b claude/server-backend-openai https://github.com/HackNationOBSGAKMKMSCW/prawdowid.git /opt/prawdowid
cd /opt/prawdowid
sudo cp deploy/server.env.example .env
sudo nano .env        # uzupełnij wszystkie <...>
```

Node.js 22 musi być zainstalowany systemowo (`node -v`), np. z NodeSource.

## Krok 4. Instalacja (jedno polecenie)

```bash
sudo deploy/setup.sh :80                    # http://<IP-serwera>
# albo z HTTPS, bez kupowania domeny (IP 203.0.113.5 → 203-0-113-5.sslip.io):
sudo deploy/setup.sh 203-0-113-5.sslip.io
```

Skrypt tworzy użytkownika `prawdowid`, instaluje Caddy i `uv` (Python 3.13 + zależności),
uruchamia migracje bazy, buduje stronę i panel, zakłada usługę `prawdowid-backend` i
konfiguruje Caddy. Na końcu wypisuje adres.

Konto do panelu (np. osobne `analyst` tylko do podglądu dla sędziów):

```bash
cd /opt/prawdowid/backend
sudo -u prawdowid ../.venv/bin/python -m database create-user --email ... --name "..." --role analyst
```

## Krok 5. Sprawdzenie

Z telefonu na LTE (nie z sieci domowej):

- `http://<IP>/api/health` → `{"status":"ok"}`,
- `http://<IP>/` → sprawdzenie zdania,
- `http://<IP>/admin/` → logowanie.

Logi: `journalctl -u prawdowid-backend -f`, `/var/log/caddy/prawdowid.log`,
`/var/lib/prawdowid/logs/app.jsonl` (też w panelu: Logi techniczne).

## Aktualizacja

```bash
cd /opt/prawdowid
sudo -u prawdowid git pull
sudo deploy/setup.sh          # zapamiętuje poprzedni adres
```

## Kopia bazy

```bash
sudo mkdir -p /var/backups/prawdowid && sudo chown postgres: /var/backups/prawdowid
sudo crontab -u postgres -e
# 15 3 * * * /opt/prawdowid/deploy/backup-db.sh
```

## Uwagi

- Przy samym IP (HTTP) hasło do panelu idzie otwartym tekstem: sędziom daj konto `analyst`,
  po konkursie zmień hasła. Z `sslip.io` jest HTTPS.
- Ustaw limit wydatków w panelu OpenAI (Settings → Limits): adres jest publiczny.
- Klucz Google Fact Check był w rozmowie: wygeneruj nowy i wpisz go do `.env`.
