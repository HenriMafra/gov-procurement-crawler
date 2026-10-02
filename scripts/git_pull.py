# -*- coding: utf-8 -*-
import subprocess
import os

def run():
    print("Iniciando git pull remotos...", flush=True)
    
    # 1) Pilot directory
    pilot_dir = os.environ.get("ATLAS_PIPELINE_ROOT") or "/opt/ATLAS-PNCP-Pilot"
    if os.path.isdir(pilot_dir):
        print(f"Executando git pull em: {pilot_dir}", flush=True)
        r1 = subprocess.run(["git", "pull"], cwd=pilot_dir, capture_output=True, text=True)
        print("STDOUT:", r1.stdout, flush=True)
        print("STDERR:", r1.stderr, flush=True)
    else:
        print(f"Diretório {pilot_dir} não encontrado.", flush=True)
        
    # 2) Online directory
    online_dir = os.environ.get("ATLAS_ONLINE_ROOT") or "/opt/atlas-b2g-online"
    if os.path.isdir(online_dir):
        print(f"Executando git pull em: {online_dir}", flush=True)
        r2 = subprocess.run(["git", "pull"], cwd=online_dir, capture_output=True, text=True)
        print("STDOUT:", r2.stdout, flush=True)
        print("STDERR:", r2.stderr, flush=True)
    else:
        print(f"Diretório {online_dir} não encontrado.", flush=True)
        
    print("Git pull remoto finalizado!", flush=True)

if __name__ == "__main__":
    run()
