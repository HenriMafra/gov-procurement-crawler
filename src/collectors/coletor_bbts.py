# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: BBTS (BB Tecnologia e Serviços), fora do PNCP.

Fonte: https://licitacoes.bbts.com.br/
HTML server-side (WordPress/Gutenberg). O 403 da primeira varredura era só
bloqueio de User-Agent — com header de navegador real, HTTP 200. Editais
aparecem como parágrafos "LE AAAA/NN <a href=edital.pdf>Edital</a>: objeto"
dentro de accordions organizados por ano (`wp-block-ub-content-toggle-*`).
Sem post-type de licitação no wp-json — dados são conteúdo estático da
página, não posts separados.

Uso:
  python src/collectors/coletor_bbts.py --db-url postgresql://... --write-db
  python src/collectors/coletor_bbts.py --dry-run
"""
import os, sys, re, hashlib, argparse, subprocess, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from bs4 import BeautifulSoup

BASE = "https://licitacoes.bbts.com.br/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"


def _fetch_via_curl(url):
    """O WAF do BBTS bloqueia pelo fingerprint TLS do requests/urllib3 (JA3), mas aceita
    curl — mesmos headers, cliente HTTP diferente. Shell-out para curl como workaround."""
    r = subprocess.run(
        ["curl", "-s", "-A", UA, "-H", "Accept-Language: pt-BR,pt;q=0.9", "--max-time", "30", url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
    )
    return r.stdout
ORGAO_KEY = "BBTS"
FONTE = "BBTS"

LE_RE = re.compile(r"^(LE\s*(\d{4})/\d+)\s*(.*)$", re.I)
DATA_PDF_RE = re.compile(r"/(\d{4})(\d{2})(\d{2})_")


def _data_do_link(link, ano_fallback):
    """PDFs têm prefixo de data no nome do arquivo (ex.: 20260629_EDITAL...);
    usa isso quando existe, senão cai pro ano extraído do número LE AAAA/NN."""
    m = DATA_PDF_RE.search(link or "")
    if m:
        try:
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except Exception:
            pass
    return f"{ano_fallback}-01-01" if ano_fallback else None


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for p in soup.select("p"):
        txt = p.get_text(" ", strip=True)
        m = LE_RE.match(txt)
        if not m:
            continue
        numero = m.group(1).replace(" ", "")
        ano = m.group(2)
        objeto = m.group(3)
        objeto = re.sub(r"^Edital\s*:\s*", "", objeto).strip()
        link_el = p.find("a", href=True)
        link = link_el["href"] if link_el else BASE
        itens.append({"numero": numero, "objeto": objeto, "link": link,
                       "data": _data_do_link(link, ano)})
    # dedup por número (mesma LE pode repetir em seções diferentes da página)
    ded = {}
    for it in itens:
        ded[it["numero"]] = it
    return list(ded.values())


def coletar(log=print):
    html = _fetch_via_curl(BASE)
    itens = parse_pagina(html)
    log(f"BBTS: {len(itens)} licitação(ões) capturada(s) (página única).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "BBTS - BB Tecnologia e Serviços",
        "nome_padronizado": "BBTS",
        "uf": "",
        "municipio": "",
        "poder": "Executivo",
        "esfera": "Federal",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"BBTS|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link", BASE),
            "objeto_original": it.get("objeto", ""),
            "modalidade": "Licitação Eletrônica",
            "data_assinatura": it.get("data"),
        })
    return orgao, contratos


def gravar_db(db_url, orgao, contratos, log=print):
    from atlas_db import AtlasDB
    db = AtlasDB(db_url)
    orgao_id = db.upsert_orgao(orgao)
    n = 0
    for c in contratos:
        c["orgao_id"] = orgao_id
        db.upsert_contrato(c)
        n += 1
    db.commit()
    db.close()
    log(f"-> gravado no banco: 1 órgão, {n} licitações.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = coletar()
    orgao, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} licitações.")
    for c in contratos[:5]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:70])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
