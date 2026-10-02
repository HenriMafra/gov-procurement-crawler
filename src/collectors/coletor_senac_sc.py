# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: SENAC SC, fora do PNCP.

Fonte: https://licitacao.sc.senac.br/
Certificado SSL malconfigurado (self-signed) — requer verify=False. HTML
server-side simples: Bootstrap accordion (`div.accordion-item`), SEM
postback/JS. Cabeçalho de cada item tem modalidade/número/objeto/status;
corpo tem datas de publicação/abertura/disputa.

Uso:
  python src/collectors/coletor_senac_sc.py --db-url postgresql://... --write-db
  python src/collectors/coletor_senac_sc.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests, urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE = "https://licitacao.sc.senac.br/"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "SENAC-SC"
FONTE = "SENAC-SC"


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
    for card in soup.select("div.accordion-item"):
        modalidade_el = card.select_one(".col-md-2 small b")
        numero_el = card.select_one(".col-md-2 span")
        objeto_el = card.select_one(".col-md-8 small")
        status_el = card.select_one(".col-md-2 h6")
        if not (numero_el and objeto_el):
            continue
        body_txt = card.get_text(" ", strip=True)
        m_pub = re.search(r"Data publicação edital:\s*([\d/]+)", body_txt)
        m_abe = re.search(r"Data da abertura:\s*([\d/]+)", body_txt)
        # link específico e verificável: primeiro PDF anexado ao processo (edital), não a página inicial
        pdf_el = card.select_one(".accordion-body a[href$='.pdf']")
        link = requests.compat.urljoin(BASE, pdf_el["href"]) if pdf_el and pdf_el.get("href") else BASE
        itens.append({
            "modalidade": modalidade_el.get_text(strip=True) if modalidade_el else "",
            "numero": numero_el.get_text(strip=True) if numero_el else "",
            "objeto": objeto_el.get_text(strip=True) if objeto_el else "",
            "status": status_el.get_text(strip=True) if status_el else "",
            "data_publicacao": m_pub.group(1) if m_pub else "",
            "data_abertura": m_abe.group(1) if m_abe else "",
            "link": link,
        })
    return itens


def coletar(log=print):
    r = requests.get(BASE, headers=HEADERS, verify=False, timeout=30)
    r.raise_for_status()
    itens = parse_pagina(r.text)
    log(f"SENAC-SC: {len(itens)} processo(s) capturado(s) (página única, sem paginação).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "SENAC SC - Serviço Nacional de Aprendizagem Comercial de Santa Catarina",
        "nome_padronizado": "SENAC SC",
        "uf": "SC",
        "municipio": "Florianópolis",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"SENAC-SC|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto", ""),
            "modalidade": it.get("modalidade", ""),
            "situacao_pncp": it.get("status", ""),
            "data_assinatura": _parse_data(it.get("data_publicacao")),
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
    log(f"-> gravado no banco: 1 órgão, {n} processos.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = coletar()
    orgao, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} processos.")
    for c in contratos[:3]:
        print(" -", c["numero_processo"], "|", c["modalidade"], "|", c["objeto_original"][:70])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
