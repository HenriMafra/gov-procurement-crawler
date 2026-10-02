#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Planner de CHUNKS do MAPPER — cria os pedacos de uma "rodada de coleta" na fila atlas_chunks.

  python src/atlas_chunk_plan.py --kind completo        # 2021..ano-atual, 4 trimestres x 9 UFs
  python src/atlas_chunk_plan.py --kind incremental     # ano-atual, ultimos ~2 trimestres x 9 UFs

Granularidade = (trimestre x 1 UF): memoria-segura no pior caso (VM de 1GB) e da pedacos
pequenos pro pool oportunista (VM1+VM2+PC) balancear bem. Todos os chunks ficam PINADOS na
rodada estavel (ATLAS_RODADA_PIN) e serao coletados ADD-only (a base nunca encolhe).

Tambem expoe plan()/progress() pra serem chamados pelo coordenador (atlas_job_runner).
"""
import os, sys, time, argparse, datetime
import psycopg2

UFS = ["DF", "GO", "CE", "SP", "MT", "PR", "PE", "AM", "RS"]
PIN = os.environ.get("ATLAS_RODADA_PIN", "2026-06-12")

DDL = """
create table if not exists atlas_chunks (
  id bigserial primary key,
  run_id bigint not null,
  kind text not null,
  win_from date not null,
  win_to date not null,
  uf text not null,
  rodada_pin date not null,
  status text not null default 'queued',
  locked_by text,
  locked_at timestamptz,
  attempts int not null default 0,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index if not exists ix_atlas_chunks_claim on atlas_chunks(status, id);
create index if not exists ix_atlas_chunks_run on atlas_chunks(run_id);
"""

def _months(y, m_start=1, m_end=12):
    # Janela MENSAL: o indice nacional de um trimestre recente (~535k registros) estoura o 1GB
    # (earlyoom mata). Um mes (~1/3 disso) cabe. Por isso a granularidade e (mes x UF).
    import calendar
    out = []
    for m in range(m_start, m_end + 1):
        last = calendar.monthrange(y, m)[1]
        out.append((datetime.date(y, m, 1), datetime.date(y, m, last)))
    return out

def ensure_table(db_url=None):
    db = db_url or os.environ["DATABASE_URL"]
    cn = psycopg2.connect(db); cn.autocommit = True; c = cn.cursor()
    c.execute(DDL)
    # tabela interna: so worker (owner) e API (service_role) tocam -> RLS ON sem policy bloqueia anon/auth.
    try: c.execute("alter table atlas_chunks enable row level security")
    except Exception: pass
    cn.close()

def plan(kind, db_url=None, start_year=2021):
    """Enfileira os chunks de um run. Retorna (run_id, n_chunks)."""
    db = db_url or os.environ["DATABASE_URL"]
    ensure_table(db)
    ynow = time.localtime().tm_year
    mon = time.localtime().tm_mon
    rows = []
    if kind == "completo":
        for y in range(start_year, ynow + 1):
            m_end = 12 if y < ynow else mon       # ano corrente: so ate o mes atual
            for (wf, wt) in _months(y, 1, m_end):
                for uf in UFS:
                    rows.append((kind, wf, wt, uf, PIN))
    elif kind == "incremental":
        # ultimos 3 meses (mes atual + 2 anteriores)
        sel, yy, mm = [], ynow, mon
        for _ in range(3):
            sel.append((yy, mm)); mm -= 1
            if mm == 0: mm, yy = 12, yy - 1
        import calendar
        for (yy2, mm2) in sorted(sel):
            wf = datetime.date(yy2, mm2, 1)
            wt = datetime.date(yy2, mm2, calendar.monthrange(yy2, mm2)[1])
            for uf in UFS:
                rows.append((kind, wf, wt, uf, PIN))
    else:
        raise ValueError("kind invalido: %s" % kind)

    cn = psycopg2.connect(db); cn.autocommit = True; c = cn.cursor()
    c.execute("select coalesce(max(run_id), 0) + 1 from atlas_chunks")
    run_id = c.fetchone()[0]
    c.executemany(
        "insert into atlas_chunks(run_id, kind, win_from, win_to, uf, rodada_pin) "
        "values (%s, %s, %s, %s, %s, %s)",
        [(run_id, r[0], r[1], r[2], r[3], r[4]) for r in rows])
    cn.close()
    return run_id, len(rows)

def progress(run_id, db_url=None):
    """Retorna dict {status: n} para um run."""
    db = db_url or os.environ["DATABASE_URL"]
    cn = psycopg2.connect(db); c = cn.cursor()
    c.execute("select status, count(*) from atlas_chunks where run_id=%s group by status", (run_id,))
    d = {s: n for (s, n) in c.fetchall()}
    cn.close()
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["completo", "incremental"], required=True)
    ap.add_argument("--start-year", type=int, default=2021)
    ap.add_argument("--db-url")
    a = ap.parse_args()
    rid, n = plan(a.kind, db_url=a.db_url, start_year=a.start_year)
    print("run_id=%s chunks=%s kind=%s pino=%s" % (rid, n, a.kind, PIN))

if __name__ == "__main__":
    main()
