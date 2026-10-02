# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: Pregão Online Banrisul, fora do PNCP.

Fonte: https://pregaobanrisul.com.br/editais/pesquisa.json (POST, DataTables
server-side). A plataforma é MULTI-ENTIDADE (dezenas de municípios do RS
também publicam aqui), mas este coletor filtra por `tradeOffice=9807`
(BANCO DO ESTADO DO RIO GRANDE DO SUL S.A. - BANRISUL) — o único órgão
dessa lista que está no escopo original de 226 clientes ENTERPRISECORE. BRDE usa
uma plataforma DIFERENTE ("Licitações-e" do BB, ainda não coletada) —
não confundir os dois sistemas de nome parecido.

Exige filtro obrigatório: janela de publicação de até 12 meses por
requisição (ou número de edital/processo) — paginamos por ano-calendário
de 2021 até hoje, como o pipeline PNCP faz com "ultimos_anos".

Uso:
  python src/collectors/coletor_pregao_banrisul.py --db-url postgresql://... --write-db
  python src/collectors/coletor_pregao_banrisul.py --dry-run --ano-inicio 2025
"""
import os, sys, re, hashlib, argparse, datetime, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

BASE_HTML = "https://pregaobanrisul.com.br/editais/pesquisar"
BASE_API = "https://pregaobanrisul.com.br/editais/pesquisa.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)",
           "X-Requested-With": "XMLHttpRequest"}
FONTE = "PREGAO-BANRISUL"
PAGE_SIZE = 100
TRADE_OFFICE_BANRISUL = "9807"


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


def _ms_to_date(ms):
    if not ms:
        return None
    try:
        return datetime.datetime.utcfromtimestamp(ms / 1000).date().isoformat()
    except Exception:
        return None


def coletar_janela(sess, dt_ini, dt_fim, log=print):
    itens, start = [], 0
    while True:
        r = sess.post(BASE_API, data={
            "draw": 1, "start": start, "length": PAGE_SIZE, "status": "", "description": "",
            "tradeOffice": TRADE_OFFICE_BANRISUL,
            "publicationStartDate": dt_ini, "publicationEndDate": dt_fim,
        }, timeout=30)
        r.raise_for_status()
        d = r.json()
        rows = d.get("data", [])
        total = d.get("iTotalDisplayRecords", len(rows))
        itens.extend(rows)
        log(f"  janela {dt_ini}-{dt_fim}: start={start} +{len(rows)} (total janela {total})")
        start += len(rows)  # servidor ignora o "length" pedido e devolve um tamanho fixo próprio
        if not rows or start >= total:
            break
        time.sleep(0.5)
    return itens


def coletar(ano_inicio=2021, log=print):
    sess = requests.Session()
    sess.headers.update(HEADERS)
    sess.get(BASE_HTML, timeout=30)  # inicializa sessão/cookies exigidos pela API
    hoje = datetime.date.today()
    todos = []
    for ano in range(hoje.year, ano_inicio - 1, -1):
        ini = f"01/01/{ano}"
        fim = hoje.strftime("%d/%m/%Y") if ano == hoje.year else f"31/12/{ano}"
        log(f"Coletando ano {ano} ({ini} a {fim})...")
        todos.extend(coletar_janela(sess, ini, fim, log=log))
    log(f"PREGAO-BANRISUL: {len(todos)} edital(is) capturado(s) no total ({ano_inicio}-{hoje.year}).")
    return todos


def para_registros_db(itens):
    orgaos, contratos = {}, []
    for it in itens:
        nome_org = it.get("tradeOffice") or "Órgão não identificado (Pregão Banrisul)"
        ok = _norm(nome_org)
        if ok not in orgaos:
            orgaos[ok] = {
                "orgao_key": f"PREGAO-BANRISUL|{ok}",
                "nome_orgao": nome_org, "nome_padronizado": nome_org,
                "uf": "RS", "poder": "Executivo", "esfera": "Municipal",
                "fonte_primeira_ocorrencia": FONTE,
            }
        edital = it.get("issuanceNumber") or ""
        simpl = it.get("simplifiedIssuanceNumber") or ""
        link = f"https://pregaobanrisul.com.br/editais/{simpl}/{it.get('id')}" if simpl and it.get("id") else BASE_HTML
        obj_hash = hashlib.md5((it.get("description") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"{FONTE}|{edital or it.get('id')}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_contrato": edital,
            "numero_processo": it.get("processNumber", ""),
            "fonte": FONTE,
            "link_fonte": link,
            "_orgao_key": ok,
            "objeto_original": it.get("description", ""),
            "modalidade": it.get("biddingTypeName", ""),
            "data_assinatura": _ms_to_date(it.get("publishDate")),
            "inicio_vigencia": _ms_to_date(it.get("startDate")),
        })
    return list(orgaos.values()), contratos


def gravar_db(db_url, orgaos, contratos, log=print):
    from atlas_db import AtlasDB
    db = AtlasDB(db_url)
    orgao_ids = db.batch_upsert("orgaos", "orgao_key", orgaos, touch=True)  # {orgao_key: id}
    for c in contratos:
        ok = c.pop("_orgao_key")  # nome normalizado, SEM o prefixo "FONTE|"
        c["orgao_id"] = orgao_ids.get(f"{FONTE}|{ok}")
    db.batch_upsert("contratos", "contrato_key", contratos, touch=True)
    db.commit()
    db.close()
    log(f"-> gravado no banco: {len(orgaos)} órgãos, {len(contratos)} editais.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ano-inicio", type=int, default=2021)
    args = ap.parse_args()

    itens = coletar(ano_inicio=args.ano_inicio)
    orgaos, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} editais, {len(orgaos)} órgãos distintos.")
    for c in contratos[:5]:
        print(" -", c["numero_contrato"], "|", c["modalidade"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgaos, contratos)


if __name__ == "__main__":
    main()
