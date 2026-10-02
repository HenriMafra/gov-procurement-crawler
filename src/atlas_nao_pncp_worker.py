# -*- coding: utf-8 -*-
"""
ATLAS B2G — Worker contínuo das fontes não-PNCP (estatais/fundações do DF).

Mesmo padrão do atlas_chunk_worker.py: processo de longa duração, iniciado
por watchdog (cron */5 + @reboot), que roda um ciclo completo de todas as
18 fontes + classificação e dorme até completar INTERVALO_S desde o início
do ciclo anterior (se o ciclo demorar mais que o intervalo, emenda direto
no próximo sem dormir — nunca fica mais lento que o INTERVALO_S configurado).

Diferente do chunk_worker (que faz polling da fila a cada poucos segundos),
aqui o intervalo é de 6h por padrão: os sites-fonte são institucionais e
publicam poucos editais novos por semana, e vários têm proteção anti-bot —
bater neles com mais frequência não traria dado mais fresco e arriscaria
bloqueio (visto na prática: TERRACAP/SENAC-PR já retornam 403 pro IP desta
VM mesmo em execução diária). A VM1 também tem só 1GB de RAM compartilhado
com o chunk_worker/job_worker do PNCP — ciclos menos frequentes reduzem o
risco de o earlyoom matar o worker no meio de um ciclo pesado (CEASA-DF via
Playwright/Chromium é o mais custoso).

Uso:
  ./.venv/bin/python src/atlas_nao_pncp_worker.py
  ATLAS_NAO_PNCP_INTERVALO_S=1800 ./.venv/bin/python src/atlas_nao_pncp_worker.py
"""
import os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coleta_nao_pncp_diaria as diaria

INTERVALO_S = int(os.environ.get("ATLAS_NAO_PNCP_INTERVALO_S", 21600))


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERRO: defina $DATABASE_URL"); sys.exit(1)

    log(f"=== ATLAS B2G — worker não-PNCP iniciado (ciclo a cada {INTERVALO_S}s) ===")
    ciclo = 0
    while True:
        ciclo += 1
        t0 = time.time()
        log(f"--- ciclo {ciclo} ---")
        ok, falhas = 0, []
        for nome, script in diaria.COLETORES:
            if nome == "CEASA-DF":
                timeout_s = 1200
            elif nome in ("CIASC-SC", "PREGAO-BANRISUL", "SENAC-SC"):
                timeout_s = 700
            else:
                timeout_s = 350
            if diaria.rodar(nome, script, db_url, timeout_s):
                ok += 1
            else:
                falhas.append(nome)
        diaria.rodar_pos_processar(db_url)
        dt = time.time() - t0
        log(f"--- ciclo {ciclo} concluído em {dt:.0f}s — {ok}/{len(diaria.COLETORES)} OK "
            f"{'(falhas: ' + ', '.join(falhas) + ')' if falhas else ''} ---")

        resta = INTERVALO_S - dt
        if resta > 0:
            log(f"dormindo {resta:.0f}s até o próximo ciclo...")
            time.sleep(resta)
        else:
            log("ciclo demorou mais que o intervalo — emendando no próximo sem dormir.")


if __name__ == "__main__":
    main()
