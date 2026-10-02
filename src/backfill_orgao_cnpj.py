# -*- coding: utf-8 -*-
"""
ATLAS B2G — Backfill exaustivo de UM órgão específico via PNCP, por CNPJ.

Criado após achar (2026-07-13) que o sweep nacional por janela de tempo
(atlas_pncp_ingest.py, MAX_PAGINAS=90) estava perdendo ~99% dos contratos
de órgãos de alto volume (ex.: IMBEL: 30 no banco vs 2.999 reais no PNCP)
— o volume nacional mensal estoura o teto de páginas antes de cobrir tudo.

Este script usa o parâmetro `cnpjOrgao` da API do PNCP (mais preciso e
sem o problema de volume nacional) para puxar TODOS os contratos de UM
órgão, sem teto de páginas, ano a ano (limite de 365 dias por consulta).

Uso:
  python src/backfill_orgao_cnpj.py --cnpj 00444232000139 --orgao-id 739 \
      --db-url postgresql://... --ano-inicio 2021
"""
import os, sys, time, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import requests
import atlas_pncp_ingest as core

BASE_URL = "https://pncp.gov.br/api/consulta/v1/contratos"
HEADERS = {"User-Agent": "Mozilla/5.0 (ATLAS-B2G backfill institucional; contato: henri.afly@gmail.com)"}


def log(m): print(f"[{datetime.datetime.now():%H:%M:%S}] {m}", flush=True)


# PNCP rate-limita agressivamente (HTTP 429) sob uso intenso — visto na prática hoje.
# Backoff exponencial real (8/16/32/64/120s) em vez de retry fixo curto, que só martelava
# a mesma página sem dar tempo do limite liberar. PAUSA_BASE_S entre páginas OK evita
# disparar o 429 em primeiro lugar (rodando 24/7 numa fila, não precisa ter pressa).
PAUSA_BASE_S = 1.2
MAX_TENTATIVAS = 6


def fetch_ano(cnpj, ano, log=log):
    itens = []
    ini = f"{ano}0101"
    fim = f"{ano}1231" if ano < datetime.date.today().year else datetime.date.today().strftime("%Y%m%d")
    pagina = 1
    while True:
        url = f"{BASE_URL}?cnpjOrgao={cnpj}&dataInicial={ini}&dataFinal={fim}&pagina={pagina}&tamanhoPagina=50"
        r = None
        for tentativa in range(MAX_TENTATIVAS):
            try:
                r = requests.get(url, headers=HEADERS, timeout=45)
            except requests.exceptions.RequestException as e:
                espera = min(120, 8 * (2 ** tentativa))
                log(f"    tentativa {tentativa+1} falhou ({e}); retry em {espera}s")
                time.sleep(espera)
                continue
            if r.status_code == 429:
                espera = int(r.headers.get("Retry-After", 0)) or min(120, 8 * (2 ** tentativa))
                log(f"    429 (rate limit) na página {pagina} — retry em {espera}s")
                time.sleep(espera)
                continue
            if r.status_code in (500, 502, 503, 504):
                espera = min(60, 8 * (2 ** tentativa))
                log(f"    status {r.status_code} na página {pagina} — retry em {espera}s")
                time.sleep(espera)
                continue
            break
        else:
            log(f"    página {pagina} desistiu após {MAX_TENTATIVAS} tentativas — pulando o resto do ano {ano}")
            break
        if r.status_code == 204:
            break
        if r.status_code != 200:
            log(f"    status {r.status_code} definitivo na página {pagina} — pulando o resto do ano {ano}")
            break
        d = r.json()
        data = d.get("data") or []
        if not data:
            break
        itens.extend(data)
        total = d.get("totalRegistros", 0)
        if len(itens) >= total:
            break
        pagina += 1
        time.sleep(PAUSA_BASE_S)
    log(f"  {ano}: {len(itens)} contrato(s)")
    return itens


def coletar_tudo(cnpj, ano_inicio, log=log):
    hoje_ano = datetime.date.today().year
    todos = []
    for ano in range(ano_inicio, hoje_ano + 1):
        todos.extend(fetch_ano(cnpj, ano, log))
    return todos


