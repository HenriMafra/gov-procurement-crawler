#!/usr/bin/env bash
# Inicia o CHUNK-WORKER do MAPPER se ainda nao estiver rodando.
# Usado pelo cron-watchdog (*/5) e no @reboot das VMs. Roda igual em VM1 e VM2.
set -a; source "$HOME/.atlas_env"; set +a
cd "$HOME/atlas-pncp-pilot" || exit 1
if pgrep -f "atlas_chunk_worker.py" >/dev/null; then exit 0; fi
nohup ./.venv/bin/python "$HOME/atlas-pncp-pilot/src/atlas_chunk_worker.py" \
  >> "$HOME/atlas_chunk_worker.log" 2>&1 &
