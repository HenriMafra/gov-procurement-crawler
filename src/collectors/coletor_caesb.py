# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: CAESB (Companhia de Saneamento Ambiental do
Distrito Federal), fora do PNCP.

Fonte: Portal de Compras Públicas (marketplace nacional privado,
`portaldecompraspublicas.com.br`), pra onde a CAESB migrou em 2025. API
pública real (achada via Playwright, sem autenticação):
  GET https://compras.api.portaldecompraspublicas.com.br/v2/licitacao/processos
      ?limitePagina=50&pagina=N&orgao=CAESB
Retorna paginação real (total/pageCount). Campo "resumo" é o objeto,
"urlReferencia" é o link verificado (relativo ao portal).

NOTA: essa mesma API/plataforma é usada por MUITOS outros órgãos no Brasil
(vi "Prefeitura Municipal de Porto Grande" nos resultados sem filtro) —
o parâmetro ?orgao= filtra por texto, então esse mesmo coletor pode ser
reaproveitado pra outras entidades do DF que também migrarem pra cá,
só trocando ORGAO_FILTRO.

Uso:
  python src/collectors/coletor_caesb.py --db-url postgresql://... --write-db
  python src/collectors/coletor_caesb.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

API = "https://compras.api.portaldecompraspublicas.com.br/v2/licitacao/processos"
PORTAL_BASE = "https://www.portaldecompraspublicas.com.br"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "CAESB"
FONTE = "CAESB"
ORGAO_FILTRO = "CAESB"


def coletar(log=print):
    itens, pagina = [], 1
    while True:
        r = requests.get(API, params={"limitePagina": 50, "pagina": pagina, "orgao": ORGAO_FILTRO},
                          headers=HEADERS, timeout=30)
        r.raise_for_status()
        d = r.json()
        rows = d.get("result", [])
        total = d.get("total", len(rows))
        itens.extend(rows)
        log(f"  página {pagina}: +{len(rows)} (total anunciado {total})")
        if not rows or len(itens) >= total:
            break
        pagina += 1
    log(f"CAESB: {len(itens)} licitação(ões) capturada(s) no total.")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "CAESB - Companhia de Saneamento Ambiental do Distrito Federal",
        "nome_padronizado": "CAESB",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        numero = it.get("numero") or str(it.get("codigoLicitacao") or "")
        objeto = it.get("resumo") or ""
        modalidade = (it.get("tipoLicitacao") or {}).get("tipoLicitacao") or ""
        url_ref = it.get("urlReferencia") or ""
        link = f"{PORTAL_BASE}/processos{url_ref}" if url_ref else PORTAL_BASE
        data_pub = (it.get("dataHoraPublicacao") or "")[:10] or None
        obj_hash = hashlib.md5(objeto.encode("utf-8")).hexdigest()[:8]
        contrato_key = f"CAESB|{numero}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": numero,
            "fonte": FONTE,
            "link_fonte": link,
            "objeto_original": objeto,
            "modalidade": modalidade,
            "data_assinatura": data_pub,
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
