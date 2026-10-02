# -*- coding: utf-8 -*-
"""
ATLAS B2G — Worker da fila de jobs.
  python src/atlas_job_worker.py --once                 # processa 1 job e sai
  python src/atlas_job_worker.py --loop --interval 5    # fica processando
Configs por flag/env: --db-url/DATABASE_URL, --interval, --timeout, --worker-id.
Lock: claim_next usa FOR UPDATE SKIP LOCKED (PG) / claim-guard (SQLite) e garante que apenas
um job de produção rode por vez (exclusividade).
"""
import os, sys, time, socket, argparse, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from atlas_job_client import JobClient
import atlas_job_runner as runner

def _notify(method, *args):
    """Notificação best-effort: nunca quebra o job (tabela pode não existir em ambientes mínimos)."""
    try:
        from atlas_notifications import NotifClient
        nc = NotifClient(os.environ.get("DATABASE_URL")); getattr(nc, method)(*args); nc.close()
    except Exception as e:
        if os.environ.get("ATLAS_NOTIF_DEBUG"): print(f"[worker] notif {method} ignorada: {e}")

def process(client, job, default_timeout):
    jid = job["id"]; jt = job["job_type"]
    print(f"[worker] processando job {jid} ({jt})")
    _notify("notify_job_started", job)
    t0 = time.time()
    try:
        status, code, result = runner.execute(client, job)
    except Exception as e:
        status, code, result = "failed", 1, {"excecao": str(e)}
        client.log(jid, "error", "Exceção no worker: " + str(e), step="Finalizando",
                   details={"trace": traceback.format_exc()[-1500:]})
    dur = round(time.time() - t0, 2)

    if status in ("failed", "timeout"):
        retries = int(job.get("retries") or 0); maxr = int(job.get("max_retries") or 0)
        if retries < maxr:
            client.update(jid, status="queued", retries=retries + 1, locked_by=None,
                          progress_percent=0, current_step="Reenfileirado (retry)")
            client.log(jid, "warning", f"Retry {retries + 1}/{maxr} após {status}", step="Reenfileirado")
            print(f"[worker] job {jid} -> retry {retries + 1}/{maxr}")
            return
        errmsg = (result or {}).get("saida") or (result or {}).get("erro") or status
        client.finish(jid, status, exit_code=code, result=result, error=errmsg, duration=dur)
        _notify("notify_job_failed", job, errmsg)
    else:
        client.finish(jid, status, exit_code=code, result=result, duration=dur)
        if status == "success":
            _notify("notify_job_success", job, result if isinstance(result, dict) else {})
    print(f"[worker] job {jid} -> {status} em {dur}s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", action="store_true"); ap.add_argument("--once", action="store_true")
    ap.add_argument("--interval", type=float, default=5.0); ap.add_argument("--timeout", type=int, default=290)
    ap.add_argument("--db-url"); ap.add_argument("--worker-id")
    a = ap.parse_args()
    if a.db_url: os.environ["DATABASE_URL"] = a.db_url
    worker_id = a.worker_id or f"{socket.gethostname()}-{os.getpid()}"
    client = JobClient(a.db_url)
    print(f"[worker] iniciado id={worker_id} dialeto={client.dialect}")
    try:
        if a.once or not a.loop:
            job = client.claim_next(worker_id)
            if not job:
                print("[worker] nenhum job na fila."); return 0
            process(client, job, a.timeout); return 0
        # loop
        while True:
            job = client.claim_next(worker_id)
            if job:
                process(client, job, a.timeout)
            else:
                time.sleep(a.interval)
    except KeyboardInterrupt:
        print("\n[worker] encerrado pelo usuário.")
    finally:
        client.close()
    return 0

if __name__ == "__main__":
    sys.exit(main())
