# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: TCB (Sociedade de Transportes Coletivos de
Brasília), fora do PNCP.

Fonte: site institucional em Liferay (`tcb.df.gov.br`), mesma plataforma
compartilhada usada por NOVACAP/CEASA/FUNAP (`gdf-secretarias-lf7_4`).
Uma página por ano (2021-2026), com dois padrões de marcação distintos
achados navegando manualmente cada uma:
  - 2025/2026: cada pregão é uma <table> com o objeto completo em texto
    corrido e um link de PDF do Edital.
  - 2021-2024: cada pregão é um bloco de acordeão (`.panel-body`) com o
    texto "Pregão (Eletrônico) Nº NN/AAAA" seguido de links de PDF
    (Aviso de Licitação / Edital / DODF); quase nunca tem objeto em texto
    corrido, só o número — nesses casos o objeto grava como label
    genérico (número + fonte), mas o link é sempre real e verificado.

Uso:
  python src/collectors/coletor_tcb.py --db-url postgresql://... --write-db
  python src/collectors/coletor_tcb.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup, NavigableString

BASE = "https://tcb.df.gov.br"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G coletor institucional; contato: henri.afly@gmail.com)"}
ORGAO_KEY = "TCB"
FONTE = "TCB"

ANOS_URLS = {
    2021: "https://tcb.df.gov.br/licitacoes-2021",
    2022: "https://tcb.df.gov.br/licitacoes-2022-2",
    2023: "https://tcb.df.gov.br/licitacoes-2023-2",
    2024: "https://tcb.df.gov.br/licitacoes-2024-1",
    2025: "https://tcb.df.gov.br/licitacoes-2025/",
    2026: "https://tcb.df.gov.br/preg%C3%B5es-eletr%C3%B4nicos2",
}

NUM_RE = re.compile(r"Preg[ãa]o\s+(?:Eletr[ôo]nico\s+)?N[º°o]\s*([\d]+/\d{4})", re.I)
OBJETO_RE = re.compile(r"Objeto:\s*(.+)", re.I)


def _parse_tabelas(soup, ano):
    itens = []
    for t in soup.find_all("table"):
        links = t.find_all("a", href=True)
        if not links:
            continue
        objeto = t.get_text(" ", strip=True)
        edital = next((a["href"] for a in links
                        if "edital" in a.get_text(" ", strip=True).lower()
                        or "edital" in a["href"].lower()), links[0]["href"])
        # dois formatos de link observados:
        #  /documents/{id1}/{id2}/{nome-do-arquivo}/{uuid}  (a maioria)
        #  /documents/d/tcb/{slug-sem-uuid}                 (alguns 2025/2026)
        # o número do processo (quando presente) fica embutido no nome do
        # arquivo ou no slug, nunca nos ids numéricos internos da URL —
        # então procuramos primeiro um padrão "90NNN-AAAA"/"90NNN_AAAA"
        # (mais específico) em toda a URL antes de cair pro genérico.
        # restringe a busca ao segmento de NOME do arquivo/slug (penúltimo
        # segmento da URL) — nunca aos ids numéricos internos do Liferay
        # (ex: "28997140"), que por acaso também contêm sequências "9\d{4}"
        # e geravam números de processo falsos.
        partes = [p for p in edital.split("/") if p]
        ultimo = partes[-1] if partes else edital
        eh_uuid = bool(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ultimo, re.I))
        nome_arquivo = partes[-2] if eh_uuid and len(partes) >= 2 else ultimo
        m = (re.search(r"(9\d{4})[-_.]?" + str(ano), nome_arquivo)
             or re.search(r"(9\d{4})[-_.]", nome_arquivo)
             or re.search(r"(9\d{4})", nome_arquivo)
             or re.search(r"(\d{4,6})", nome_arquivo))
        numero = f"{m.group(1)}/{ano}" if m else f"?/{ano}"
        itens.append({"numero": numero, "objeto": objeto[:2000], "ano": ano, "link": edital})
    return itens


def _parse_paineis(soup, ano):
    itens = {}
    for body in soup.select("div.collapse-gdf .panel-body"):
        current = None
        for node in body.descendants:
            if isinstance(node, NavigableString):
                s = str(node)
                m = NUM_RE.search(s)
                if m:
                    current = m.group(1)
                    if current not in itens:
                        itens[current] = {"numero": current, "objeto": "", "ano": ano, "links": []}
                    om = OBJETO_RE.search(s)
                    if om and not itens[current]["objeto"]:
                        itens[current]["objeto"] = om.group(1).strip()[:2000]
            elif getattr(node, "name", None) == "a" and node.get("href") and current:
                itens[current]["links"].append((node.get_text(" ", strip=True), node["href"]))
    out = []
    for numero, it in itens.items():
        links = it["links"]
        link = next((h for t, h in links if "edital" in t.lower()), None) \
            or next((h for t, h in links if "aviso" in t.lower()), None) \
            or (links[0][1] if links else None)
        if not link:
            continue
        out.append({
            "numero": numero,
            "objeto": it["objeto"] or f"Pregão Eletrônico Nº {numero} - TCB (ver edital no link)",
            "ano": ano,
            "link": link,
        })
    return out


def _abs_link(href):
    if not href:
        return BASE
    return href if href.startswith("http") else BASE + href


def coletar(log=print):
    todos = []
    for ano, url in sorted(ANOS_URLS.items()):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            itens = _parse_tabelas(soup, ano)
            if not itens:
                itens = _parse_paineis(soup, ano)
            for it in itens:
                it["link"] = _abs_link(it["link"])
            todos.extend(itens)
            log(f"  {ano}: +{len(itens)}")
        except Exception as e:
            log(f"  {ano}: falhou ({e})")
    log(f"TCB: {len(todos)} pregão(ões) capturado(s) no total (2021-2026).")
    return todos


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "TCB - Sociedade de Transportes Coletivos de Brasília",
        "nome_padronizado": "TCB",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"TCB|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
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
