# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: CEASA-DF (Centrais de Abastecimento do
Distrito Federal), fora do PNCP.

Fonte: site institucional em Liferay (`ceasa.df.gov.br`), mesma plataforma
compartilhada de NOVACAP/TCB/FUNAP. Diferente do TCB/EMATER-DF, aqui o
conteúdo é renderizado 100% client-side (JS) — `requests`/BeautifulSoup
não veem nada, precisa de um browser real (Playwright, headless Chromium).
Cada ano tem uma página-índice (`/pregoes-eletronicos-AAAA`) que lista
links para sub-páginas individuais por pregão; cada sub-página tem o
objeto completo em texto e os PDFs reais (edital, aviso DODF, anexos)
no repositório de documentos Liferay (`/documents/d/ceasa/...`).

Requer Playwright com Chromium instalado (`playwright install chromium`).

Uso:
  python src/collectors/coletor_ceasa_df.py --db-url postgresql://... --write-db
  python src/collectors/coletor_ceasa_df.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from playwright.sync_api import sync_playwright

BASE = "https://www.ceasa.df.gov.br"
ORGAO_KEY = "CEASA-DF"
FONTE = "CEASA-DF"

ANOS_URLS = {
    2021: f"{BASE}/pregoes-eletronicos-2021",
    2022: f"{BASE}/pregoes-eletronicos-2022",
    2023: f"{BASE}/pregao-eletronico-2023",
    2024: f"{BASE}/pregoes-eletronicos-2024",
    2025: f"{BASE}/pregoes-eletronicos-2025",
    2026: f"{BASE}/preg%C3%B5es-eletr%C3%B4nicos-2026",
}

NUM_RE = re.compile(r"N[ºo°.]*\s*(\d+)", re.I)
OBJETO_RE = re.compile(r"Objeto:\s*(.+)", re.I)


def _listar_pregoes_do_ano(page, url, ano, log):
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    links = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => [e.textContent.trim(), e.href])")
    vistos, out = set(), []
    for texto, href in links:
        if ("PREGÃO" in texto.upper() or "PREGAO" in texto.upper()) and href not in vistos:
            vistos.add(href)
            out.append((texto, href))
    log(f"  {ano}: {len(out)} sub-página(s) de pregão")
    return out


def _extrair_pregao(page, titulo, url):
    page.goto(url, timeout=30000, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)
    texto = page.inner_text("body")
    m = NUM_RE.search(titulo)
    if not m:
        # títulos sem "Nº" explícito (ex: "Pregão Eletrônico 01/2021 – ...")
        # ainda têm o padrão NN/AAAA solto no texto — usa isso como fallback
        # em vez do título inteiro (que virava um "número" absurdo).
        m2 = re.search(r"\b(\d{1,5})/\d{4}\b", titulo)
        numero = m2.group(1) if m2 else "?"
    else:
        numero = m.group(1)
    om = OBJETO_RE.search(texto)
    objeto = om.group(1).strip()[:2000] if om else titulo
    links = page.eval_on_selector_all(
        "a[href]", "els => els.map(e => [e.textContent.trim(), e.href])")
    edital = next((h for t, h in links if "edital" in t.lower() and "/documents/" in h), None) \
        or next((h for t, h in links if "/documents/d/ceasa/" in h), None)
    return {"numero": numero, "objeto": objeto, "link": edital or url}


def coletar(log=print):
    itens = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        for ano, url in sorted(ANOS_URLS.items()):
            try:
                pregoes = _listar_pregoes_do_ano(page, url, ano, log)
            except Exception as e:
                log(f"  {ano}: falhou ao listar ({e})")
                continue
            for titulo, href in pregoes:
                try:
                    it = _extrair_pregao(page, titulo, href)
                    it["ano"] = ano
                    itens.append(it)
                except Exception as e:
                    log(f"    falhou {href[:80]}: {type(e).__name__}")
                    try:
                        page.close()
                        page = browser.new_page()
                    except Exception:
                        pass
        try:
            browser.close()
        except Exception:
            pass
    log(f"CEASA-DF: {len(itens)} pregão(ões) capturado(s) no total (2021-2026).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "CEASA-DF - Centrais de Abastecimento do Distrito Federal",
        "nome_padronizado": "CEASA-DF",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"CEASA-DF|{it.get('numero') or '-'}/{it['ano']}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": f"{it.get('numero','')}/{it['ano']}",
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
    for c in contratos[:8]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["link_fonte"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
