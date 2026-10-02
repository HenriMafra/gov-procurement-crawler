# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: SENAC PR, fora do PNCP.

Fonte: https://www.pr.senac.br/licitacoes/
HTML server-side simples (Bootstrap panels), página única (todas as seções
de status já vêm no HTML, sem paginação). Cada licitação é um
`div.panel` com `.panel-heading` (modalidade+número+data de abertura) e
`.panel-body` (objeto). A cor do panel (panel-green/panel-yellow/...)
reflete o status, mas o texto confiável vem do cabeçalho.

Uso:
  python src/collectors/coletor_senac_pr.py --db-url postgresql://... --write-db
  python src/collectors/coletor_senac_pr.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.pr.senac.br/licitacoes/"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "SENAC-PR"
FONTE = "SENAC-PR"


def _parse_data(txt):
    if not txt:
        return None
    m = re.search(r"(\d{2})/(\d{2})/(\d{2,4})", txt)
    if not m:
        return None
    d, mth, y = m.groups()
    y = int(y)
    if y < 100:
        y += 2000
    try:
        return datetime.date(y, int(mth), int(d)).isoformat()
    except Exception:
        return None


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for panel in soup.select("div.panel"):
        heading = panel.select_one(".panel-heading")
        body_txt_el = panel.select_one(".panel-body .col-md-11")
        if not heading:
            continue
        titulo = heading.get_text(" ", strip=True)
        m_num = re.search(r"(PREGÃO\s*ELETRÔNICO|CONCORRÊNCIA|TOMADA\s*DE\s*PREÇOS|CONVITE|CHAMADA\s*PÚBLICA)\s*[Nn]?[ºo°.]?\s*([\d/]+)", titulo, re.I)
        m_data = re.search(r"Abertura:\s*([\d/]+)", titulo)
        # link específico e verificável: primeiro PDF estático de documento do processo
        # (não o link com querystring, que é um redirecionador interno do site)
        pdf_el = panel.select_one("a[href^='/licitacoes/Arquivos']")
        link = requests.compat.urljoin(BASE, pdf_el["href"]) if pdf_el and pdf_el.get("href") else BASE
        itens.append({
            "titulo": titulo,
            "modalidade": m_num.group(1).title() if m_num else "",
            "numero": m_num.group(2) if m_num else "",
            "objeto": body_txt_el.get_text(strip=True) if body_txt_el else "",
            "data_abertura": m_data.group(1) if m_data else "",
            "link": link,
        })
    return itens


def coletar(log=print):
    r = requests.get(BASE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    itens = parse_pagina(r.text)
    log(f"SENAC-PR: {len(itens)} processo(s) capturado(s) (página única).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "SENAC PR - Serviço Nacional de Aprendizagem Comercial do Paraná",
        "nome_padronizado": "SENAC PR",
        "uf": "PR",
        "municipio": "Curitiba",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or it.get("titulo") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"SENAC-PR|{it.get('numero') or it.get('titulo') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero") or it.get("titulo", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto") or it.get("titulo", ""),
            "modalidade": it.get("modalidade", ""),
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
    for c in contratos[:5]:
        print(" -", c["numero_processo"], "|", c["modalidade"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
