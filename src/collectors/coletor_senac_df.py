# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: SENAC DF, fora do PNCP.

Fonte: https://www.df.senac.br/wp-json/wp/v2/licitacoes
WordPress com post-type customizado "licitacoes" — API REST nativa, sem
scraping. Título já vem como "PE NNNNN/AAAA – Objeto completo". Paginação
via ?page=N (padrão WP REST), total real informado no header X-WP-Total.

Uso:
  python src/collectors/coletor_senac_df.py --db-url postgresql://... --write-db
  python src/collectors/coletor_senac_df.py --dry-run
"""
import os, sys, re, hashlib, argparse, html as html_lib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

BASE = "https://www.df.senac.br/wp-json/wp/v2/licitacoes"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "SENAC-DF"
FONTE = "SENAC-DF"

TITULO_RE = re.compile(r"^(PE\s*[\d/]+)\s*[–-]\s*(.*)$", re.I)


def coletar(log=print):
    itens, page = [], 1
    while True:
        r = requests.get(BASE, params={"per_page": 50, "page": page}, headers=HEADERS, timeout=30, verify=False)
        if r.status_code == 400:  # página além do total -> WP responde 400 rest_post_invalid_page_number
            break
        r.raise_for_status()
        rows = r.json()
        if not rows:
            break
        total = r.headers.get("X-WP-Total")
        itens.extend(rows)
        log(f"  página {page}: +{len(rows)} (total anunciado {total})")
        if len(rows) < 50:
            break
        page += 1
    log(f"SENAC-DF: {len(itens)} licitação(ões) capturada(s).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "SENAC DF - Serviço Nacional de Aprendizagem Comercial do Distrito Federal",
        "nome_padronizado": "SENAC DF",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        titulo = html_lib.unescape(it.get("title", {}).get("rendered", "")).strip()
        if not titulo or "rascunho" in titulo.lower():
            continue
        m = TITULO_RE.match(titulo)
        numero, objeto = (m.group(1), m.group(2)) if m else (titulo, "")
        link = it.get("link") or BASE
        obj_hash = hashlib.md5(objeto.encode("utf-8")).hexdigest()[:8]
        contrato_key = f"SENAC-DF|{numero}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": numero,
            "fonte": FONTE,
            "link_fonte": link,
            "objeto_original": objeto,
            "modalidade": "Pregão Eletrônico" if numero.upper().startswith("PE") else "",
            "data_assinatura": (it.get("date") or "")[:10] or None,
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
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["data_assinatura"])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
