# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: EMATER-DF (Empresa de Assistência Técnica e
Extensão Rural do Distrito Federal), fora do PNCP.

Fonte: site institucional em Liferay (`emater.df.gov.br`), mesma plataforma
compartilhada de NOVACAP/TCB/CEASA/FUNAP. Diferente do TCB (que tem uma
página por ano), aqui TODOS os avisos de licitação (2020-hoje) vivem numa
única página longa (`/avisos-de-licitacao`) como uma sequência linear de
parágrafos: um cabeçalho "AVISO DE LICITAÇÃO PREGÃO ELETRÔNICO Nº NN/AAAA",
seguido de um parágrafo "Objeto: ..." e parágrafos com links de publicação
(DODF/DOU) e do próprio edital (`documents/d/emater/...`).

Uso:
  python src/collectors/coletor_emater_df.py --db-url postgresql://... --write-db
  python src/collectors/coletor_emater_df.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.emater.df.gov.br"
URL = "https://www.emater.df.gov.br/avisos-de-licitacao"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "EMATER-DF"
FONTE = "EMATER-DF"

NUM_RE = re.compile(r"PREG[ÃA]O\s+ELETR[ÔO]NICO\s+N[º°o]?\s*([\d]+/\d{4})", re.I)
OBJETO_RE = re.compile(r"Objeto:\s*(.+)", re.I)
IGNORAR_LINK = re.compile(r"gov\.br/compras|sei\.df\.gov\.br/sei/licitacoes@|mailto:", re.I)


def _abs_link(href):
    if not href:
        return URL
    href = href if href.startswith("http") else BASE + href
    # o site às vezes gera hrefs absolutos sem "www.", que falha resolução
    # de DNS separadamente do domínio com "www." — normaliza sempre.
    return href.replace("https://emater.df.gov.br", "https://www.emater.df.gov.br")


def coletar(log=print):
    r = requests.get(URL, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    art = soup.select_one("div.journal-content-article")
    if not art:
        log("EMATER-DF: artigo não encontrado na página.")
        return []

    blocos = {}
    cur = None
    for p in art.find_all("p"):
        txt = p.get_text(" ", strip=True)
        m = NUM_RE.search(txt)
        if m and "aviso de licita" in txt.lower():
            cur = m.group(1)
            if cur not in blocos:
                blocos[cur] = {"numero": cur, "objeto": "", "links": []}
            continue
        if not cur:
            continue
        om = OBJETO_RE.search(txt)
        if om and not blocos[cur]["objeto"]:
            blocos[cur]["objeto"] = om.group(1).strip()[:2000]
        for a in p.find_all("a", href=True):
            href = a["href"]
            # só links do repositório de documentos Liferay (`/documents/`)
            # são editais/publicações reais — descarta citações legais,
            # e-mails e páginas de navegação interna que aparecem soltos
            # no meio dos parágrafos.
            if IGNORAR_LINK.search(href) or "/documents/" not in href:
                continue
            blocos[cur]["links"].append((a.get_text(" ", strip=True), href))

    itens = []
    for numero, b in blocos.items():
        links = b["links"]
        link = next((h for t, h in links if "edital" in t.lower() or "edital" in h.lower()), None) \
            or (links[0][1] if links else None)
        if not link:
            continue
        ano = numero.split("/")[-1]
        itens.append({
            "numero": numero,
            "objeto": b["objeto"] or f"Pregão Eletrônico Nº {numero} - EMATER-DF (ver edital no link)",
            "ano": ano,
            "link": _abs_link(link),
        })
    log(f"EMATER-DF: {len(itens)} pregão(ões) capturado(s) no total.")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "EMATER-DF - Empresa de Assistência Técnica e Extensão Rural do Distrito Federal",
        "nome_padronizado": "EMATER-DF",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"EMATER-DF|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or URL,
            "objeto_original": it.get("objeto", ""),
            "modalidade": "Pregão Eletrônico",
            "data_assinatura": f"{it['ano']}-01-01",
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
    log(f"-> gravado no banco: 1 órgão, {n} pregões.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = coletar()
    orgao, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} pregões.")
    for c in contratos[:8]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["link_fonte"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
