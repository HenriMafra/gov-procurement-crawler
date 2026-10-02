# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: NOVACAP (Companhia Urbanizadora da Nova
Capital do Brasil), fora do PNCP.

Fonte: https://app.novacap.df.gov.br/sislicitapublica/
Sistema próprio (AdminLTE/Laravel), HTML server-side. Dashboard em
`/sislicitapublica/` lista 13 modalidades com link `licitalisting/{id}`;
cada listagem tem TODOS os registros daquela modalidade numa página só
(sem paginação), com número/processo, objeto completo, datas de
abertura/expiração, valor estimado e link de detalhe/anexos verificado.

Uso:
  python src/collectors/coletor_novacap.py --db-url postgresql://... --write-db
  python src/collectors/coletor_novacap.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://app.novacap.df.gov.br/sislicitapublica"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "NOVACAP"
FONTE = "NOVACAP"
MODALIDADE_IDS = [1, 4, 5, 6, 7, 10, 11, 12, 13, 14, 15, 16, 17]


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


def _parse_valor(txt):
    if not txt:
        return 0.0
    txt = re.sub(r"[^\d,.-]", "", txt).replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return 0.0


def parse_pagina(html, modalidade_nome=""):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for tr in soup.select("tbody > tr"):
        numero_el = tr.select_one("td[data-title*='mero'] a")
        objeto_el = tr.select_one("td[data-title*='escri']")
        abertura_el = tr.select_one("td[data-title*='Data-hora']")
        expira_el = tr.select_one("td[data-title*='Data-expira']")
        valor_el = tr.select_one("td[data-title*='Custo']")
        if not numero_el:
            continue
        link = numero_el.get("href", BASE)
        numero = numero_el.get_text(strip=True).replace("→", "").strip()
        itens.append({
            "numero": numero,
            "objeto": objeto_el.get_text(strip=True) if objeto_el else "",
            "abertura": abertura_el.get_text(strip=True) if abertura_el else "",
            "expira": expira_el.get_text(strip=True) if expira_el else "",
            "valor": valor_el.get_text(strip=True) if valor_el else "",
            "link": link,
            "modalidade": modalidade_nome,
        })
    return itens


def coletar(log=print, sleep=0.5):
    sess = requests.Session()
    sess.headers.update(HEADERS)
    r = sess.get(BASE + "/", timeout=30, verify=False)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    nomes_modalidade = {}
    for card in soup.select("div.card"):
        header = card.select_one(".card-header")
        link = card.find_parent("a")
        if header and link and "licitalisting" in (link.get("href") or ""):
            mid = link["href"].rstrip("/").split("/")[-1]
            nomes_modalidade[mid] = header.get_text(strip=True)

    todos = []
    for mid in MODALIDADE_IDS:
        nome_mod = nomes_modalidade.get(str(mid), f"Modalidade {mid}")
        rr = sess.get(f"{BASE}/licitalisting/{mid}", timeout=30, verify=False)
        if rr.status_code != 200:
            log(f"  modalidade {mid} ({nome_mod}): HTTP {rr.status_code}, pulando")
            continue
        itens = parse_pagina(rr.text, modalidade_nome=nome_mod)
        todos.extend(itens)
        log(f"  modalidade {mid} ({nome_mod}): +{len(itens)}")
        time.sleep(sleep)
    log(f"NOVACAP: {len(todos)} licitação(ões) capturada(s) no total.")
    return todos


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "NOVACAP - Companhia Urbanizadora da Nova Capital do Brasil",
        "nome_padronizado": "NOVACAP",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"NOVACAP|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto", ""),
            "modalidade": it.get("modalidade", ""),
            "valor_total": _parse_valor(it.get("valor")),
            "inicio_vigencia": _parse_data(it.get("abertura")),
            "fim_vigencia": _parse_data(it.get("expira")),
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
        print(" -", c["numero_processo"], "|", c["modalidade"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
