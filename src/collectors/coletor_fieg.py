# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: FIEG (SESI/SENAI/IEL Goiás), fora do PNCP.

Fonte: https://www.fieg.com.br/licitacao/site/Licitacao.do
Java/Struts, HTML server-side, paginação via GET (`?page=N`), precisa manter
cookie de sessão (jsessionid) entre requisições — por isso usamos
requests.Session(). filtro.status=1 = licitações abertas (escopo inicial).

Uso:
  python src/collectors/coletor_fieg.py --db-url postgresql://... --write-db
  python src/collectors/coletor_fieg.py --dry-run
"""
import os, sys, re, hashlib, argparse, time, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.fieg.com.br/licitacao/site/Licitacao.do"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "FIEG"
FONTE = "FIEG"


def _parse_data(txt):
    if not txt:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt)
    if not m:
        return None
    d, mth, y = m.groups()
    try:
        return datetime.date(int(y), int(mth), int(d)).isoformat()
    except Exception:
        return None


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for li in soup.select("ul.licitacoesLista > li"):
        titu = li.select_one("span.titu")
        desc = li.select_one("div.tituDesc p")
        data = li.select_one("span.maior")
        link = li.select_one("a.visualizarLic")
        if not titu:
            continue
        itens.append({
            "titulo": titu.get_text(strip=True),
            "objeto": desc.get_text(strip=True) if desc else "",
            "data_abertura": data.get_text(strip=True) if data else "",
            "link": ("https://www.fieg.com.br/licitacao/site/" + link["href"]) if link and link.get("href") else BASE,
        })
    m = re.search(r"(\d+)\s*itens encontrado", html)
    total = int(m.group(1)) if m else None
    return itens, total


def coletar(sleep=1.0, log=print):
    sess = requests.Session()
    sess.headers.update(HEADERS)
    r = sess.get(BASE, params={"filtro.status": 1}, timeout=30)
    r.raise_for_status()
    itens, total = parse_pagina(r.text)
    log(f"FIEG: total anunciado={total}, página 1 = {len(itens)} item(ns).")
    page = 2
    while total and len(itens) < total and page <= 30:
        time.sleep(sleep)
        r = sess.get(BASE, params={"filtro.status": 1, "page": page}, timeout=30)
        r.raise_for_status()
        novos, _ = parse_pagina(r.text)
        if not novos:
            break
        itens.extend(novos)
        log(f"  página {page}: +{len(novos)} (total {len(itens)})")
        page += 1
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "FIEG - Federação das Indústrias do Estado de Goiás (SESI/SENAI/IEL)",
        "nome_padronizado": "FIEG",
        "uf": "GO",
        "municipio": "Goiânia",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"FIEG|{it.get('titulo') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("titulo", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link", BASE),
            "objeto_original": it.get("objeto", ""),
            "modalidade": "Credenciamento/Licitação",
            "inicio_vigencia": _parse_data(it.get("data_abertura")),
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
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
