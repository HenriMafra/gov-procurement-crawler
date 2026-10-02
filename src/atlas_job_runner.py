# -*- coding: utf-8 -*-
"""
ATLAS B2G — Runner de jobs: executa cada tipo, reporta progresso/logs/etapas,
registra artefatos e respeita cancelamento. Usado pelo worker.
Modo simulado (parameters.simulate=true ou ATLAS_JOB_SIMULATE=1) percorre as 14 etapas
sem o pipeline pesado — para testes determinísticos.
"""
import os, sys, glob, json, time, subprocess, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from atlas_job_client import online_root
import atlas_storage as storage

PILOT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def pipeline_root():
    return os.environ.get("ATLAS_PIPELINE_ROOT") or os.environ.get("ATLAS_PIPELINE_DIR") or PILOT_ROOT
def py():
    return os.environ.get("ATLAS_PYTHON") or sys.executable or "python"

STEPS = [
    (5, "Preparando ambiente"), (10, "Lendo configuração"), (15, "Rodando doctor"),
    (30, "Coletando PNCP"), (45, "Classificando contratos"), (55, "Calculando score"),
    (65, "Gerando lista de ataque"), (72, "Gerando Excel"), (80, "Gerando relatório"),
    (86, "Atualizando protótipo"), (90, "Gravando no banco"), (94, "Subindo artefatos"),
    (98, "Validando views"), (100, "Finalizando"),
]
# padrões de arquivos de uma rodada (o tipo é detectado por atlas_storage.detect_artifact_type)
ARTIFACT_GLOBS = ["*.xlsx", "*.csv", "*.md", "*.pdf", "*.zip", "*.html",
                  "atlas_dados_reais*prototipo*.js", "*[Pp]rototipo*.js",
                  "atlas_log_execucao_*.txt", "atlas_config_*.json"]

def _latest_round():
    rd = os.path.join(pipeline_root(), "outputs", "rodadas")
    dirs = [d for d in glob.glob(os.path.join(rd, "*")) if os.path.isdir(d)]
    return sorted(dirs, key=lambda d: os.path.basename(d))[-1] if dirs else None

def _gather_files(folder):
    files = []
    for pat in ARTIFACT_GLOBS:
        files += glob.glob(os.path.join(folder, pat))
    return sorted(set(files))

def _register_artifacts(client, job_id, folder, job=None):
    """Registra artefatos com metadata e ENVIA ao Storage (se configurado); senão local_only."""
    if not folder or not os.path.isdir(folder): return 0
    job = job or client.get_job(job_id)
    configured = storage.is_storage_configured()
    if configured: storage.ensure_buckets()
    files = _gather_files(folder)
    n = up = fail = 0
    for f in files:
        meta = storage.upload_artifact(job, f)   # type/sha/mime/size + upload OU local_only/missing
        client.add_artifact(job_id, **meta)
        n += 1
        st = meta.get("upload_status")
        up += (st == "uploaded"); fail += (st == "failed")
    msg = f"{n} artefato(s) registrado(s); {up} enviado(s)" + (f", {fail} falha(s)" if fail else "")
    if not configured: msg += " (Storage não configurado → local_only)"
    client.log(job_id, "info", msg, step="Subindo artefatos", details={"pasta": os.path.basename(folder), "enviados": up})
    if up > 0:  # notifica disponibilidade (best-effort; reaching Admin/Operador/Coordenador/Diretoria)
        try:
            from atlas_notifications import NotifClient
            nc = NotifClient(os.environ.get("DATABASE_URL"))
            nc.notify_artifact_available(job, {"id": None, "artifact_type": "report_pdf", "file_name": f"{up} artefato(s) da rodada"})
            nc.close()
        except Exception: pass
    return n

def _cancelled(client, job_id):
    if client.is_cancel_requested(job_id):
        client.log(job_id, "warning", "Cancelamento detectado — interrompendo.", step="Cancelando")
        return True
    return False

