#!/usr/bin/env bash
# =====================================================================
# ATLAS / MAPPER - setup do COLETOR na Oracle Cloud (Ubuntu)
# Roda 24/7 na nuvem. Cache no disco da VM. AUTH = DEPLOY KEY SSH (sem token).
#
# PRE-REQUISITO: ~/.atlas_env com:
#   DATABASE_URL="postgresql://...."   (a mesma do .env.local)
# Rode: bash oracle_setup.sh  (na 1a vez ele gera a deploy key e pede pra
#   voce adicionar no repo; depois re-rode).
# =====================================================================
set -euo pipefail
echo "==> ATLAS/MAPPER - setup do coletor (auth via deploy key SSH)"

# 0) segredos (so DATABASE_URL - sem token)
[ -f "$HOME/.atlas_env" ] || { echo "ERRO: crie ~/.atlas_env com DATABASE_URL antes."; exit 1; }
set -a; source "$HOME/.atlas_env"; set +a
: "${DATABASE_URL:?defina DATABASE_URL em ~/.atlas_env}"

# 1) pacotes
sudo timedatectl set-timezone America/Sao_Paulo || true
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip python3-venv git openssh-client

# 2) deploy key SSH (gera se nao existir) + config + known_hosts
mkdir -p ~/.ssh && chmod 700 ~/.ssh
KEY="$HOME/.ssh/atlas_deploy"
[ -f "$KEY" ] || ssh-keygen -t ed25519 -f "$KEY" -N "" -C "atlas-coletor-deploy" >/dev/null
chmod 600 "$KEY"
grep -q "Host github.com" ~/.ssh/config 2>/dev/null || printf "\nHost github.com\n  IdentityFile %s\n  IdentitiesOnly yes\n" "$KEY" >> ~/.ssh/config
chmod 600 ~/.ssh/config
ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts 2>/dev/null || true
sort -u ~/.ssh/known_hosts -o ~/.ssh/known_hosts 2>/dev/null || true

# 3) testa SSH ao repo; se faltar a deploy key, mostra e PARA
if ! ssh -T -o BatchMode=yes -o StrictHostKeyChecking=accept-new git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo
  echo "!! FALTA ADICIONAR A DEPLOY KEY NO GITHUB !!"
  echo "   1) GitHub > repo HenriMafra/atlas-pncp-pilot > Settings > Deploy keys > Add deploy key"
  echo "   2) Marque Allow write access e cole a chave abaixo:"
  echo "   ----------------------------------------------------------"
  cat "$KEY.pub"
  echo "   ----------------------------------------------------------"
  echo "   3) Depois rode de novo: bash oracle_setup.sh"
  exit 1
fi
echo "==> Deploy key OK (autenticado no GitHub)."

# 4) baixa/atualiza o coletor via SSH
APP="$HOME/atlas-pncp-pilot"
REPO="git@github.com:HenriMafra/atlas-pncp-pilot.git"
if [ -d "$APP/.git" ]; then
  git -C "$APP" remote set-url origin "$REPO"; git -C "$APP" pull || true
else
  git clone "$REPO" "$APP"
fi
cd "$APP"

# 5) Python isolado + deps
python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt

# 6) script de coleta diaria
cat > "$HOME/atlas_run.sh" <<'SH'
#!/usr/bin/env bash
set -a; source "$HOME/.atlas_env"; set +a
cd "$HOME/atlas-pncp-pilot"
git pull -q || true
export ATLAS_FETCH_WORKERS="${ATLAS_FETCH_WORKERS:-1}"
LOG="$HOME/atlas_logs"; mkdir -p "$LOG"; TS=$(date +%Y%m%d_%H%M%S); F="$LOG/coleta_$TS.log"
echo "=== INICIO $TS ===" > "$F"
./.venv/bin/python coleta_editais_diaria.py >> "$F" 2>&1 || echo "[aviso] editais falhou" >> "$F"
./.venv/bin/python src/atlas_weekly_runner.py --config config/atlas_config_semanal.json --tag PRODUCAO --write-db >> "$F" 2>&1 || echo "[aviso] coleta completa falhou" >> "$F"
echo "=== FIM $(date +%H:%M:%S) ===" >> "$F"
SH
chmod +x "$HOME/atlas_run.sh"

# 7) cron diario 06:00 BRT
( crontab -l 2>/dev/null | grep -v atlas_run.sh || true ; echo "0 6 * * * $HOME/atlas_run.sh" ) | crontab -

echo "==> Setup concluido (auth SSH, sem token)."
echo "==> Rodando a 1a coleta em segundo plano (1a vez pode levar horas)."
nohup "$HOME/atlas_run.sh" >/dev/null 2>&1 &
echo "==> Logs em ~/atlas_logs/  |  Proximas: automaticas todo dia 06:00 (BRT)."