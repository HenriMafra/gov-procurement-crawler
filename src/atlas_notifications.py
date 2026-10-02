# -*- coding: utf-8 -*-
"""
ATLAS B2G — Centro de Notificações (camada Python; Postgres/Supabase e SQLite).
Cria notificações persistentes (uma linha por destinatário) e oferece helpers notify_*.
Usado pelo worker/runner/storage/carga. Reutiliza atlas_db.AtlasDB (dialeto + tradução).
Segurança: a RLS recorta a LEITURA no Supabase; aqui escrevemos via service role/DB direto.
"""
import os, sys, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_db import AtlasDB
from atlas_job_client import online_root

ROLES = ["Administrador", "Operador de Inteligência", "Coordenador Comercial", "Vendedor", "Diretoria"]
LEVELS = ["info", "success", "warning", "error", "critical"]

# tipo -> chave de preferência (para filtragem na leitura)
TYPE_PREF = {
    "job_started": "notify_jobs", "job_success": "notify_jobs", "job_failed": "notify_jobs",
    "job_cancelled": "notify_jobs",
    "artifact_available": "notify_artifacts", "artifact_failed": "notify_artifacts",
    "opportunity_created": "notify_opportunities", "opportunity_critical": "notify_opportunities",
    "opportunity_changed": "notify_opportunities",
    "opportunity_assigned": "notify_assignments", "task_created": "notify_assignments",
    "contact_registered": "notify_assignments",
    "review_required": "notify_reviews", "review_resolved": "notify_reviews",
    "pipeline_error": "notify_errors", "storage_error": "notify_errors", "system_alert": "notify_errors",
    "weekly_summary": "notify_weekly_summary",
}
ENTITY_FIELDS = ("entidade_tipo", "entidade_id", "job_id", "oportunidade_id", "rodada_id", "artifact_id", "link_url")

def _money(v):
    try: return "R$ " + f"{float(v):,.0f}".replace(",", ".")
    except Exception: return "R$ " + str(v or 0)