def _simulate(client, job):
    jid = job["id"]
    out_dir = os.path.join(pipeline_root(), "outputs", "jobs", f"job_{jid}")
    os.makedirs(out_dir, exist_ok=True)
    for pct, label in STEPS:
        if _cancelled(client, jid): return ("cancelled", 0, {"simulado": True, "ate": label})
        client.progress(jid, pct, label)
        time.sleep(0.05)
    # artefato simulado
    art = os.path.join(out_dir, f"resultado_simulado_{jid}.json")
    json.dump({"job_id": jid, "tipo": job["job_type"], "simulado": True,
               "gerado_em": datetime.datetime.now().isoformat()}, open(art, "w", encoding="utf-8"), ensure_ascii=False)
    meta = storage.upload_artifact(job, art)   # local_only (sem creds) ou uploaded (com Storage)
    client.add_artifact(jid, **meta)
    return ("success", 0, {"simulado": True, "artefatos": 1, "upload": meta.get("upload_status")})

def _run_cmd(client, job, args, cwd, prep_pct=30, timeout=290):
    """Roda um subprocess com polling de cancelamento e timeout; reporta progresso."""
    jid = job["id"]
    for pct, label in STEPS:
        if pct > prep_pct: break
        if _cancelled(client, jid): return ("cancelled", 0, {})
        client.progress(jid, pct, label)
    client.log(jid, "info", "Executando: " + " ".join(os.path.basename(a) for a in args[:2]), step="Coletando PNCP")
    t0 = time.time()
    import threading, collections
    env = dict(os.environ)
    env["ATLAS_JOB_ID"] = str(jid)
    p = subprocess.Popen([py()] + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace", env=env)
    # Drena o stdout continuamente (thread) para um buffer limitado: evita o deadlock
    # do pipe (~64KB) em jobs LONGOS/verbosos como a varredura de 6 anos.
    tail = collections.deque(maxlen=400)
    def _drain():
        try:
            for ln in p.stdout: tail.append(ln.rstrip("\n"))
        except Exception: pass
    th = threading.Thread(target=_drain, daemon=True); th.start()
    while True:
        if p.poll() is not None: break
        if client.is_cancel_requested(jid):
            p.terminate()
            try: p.wait(timeout=10)
            except Exception: p.kill()
            return ("cancelled", None, {})
        if time.time() - t0 > timeout:
            p.kill(); return ("timeout", None, {"timeout_s": timeout})
        # progresso "vivo" entre prep e 90%
        cur = min(90, prep_pct + int((time.time() - t0) / max(timeout, 1) * (90 - prep_pct)))
        client.update(jid, progress_percent=cur)
        time.sleep(2)
    th.join(timeout=5)
    out_lines = list(tail)
    for ln in out_lines[-6:]:
        if ln.strip(): client.log(jid, "debug", ln.strip()[:400])
    code = p.returncode
    if code != 0:
        return ("failed", code, {"saida": "\n".join(out_lines[-8:])[:1500]})
    # etapas finais + artefatos
    for pct, label in STEPS:
        if pct < prep_pct: continue
        if _cancelled(client, jid): return ("cancelled", code, {})
        client.progress(jid, pct, label)
        if label == "Subindo artefatos":
            job_folder = os.path.join(pipeline_root(), "outputs", "jobs", f"job_{jid}")
            if not os.path.isdir(job_folder) and online_root():
                job_folder = os.path.join(online_root(), "outputs", "jobs", f"job_{jid}")
            folder = job_folder if os.path.isdir(job_folder) else _latest_round()
            _register_artifacts(client, jid, folder)
    return ("success", code, {"resumo": next((l for l in reversed(out_lines) if l.strip()), "")[:300]})

_UP_FIELDS = ("storage_bucket", "storage_path", "mime_type", "size_bytes", "checksum_sha256",
              "upload_status", "upload_error", "uploaded_at")
def _apply_meta(client, artifact_id, meta):
    client.update_artifact(artifact_id, **{k: meta[k] for k in _UP_FIELDS if k in meta})

def _job_upload_artifacts(client, job, params):
    jid = job["id"]
    folder = params.get("folder") or _latest_round()
    client.progress(jid, 20, "Subindo artefatos")
    n = _register_artifacts(client, jid, folder, job)
    return ("success", 0, {"artefatos": n, "storage_configurado": storage.is_storage_configured()})

def _job_reupload(client, job, params):
    jid = job["id"]; aid = params.get("artifact_id")
    art = client.get_artifact(aid) if aid else None
    if not art: return ("failed", 2, {"erro": "artifact_id inválido"})
    client.progress(jid, 30, "Subindo artefatos")
    lp = art.get("local_path")
    if not lp or not os.path.exists(lp):
        client.update_artifact(aid, upload_status="missing")
        return ("failed", 2, {"erro": "arquivo local ausente", "artifact_id": aid})
    pj = client.get_job(art["job_id"]) or job
    meta = storage.upload_artifact(pj, lp)
    _apply_meta(client, aid, meta)
    st = meta.get("upload_status")
    return (("success" if st in ("uploaded", "local_only") else "failed"), 0, {"artifact_id": aid, "status": st})

def _job_sync(client, job):
    jid = job["id"]
    pend = client.local_only_artifacts()
    client.progress(jid, 10, "Subindo artefatos")
    up = miss = 0
    for art in pend:
        lp = art.get("local_path")
        if not lp or not os.path.exists(lp):
            client.update_artifact(art["id"], upload_status="missing"); miss += 1; continue
        pj = client.get_job(art["job_id"]) or job
        meta = storage.upload_artifact(pj, lp)
        _apply_meta(client, art["id"], meta)
        up += (meta.get("upload_status") == "uploaded")
    return ("success", 0, {"pendentes": len(pend), "enviados": up, "ausentes": miss,
                            "storage_configurado": storage.is_storage_configured()})

def _job_cleanup(client, job):
    client.progress(job["id"], 50, "Finalizando")
    client._exec("UPDATE atlas_job_artifacts SET signed_url_expires_at=NULL WHERE signed_url_expires_at IS NOT NULL")
    client.con.commit()
    return ("success", 0, {"limpeza": "signed_url_expires_at zeradas (não persistimos URLs assinadas)"})

def _coordinate_chunks(client, job, kind):
    """Coleta via POOL: enfileira os chunks (uf x trimestre) e acompanha VM1+VM2+PC ate terminar.
    Tudo ADD-only e pinado na rodada estavel -> a base nunca encolhe. Se o coordenador morrer,
    os chunks continuam sendo processados pelas VMs (o dado nao se perde; so o status do job fica velho)."""
    jid = job["id"]
    import atlas_chunk_plan as planner
    run_id, n = planner.plan(kind)
    client.log(jid, "info", "Enfileirados %d chunks (run %s, %s). O pool (2 VMs + PC quando ligado) "
               "coleta em paralelo, ADD-only." % (n, run_id, kind), step="Coletando PNCP")
    client.update(jid, current_step="Coletando PNCP (0/%d)" % n, progress_percent=5)
    deadline = time.time() + int(os.environ.get("ATLAS_CHUNK_RUN_TIMEOUT", "57600"))  # 16h
    last = None
    while time.time() < deadline:
        if client.is_cancel_requested(jid):
            client.log(jid, "warning", "Cancelado — chunks restantes nao serao coletados.", step="Finalizando")
            return ("cancelled", 0, {"run_id": run_id, "motivo": "cancelado"})
        prog = planner.progress(run_id)
        total = sum(prog.values()) or n
        done = prog.get("done", 0); failed = prog.get("failed", 0)
        pend = total - done - failed
        if prog != last:
            pct = 5 + int(90 * (done + failed) / max(1, total))
            client.update(jid, current_step="Coletando PNCP (%d/%d)" % (done, total), progress_percent=min(95, pct))
            client.log(jid, "info", "progresso: %d ok, %d falha, %d na fila (de %d)." % (done, failed, pend, total), step="Coletando PNCP")
            last = dict(prog)
        if total > 0 and pend == 0:
            if failed == 0:
                return ("success", 0, {"run_id": run_id, "done": done, "total": total})
            if done > 0:
                return ("success", 0, {"run_id": run_id, "done": done, "failed": failed, "total": total, "obs": "alguns chunks falharam"})
            return ("failed", 1, {"run_id": run_id, "failed": failed, "total": total})
        time.sleep(20)
    return ("timeout", 1, {"run_id": run_id, "motivo": "deadline de coordenacao"})

def execute(client, job):
    """Ponto de entrada do worker. Retorna (status, exit_code, result_dict)."""
    jid = job["id"]; jt = job["job_type"]
    params = job.get("parameters_json") or {}
    if isinstance(params, str):
        try: params = json.loads(params)
        except Exception: params = {}
    # jobs de Storage (rodam sempre; sem pipeline pesado)
    if jt == "upload_artifacts":       return _job_upload_artifacts(client, job, params)
    if jt == "reupload_artifact":      return _job_reupload(client, job, params)
    if jt == "sync_storage":           return _job_sync(client, job)
    if jt == "cleanup_old_signed_urls": return _job_cleanup(client, job)
    simulate = params.get("simulate") or os.environ.get("ATLAS_JOB_SIMULATE") in ("1", "true", "True")

    if jt not in __import__("atlas_job_client").JOB_TYPES:
        client.log(jid, "error", f"Tipo de job desconhecido: {jt}", step="Finalizando")
        return ("failed", 2, {"erro": "job_type inválido"})

    if simulate:
        client.log(jid, "info", "Modo SIMULADO (sem pipeline pesado)", step="Preparando ambiente")
        return _simulate(client, job)

    pipe = pipeline_root(); onl = online_root()
    cfg = job.get("config_path") or "config/atlas_config_producao.json"
    tag = job.get("tag") or "PRODUCAO"
    if jt == "run_test":
        return _run_cmd(client, job, ["src/atlas_weekly_runner.py", "--config", "config/atlas_config_teste.json", "--tag", "TESTE"], pipe)
    if jt in ("run_production", "run_production_write_db"):
        write_db = (jt == "run_production_write_db" or job.get("write_db"))
        if write_db:
            # NOVA ARQUITETURA: coleta no banco roda pelo POOL DE CHUNKS (VM1+VM2+PC), nao mais o monolito.
            # O job vira COORDENADOR: enfileira os pedacos e acompanha ate terminar. ADD-only + pinado.
            kind = (params.get("kind") or "").lower()
            if kind not in ("completo", "incremental"):
                kind = "completo" if "producao" in (cfg or "").lower() else "incremental"
            return _coordinate_chunks(client, job, kind)
        # sem banco: gera so os arquivos (Excel/relatorio), como antes (monolito, nao toca no banco)
        args = ["src/atlas_weekly_runner.py", "--config", cfg, "--tag", tag]
        prod_to = int(os.environ.get("ATLAS_PROD_TIMEOUT", "43200"))  # 12h: varredura de até 6 anos
        return _run_cmd(client, job, args, pipe, timeout=prod_to)
    if jt == "load_round_to_db":
        rd = params.get("rodada") or _latest_round()
        args = ["src/load_weekly_to_db.py", "--rodada", rd, "--no-init"]
        if os.environ.get("DATABASE_URL"): args += ["--db-url", os.environ["DATABASE_URL"]]
        return _run_cmd(client, job, args, pipe, prep_pct=15)
    if jt == "update_prototype":
        return _run_cmd(client, job, ["src/build_prototipo_real.py"], pipe, prep_pct=15)
    if jt == "generate_package":
        _register_artifacts(client, jid, _latest_round()); return ("success", 0, {"pacote": "registrado"})
    # jobs que chamam os scripts do projeto online ou scripts genericos do pilot
    if jt in ("validate_online", "apply_sql", "create_users", "auto_setup"):
        custom = params.get("args")
        smap = {"validate_online": ["scripts/atlas_validate_online.py"],
                "apply_sql": ["scripts/atlas_apply_sql.py"],
                "create_users": ["scripts/atlas_create_users.py"],
                "auto_setup": (custom if isinstance(custom, list) and len(custom) > 0
                               else ["scripts/atlas_auto_setup.py", "--mode", params.get("mode", "validate")])}
        script_rel = smap[jt][0]
        to_val = 1800 if "coleta_orgaos_especificos.py" in script_rel else 290
        if os.path.exists(os.path.join(pipe, script_rel)):
            return _run_cmd(client, job, smap[jt], pipe, prep_pct=15, timeout=to_val)
        elif onl:
            return _run_cmd(client, job, smap[jt], onl, prep_pct=15, timeout=to_val)
    client.log(jid, "error", f"Sem handler para {jt}", step="Finalizando")
    return ("failed", 2, {"erro": "sem handler"})
