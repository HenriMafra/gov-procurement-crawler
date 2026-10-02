#!/usr/bin/env bash
# Inicia o JOB-WORKER (coordenador dos botoes + Storage/publish) na VM1, sempre-ligada.
# Quando alguem aperta um botao no site, este worker pega o job; se for coleta, ele
# enfileira os chunks e acompanha o pool ate terminar. Watchdog (*/5) + @reboot.
set -a; source "$HOME/.atlas_env"; set +a
cd "$HOME/atlas-pncp-pilot" || exit 1
if pgrep -f "atlas_job_worker.py" >/dev/null; then exit 0; fi
nohup ./.venv/bin/python "$HOME/atlas-pncp-pilot/src/atlas_job_worker.py" --loop --interval 5 \
  >> "$HOME/atlas_job_worker.log" 2>&1 &
