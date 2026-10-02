# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: CIASC (Centro de Informática e Automação do
Estado de Santa Catarina), fora do PNCP.

Fonte: https://transparenciaempresas.sc.gov.br/ciasc/despesa/licitacoes-e-contratos/contratos
Portal Joomla FlexiContent, sem API, sem JS — HTML server-side, paginação
real via querystring ?start=N (10 registros por página, ~549 registros).

Cada contrato é um <div class="catalogitem">; campos em
<div class="flexi value field_<nome>">. Sem CNPJ do fornecedor exposto no
HTML — forn_key cai para o nome normalizado (mesmo padrão de fallback do
resto do pipeline, ver atlas_db.py).

Uso:
  python src/collectors/coletor_ciasc_sc.py --db-url postgresql://... --write-db
  python src/collectors/coletor_ciasc_sc.py --dry-run   (só imprime o que capturou)
"""
import os, sys, re, time, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://transparenciaempresas.sc.gov.br/ciasc/despesa/licitacoes-e-contratos/contratos"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "CIASC-SC"  # órgão fixo: todos os contratos aqui são da própria CIASC como contratante
FONTE = "CIASC-SC"

FIELD_MAP = {
    "numero-do-processo": "numero_processo",
    "numero-do-contrato": "numero_contrato",
    "numero-do-edital": "numero_edital",
    "modalidade": "modalidade",
    "empresa-contratada": "fornecedor",
    "data-da-assinatura": "data_assinatura",
    "inicio-da-vigencia": "inicio_vigencia",
    "termino-da-vigencia": "fim_vigencia",
    "valor": "valor_total",
    "valor-do-aditivo": "valor_aditivo",
    "objeto": "objeto",
}


def _parse_valor(txt):
    if not txt:
        return 0.0
    txt = re.sub(r"[^\d,.-]", "", txt).replace(".", "").replace(",", ".")
    try:
        return float(txt)
    except Exception:
        return 0.0


def _valor_final(valor_txt, aditivo_txt):
    """CIASC repete o mesmo valor no campo 'aditivo' quando não há aditivo real —
    somar sempre dobrava o valor. Só soma se for um valor genuinamente diferente."""
    v = _parse_valor(valor_txt)
    a = _parse_valor(aditivo_txt)
    return v + a if (a and abs(a - v) > 0.01) else v


def _parse_data(txt):
    if not txt:
        return None
    txt = txt.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.datetime.strptime(txt, fmt).date().isoformat()
        except Exception:
            pass
    return None


def _norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip().upper()


DOWNLOAD_RE = re.compile(r"window\.open\('([^']+)'")


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for card in soup.select("div.catalogitem"):
        d = {}
        for slug, key in FIELD_MAP.items():
            el = card.select_one(f"div.flexi.value.field_{slug}")
            d[key] = el.get_text(strip=True) if el else ""
        if not d.get("numero_contrato") and not d.get("objeto"):
            continue
        # link específico e verificável: URL real de download do anexo (não a página genérica)
        btn = card.select_one("button.fcfile_downloadFile")
        if btn and btn.get("onclick"):
            m = DOWNLOAD_RE.search(btn["onclick"])
            d["link"] = ("https://transparenciaempresas.sc.gov.br" + m.group(1)) if m else BASE
        else:
            d["link"] = BASE
        itens.append(d)
    return itens


def total_paginas(html):
    m = re.search(r"P[áa]gina\s+\d+\s+de\s+(\d+)", html)
    if m:
        return int(m.group(1))
    m = re.search(r"Resultados\s+\d+\s*-\s*\d+\s+de\s+(\d+)", html)
    if m:
        return (int(m.group(1)) + 9) // 10
    return 1


def coletar(max_paginas=None, sleep=1.0, log=print):
    sess = requests.Session()
    sess.headers.update(HEADERS)
    r = sess.get(BASE, timeout=30)
    r.raise_for_status()
    tot = total_paginas(r.text)
    if max_paginas:
        tot = min(tot, max_paginas)
    log(f"CIASC-SC: {tot} página(s) a coletar (10 registros/página).")
    todos = parse_pagina(r.text)
    for p in range(1, tot):
        start = p * 10
        time.sleep(sleep)
        rr = sess.get(BASE, params={"start": start}, timeout=30)
        rr.raise_for_status()
        itens = parse_pagina(rr.text)
        if not itens:
            log(f"  página start={start}: vazia, parando.")
            break
        todos.extend(itens)
        log(f"  página start={start}: +{len(itens)} (total {len(todos)})")
    return todos


def para_registros_db(itens):
    """Converte para o formato de upsert do AtlasDB (orgaos/fornecedores/contratos)."""
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "CIASC - Centro de Informática e Automação do Estado de Santa Catarina",
        "nome_padronizado": "CIASC (SC)",
        "uf": "SC",
        "municipio": "Florianópolis",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    fornecedores, contratos = {}, []
    for it in itens:
        forn_nome = it.get("fornecedor") or ""
        forn_key = _norm(forn_nome) or "FORNECEDOR-NAO-IDENTIFICADO-CIASC"
        if forn_key not in fornecedores:
            fornecedores[forn_key] = {"forn_key": forn_key, "nome_fornecedor": forn_nome, "nome_padronizado": forn_nome}
        import hashlib
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = (f"CIASC-SC|{it.get('numero_contrato') or '-'}"
                        f"|{it.get('numero_processo') or '-'}|{obj_hash}")
        contratos.append({
            "contrato_key": contrato_key,
            "numero_contrato": it.get("numero_contrato", ""),
            "numero_processo": it.get("numero_processo", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "_forn_key": forn_key,
            "objeto_original": it.get("objeto", ""),
            "valor_total": _valor_final(it.get("valor_total"), it.get("valor_aditivo")),
            "data_assinatura": _parse_data(it.get("data_assinatura")),
            "inicio_vigencia": _parse_data(it.get("inicio_vigencia")),
            "fim_vigencia": _parse_data(it.get("fim_vigencia")),
            "modalidade": it.get("modalidade", ""),
        })
    return orgao, list(fornecedores.values()), contratos


def gravar_db(db_url, orgao, fornecedores, contratos, log=print):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
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
    log(f"-> gravado no banco: 1 órgão, {len(fornecedores)} fornecedores, {n} contratos.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-paginas", type=int, default=None)
    args = ap.parse_args()

    itens = coletar(max_paginas=args.max_paginas)
    orgao, fornecedores, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} contratos, {len(fornecedores)} fornecedores únicos.")
    for c in contratos[:3]:
        print(" -", c["numero_contrato"], "|", c["objeto_original"][:70], "|", c["valor_total"])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, fornecedores, contratos)


if __name__ == "__main__":
    main()
