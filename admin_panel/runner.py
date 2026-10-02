# -*- coding: utf-8 -*-
"""Camada que executa o pipeline ATLAS por trás dos botões do painel.
Usa subprocess de forma segura (lista de args, sem shell) e captura tudo."""
import os, sys, subprocess, glob, re, time, csv, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
RODADAS = os.path.join(ROOT, "outputs", "rodadas")

def _run(args, timeout=5400):
    t0 = time.time()
    try:
        p = subprocess.run([PY] + args, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out, err, code = p.stdout or "", p.stderr or "", p.returncode
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": -1, "dur": round(time.time()-t0, 1), "out": "", "err": "Tempo excedido (timeout).", "resumo": ""}
    except Exception as e:
        return {"ok": False, "code": -1, "dur": round(time.time()-t0, 1), "out": "", "err": str(e), "resumo": ""}
    res = {"ok": code == 0, "code": code, "dur": round(time.time()-t0, 1), "out": out, "err": err}
    m = re.search(r"RESUMO:.*", out)
    res["resumo"] = m.group(0) if m else (out.strip().splitlines()[-1] if out.strip() else "")
    mp = re.search(r"pasta:\s*(.+)\s*===", out)
    res["rodada_dir"] = mp.group(1).strip() if mp else None
    return res

# ---------- operações ----------
def rodar_teste():
    cfg = "config/atlas_config_teste.json"
    if not os.path.exists(os.path.join(ROOT, cfg)): cfg = "config/atlas_config.json"
    return _run(["src/atlas_weekly_runner.py", "--config", cfg, "--tag", "TESTE"])

def rodar_producao():
    return _run(["src/atlas_weekly_runner.py", "--config", "config/atlas_config_producao.json", "--tag", "PRODUCAO"])

def rodar_producao_com_banco(db_url=None):
    args = ["src/atlas_weekly_runner.py", "--config", "config/atlas_config_producao.json", "--tag", "PRODUCAO", "--write-db"]
    if db_url: args += ["--db-url", db_url]
    return _run(args)

def carregar_rodada_no_banco(rodada_dir, db_url=None):
    args = ["src/load_weekly_to_db.py", "--rodada", rodada_dir]
    if db_url: args += ["--db-url", db_url]
    return _run(args, timeout=1800)

def atualizar_prototipo(rodada_dir=None):
    args = ["src/build_prototipo_real.py"]
    if rodada_dir:
        csvs = glob.glob(os.path.join(rodada_dir, "atlas_lista_ataque_comercial_*.csv"))
        if csvs: args += ["--csv", csvs[0], "--out", rodada_dir]
    return _run(args, timeout=600)

def gerar_pacote(rodada_dir=None):
    """O ZIP já é gerado em cada rodada; aqui retornamos o caminho do pacote mais recente."""
    rd = rodada_dir or _ultima_rodada_dir()
    if not rd: return {"ok": False, "err": "Nenhuma rodada encontrada."}
    z = glob.glob(os.path.join(rd, "*.zip"))
    return {"ok": bool(z), "zip": (z[0] if z else None), "rodada_dir": rd,
            "err": "" if z else "ZIP não encontrado na rodada (rode a esteira primeiro)."}

# ---------- leitura / status ----------
def _parse_resumo(txt):
    d = {}
    m = re.search(r"Oportunidades:\s*(\d+)", txt);  d["oportunidades"] = int(m.group(1)) if m else None
    m = re.search(r"Cr[ií]ticas:\s*(\d+)", txt);     d["criticas"] = int(m.group(1)) if m else None
    m = re.search(r"Valor total:\s*([^\n|]+)", txt); d["valor"] = m.group(1).strip() if m else None
    return d

def _metrics_from_csv(rd):
    csvs = glob.glob(os.path.join(rd, "atlas_lista_ataque_comercial_*.csv"))
    if not csvs: return {}
    rows = list(csv.DictReader(open(csvs[0], encoding="utf-8-sig")))
    valor = sum(float(r.get("Valor Total") or 0) for r in rows)
    crit = sum(1 for r in rows if r.get("Urgência Comercial") == "Crítica")
    return {"oportunidades": len(rows), "criticas": crit,
            "valor": "R$ " + format(valor, ",.0f").replace(",", ".")}

def listar_rodadas():
    if not os.path.isdir(RODADAS): return []
    out = []
    for nome in sorted(os.listdir(RODADAS), reverse=True):
        rd = os.path.join(RODADAS, nome)
        if not os.path.isdir(rd): continue
        m = re.match(r"^(?:(.+)_)?(\d{4}-\d{2}-\d{2})$", nome)
        if not m: continue
        info = {"pasta": nome, "caminho": rd, "tag": m.group(1) or "", "data": m.group(2)}
        info.update(_metrics_from_csv(rd))
        c = caminhos_rodada(rd)
        info["tem_excel"] = bool(c["excel"]); info["tem_relatorio"] = bool(c["relatorio"])
        info["tem_prototipo"] = bool(c["prototipo"]); info["tem_zip"] = bool(c["zip"])
        out.append(info)
    return out

def _ultima_rodada_dir():
    rs = listar_rodadas()
    # prioriza PRODUCAO; senão a mais recente por data
    prod = [r for r in rs if r["tag"].upper() == "PRODUCAO"]
    base = prod or rs
    return base[0]["caminho"] if base else None

def obter_status_ultima_rodada():
    rd = _ultima_rodada_dir()
    if not rd: return {"existe": False}
    nome = os.path.basename(rd)
    m = re.match(r"^(?:(.+)_)?(\d{4}-\d{2}-\d{2})$", nome)
    d = {"existe": True, "pasta": nome, "caminho": rd, "tag": (m.group(1) if m else ""), "data": (m.group(2) if m else "")}
    d.update(_metrics_from_csv(rd))
    return d

def caminhos_rodada(rd):
    def first(pat):
        g = glob.glob(os.path.join(rd, pat)); return g[0] if g else None
    return {
        "excel": first("atlas_lista_ataque_comercial_*.xlsx"),
        "relatorio": first("atlas_relatorio_semanal_*.md") or first("atlas_relatorio_semanal_*.pdf"),
        "relatorio_pdf": first("atlas_relatorio_semanal_*.pdf"),
        "prototipo": first("ATLAS-B2G_Prototipo-Dados-Reais-PNCP_*.html"),
        "zip": first("atlas_pacote_*_*.zip"),
        "log": first("atlas_log_execucao_*.txt"),
        "csv": first("atlas_lista_ataque_comercial_*.csv"),
        "calibracao": first("atlas_relatorio_calibracao_*.md"),
        "mapa": first("mapa_distribuicao_comercial_*.md"),
        "pasta": rd,
    }

def ler_logs(rd, n=200):
    lg = caminhos_rodada(rd)["log"]
    if not lg or not os.path.exists(lg): return "(sem log nesta rodada)"
    linhas = open(lg, encoding="utf-8", errors="replace").read().splitlines()
    return "\n".join(linhas[-n:])

def obter_status_banco(db_url=None):
    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        return {"configurado": False, "msg": "Banco não configurado. Defina DATABASE_URL ou use sqlite de teste."}
    try:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from atlas_db import AtlasDB
        db = AtlasDB(url)
        tabelas = {}
        for t in ["rodadas", "orgaos", "fornecedores", "contratos", "oportunidades", "oportunidade_historico"]:
            try: tabelas[t] = db.count(t)
            except Exception: tabelas[t] = "—"
        try:
            ult = db.fetch("SELECT data_rodada, tag FROM rodadas ORDER BY data_rodada DESC, id DESC LIMIT 1")
        except Exception:
            ult = []
        db.close()
        return {"configurado": True, "dialeto": db.dialect, "tabelas": tabelas,
                "ultima_rodada": (ult[0] if ult else None), "msg": "Conexão OK."}
    except Exception as e:
        return {"configurado": True, "erro": str(e), "msg": "Falha ao conectar/consultar o banco."}

def abrir_caminho(path):
    """Abre arquivo/pasta no SO (Windows: os.startfile)."""
    if not path or not os.path.exists(path):
        return False
    try:
        os.startfile(path)  # Windows
        return True
    except Exception:
        try:
            import subprocess as _s
            _s.Popen(["explorer", os.path.normpath(path)])
            return True
        except Exception:
            return False
