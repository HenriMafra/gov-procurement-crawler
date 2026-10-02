# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: Metrô-DF (Companhia do Metropolitano do
Distrito Federal), fora do PNCP.

Fonte: https://metro.df.gov.br/licitacoes_data.json
Arquivo JSON estático (achado via Playwright — a página HTML carrega esse
JSON via fetch). Estrutura: {ano: {modalidade: [itens]}}, cada item com
título, lista "info" (linhas de texto com Objeto/datas/UASG/processo) e
lista "links" (PDFs reais — edital, esclarecimentos, atas, contratos).
Cobre histórico completo (2011-2026); filtramos 2021+ pra bater com o
escopo do restante do pipeline.

Uso:
  python src/collectors/coletor_metro_df.py --db-url postgresql://... --write-db
  python src/collectors/coletor_metro_df.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

DATA_URL = "https://metro.df.gov.br/licitacoes_data.json"
BASE = "https://metro.df.gov.br/"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "METRO-DF"
FONTE = "METRO-DF"
ANO_MIN = 2021


def _parse_data(txt):
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", txt or "")
    if not m:
        return None
    d, mth, y = m.groups()
    try:
        return datetime.date(int(y), int(mth), int(d)).isoformat()
    except Exception:
        return None


def coletar(log=print):
    r = requests.get(DATA_URL, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    dados = r.json()
    itens = []
    for ano_str, modalidades in dados.items():
        try:
            ano = int(ano_str)
        except Exception:
            continue
        if ano < ANO_MIN:
            continue
        for modalidade, lista in (modalidades or {}).items():
            for it in lista or []:
                info = it.get("info") or []
                objeto = ""
                data_pub = None
                for linha in info:
                    if linha.lower().startswith("objeto:"):
                        objeto = linha.split(":", 1)[1].strip()
                    elif "publica" in linha.lower():
                        data_pub = _parse_data(linha)
                links = it.get("links") or []
                link = None
                for l in links:
                    if l.get("text", "").lower() in ("edital", "aviso de licitação", "aviso de licitacao"):
                        link = l.get("localUrl") or l.get("url")
                        break
                if not link and links:
                    link = links[0].get("localUrl") or links[0].get("url")
                link_abs = (BASE + link) if link and not link.startswith("http") else (link or BASE)
                itens.append({
                    "titulo": it.get("title", ""),
                    "objeto": objeto,
                    "modalidade": modalidade,
                    "ano": ano,
                    "data_publicacao": data_pub,
                    "link": link_abs,
                })
    log(f"METRO-DF: {len(itens)} licitação(ões) capturada(s) ({ANO_MIN}-hoje).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "Metrô-DF - Companhia do Metropolitano do Distrito Federal",
        "nome_padronizado": "Metrô-DF",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or it.get("titulo") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"METRO-DF|{it.get('titulo') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("titulo", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto") or it.get("titulo", ""),
            "modalidade": it.get("modalidade", ""),
            "data_assinatura": it.get("data_publicacao") or f"{it['ano']}-01-01",
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
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["link_fonte"][:50])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