class NotifClient:
    def __init__(self, db_url=None):
        db_url = db_url or os.environ.get("DATABASE_URL") or \
            "sqlite:///" + os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "atlas_b2g.sqlite")
        self.db = AtlasDB(db_url); self.dialect = self.db.dialect
        self.con = self.db.con; self.cur = self.db.cur; self.ph = self.db.ph

    # ---------- schema ----------
    def apply_schema(self):
        r = online_root()
        if not r: raise FileNotFoundError("online_root não encontrado (ATLAS_ONLINE_ROOT).")
        sql = open(os.path.join(r, "supabase", "notifications_schema.sql"), encoding="utf-8").read()
        if self.dialect == "sqlite": self.con.executescript(self.db._to_sqlite(sql))
        else: self.cur.execute(sql)
        self.con.commit()

    def _ph(self, n): return ",".join([self.ph] * n)
    def _exec(self, sql, p=()): self.cur.execute(self.db.q(sql), p)
    def _now(self): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---------- criação ----------
    def create(self, tipo, titulo, mensagem=None, nivel="info", perfil_destino=None,
               usuario_destino_id=None, usuario_destino_email=None, responsavel_destino=None,
               escopo="role", criada_por="sistema", metadata=None, **entity):
        f = {"tipo": tipo, "titulo": titulo, "mensagem": mensagem, "nivel": nivel,
             "perfil_destino": perfil_destino, "usuario_destino_id": usuario_destino_id,
             "usuario_destino_email": usuario_destino_email, "responsavel_destino": responsavel_destino,
             "escopo": escopo, "criada_por": criada_por, "metadata_json": metadata}
        for k in ENTITY_FIELDS:
            if k in entity and entity[k] is not None: f[k] = entity[k]
        cols = list(f.keys())
        vals = [self.db.jsonval(f[c]) if c.endswith("_json") else f[c] for c in cols]
        sql = f"INSERT INTO notificacoes ({','.join(cols)}) VALUES ({self._ph(len(cols))})"
        if self.dialect == "postgres":
            self.cur.execute(sql + " RETURNING id", vals); nid = self.cur.fetchone()[0]
        else:
            self.cur.execute(sql, vals); nid = self.cur.lastrowid
        self.con.commit(); return nid

    def fanout(self, *, roles=None, responsavel=None, email=None, **base):
        """Cria uma linha por destinatário (perfil/responsável/email)."""
        ids = []
        for r in (roles or []):
            ids.append(self.create(perfil_destino=r, escopo="role", **base))
        if responsavel:
            ids.append(self.create(responsavel_destino=responsavel, escopo="user", **base))
        if email:
            ids.append(self.create(usuario_destino_email=email, escopo="user", **base))
        return ids

    # ---------- leitura (espelha a RLS; usado em teste e fallback) ----------
    def list_for(self, *, role, email=None, vendedor_nome=None, is_admin=None, only_unread=False, limit=100):
        is_admin = is_admin if is_admin is not None else (role == "Administrador")
        rows = self.db.fetch(self.db.q("SELECT * FROM notificacoes ORDER BY created_at DESC, id DESC"))
        out = []
        for n in rows:
            visible = (is_admin
                       or (email and n.get("usuario_destino_email") == email)
                       or (n.get("perfil_destino") and n.get("perfil_destino") == role)
                       or (n.get("responsavel_destino") and n.get("responsavel_destino") == vendedor_nome))
            if not visible: continue
            if only_unread and n.get("lida") in (True, 1, "1"): continue
            out.append(n)
        return out[:limit]

    def unread_count_for(self, **kw):
        return len(self.list_for(only_unread=True, **kw))

    def mark_read(self, ids):
        if not ids: return 0
        ph = self._ph(len(ids))
        self._exec(f"UPDATE notificacoes SET lida=TRUE, lida_em={self.ph} WHERE id IN ({ph})", [self._now()] + list(ids))
        self.con.commit(); return self.cur.rowcount

    def dashboard(self):
        r = self.db.fetch("SELECT * FROM vw_notification_dashboard"); return r[0] if r else {}

    # ---------- preferências ----------
    def set_pref(self, user_id, email=None, role=None, **flags):
        f = {"user_id": user_id, "email": email, "role": role, "updated_at": self._now(), **flags}
        cols = list(f.keys())
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c != "user_id")
        sql = f"INSERT INTO notification_preferences ({','.join(cols)}) VALUES ({self._ph(len(cols))}) ON CONFLICT(user_id) DO UPDATE SET {sets}"
        self._exec(sql, [f[c] for c in cols]); self.con.commit()

    def get_pref(self, user_id):
        r = self.db.fetch(self.db.q("SELECT * FROM notification_preferences WHERE user_id=?"), [user_id])
        return r[0] if r else None

    def close(self):
        try: self.db.close()
        except Exception: pass

    # =================== helpers notify_* ===================
    def notify_job_started(self, job, by=None):
        return self.fanout(roles=["Administrador", "Operador de Inteligência"], tipo="job_started", nivel="info",
                           titulo=f"Job #{job.get('id')} iniciado", job_id=job.get("id"),
                           mensagem=f"Job {job.get('job_type')} iniciado por {by or job.get('requested_by_email') or 'sistema'}.",
                           link_url=f"/admin/jobs/{job.get('id')}", criada_por="worker")

    def notify_job_success(self, job, meta=None):
        meta = meta or {}; prod = str(job.get("job_type", "")).startswith("run_production")
        # Job é técnico → só quem opera (Admin + Operador). O resumo de negócio vai no weekly_summary.
        roles = ["Administrador", "Operador de Inteligência"]
        if prod and any(k in meta for k in ("oportunidades", "criticas", "valor_total")):
            msg = f"Rodada concluída com {meta.get('oportunidades','?')} oportunidades, {meta.get('criticas','?')} críticas e {_money(meta.get('valor_total'))} mapeados."
        else:
            msg = f"Job {job.get('job_type')} concluído com sucesso."
        return self.fanout(roles=roles, tipo="job_success", nivel="success",
                           titulo=f"Job #{job.get('id')} concluído", mensagem=msg, job_id=job.get("id"),
                           link_url=f"/admin/jobs/{job.get('id')}", criada_por="worker", metadata=meta)

    def notify_job_failed(self, job, err=None):
        prod = str(job.get("job_type", "")).startswith("run_production")
        return self.fanout(roles=["Administrador", "Operador de Inteligência"], tipo="job_failed",
                           nivel="critical" if prod else "error", titulo=f"Job #{job.get('id')} falhou",
                           mensagem=(err or "Falha ao executar pipeline. Verifique os logs do job.")[:300],
                           job_id=job.get("id"), link_url=f"/admin/jobs/{job.get('id')}", criada_por="worker")

    def notify_artifact_available(self, job, artifact):
        atype = artifact.get("artifact_type", "")
        roles = ["Administrador", "Operador de Inteligência"]
        if atype in ("report_md", "report_pdf", "validation_report", "prototype_html"):
            roles += ["Coordenador Comercial", "Diretoria"]
        return self.fanout(roles=list(dict.fromkeys(roles)), tipo="artifact_available", nivel="info",
                           titulo="Novo artefato disponível", mensagem=f"{atype}: {artifact.get('file_name')} pronto para download.",
                           job_id=job.get("id"), artifact_id=artifact.get("id"),
                           link_url=f"/admin/jobs/{job.get('id')}", criada_por="worker")

    def notify_artifact_failed(self, job, artifact):
        return self.fanout(roles=["Administrador", "Operador de Inteligência"], tipo="artifact_failed", nivel="error",
                           titulo="Falha ao enviar artefato", mensagem=f"{artifact.get('file_name')} não subiu ao Storage.",
                           job_id=job.get("id"), artifact_id=artifact.get("id"), criada_por="worker")

    def notify_opportunity_critical(self, opp):
        resp = opp.get("responsavel_atribuido")
        return self.fanout(roles=["Administrador", "Coordenador Comercial"], responsavel=resp,
                           tipo="opportunity_critical", nivel="critical", titulo="Nova oportunidade crítica",
                           mensagem=f"{opp.get('orgao') or opp.get('nome_orgao')}, {opp.get('categoria_principal','?')}, score {opp.get('score_comercial','?')}.",
                           oportunidade_id=opp.get("id"), link_url=f"/oportunidades/{opp.get('id_oportunidade') or opp.get('id')}", criada_por="pipeline")

    def notify_opportunity_assigned(self, opp, vendedor_nome):
        return self.fanout(responsavel=vendedor_nome, tipo="opportunity_assigned", nivel="info",
                           titulo="Nova oportunidade atribuída a você",
                           mensagem=f"{opp.get('orgao') or opp.get('nome_orgao')} — próxima ação: {opp.get('proxima_acao_recomendada','definir abordagem')}.",
                           oportunidade_id=opp.get("id"), link_url=f"/oportunidades/{opp.get('id_oportunidade') or opp.get('id')}", criada_por="coordenacao")

    def notify_review_required(self, opp=None):
        return self.fanout(roles=["Operador de Inteligência", "Administrador"], tipo="review_required", nivel="warning",
                           titulo="Nova revisão pendente",
                           mensagem="Oportunidade com classificação incerta ou dados incompletos precisa de revisão.",
                           oportunidade_id=(opp or {}).get("id"), link_url="/qualidade", criada_por="pipeline")

    def notify_weekly_summary(self, meta):
        return self.fanout(roles=["Diretoria", "Coordenador Comercial", "Administrador"], tipo="weekly_summary", nivel="info",
                           titulo="Resumo semanal ATLAS B2G",
                           mensagem=f"Resumo semanal: {meta.get('oportunidades','?')} oportunidades, {meta.get('criticas','?')} críticas, {_money(meta.get('valor_total'))} mapeados.",
                           rodada_id=meta.get("rodada_id"), link_url="/dashboard", criada_por="esteira", metadata=meta)
