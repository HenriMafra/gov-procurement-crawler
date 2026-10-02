# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: ABDI (Agência Brasileira de Desenvolvimento
Industrial), fora do PNCP.

Fonte: https://www.abdi.com.br/transparencia/aquisicao-de-bens-e-servicos/
WordPress/Elementor, accordion (`<details>`) com título "Modalidade nº X/Y
– Objeto" e link de download real (`?jet_download=HASH`, redireciona pro
PDF real). Cada item já é a dispensa/inexigibilidade/edital em si.

LIMITAÇÃO CONHECIDA: a página carrega só os ~10 itens mais recentes
estaticamente; o resto vem via botão "Carregar Mais" (AJAX JetEngine, não
mapeado ainda) — cobre só o mais recente por enquanto, não o histórico
completo. Rodar periodicamente já mantém os itens novos capturados.

Uso:
  python src/collectors/coletor_abdi.py --db-url postgresql://... --write-db
  python src/collectors/coletor_abdi.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.abdi.com.br/transparencia/aquisicao-de-bens-e-servicos/"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "ABDI"
FONTE = "ABDI"

TITULO_RE = re.compile(r"^(.*?nº\s*[\d/]+)\s*[–-]\s*(.*)$")
ANO_RE = re.compile(r"/(\d{4})\b")


def _ano_do_titulo(titulo):
    """Sem data explícita na página — o número do processo (ex.: "nº 005/2026")
    já traz o ano; usa 1º de janeiro daquele ano como data aproximada."""
    m = ANO_RE.search(titulo or "")
    return f"{m.group(1)}-01-01" if m else None


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for d in soup.select("details"):
        title_el = d.select_one(".e-n-accordion-item-title-text")
        link_el = d.select_one("a.jet-download")
        if not title_el:
            continue
        titulo = title_el.get_text(strip=True)
        m = TITULO_RE.match(titulo)
        numero_modalidade, objeto = (m.group(1), m.group(2)) if m else (titulo, "")
        itens.append({
            "titulo": numero_modalidade,
            "objeto": objeto,
            "link": link_el["href"] if link_el and link_el.get("href") else BASE,
        })
    return itens


def coletar(log=print):
    r = requests.get(BASE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    itens = parse_pagina(r.text)
    log(f"ABDI: {len(itens)} processo(s) capturado(s) (só os mais recentes — 'Carregar Mais' não mapeado).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "ABDI - Agência Brasileira de Desenvolvimento Industrial",
        "nome_padronizado": "ABDI",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Federal",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"ABDI|{it.get('titulo') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("titulo", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto", ""),
            "modalidade": re.sub(r"\s*nº.*$", "", it.get("titulo", ""), flags=re.I).strip(),
            "data_assinatura": _ano_do_titulo(it.get("titulo", "")),
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
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
