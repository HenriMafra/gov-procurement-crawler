# -*- coding: utf-8 -*-
"""
ATLAS B2G — Camada de Storage (Supabase Storage via REST + service role).
Upload de artefatos, signed URLs, sha256, mime, mapeamento tipo→bucket, matriz de permissão.
NUNCA expõe a service role; mascara segredos. Fallback local quando Storage não configurado.
"""
import os, re, sys, hashlib, mimetypes, datetime

BUCKETS = ["rodadas", "relatorios", "exports", "logs", "prototipos"]

# tipo de artefato -> bucket
BUCKET_FOR = {
    "excel": "exports", "csv": "exports", "zip": "exports",
    "report_md": "relatorios", "report_pdf": "relatorios", "validation_report": "relatorios",
    "prototype_html": "prototipos", "prototype_js": "prototipos",
    "log": "logs", "json": "rodadas", "config": "rodadas",
}
# matriz de download: perfil -> tipos permitidos ("*" = todos)
DOWNLOAD_MATRIX = {
    "Administrador": {"*"},
    "Operador de Inteligência": {"excel", "csv", "zip", "report_md", "report_pdf", "validation_report",
                                  "prototype_html", "prototype_js", "log", "json", "config"},
    "Coordenador Comercial": {"excel", "csv", "zip", "report_md", "report_pdf", "prototype_html"},
    "Vendedor": {"csv", "report_pdf"},
    "Diretoria": {"report_md", "report_pdf", "validation_report", "zip", "prototype_html"},
}

def can_download(role, artifact_type):
    allowed = DOWNLOAD_MATRIX.get(role, set())
    return "*" in allowed or artifact_type in allowed

def _cfg():
    url = os.environ.get("NEXT_PUBLIC_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    svc = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    bad = lambda v: (not v) or ("placeholder" in v.lower()) or ("seu-projeto" in v.lower())
    if bad(url) or bad(svc): return None, None
    return url.rstrip("/"), svc

def is_storage_configured():
    u, s = _cfg(); return bool(u and s)

def _headers(svc, extra=None):
    h = {"apikey": svc, "Authorization": f"Bearer {svc}"}
    if extra: h.update(extra)
    return h

def _mask(msg):
    _, svc = _cfg()
    return msg.replace(svc, "***") if svc and msg else msg

# ---------- metadados ----------
def detect_artifact_type(path):
    n = os.path.basename(path).lower(); ext = os.path.splitext(n)[1]
    if ext == ".xlsx": return "excel"
    if ext == ".zip": return "zip"
    if ext == ".pdf": return "report_pdf"
    if ext == ".md":
        if "valida" in n: return "validation_report"
        return "report_md"
    if ext == ".html": return "prototype_html"
    if ext == ".js": return "prototype_js"
    if ext in (".txt", ".log"): return "log"
    if ext == ".csv": return "csv"
    if ext == ".json":
        return "config" if "config" in n else "json"
    return "json"

def bucket_for_artifact(atype):
    return BUCKET_FOR.get(atype, "rodadas")

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def mime_type_for(path):
    mt, _ = mimetypes.guess_type(path)
    if mt: return mt
    ext = os.path.splitext(path)[1].lower()
    return {".md": "text/markdown", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".zip": "application/zip", ".csv": "text/csv", ".json": "application/json",
            ".js": "application/javascript", ".txt": "text/plain"}.get(ext, "application/octet-stream")

def _sanitize(part):
    part = re.sub(r"[^A-Za-z0-9_.\-]", "_", str(part or ""))
    return part.replace("..", "_")

def build_storage_path(job, artifact_type, file_path):
    tag = _sanitize(job.get("tag") or "SEMTAG")
    created = str(job.get("created_at") or "")
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(file_path)) or re.search(r"(\d{4}-\d{2}-\d{2})", created)
    data = m.group(1) if m else (created[:10] if created else "sem-data")
    jid = _sanitize(job.get("id"))
    fname = _sanitize(os.path.basename(file_path))
    return f"{tag}/{data}/{jid}/{_sanitize(artifact_type)}/{fname}"

# ---------- buckets ----------
def ensure_buckets(buckets=None):
    u, s = _cfg()
    if not u: return {"ok": False, "reason": "storage_nao_configurado"}
    import requests
    res = {}
    for b in (buckets or BUCKETS):
        try:
            r = requests.post(f"{u}/storage/v1/bucket", headers=_headers(s, {"Content-Type": "application/json"}),
                              json={"id": b, "name": b, "public": False}, timeout=15)
            res[b] = "criado" if r.status_code in (200, 201) else ("existe" if r.status_code in (400, 409) else f"HTTP {r.status_code}")
        except Exception as e:
            res[b] = "erro: " + _mask(str(e))[:80]
    return {"ok": True, "buckets": res}

# ---------- upload / signed ----------
def upload_artifact(job, file_path):
    """Retorna metadados + status. Nunca levanta exceção fatal."""
    base = {"file_name": os.path.basename(file_path), "local_path": file_path}
    if not os.path.exists(file_path):
        return {**base, "upload_status": "missing", "artifact_type": detect_artifact_type(file_path)}
    atype = detect_artifact_type(file_path)
    meta = {**base, "artifact_type": atype, "mime_type": mime_type_for(file_path),
            "size_bytes": os.path.getsize(file_path), "checksum_sha256": sha256_file(file_path)}
    u, s = _cfg()
    if not (u and s):
        return {**meta, "upload_status": "local_only"}
    bucket = bucket_for_artifact(atype); spath = build_storage_path(job, atype, file_path)
    try:
        import requests
        with open(file_path, "rb") as f:
            data = f.read()
        r = requests.post(f"{u}/storage/v1/object/{bucket}/{spath}",
                          headers=_headers(s, {"Content-Type": meta["mime_type"], "x-upsert": "true"}),
                          data=data, timeout=120)
        if r.status_code in (200, 201):
            return {**meta, "storage_bucket": bucket, "storage_path": spath, "upload_status": "uploaded",
                    "uploaded_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        return {**meta, "storage_bucket": bucket, "storage_path": spath, "upload_status": "failed",
                "upload_error": _mask(f"HTTP {r.status_code}: {r.text[:160]}")}
    except Exception as e:
        return {**meta, "storage_bucket": bucket, "storage_path": spath, "upload_status": "failed",
                "upload_error": _mask(str(e))[:200]}

def upload_artifacts_for_job(job, files):
    return [upload_artifact(job, f) for f in files]

def create_signed_url(bucket, path, expires_in=3600):
    u, s = _cfg()
    if not (u and s): return None
    if ".." in (path or ""): return None  # anti path-traversal
    try:
        import requests
        r = requests.post(f"{u}/storage/v1/object/sign/{bucket}/{path}",
                          headers=_headers(s, {"Content-Type": "application/json"}),
                          json={"expiresIn": int(expires_in)}, timeout=15)
        if r.ok:
            signed = r.json().get("signedURL") or r.json().get("signedUrl")
            return (u + "/storage/v1" + signed) if signed else None
    except Exception:
        return None
    return None

def download_to(url, dest):
    import requests
    r = requests.get(url, timeout=60); r.raise_for_status()
    with open(dest, "wb") as f: f.write(r.content)
    return dest
