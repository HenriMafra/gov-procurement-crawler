# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: SESC SC, fora do PNCP.

Fonte: https://www.sesc-sc.com.br/sobre-o-sesc/licitacoes
HTML 100% server-side. Cada edital é um <span id="lic_NNNNN" class="dark
aba_licitacao"> com título "NÚMERO | OBJETO | MODALIDADE | STATUS", seguido
de um <div class="open-close"> irmão com datas/valor/PDFs. Não há SPA nem
postback — o "modal" visto na primeira varredura é só um formulário de
"acompanhar licitação por e-mail", não a fonte dos dados.

Uso:
  python src/collectors/coletor_sesc_sc.py --db-url postgresql://... --write-db
  python src/collectors/coletor_sesc_sc.py --dry-run
"""
import os, sys, re, hashlib, argparse, datetime
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.sesc-sc.com.br/sobre-o-sesc/licitacoes"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)",
           "Accept-Language": "pt-BR,pt;q=0.9"}
ORGAO_KEY = "SESC-SC"
FONTE = "SESC-SC"


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


def parse_pagina(html):
    soup = BeautifulSoup(html, "html.parser")
    itens = []
    for span in soup.select("span.aba_licitacao"):
        titulo = span.get_text(" ", strip=True)
        partes = [p.strip() for p in titulo.split("|")]
        if len(partes) < 3:
            continue
        numero, objeto, modalidade = partes[0], partes[1], partes[2]
        status = partes[3] if len(partes) > 3 else ""
        detalhe = span.find_next_sibling("div", class_="open-close")
        det_txt = detalhe.get_text(" ", strip=True) if detalhe else ""
        m_abe = re.search(r"Data abertura:\s*([\d/]+)", det_txt)
        m_val = re.search(r"Valor Estimado:\s*R\$\s*([\d.,]*)", det_txt)
        # link específico e verificável: PDF do edital (não a página de listagem)
        pdf_el = detalhe.select_one("a[href$='.pdf']") if detalhe else None
        link = requests.compat.urljoin(BASE, pdf_el["href"]) if pdf_el and pdf_el.get("href") else BASE
        itens.append({
            "numero": numero, "objeto": objeto, "modalidade": modalidade, "status": status,
            "data_abertura": m_abe.group(1) if m_abe else "",
            "valor": m_val.group(1) if m_val else "",
            "link": link,
        })
    return itens


def coletar(log=print):
    r = requests.get(BASE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    itens = parse_pagina(r.text)
    log(f"SESC-SC: {len(itens)} edital(is) capturado(s).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "SESC SC - Serviço Social do Comércio de Santa Catarina",
        "nome_padronizado": "SESC SC",
        "uf": "SC",
        "municipio": "Florianópolis",
        "poder": "Executivo",
        "esfera": "Estadual",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"SESC-SC|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or BASE,
            "objeto_original": it.get("objeto", ""),
            "modalidade": it.get("modalidade", ""),
            "situacao_pncp": it.get("status", ""),
            "valor_total": _parse_valor(it.get("valor")),
            "inicio_vigencia": _parse_data(it.get("data_abertura")),
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
    log(f"-> gravado no banco: 1 órgão, {n} editais.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--write-db", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    itens = coletar()
    orgao, contratos = para_registros_db(itens)
    print(f"\nTotal capturado: {len(contratos)} editais.")
    for c in contratos[:5]:
        print(" -", c["numero_processo"], "|", c["modalidade"], "|", c["objeto_original"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
