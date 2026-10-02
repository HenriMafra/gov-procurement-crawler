# -*- coding: utf-8 -*-
"""
ATLAS B2G — Cliente da fila de jobs (Postgres/Supabase e SQLite).
Camada de dados usada pelo worker, pelo runner e pelos testes. Reutiliza atlas_db.AtlasDB
(detecção de dialeto + tradução SQLite). Lock: FOR UPDATE SKIP LOCKED (PG) ou claim-guard (SQLite).
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_db import AtlasDB

EXCLUSIVE_TYPES = ("run_production", "run_production_write_db", "auto_setup")
JOB_TYPES = ("run_test", "run_production", "run_production_write_db", "load_round_to_db",
             "generate_package", "update_prototype", "validate_online", "auto_setup",
             "apply_sql", "create_users",
             "upload_artifacts", "reupload_artifact", "sync_storage", "cleanup_old_signed_urls")

def online_root():
    r = os.environ.get("ATLAS_ONLINE_ROOT")
    if r: return r
    pilot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # raiz do pilot
    cand = os.path.join(os.path.dirname(pilot), "atlas-b2g-online")
    return cand

def jobs_schema_path():
    r = online_root()
    return os.path.join(r, "supabase", "jobs_schema.sql") if r else None

class JobClient:
    def __init__(self, db_url=None):
        db_url = db_url or os.environ.get("DATABASE_URL") or \
            "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "atlas_b2g.sqlite")
        self.db = AtlasDB(db_url)
        self.dialect = self.db.dialect
        self.con = self.db.con
        self.cur = self.db.cur
        self.ph = self.db.ph

    # ---------- schema ----------
    def apply_jobs_schema(self, path=None):
        path = path or jobs_schema_path()
        if not path or not os.path.exists(path):
            raise FileNotFoundError("jobs_schema.sql não encontrado (defina ATLAS_ONLINE_ROOT).")
        sql = open(path, encoding="utf-8").read()
        if self.dialect == "sqlite":
            self.con.executescript(self.db._to_sqlite(sql))
        else:
            self.cur.execute(sql)
        self.con.commit()

    def ensure_full_schema(self):
        """Aplica schema principal + seed + jobs (usado no fallback local/teste)."""
        r = online_root()
        sch = os.path.join(r, "supabase", "schema_atlas_b2g.sql")
        seed = os.path.join(r, "supabase", "seed_atlas_b2g.sql")
        self.db.init_schema(sch, seed)
        self.apply_jobs_schema()

    # ---------- helpers ----------
    def _ph(self, n): return ",".join([self.ph] * n)

    def _exec(self, sql, params=()):
        self.cur.execute(self.db.q(sql), params)

    # ---------- criação ----------
    def create_job(self, **f):
        f.setdefault("status", "queued")
        cols = list(f.keys())
        vals = [self.db.jsonval(f[c]) if c.endswith("_json") else f[c] for c in cols]
        sql = f"INSERT INTO atlas_jobs ({','.join(cols)}) VALUES ({self._ph(len(cols))})"
        if self.dialect == "postgres":
            self.cur.execute(sql + " RETURNING id", vals); jid = self.cur.fetchone()[0]
        else:
            self.cur.execute(sql, vals); jid = self.cur.lastrowid
        self.con.commit()
        self.log(jid, "info", f"Job criado ({f.get('job_type')})", step="Enfileirado")
        return jid

    # ---------- reserva (lock) ----------
    def claim_next(self, worker_id, exclusive_types=EXCLUSIVE_TYPES):
        ex = list(exclusive_types)
        self._exec(f"SELECT COUNT(*) FROM atlas_jobs WHERE status='running' AND job_type IN ({self._ph(len(ex))})", ex)
        running_excl = self.cur.fetchone()[0] > 0
        cancel_false = "false" if self.dialect == "postgres" else "0"
        cond = f"status='queued' AND cancel_requested={cancel_false}"
        params = []
        if running_excl:
            cond += f" AND job_type NOT IN ({self._ph(len(ex))})"; params += ex
        if self.dialect == "postgres":
            self.cur.execute(f"SELECT id FROM atlas_jobs WHERE {cond} ORDER BY priority DESC, id ASC FOR UPDATE SKIP LOCKED LIMIT 1", params)
            row = self.cur.fetchone()
            if not row: self.con.rollback(); return None
            jid = row[0]
            self.cur.execute("UPDATE atlas_jobs SET status='running', locked_by=%s, locked_at=CURRENT_TIMESTAMP, started_at=CURRENT_TIMESTAMP, progress_percent=0, updated_at=CURRENT_TIMESTAMP WHERE id=%s", [worker_id, jid])
            self.con.commit()
        else:
            self._exec(f"SELECT id FROM atlas_jobs WHERE {cond} ORDER BY priority DESC, id ASC LIMIT 1", params)
            row = self.cur.fetchone()
            if not row: return None
            jid = row[0]
            self._exec("UPDATE atlas_jobs SET status='running', locked_by=?, locked_at=CURRENT_TIMESTAMP, started_at=CURRENT_TIMESTAMP, progress_percent=0, updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued'", [worker_id, jid])
            self.con.commit()
            if self.cur.rowcount != 1: return None
        self.log(jid, "info", f"Worker {worker_id} reservou o job", step="Preparando ambiente")
        return self.get_job(jid)

    # ---------- atualizações ----------
    def update(self, job_id, **fields):
        fields["updated_at"] = self._now()
        cols = list(fields.keys())
        vals = [self.db.jsonval(fields[c]) if c.endswith("_json") else fields[c] for c in cols] + [job_id]
        sets = ",".join(f"{c}={self.ph}" for c in cols)
        self._exec(f"UPDATE atlas_jobs SET {sets} WHERE id={self.ph}", vals)
        self.con.commit()

    def progress(self, job_id, percent, step):
        self.update(job_id, progress_percent=int(percent), current_step=step)
        self.log(job_id, "info", step, step=step)

    def log(self, job_id, level, message, step=None, details=None):
        self._exec(f"INSERT INTO atlas_job_logs (job_id,level,step,message,details_json) VALUES ({self._ph(5)})",
                   [job_id, level, step, message, self.db.jsonval(details)])
        self.con.commit()

    ARTIFACT_COLS = ("artifact_type", "file_name", "local_path", "storage_bucket", "storage_path",
                     "public_url", "mime_type", "size_bytes", "checksum_sha256",
                     "upload_status", "upload_error", "uploaded_at")

    def add_artifact(self, job_id, **meta):
        f = {k: meta[k] for k in self.ARTIFACT_COLS if k in meta}
        f["job_id"] = job_id
        cols = list(f.keys()); vals = [f[c] for c in cols]
        sql = f"INSERT INTO atlas_job_artifacts ({','.join(cols)}) VALUES ({self._ph(len(cols))})"
        if self.dialect == "postgres":
            self.cur.execute(sql + " RETURNING id", vals); aid = self.cur.fetchone()[0]
        else:
            self.cur.execute(sql, vals); aid = self.cur.lastrowid
        self.con.commit()
        return aid

    def update_artifact(self, artifact_id, **fields):
        cols = list(fields.keys()); vals = [fields[c] for c in cols] + [artifact_id]
        sets = ",".join(f"{c}={self.ph}" for c in cols)
        self._exec(f"UPDATE atlas_job_artifacts SET {sets} WHERE id={self.ph}", vals)
        self.con.commit()

    def get_artifact(self, artifact_id):
        r = self.db.fetch(self.db.q(f"SELECT * FROM atlas_job_artifacts WHERE id={self.ph}"), [artifact_id])
        return r[0] if r else None

    def local_only_artifacts(self):
        return self.db.fetch("SELECT * FROM atlas_job_artifacts WHERE upload_status IN ('local_only','failed')")

    def finish(self, job_id, status, exit_code=None, result=None, error=None, duration=None):
        fields = dict(status=status, exit_code=exit_code, result_json=result,
                      finished_at=self._now(), duration_seconds=duration)
        if error: fields["error_message"] = str(error)[:4000]
        if status == "success": fields["progress_percent"] = 100
        self.update(job_id, **fields)
        self.log(job_id, "success" if status == "success" else "error", f"Job finalizado: {status}", step="Finalizando")

    def request_cancel(self, job_id):
        truev = "true" if self.dialect == "postgres" else "1"
        self._exec(f"UPDATE atlas_jobs SET cancel_requested={truev}, updated_at={self.ph} WHERE id={self.ph}", [self._now(), job_id])
        self.con.commit()
        self.log(job_id, "warning", "Cancelamento solicitado", step="Cancelando")

    def is_cancel_requested(self, job_id):
        self._exec(f"SELECT cancel_requested FROM atlas_jobs WHERE id={self.ph}", [job_id])
        r = self.cur.fetchone()
        return bool(r and (r[0] in (True, 1, "1", "t", "true")))

    # ---------- leitura ----------
    def get_job(self, job_id):
        r = self.db.fetch(self.db.q(f"SELECT * FROM atlas_jobs WHERE id={self.ph}"), [job_id])
        return r[0] if r else None

    def get_logs(self, job_id, after_id=0):
        return self.db.fetch(self.db.q("SELECT * FROM atlas_job_logs WHERE job_id=? AND id>? ORDER BY id ASC"), [job_id, after_id])

    def list_artifacts(self, job_id):
        return self.db.fetch(self.db.q("SELECT * FROM atlas_job_artifacts WHERE job_id=? ORDER BY id ASC"), [job_id])

    def dashboard(self):
        r = self.db.fetch("SELECT * FROM vw_job_dashboard")
        return r[0] if r else {}

    def recent(self, limit=50):
        return self.db.fetch(self.db.q("SELECT * FROM vw_jobs_recentes LIMIT ?"), [limit])

    def _now(self):
        return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def close(self):
        try: self.db.close()
        except Exception: pass
