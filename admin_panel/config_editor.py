# -*- coding: utf-8 -*-
"""Edição segura das configurações (JSON) do ATLAS: valida, faz backup, diff e restaura."""
import os, json, shutil, datetime, glob

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CFG_DIR = os.path.join(ROOT, "config")
BKP_DIR = os.path.join(CFG_DIR, "_backups")

def load(nome):
    path = os.path.join(CFG_DIR, nome)
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def validar(texto):
    try:
        return True, json.loads(texto), ""
    except Exception as e:
        return False, None, f"JSON inválido: {e}"

def diff(antigo, novo):
    chaves = set(antigo) | set(novo)
    mudancas = []
    for k in sorted(chaves):
        a, n = antigo.get(k, "<ausente>"), novo.get(k, "<ausente>")
        if a != n:
            mudancas.append({"chave": k, "antes": a, "depois": n})
    return mudancas

def backup(nome):
    os.makedirs(BKP_DIR, exist_ok=True)
    src = os.path.join(CFG_DIR, nome)
    if not os.path.exists(src):
        return None
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    dst = os.path.join(BKP_DIR, f"{nome}.{ts}.bak")
    shutil.copyfile(src, dst)
    return dst

def salvar(nome, data):
    """Faz backup do atual, grava o novo (valida via dump) e retorna (diff, caminho_backup)."""
    path = os.path.join(CFG_DIR, nome)
    antigo = {}
    if os.path.exists(path):
        try: antigo = json.load(open(path, encoding="utf-8"))
        except Exception: antigo = {}
    bkp = backup(nome)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return diff(antigo, data), bkp

def listar_backups(nome):
    os.makedirs(BKP_DIR, exist_ok=True)
    gs = sorted(glob.glob(os.path.join(BKP_DIR, f"{nome}.*.bak")), reverse=True)
    return gs

def restaurar(nome, backup_path):
    if not os.path.exists(backup_path):
        raise FileNotFoundError("Backup não encontrado.")
    # salva o estado atual antes de restaurar (segurança)
    backup(nome)
    shutil.copyfile(backup_path, os.path.join(CFG_DIR, nome))
    return True
