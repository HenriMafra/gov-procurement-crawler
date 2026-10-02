# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: EBC (Empresa Brasil de Comunicação), fora do PNCP.

Fonte: https://acessoainformacao.ebc.com.br/licitacoes-e-contratos/licitacoes
Site em Plone CMS com plone.restapi ATIVO e público — API REST JSON completa,
sem necessidade de scraping HTML. Endpoint de busca:
  .../licitacoes/@search?portal_type=licitacao&b_size=50
Cada item da busca só tem título; os campos completos (objeto, valor, edital,
vencedor/CNPJ, situação) vêm ao consultar o @id de cada item individualmente.

Uso:
  python src/collectors/coletor_ebc.py --db-url postgresql://... --write-db
  python src/collectors/coletor_ebc.py --dry-run
"""
import os, sys, re, hashlib, argparse, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests

BASE = "https://acessoainformacao.ebc.com.br/licitacoes-e-contratos/licitacoes"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)",
           "Accept": "application/json"}
ORGAO_KEY = "EBC"
FONTE = "EBC"

CNPJ_RE = re.compile(r"CNPJ:?\s*([\d./-]{14,18})")


def _rich(field):
    if isinstance(field, dict):
        txt = field.get("data", "")
        return re.sub(r"<[^>]+>", " ", txt).strip()
    return field or ""


def _parse_valor(txt):
    """Campos valor_estimado/valor_adjudicado da API do EBC vêm em DOIS formatos
    misturados dependendo do registro: BR ("1.381.245,36", ponto=milhar,
    vírgula=decimal) e numérico puro ("R$3044949.31", ponto já é decimal).
    Detecta pela presença de vírgula — tratar tudo como BR inflava ~100x os
    registros no formato puro (ponto decimal virava separador de milhar)."""
    if not txt:
        return 0.0
    txt = re.sub(r"[^\d,.-]", "", str(txt))
    if not txt:
        return 0.0
    if "," in txt:
        txt = txt.replace(".", "").replace(",", ".")
    else:
        partes = txt.split(".")
        if len(partes) > 2:
            txt = "".join(partes[:-1]) + "." + partes[-1]
    try:
        return float(txt)
    except Exception:
        return 0.0


def listar_ids(sess, log=print):
    ids, b_start, b_size = [], 0, 50
    while True:
        r = sess.get(f"{BASE}/@search", params={"portal_type": "licitacao", "b_start": b_start, "b_size": b_size}, timeout=30)
        r.raise_for_status()
        d = r.json()
        items = d.get("items", [])
        ids.extend(it["@id"] for it in items if it.get("@type") == "licitacao")
        total = d.get("items_total", len(ids))
        log(f"EBC: listagem b_start={b_start} — {len(items)} item(ns) (total anunciado {total}).")
        if b_start + b_size >= total or not items:
            break
        b_start += b_size
    return ids


def detalhar(sess, item_id, sleep=0.3):
    time.sleep(sleep)
    r = sess.get(item_id, timeout=30)
    r.raise_for_status()
    return r.json()


def coletar(log=print):
    sess = requests.Session()
    sess.headers.update(HEADERS)
    ids = listar_ids(sess, log=log)
    itens = []
    for i, item_id in enumerate(ids, 1):
        try:
            d = detalhar(sess, item_id)
        except Exception as e:
            log(f"  aviso: falhou detalhe de {item_id}: {e}")
            continue
        vencedores_txt = d.get("vencedores") or ""
        m_cnpj = CNPJ_RE.search(vencedores_txt)
        itens.append({
            "titulo": d.get("title", ""),
            "edital": d.get("edital", ""),
            "ano": d.get("ano"),
            "objeto": _rich(d.get("objeto")),
            "situacao": (d.get("situacao") or {}).get("title", ""),
            "valor_estimado": d.get("valor_estimado", ""),
            "valor_adjudicado": d.get("valor_adjudicado", ""),
            "vencedor_nome": vencedores_txt.split(",")[0].strip() if vencedores_txt else "",
            "vencedor_cnpj": m_cnpj.group(1) if m_cnpj else "",
            "data": d.get("data", ""),
            "link": d.get("@id", BASE),
        })
        if i % 10 == 0:
            log(f"  detalhado {i}/{len(ids)}")
    log(f"EBC: {len(itens)} licitação(ões) com detalhe completo.")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "EBC - Empresa Brasil de Comunicação",
        "nome_padronizado": "EBC",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Federal",
        "fonte_primeira_ocorrencia": FONTE,
    }
    fornecedores, contratos = {}, []
    for it in itens:
        forn_nome = it.get("vencedor_nome") or ""
        forn_key = it.get("vencedor_cnpj") or (re.sub(r"\s+", " ", forn_nome).strip().upper() or None)
        if forn_key and forn_key not in fornecedores:
            fornecedores[forn_key] = {"forn_key": forn_key, "nome_fornecedor": forn_nome, "cnpj_fornecedor": it.get("vencedor_cnpj") or None}
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"EBC|{it.get('edital') or it.get('titulo') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("titulo", ""),
            "numero_contrato": it.get("edital", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link", BASE),
            "objeto_original": it.get("objeto", ""),
            "situacao_pncp": it.get("situacao", ""),
            "valor_total": _parse_valor(it.get("valor_adjudicado") or it.get("valor_estimado")),
            "data_assinatura": it.get("data") or None,
            "_forn_key": forn_key,
        })
    return orgao, list(fornecedores.values()), contratos


def gravar_db(db_url, orgao, fornecedores, contratos, log=print):
    from atlas_db import AtlasDB
    db = AtlasDB(db_url)
    orgao_id = db.upsert_orgao(orgao)
    forn_ids = {f["forn_key"]: db.upsert_fornecedor(f) for f in fornecedores}
    n = 0
    for c in contratos:
        forn_key = c.pop("_forn_key")
        c["orgao_id"] = orgao_id
        c["fornecedor_id"] = forn_ids.get(forn_key)
        db.upsert_contrato(c)
        n += 1
    db.commit()
    db.close()
    log(f"-> gravado no banco: 1 órgão, {len(fornecedores)} fornecedores, {n} licitações.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = coletar()
    orgao, fornecedores, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} licitações, {len(fornecedores)} fornecedores.")
    for c in contratos[:5]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["valor_total"])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, fornecedores, contratos)


if __name__ == "__main__":
    main()
