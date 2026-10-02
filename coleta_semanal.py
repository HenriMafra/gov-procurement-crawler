# -*- coding: utf-8 -*-
# Coleta SEMANAL automática do ATLAS B2G — rodada pela Tarefa Agendada do Windows
# ("ATLAS-B2G-Coleta-Semanal"). Lê a DATABASE_URL do .env.local em tempo real
# (não guarda segredo aqui). Roda a coleta com a config semanal e grava no banco.
import os, sys, subprocess, pathlib, datetime

ROOT = pathlib.Path(r"C:\Users\henri\Desktop\ATLAS-PNCP-Pilot")
ENVF = pathlib.Path(r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local")

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
    print("ERRO: DATABASE_URL não encontrado em .env.local"); sys.exit(1)

env = dict(os.environ)
env["DATABASE_URL"] = dburl
env["ATLAS_FETCH_WORKERS"] = "2"   # limite seguro do PNCP

logdir = ROOT / "logs"; logdir.mkdir(exist_ok=True)
ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open(logdir / "coleta_semanal.log", "a", encoding="utf-8") as f:
    f.write(f"\n===== Coleta semanal iniciada {ts} =====\n"); f.flush()
    r = subprocess.run(
        [sys.executable, "src/atlas_weekly_runner.py",
         "--config", "config/atlas_config_semanal.json", "--tag", "PRODUCAO", "--write-db"],
        cwd=str(ROOT), env=env, stdout=f, stderr=subprocess.STDOUT,
    )
    f.write(f"===== Coleta semanal terminou (exit {r.returncode}) =====\n")
sys.exit(r.returncode)
