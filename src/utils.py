# -*- coding: utf-8 -*-
"""Utilitários compartilhados do ATLAS B2G (rotina semanal)."""
import os, json, csv, zipfile, datetime, re

def carregar_config(path):
    """Lê o atlas_config.json (ignora chaves de ajuda iniciadas por '_')."""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg

def brl(v):
    try: return "R$ " + format(float(v), ",.0f").replace(",", ".")
    except Exception: return "R$ 0"

def brlk(v):
    v = float(v or 0)
    if v >= 1e6: return "R$ " + (f"{v/1e6:.1f}").replace(".", ",") + " mi"
    if v >= 1e3: return "R$ " + f"{v/1e3:.0f}" + " mil"
    return brl(v)

def ler_csv(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def escrever_csv(path, linhas, cols):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for l in linhas: w.writerow(l)

def rodadas_anteriores(rodadas_dir, data_atual):
    """Lista pastas de rodadas (YYYY-MM-DD) anteriores à data_atual, mais recente primeiro."""
    if not os.path.isdir(rodadas_dir): return []
    rs = []
    for nome in os.listdir(rodadas_dir):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", nome) and nome < data_atual:
            rs.append(nome)
    return sorted(rs, reverse=True)

def zipar(zip_path, arquivos):
    """Compacta a lista de arquivos (caminhos absolutos) em zip_path (nomes-base)."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for a in arquivos:
            if a and os.path.exists(a):
                z.write(a, os.path.basename(a))
    return zip_path

def parse_data_br(s):
    if not s: return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(str(s)[:10], fmt).date()
        except Exception: pass
    return None