def para_registros_db(itens, orgao_id_existente=None):
    contratos, fornecedores = [], {}
    for it in itens:
        org = it.get("orgaoEntidade") or {}
        uni = it.get("unidadeOrgao") or {}
        objeto = (it.get("objetoContrato") or "").strip()
        forn_nome = (it.get("nomeRazaoSocialFornecedor") or "").strip()
        forn_cnpj = core.limpa_cnpj(it.get("niFornecedor"))
        valor = core.to_float(it.get("valorGlobal")) or core.to_float(it.get("valorInicial")) or 0.0
        fim = core.parse_data(it.get("dataVigenciaFim"))
        inicio = core.parse_data(it.get("dataVigenciaInicio"))
        assinatura = core.parse_data(it.get("dataAssinatura"))
        chave = it.get("numeroControlePNCP") or it.get("numeroControlePncpCompra")
        if not chave:
            continue
        cnpj_org = core.limpa_cnpj(org.get("cnpj"))
        ano_c = it.get("anoContrato"); seq = it.get("sequencialContrato")
        link = f"https://pncp.gov.br/app/contratos/{cnpj_org}/{ano_c}/{seq}" if (cnpj_org and ano_c and seq) else "https://pncp.gov.br"
        if forn_cnpj:
            fornecedores[forn_cnpj] = {"forn_key": forn_cnpj, "cnpj_fornecedor": forn_cnpj, "nome_fornecedor": forn_nome}
        contratos.append({
            "contrato_key": chave,
            "id_pncp": chave,
            "numero_contrato": it.get("numeroContratoEmpenho") or "",
            "numero_processo": it.get("processo") or "",
            "fonte": "PNCP",
            "link_fonte": link,
            "objeto_original": objeto,
            "modalidade": (it.get("tipoContrato") or {}).get("nome") or "",
            "situacao_pncp": (it.get("categoriaProcesso") or {}).get("nome") or "",
            "valor_total": valor,
            "data_assinatura": assinatura.isoformat() if assinatura else None,
            "inicio_vigencia": inicio.isoformat() if inicio else None,
            "fim_vigencia": fim.isoformat() if fim else None,
            "_forn_cnpj": forn_cnpj,
        })
    return contratos, list(fornecedores.values())


