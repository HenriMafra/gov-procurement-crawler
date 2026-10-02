#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker de CHUNKS do MAPPER — roda IGUAL em VM1, VM2 e no PC do henri.

Cada instancia puxa pedacos (uf x janela de trimestre) da fila `atlas_chunks` usando
FOR UPDATE SKIP LOCKED (nunca dois pegam o mesmo), roda a coleta ADD-only PINADA na
rodada estavel e marca o chunk como done. Tudo idempotente: reprocessar um chunk so
re-soma os mesmos dados (nunca encolhe a base).

Oportunista: se o PC liga, ele comeca a puxar chunks e ajuda. Se desliga no meio de um
chunk, o lock daquele chunk fica velho (stale) -> volta pra fila -> uma VM pega. Nada se
perde, nada quebra, o resultado e "como se fosse uma coleta so".

Uso:  python src/atlas_chunk_worker.py            # loop infinito
      python src/atlas_chunk_worker.py --once     # processa 1 chunk e sai
Config por env: DATABASE_URL, ATLAS_PIPELINE_ROOT, ATLAS_PYTHON, ATLAS_WORKER_ID,
ATLAS_CHUNK_STALE_MIN (40), ATLAS_CHUNK_MAX_ATTEMPTS (4), ATLAS_CHUNK_POLL (10),
ATLAS_CHUNK_TIMEOUT (5400), ATLAS_BASE_CONFIG (config/atlas_config_producao.json).
"""
import os, sys, time, json, socket, argparse, tempfile, datetime, subprocess
import psycopg2

DB    = os.environ["DATABASE_URL"]
HOME  = os.path.expanduser("~")
PIPE  = os.environ.get("ATLAS_PIPELINE_ROOT") or os.path.join(HOME, "atlas-pncp-pilot")
PY    = os.environ.get("ATLAS_PYTHON") or os.path.join(PIPE, ".venv", "bin", "python")
WID   = os.environ.get("ATLAS_WORKER_ID") or ("%s-%d" % (socket.gethostname(), os.getpid()))
STALE = int(os.environ.get("ATLAS_CHUNK_STALE_MIN", "40"))
MAXA  = int(os.environ.get("ATLAS_CHUNK_MAX_ATTEMPTS", "4"))
POLL  = float(os.environ.get("ATLAS_CHUNK_POLL", "10"))
CTIMO = int(os.environ.get("ATLAS_CHUNK_TIMEOUT", "5400"))
BASE_CFG = os.environ.get("ATLAS_BASE_CONFIG", "config/atlas_config_producao.json")

def conn():
    cn = psycopg2.connect(DB); cn.autocommit = True; return cn

def log(m):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), WID, m, flush=True)

def requeue_stale(c):
    c.execute("update atlas_chunks set status='queued', locked_by=null, locked_at=null "
              "where status='running' and locked_at < now() - make_interval(mins => %s)", (STALE,))

def claim(c):
    c.execute(
        "update atlas_chunks set status='running', locked_by=%s, locked_at=now(), "
        "started_at=coalesce(started_at, now()), attempts=attempts+1 "
        "where id = (select id from atlas_chunks where status='queued' "
        "order by id asc limit 1 for update skip locked) "
        "returning id, run_id, kind, win_from, win_to, uf, rodada_pin, attempts", (WID,))
    return c.fetchone()

def build_config(win_from, win_to):
    base = json.load(open(os.path.join(PIPE, BASE_CFG), encoding="utf-8"))
    base["janelas"] = {"modo": "explicito",
                       "explicito": [[win_from.strftime("%Y%m%d"), win_to.strftime("%Y%m%d")]]}
    fd, path = tempfile.mkstemp(prefix="chunk_", suffix=".json", dir=os.path.join(PIPE, "config"))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(base, f)
    return path

def run_chunk(row):
    cid, run_id, kind, wf, wt, uf, pin, attempts = row
    cfg = build_config(wf, wt)
    rel = os.path.relpath(cfg, PIPE)
    # NAO passar --db-url (senha apareceria no `ps`): o runner usa $DATABASE_URL do env do subprocesso.
    args = [PY, "-X", "utf8", "src/atlas_weekly_runner.py", "--config", rel,
            "--tag", "PRODUCAO", "--date", pin.strftime("%Y-%m-%d"), "--ufs", uf,
            "--write-db", "--no-remove", "--no-init"]
    env = dict(os.environ); env["DATABASE_URL"] = DB
    env["ATLAS_FETCH_WORKERS"] = env.get("ATLAS_FETCH_WORKERS", "1"); env["PYTHONUNBUFFERED"] = "1"
    try:
        p = subprocess.run(args, cwd=PIPE, capture_output=True, text=True, env=env, timeout=CTIMO)
        rc, out = p.returncode, ((p.stdout or "") + (p.stderr or ""))
    finally:
        try: os.remove(cfg)
        except Exception: pass
    return rc, out[-1200:]

def finish_ok(cid):
    cn = conn(); c = cn.cursor()
    c.execute("update atlas_chunks set status='done', finished_at=now(), error=null where id=%s", (cid,))
    cn.close()

def finish_retry(cid, attempts, err):
    st = "failed" if attempts >= MAXA else "queued"
    cn = conn(); c = cn.cursor()
    c.execute("update atlas_chunks set status=%s, locked_by=null, locked_at=null, "
              "finished_at=case when %s='failed' then now() else null end, error=%s where id=%s",
              (st, st, (err or "")[:900], cid))
    cn.close()
    return st

def process(row):
    cid, run_id, kind, wf, wt, uf, pin, attempts = row
    log("chunk %s run=%s %s %s [%s..%s] tentativa=%s" % (cid, run_id, kind, uf, wf, wt, attempts))
    try:
        rc, tail = run_chunk(row)
    except subprocess.TimeoutExpired:
        log("chunk %s TIMEOUT -> requeue" % cid); finish_retry(cid, attempts, "timeout"); return
    except Exception as e:
        st = finish_retry(cid, attempts, str(e)); log("chunk %s EXC -> %s" % (cid, st)); return
    if rc == 0:
        finish_ok(cid); log("chunk %s OK" % cid)
    else:
        st = finish_retry(cid, attempts, tail); log("chunk %s rc=%s -> %s" % (cid, rc, st))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    log("chunk-worker iniciado | pipe=%s | once=%s" % (PIPE, a.once))
    idle = 0
    while True:
        try:
            cn = conn(); c = cn.cursor()
            requeue_stale(c)
            row = claim(c)
            cn.close()
        except Exception as e:
            log("erro no claim: %s" % str(e)[:160]); time.sleep(POLL); continue
        if not row:
            if a.once:
                log("fila vazia."); return 0
            idle += 1
            if idle == 1 or idle % 30 == 0: log("fila vazia, aguardando...")
            time.sleep(POLL); continue
        idle = 0
        process(row)
        if a.once:
            return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
