# -*- coding: utf-8 -*-
# "ATUALIZAR TUDO" — varredura COMPLETA dos 6 anos, SEM PULAR NADA POR ERRO.
# Estratégia: o coletor é resumível pelo cache (página que falhou NÃO é gravada
# no cache, então uma nova passada baixa só o que faltou). Aqui repetimos a coleta
# em CICLOS até nenhuma página falhar (marcadores no log), e SÓ ENTÃO gravamos no
# banco uma única vez (lendo o cache já completo). Assim "volta no que não puxou".
import os, sys, subprocess, pathlib, datetime

ROOT = pathlib.Path(r"C:\Users\henri\Desktop\ATLAS-PNCP-Pilot")
ENVF = pathlib.Path(r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local")
CONFIG = "config/atlas_config_producao.json"
MAX_CICLOS = 12
# marcadores que o coletor escreve quando NÃO conseguiu baixar tudo de uma janela
MARCADORES = ("ainda falharam", "falhou em definitivo")

def achar_dburl():
    try:
        for line in ENVF.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception as e:
        print("ERRO lendo .env.local:", e)
    return ""

dburl = achar_dburl()
if not dburl:
    print("ERRO: DATABASE_URL nao encontrado em .env.local"); sys.exit(1)

env = dict(os.environ)
env["DATABASE_URL"] = dburl
env["ATLAS_FETCH_WORKERS"] = "2"   # limite seguro do PNCP

logdir = ROOT / "logs"; logdir.mkdir(exist_ok=True)
LOG = logdir / "coleta_tudo.log"

def passe(write_db, n):
    """Roda um passe; transmite o log ao vivo e detecta se ficou pagina faltando."""
    args = [sys.executable, "-X", "utf8", "src/atlas_weekly_runner.py", "--config", CONFIG, "--tag", "PRODUCAO"]
    if write_db:
        args += ["--write-db", "--db-url", dburl]
    buf = []
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n--- ciclo {n} ({'GRAVAR BANCO' if write_db else 'coleta'}) {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ---\n"); f.flush()
        p = subprocess.Popen(args, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in p.stdout:
            f.write(line); f.flush(); buf.append(line)
        p.wait()
    txt = "".join(buf[-8000:])
    incompleto = any(m in txt for m in MARCADORES)
    return p.returncode, incompleto

with open(LOG, "a", encoding="utf-8") as f:
    f.write(f"\n===== ATUALIZAR TUDO (completo, sem pular) {datetime.datetime.now():%Y-%m-%d %H:%M:%S} =====\n")

# FASE 1 — completar o cache: repete coleta-só até NÃO faltar nenhuma página
completo = False
for ciclo in range(1, MAX_CICLOS + 1):
    print(f"[coleta] ciclo {ciclo}/{MAX_CICLOS} (preenchendo cache, sem pular)...", flush=True)
    rc, incompleto = passe(write_db=False, n=ciclo)
    if not incompleto:
        completo = True
        print(f"[coleta] CACHE COMPLETO no ciclo {ciclo} — nenhuma pagina faltando.", flush=True)
        break
    print(f"[coleta] ainda faltam paginas; repetindo (volta no que nao puxou)...", flush=True)

if not completo:
    print(f"[coleta] AVISO: apos {MAX_CICLOS} ciclos ainda restaram paginas (PNCP muito instavel). Gravando o que ja temos; rode de novo depois p/ fechar.", flush=True)

# FASE 2 — grava no banco UMA vez (le o cache; nao re-baixa o que ja esta completo)
print("[coleta] gravando rodada no banco...", flush=True)
rc, _ = passe(write_db=True, n="GRAVAR")
with open(LOG, "a", encoding="utf-8") as f:
    f.write(f"===== FIM (cache_completo={completo}, write rc={rc}) =====\n")
print(f"[coleta] FIM. cache_completo={completo}, gravacao rc={rc}", flush=True)
sys.exit(rc)
