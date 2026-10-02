# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor dedicado: TERRACAP (Companhia Imobiliária de Brasília),
fora do PNCP.

Fonte: site institucional Joomla (`terracap.df.gov.br`). O core de negócio
da TERRACAP é venda/concessão de imóveis públicos — as licitações reais e
verificáveis encontradas ficam em
`/index.php/compre-imoveis/licitacoes/listagem-compre-imoveis-licitacao`
(cada edital é uma sub-página com PDF real em `/uploads/edicts/`). A seção
genérica "Licitações (compras)" do menu institucional não tem conteúdo
navegável (só menu, sem lista) — TERRACAP tem um portal próprio de compras
de bens/serviços (`comprasonline.terracap.df.gov.br`) mas é uma SPA sem
endpoint estático descoberto; não coberto por este coletor.

Uso:
  python src/collectors/coletor_terracap.py --db-url postgresql://... --write-db
  python src/collectors/coletor_terracap.py --dry-run
"""
import os, sys, re, hashlib, argparse
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import requests
from bs4 import BeautifulSoup

BASE = "https://www.terracap.df.gov.br"
LISTA_URL = f"{BASE}/index.php/compre-imoveis/licitacoes/listagem-compre-imoveis-licitacao"
# o WAF do domínio bloqueia (403) qualquer UA que não pareça um navegador
# real — diferente dos outros coletores desta bateria, aqui é obrigatório
# um UA de browser genuíno (+ Referer) para os PDFs de /uploads/edicts/.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://www.terracap.df.gov.br/",
}
ORGAO_KEY = "TERRACAP"
FONTE = "TERRACAP"

NUM_RE = re.compile(r"Edital\s+(?:de\s+Licita[çc][ãa]o\s+)?N[ºo°]?\s*(\d+)/?(\d{4})?", re.I)


def _abs_link(href):
    if not href:
        return LISTA_URL
    return href if href.startswith("http") else BASE + href


def coletar(log=print):
    r = requests.get(LISTA_URL, headers=HEADERS, timeout=30, verify=False)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.find_all("a", href=True)
    subpaginas = []
    for a in links:
        href = a["href"]
        if "/compre-imoveis/licitacoes/listagem-compre-imoveis-licitacao/" in href and href.rstrip("/") != LISTA_URL.rstrip("/"):
            titulo = a.get_text(" ", strip=True)
            subpaginas.append((titulo, _abs_link(href)))
    vistos = set()
    dedup = []
    for titulo, url in subpaginas:
        if url in vistos:
            continue
        vistos.add(url)
        dedup.append((titulo, url))
    subpaginas = dedup

    itens = []
    for titulo, url in subpaginas:
        try:
            rr = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            rr.raise_for_status()
            soup2 = BeautifulSoup(rr.text, "html.parser")
            texto = soup2.get_text(" ", strip=True)
            m = NUM_RE.search(titulo) or NUM_RE.search(texto)
            numero = f"{m.group(1)}/{m.group(2)}" if m and m.group(2) else (m.group(1) if m else titulo)
            pdf = None
            for a in soup2.find_all("a", href=True):
                if a["href"].lower().endswith(".pdf") and "/uploads/edicts/" in a["href"]:
                    pdf = a["href"]
                    break
            objeto_m = re.search(r"(CONCORR[ÊE]NCIA[^.]*\.)", texto, re.I) \
                or re.search(r"(A COMPANHIA IMOBILI[ÁA]RIA[^.]*\.)", texto, re.I)
            objeto = objeto_m.group(1).strip() if objeto_m else titulo
            ano = (m.group(2) if m and m.group(2) else None) or re.search(r"20\d{2}", titulo)
            ano = ano if isinstance(ano, str) else (ano.group(0) if ano else "2026")
            itens.append({
                "numero": numero, "objeto": objeto[:2000], "ano": ano,
                "link": pdf or url,
            })
        except Exception as e:
            log(f"  falhou {url}: {e}")
    log(f"TERRACAP: {len(itens)} licitação(ões) de imóveis capturada(s).")
    return itens


def para_registros_db(itens):
    orgao = {
        "orgao_key": ORGAO_KEY,
        "nome_orgao": "TERRACAP - Companhia Imobiliária de Brasília",
        "nome_padronizado": "TERRACAP",
        "uf": "DF",
        "municipio": "Brasília",
        "poder": "Executivo",
        "esfera": "Distrital",
        "fonte_primeira_ocorrencia": FONTE,
    }
    contratos = []
    for it in itens:
        obj_hash = hashlib.md5((it.get("objeto") or "").encode("utf-8")).hexdigest()[:8]
        contrato_key = f"TERRACAP|{it.get('numero') or '-'}|{obj_hash}"
        contratos.append({
            "contrato_key": contrato_key,
            "numero_processo": it.get("numero", ""),
            "fonte": FONTE,
            "link_fonte": it.get("link") or LISTA_URL,
            "objeto_original": it.get("objeto", ""),
            "modalidade": "Concorrência Pública (Venda/Concessão de Imóveis)",
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
    for c in contratos[:10]:
        print(" -", c["numero_processo"], "|", c["objeto_original"][:60], "|", c["link_fonte"][:60])

    if args.write_db and not args.dry_run:
        if not args.db_url:
            print("ERRO: --write-db requer --db-url ou $DATABASE_URL"); sys.exit(1)
        gravar_db(args.db_url, orgao, contratos)


if __name__ == "__main__":
    main()
