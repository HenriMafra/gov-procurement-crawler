# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: SESC GO, fora do PNCP.

Fonte: https://www3.sescgo.com.br/licitacoes
HTML server-side, TODAS as ~2000 licitações numa página só (14MB, sem
paginação). Cada licitação é um `div.card-body > div.row` com campos
Processo/Abertura/Modalidade/Situação e uma lista de documentos (PDFs) em
`a.item[href^=.../licitacao/download/ID]` — usa o primeiro (Edital) como
link_fonte verificado.

LIMITAÇÃO CONHECIDA: a listagem NÃO expõe o objeto/descrição da licitação
(só existe dentro do PDF) — sem texto de objeto, o classificador de TI não
tem o que analisar, então estes registros ficam em `contratos` (buscáveis
por processo/modalidade, com link verificado) mas não geram `oportunidades`
automaticamente.

Uso:
  python src/collectors/coletor_sesc_go.py --db-url postgresql://... --write-db
  python src/collectors/coletor_sesc_go.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www3.sescgo.com.br/licitacoes"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "SESC-GO"
FONTE = "SESC-GO"


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


def parse_pagina(html, log=print):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for label in soup.select("span.lista-licitacoes__label"):
        if "Processo" not in label.get_text():
            continue
        row = label.find_parent("div", class_="row")
        if not row:
            continue
        campos = {}
        for lbl in row.select("span.lista-licitacoes__label"):
            key = lbl.get_text(strip=True)
            desc = lbl.find_next_sibling("span", class_="lista-licitacoes__descricao")
            campos[key] = desc.get_text(strip=True) if desc else ""
        primeiro_doc = row.select_one("a.item[href]")
        link = primeiro_doc["href"] if primeiro_doc else BASE
        itens.append({
            "processo": campos.get("Processo n°", ""),
            "abertura": campos.get("Abertura", ""),
            "modalidade": campos.get("Modalidade", ""),
            "situacao": campos.get("Situação", ""),
            "link": link,
        })
    log(f"SESC-GO: {len(itens)} processo(s) capturado(s) (página única).")
    return itens


def coletar(log=print):
    r = requests.get(BASE, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return parse_pagina(r.text, log=log)


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "SESC GO - Serviço Social do Comércio de Goiás",
        "nome_padronizado": "SESC GO",
        "uf": "GO",
        "municipio": "Goiânia",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        if not it.get("processo"):
            continue
        obj_hash = hashlib.md5(it.get("link", "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"SESC-GO|{it['processo']}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it["processo"],
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": "",  # não exposto na listagem — só dentro do PDF (ver link_fonte)
            "modalidade": it.get("modalidade", ""),
            "situacao_pncp": it.get("situacao", ""),
            "inicio_vigencia": _parse_data(it.get("abertura")),
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
    log(f"-> gravado no banco: 1 órgão, {n} processos (sem objeto — não classificáveis por TI automaticamente).")


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
        print(" -", c["numero_processo"], "|", c["modalidade"], "|", c["situacao_pncp"], "|", c["link_fonte"])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