def gravar_e_classificar(db_url, orgao_id, contratos, fornecedores, rodada_id, log=log):
    from atlas_db import AtlasDB
    db = AtlasDB(db_url)
    forn_ids = {}
    for f in fornecedores:
        fid = db.upsert_fornecedor(f)
        forn_ids[f["cnpj_fornecedor"]] = fid
    n = 0
    for c in contratos:
        c["orgao_id"] = orgao_id
        c["fornecedor_id"] = forn_ids.get(c.pop("_forn_cnpj", None))
        db.upsert_contrato(c)
        n += 1
    db.commit()
    log(f"-> gravado: {len(fornecedores)} fornecedor(es), {n} contrato(s).")

    # classificação TI (mesmo padrão do pos_processar_nao_pncp.py)
    core.CONFIG["CONCORRENTES_CONHECIDOS"] = core.CONFIG.get("CONCORRENTES_CONHECIDOS") or []
    rows = db.fetch(db.q("""
        SELECT c.id AS contrato_id, c.contrato_key, c.objeto_original, c.valor_total,
               c.fim_vigencia, c.fornecedor_id, c.orgao_id,
               o.uf, o.esfera, f.nome_fornecedor
        FROM contratos c JOIN orgaos o ON o.id = c.orgao_id
        LEFT JOIN fornecedores f ON f.id = c.fornecedor_id
        WHERE c.orgao_id = ?
    """), [orgao_id])
    hoje = datetime.date.today()
    opps, n_ti = [], 0
    for r in rows:
        objeto = r["objeto_original"] or ""
        cl = core.classifica_ti(objeto)
        if cl["eh_ti"] != "Sim":
            continue
        n_ti += 1
        fim = None
        if r["fim_vigencia"]:
            try: fim = datetime.date.fromisoformat(str(r["fim_vigencia"])[:10])
            except Exception: fim = None
        status, dias = core.status_contrato(fim)
        valor = float(r["valor_total"] or 0)
        eh_conc, grau = core.eh_concorrente(r["nome_fornecedor"] or "", cl["eh_ti"])
        checks = [bool(r["fornecedor_id"]), valor > 0, fim is not None, bool(objeto.strip())]
        qual_frac = sum(checks) / len(checks)
        score, _ = core.score_oportunidade(dias, status, valor, cl["categoria"], eh_conc, r["esfera"] or "", r["uf"] or "", qual_frac)
        prio = core.faixa_prioridade(score)
        tipo = "Relacionamento (validar dados)" if fim is None else (
            "Renovação / nova licitação" if dias is not None and dias < 0 else
            "Renovação antecipada" if dias is not None and dias <= 90 else "Relacionamento / expansão")
        opk = f"{r['contrato_key']}|{tipo}"
        opps.append({
            "op_key": opk, "contrato_id": r["contrato_id"], "orgao_id": r["orgao_id"],
            "fornecedor_id": r["fornecedor_id"], "rodada_id": rodada_id,
            "id_oportunidade": None, "tipo_oportunidade": tipo,
            "janela_comercial": ("Ataque imediato" if dias is not None and dias <= 30 else
                                  "Preparação comercial" if dias is not None and dias <= 90 else "Monitoramento"),
            "urgencia_comercial": prio, "score_comercial": score, "prioridade": prio,
            "explicacao_score": core.motivo_prioridade(score, dias, status, valor, cl["categoria"], eh_conc),
            "motivo_prioridade": core.motivo_prioridade(score, dias, status, valor, cl["categoria"], eh_conc),
            "argumento_comercial_sugerido": None,
            "proxima_acao_recomendada": core.proxima_acao(cl["eh_ti"], status, dias),
            "responsavel_sugerido": None, "responsavel_atribuido": None, "carteira_sugerida": r["uf"],
            "status_comercial": "Novo", "status_validacao": "Pendente",
            "necessita_revisao": cl["revisao"] == "Sim", "observacoes_revisao": None,
            "data_primeira_ocorrencia": hoje.isoformat(), "data_ultima_ocorrencia": hoje.isoformat(),
            "status_na_rodada": "Nova",
        })
        db.cur.execute(db.q(
            "UPDATE contratos SET categoria_principal=?, subcategoria=?, status_contrato=?, dias_ate_vencimento=? WHERE id=?"),
            [cl["categoria"], cl["subcategoria"], status, dias, r["contrato_id"]])
    n_opp = 0
    if opps:
        db.batch_upsert_oportunidades(opps)
        n_opp = len(opps)
    db.commit()
    db.close()
    log(f"-> classificação: {len(rows)} contrato(s) revisados, {n_ti} TI, {n_opp} oportunidade(s).")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnpj", required=True)
    ap.add_argument("--orgao-id", type=int, required=True)
    ap.add_argument("--ano-inicio", type=int, default=2021)
    ap.add_argument("--rodada-id", type=int, default=8)
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.db_url and not args.dry_run:
        print("ERRO: informe --db-url ou defina $DATABASE_URL"); sys.exit(1)

    log(f"=== Backfill CNPJ {args.cnpj} (orgao_id={args.orgao_id}) desde {args.ano_inicio} ===")
    itens = coletar_tudo(args.cnpj, args.ano_inicio)
    contratos, fornecedores = para_registros_db(itens)
    log(f"Total capturado: {len(contratos)} contrato(s), {len(fornecedores)} fornecedor(es) único(s).")

    if args.dry_run:
        for c in contratos[:5]:
            print(" -", c["contrato_key"], "|", c["objeto_original"][:60], "|", c["valor_total"])
        return

    gravar_e_classificar(args.db_url, args.orgao_id, contratos, fornecedores, args.rodada_id)


if __name__ == "__main__":
    main()
