# -*- coding: utf-8 -*-
"""
ATLAS B2G — Worker contínuo de backfill de órgãos via PNCP (por CNPJ).

Mesmo padrão do atlas_chunk_worker.py: puxa 1 órgão por vez da fila
`atlas_orgao_backfill` (FOR UPDATE SKIP LOCKED), roda o backfill exaustivo
(backfill_orgao_cnpj.py) desde 2021, marca como concluído. Processa a fila
inteira (~5.734 órgãos, priorizados por volume atual) e então dorme —
o objetivo é rodar uma vez até esvaziar a fila, não fazer polling eterno
como o chunk_worker do PNCP (aqui não há "chunks novos" chegando, é um
backfill de correção pontual).

Motivo: descoberto em 2026-07-13 que o sweep nacional por janela de tempo
(MAX_PAGINAS=90) perde a maioria dos contratos de órgãos de alto volume —
confirmado na IMBEL (30 no banco vs 2.999 reais). Esta fila corrige órgão
por órgão usando o parâmetro cnpjOrgao da API do PNCP, sem teto de páginas.

Uso:
  ./.venv/bin/python src/atlas_orgao_backfill_worker.py
"""
import os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import psycopg2
import psycopg2.extras
import backfill_orgao_cnpj as bf

DB = os.environ["DATABASE_URL"]
WID = os.environ.get("ATLAS_WORKER_ID") or f"backfill-{os.getpid()}"
STALE_MIN = int(os.environ.get("ATLAS_BACKFILL_STALE_MIN", "90"))
RODADA_ID = int(os.environ.get("ATLAS_BACKFILL_RODADA_ID", "8"))
ANO_INICIO = int(os.environ.get("ATLAS_BACKFILL_ANO_INICIO", "2021"))


def log(m):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {WID} {m}", flush=True)


def conn():
    cn = psycopg2.connect(DB)
    cn.autocommit = True
    return cn


def requeue_stale(cur):
    cur.execute(
        "UPDATE atlas_orgao_backfill SET status='queued', locked_by=NULL, locked_at=NULL "
        "WHERE status='running' AND locked_at < now() - make_interval(mins => %s)",
        (STALE_MIN,))


def claim(cur):
    cur.execute(
        "UPDATE atlas_orgao_backfill SET status='running', locked_by=%s, locked_at=now(), "
        "started_at=coalesce(started_at, now()), attempts=attempts+1 "
        "WHERE id = (SELECT id FROM atlas_orgao_backfill WHERE status='queued' "
        "ORDER BY prioridade DESC, id ASC LIMIT 1 FOR UPDATE SKIP LOCKED) "
        "RETURNING id, orgao_id, cnpj, contratos_antes, attempts",
        (WID,))
    return cur.fetchone()


def finish_ok(item_id, contratos_depois):
    cn = conn(); c = cn.cursor()
    c.execute("UPDATE atlas_orgao_backfill SET status='done', finished_at=now(), "
              "contratos_depois=%s, error=NULL WHERE id=%s", (contratos_depois, item_id))
    cn.close()


def finish_retry(item_id, attempts, err):
    st = "failed" if attempts >= 4 else "queued"
    cn = conn(); c = cn.cursor()
    c.execute("UPDATE atlas_orgao_backfill SET status=%s, locked_by=NULL, locked_at=NULL, "
              "finished_at=CASE WHEN %s='failed' THEN now() ELSE NULL END, error=%s WHERE id=%s",
              (st, st, (err or "")[:900], item_id))
    cn.close()
    return st


def process(row):
    item_id, orgao_id, cnpj, contratos_antes, attempts = row
    log(f"órgão {orgao_id} (cnpj {cnpj}, {contratos_antes} contrato(s) hoje) — tentativa {attempts}")
    try:
        itens = bf.coletar_tudo(cnpj, ANO_INICIO, log=log)
        contratos, fornecedores = bf.para_registros_db(itens)
        bf.gravar_e_classificar(DB, orgao_id, contratos, fornecedores, RODADA_ID, log=log)
        finish_ok(item_id, len(contratos))
        log(f"órgão {orgao_id} OK — {contratos_antes} -> {len(contratos)} contrato(s)")
    except Exception as e:
        st = finish_retry(item_id, attempts, str(e))
        log(f"órgão {orgao_id} ERRO ({e}) -> {st}")


def main():
    log(f"=== worker de backfill de órgãos iniciado (ano_inicio={ANO_INICIO}, rodada={RODADA_ID}) ===")
    idle = 0
    while True:
        try:
            cn = conn(); c = cn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            requeue_stale(c)
            row = claim(c)
            cn.close()
        except Exception as e:
            log(f"erro no claim: {str(e)[:160]}")
            time.sleep(15)
            continue
        if not row:
            idle += 1
            if idle == 1:
                log("fila vazia — backfill concluído (ou aguardando novos itens).")
            time.sleep(60)
            continue
        idle = 0
        process(tuple(row.values()))
        # pausa entre órgãos (além da pausa interna entre páginas) — respiro extra pro PNCP
        time.sleep(3)


if __name__ == "__main__":
    main()
