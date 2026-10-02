# -*- coding: utf-8 -*-
"""Ponte do painel Streamlit para a camada de automação (scripts atlas_* do projeto online)."""
import os, sys, subprocess, time

def locate_online_root():
    r = os.environ.get("ATLAS_ONLINE_ROOT")
    if r and os.path.isdir(os.path.join(r, "scripts")):
        return r
    pilot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # raiz do pilot
    cand = os.path.join(os.path.dirname(pilot), "atlas-b2g-online")        # irmão no Desktop
    return cand if os.path.isdir(os.path.join(cand, "scripts")) else None

def default_dburl(online_root):
    db = os.environ.get("DATABASE_URL")
    if db and "placeholder" not in db and "SUA_SENHA" not in db:
        return db
    return "sqlite:///" + os.path.join(online_root, "_localtest", "atlas_local.sqlite").replace("\\", "/")

def run_ps1(online_root, ps1, args=None, timeout=300):
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", os.path.join("scripts", ps1)] + (args or [])
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=online_root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        return {"ok": p.returncode == 0, "code": p.returncode, "out": out,
                "resumo": next((l for l in reversed(out.splitlines()) if l.strip()), ""), "dur": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "code": -1, "out": str(e), "resumo": str(e), "dur": round(time.time() - t0, 1)}

def run_script(online_root, script, args=None, timeout=900):
    py = os.environ.get("ATLAS_PYTHON") or sys.executable or "python"
    cmd = [py, os.path.join("scripts", script)] + (args or [])
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=online_root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
        resumo = next((l for l in reversed(out.splitlines()) if l.strip()), "")
        return {"ok": p.returncode == 0, "code": p.returncode, "out": out, "resumo": resumo,
                "dur": round(time.time() - t0, 1)}
    except Exception as e:
        return {"ok": False, "code": -1, "out": str(e), "resumo": str(e), "dur": round(time.time() - t0, 1)}
