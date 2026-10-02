# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: CODHAB-DF (Companhia de Desenvolvimento
Habitacional do Distrito Federal), fora do PNCP.

Fonte: CMS Strapi próprio, `codhabservice.codhab.df.gov.br/cms/api/paginas/{id}`.
A página de Pregões Eletrônicos (`pagina/38`) lista uma sub-página por ano
(2015-2026); cada sub-página tem um bloco de texto rico por processo, com
"Pregão Eletrônico Nº NNNNN/AAAA - objeto" seguido de link real do PDF do
Edital. Cobre 2021-2026 (IDs de página já mapeados manualmente).

Uso:
  python src/collectors/coletor_codhab.py --db-url postgresql://... --write-db
  python src/collectors/coletor_codhab.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

API_BASE = "https://codhabservice.codhab.df.gov.br/cms/api/paginas/{}?populate=*"
BASE = "https://www.codhab.df.gov.br/pagina/38"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "CODHAB-DF"
FONTE = "CODHAB-DF"

# Pregão Eletrônico por ano -> id da página no CMS (achado navegando pagina/38)
ANOS_PAGINA_ID = {2021: 378, 2022: 395, 2023: 427, 2024: 446, 2025: 485, 2026: 500}

ITEM_RE = re.compile(r"N[ºo°]\s*([\d/]+)\s*-\s*(.*)", re.I)


def _buscar_pagina(pid):
    r = requests.get(API_BASE.format(pid), timeout=30, headers=HEADERS, verify=False)
    r.raise_for_status()
    d = r.json()
    conteudo = d.get("data", {}).get("attributes", {}).get("Conteudo")
    if isinstance(conteudo, dict):
        return conteudo.get("conteudo", "")
    return conteudo or ""


def parse_conteudo(html, ano):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    strongs = soup.find_all("strong")
    for st in strongs:
        txt = st.get_text(" ", strip=True)
        m = ITEM_RE.search(txt)
        if not m:
            continue
        numero, objeto_inicio = m.group(1), m.group(2)
        # objeto pode continuar no <span> irmão (mesmo <li>/<p>) após o <strong>
        parent = st.find_parent(["li", "p"]) or st.parent
        objeto_completo = parent.get_text(" ", strip=True)
        objeto_completo = re.sub(r"^.*?N[ºo°]\s*[\d/]+\s*-\s*", "", objeto_completo, flags=re.I).strip()
        # primeiro PDF de edital logo depois deste bloco
        link = None
        nxt = parent.find_next(["p", "a"])
        hops = 0
        while nxt and hops < 6:
            a = nxt.find("a", href=True) if nxt.name != "a" else nxt
            if a and a.get("href", "").lower().endswith(".pdf"):
                link = a["href"]
                break
            nxt = nxt.find_next(["p", "a"])
            hops += 1
        itens.append({
            "numero": numero.strip(),
            "objeto": objeto_completo or objeto_inicio,
            "ano": ano,
            "link": link or BASE,
        })
    return itens


def coletar(log=print):
    todos = []
    for ano, pid in sorted(ANOS_PAGINA_ID.items()):
        try:
            conteudo = _buscar_pagina(pid)
            itens = parse_conteudo(conteudo, ano)
            todos.extend(itens)
            log(f"  {ano} (pagina {pid}): +{len(itens)}")
        except Exception as e:
            log(f"  {ano}: falhou ({e})")
    log(f"CODHAB-DF: {len(todos)} pregão(ões) capturado(s) no total (2021-2026).")
    return todos


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "CODHAB-DF - Companhia de Desenvolvimento Habitacional do Distrito Federal",
        "nome_padronizado": "CODHAB-DF",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"CODHAB-DF|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
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
    for c in contratos[:5]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["link_fonte"][:50])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
