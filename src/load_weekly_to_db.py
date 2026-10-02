# -*- coding: utf-8 -*-
"""
ATLAS B2G — Carga de uma rodada semanal para o banco (PostgreSQL/Supabase ou SQLite).

  python src/load_weekly_to_db.py --rodada outputs/rodadas/PRODUCAO_2026-05-31
  python src/load_weekly_to_db.py --csv <arquivo.csv> --db-url postgresql://...

Sem --db-url usa $DATABASE_URL ou sqlite:///data/atlas_b2g.sqlite (teste).
"""
import os, sys, re, csv, glob, json, argparse, unicodedata, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from atlas_db import AtlasDB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "supabase", "schema_atlas_b2g.sql")
SEED = os.path.join(ROOT, "supabase", "seed_atlas_b2g.sql")

# ---------- helpers ----------
def _digits(s): return re.sub(r"\D", "", str(s or ""))
def _norm(s):
    s = "".join(c for c in unicodedata.normalize("NFD", str(s or "")) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()
def _date_iso(s):
    if not s: return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(str(s)[:10], fmt).date().isoformat()
        except Exception: pass
    return None
def _f(s):
    try: return float(s) if s not in (None, "") else None
    except Exception: return None
def _i(s):
    try: return int(float(s)) if s not in (None, "") else None
    except Exception: return None

def _meta_rodada(folder, rows):
    base = os.path.basename(folder.rstrip("/\\"))
    m = re.match(r"^(?:(.+)_)?(\d{4}-\d{2}-\d{2})$", base)
    tag = (m.group(1) if m and m.group(1) else "")
    data = (m.group(2) if m else datetime.date.today().isoformat())
    cfg = None
    for c in glob.glob(os.path.join(folder, "atlas_config_*.json")):
        try: cfg = json.load(open(c, encoding="utf-8")); break
        except Exception: pass
    zips = glob.glob(os.path.join(folder, "*.zip"))
    crit = sum(1 for r in rows if r.get("Urgência Comercial") == "Crítica")
    valor = sum(_f(r.get("Valor Total")) or 0 for r in rows)
    return {"data_rodada": data, "tag": tag, "tipo": ("producao" if tag.upper() == "PRODUCAO" else "semanal"),
            "config_json": cfg, "status_execucao": "concluida", "total_coletado": 0, "total_ti": len(rows),
            "total_oportunidades": len(rows), "total_criticas": crit, "valor_total_mapeado": round(valor, 2),
            "caminho_pacote": (os.path.basename(zips[0]) if zips else None)}

# ---------- carga ----------
def carregar(rodada=None, csv_path=None, db_url=None, init=True, verbose=True, remove=True):
    # remove=False => modo ADD-only: NUNCA marca oportunidades como 'Removida' (a base só cresce).
    # Usado pela coleta pinada na rodada estável, pra garantir que uma coleta parcial nunca encolha a base.
    db_url = db_url or os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(ROOT, "data", "atlas_b2g.sqlite")
    if rodada and not csv_path:
        cands = glob.glob(os.path.join(rodada, "atlas_lista_ataque_comercial_*.csv"))
        if not cands: raise FileNotFoundError("CSV da lista de ataque não encontrado em " + rodada)
        csv_path = cands[0]
    folder = rodada or os.path.dirname(csv_path)
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    db = AtlasDB(db_url)
    if init: db.init_schema(SCHEMA, SEED)
    meta = _meta_rodada(folder, rows)
    rodada_id = db.insert_rodada(meta)
    ins = {"orgaos0": db.count("orgaos"), "forn0": db.count("fornecedores"),
           "contr0": db.count("contratos"), "opp0": db.count("oportunidades")}
    # ----- CARGA EM LOTE (rápida): agrupa por tabela e grava com execute_values + RETURNING -----
    parsed = []  # (r, ok, fk, ck, tipo, opk, valor) — evita reprocessar as chaves
    orgaos, forns = {}, {}
    for r in rows:
        cnpj_o = _digits(r.get("CNPJ do Órgão")); nome_o = r.get("Nome Padronizado (Órgão)") or r.get("Órgão")
        ok = cnpj_o if cnpj_o else _norm(f"{nome_o}|{r.get('UF')}|{r.get('Município')}")
        orgaos[ok] = {"orgao_key": ok, "cnpj_orgao": cnpj_o, "nome_orgao": r.get("Órgão"),
            "nome_padronizado": nome_o, "uf": r.get("UF"), "municipio": r.get("Município"),
            "poder": r.get("Poder"), "esfera": r.get("Esfera"), "unidade_compradora": r.get("Unidade Compradora"),
            "segmento_presumido": r.get("Segmento Presumido"), "fonte_primeira_ocorrencia": r.get("Fonte")}
        cnpj_f = _digits(r.get("CNPJ do Fornecedor")); nome_f = r.get("Fornecedor")
        fk = (cnpj_f if cnpj_f else _norm(nome_f)) or "sem-fornecedor"
        forns[fk] = {"forn_key": fk, "cnpj_fornecedor": cnpj_f, "nome_fornecedor": nome_f,
            "nome_padronizado": r.get("Nome Padronizado (Fornecedor)"),
            "possivel_concorrente": r.get("Possível Concorrente") == "Sim",
            "concorrente_conhecido": r.get("Grau de Ameaça") == "Alto",
            "grau_ameaca": r.get("Grau de Ameaça"), "categorias_detectadas": r.get("Categoria Principal")}
        idp = r.get("ID PNCP"); valor = _f(r.get("Valor Total"))
        ck = idp if idp else _norm(f"{ok}|{r.get('Número do Contrato')}|{r.get('Número do Processo')}|{valor}|{r.get('Fim da Vigência')}")
        tipo = r.get("Tipo de Oportunidade") or "Oportunidade"; opk = f"{ck}|{tipo}"
        parsed.append((r, ok, fk, ck, tipo, opk, valor))
    orgao_ids = db.batch_upsert("orgaos", "orgao_key", list(orgaos.values()), touch=True)
    forn_ids = db.batch_upsert("fornecedores", "forn_key", list(forns.values()), touch=True)

    contratos = {}
    for (r, ok, fk, ck, tipo, opk, valor) in parsed:
        contratos[ck] = {"contrato_key": ck, "id_pncp": r.get("ID PNCP"), "numero_contrato": r.get("Número do Contrato"),
            "numero_processo": r.get("Número do Processo"), "fonte": r.get("Fonte") or "PNCP", "link_fonte": r.get("Link da Fonte"),
            "orgao_id": orgao_ids[ok], "fornecedor_id": forn_ids[fk], "objeto_original": r.get("Objeto"), "objeto_normalizado": r.get("Objeto Normalizado"),
            "categoria_principal": r.get("Categoria Principal"), "subcategoria": r.get("Subcategoria"),
            "palavras_chave_encontradas": r.get("Palavras-chave Encontradas"), "valor_total": valor,
            "valor_mensal_estimado": _f(r.get("Valor Mensal Estimado")), "data_assinatura": _date_iso(r.get("Data de Assinatura")),
            "inicio_vigencia": _date_iso(r.get("Início da Vigência")), "fim_vigencia": _date_iso(r.get("Fim da Vigência")),
            "dias_ate_vencimento": _i(r.get("Dias até Vencimento")), "status_contrato": r.get("Status do Contrato"),
            "situacao_pncp": r.get("Situação"), "modalidade": r.get("Modalidade")}
    contr_ids = db.batch_upsert("contratos", "contrato_key", list(contratos.values()), touch=True)

    opps = {}
    for (r, ok, fk, ck, tipo, opk, valor) in parsed:
        opps[opk] = {"op_key": opk, "contrato_id": contr_ids[ck], "orgao_id": orgao_ids[ok], "fornecedor_id": forn_ids[fk],
            "rodada_id": rodada_id, "id_oportunidade": r.get("ID Oportunidade"), "tipo_oportunidade": tipo,
            "janela_comercial": r.get("Janela Comercial"), "urgencia_comercial": r.get("Urgência Comercial"),
            "score_comercial": _i(r.get("Score Comercial") or r.get("Score de Oportunidade")), "prioridade": r.get("Prioridade"),
            "explicacao_score": r.get("explicacao_score") or r.get("Motivo da Prioridade"), "motivo_prioridade": r.get("Motivo da Prioridade"),
            "argumento_comercial_sugerido": r.get("Argumento Comercial Sugerido"), "proxima_acao_recomendada": r.get("Próxima Ação Recomendada"),
            "responsavel_sugerido": None, "responsavel_atribuido": None,  # responsável automático REMOVIDO (henri define manualmente)
            "carteira_sugerida": None, "status_comercial": "Novo", "status_validacao": "Pendente",
            "necessita_revisao": r.get("Necessita Revisão?") == "Sim", "observacoes_revisao": r.get("Observações"),
            "data_primeira_ocorrencia": meta["data_rodada"], "data_ultima_ocorrencia": meta["data_rodada"],
            "status_na_rodada": r.get("Status na Rodada") or "Nova"}
    opp_ids = db.batch_upsert_oportunidades(list(opps.values()))

    historico, revisoes = {}, {}
    for (r, ok, fk, ck, tipo, opk, valor) in parsed:
        oppid = opp_ids[opk]
        historico[(oppid, rodada_id)] = {"oportunidade_id": oppid, "rodada_id": rodada_id,
            "score_comercial": _i(r.get("Score Comercial") or r.get("Score de Oportunidade")), "prioridade": r.get("Prioridade"),
            "urgencia_comercial": r.get("Urgência Comercial"), "valor_total": valor, "dias_ate_vencimento": _i(r.get("Dias até Vencimento")),
            "status_contrato": r.get("Status do Contrato"), "status_na_rodada": r.get("Status na Rodada") or "Nova",
            "mudanca_score": r.get("Mudança Score"), "mudanca_urgencia": r.get("Mudança Urgência"),
            "mudanca_valor": _f(r.get("Mudança Valor")), "mudanca_status": r.get("Observação Comparativo")}
        if r.get("Necessita Revisão?") == "Sim":
            revisoes[oppid] = {"oportunidade_id": oppid, "tipo_revisao": "classificacao",
                "motivo": "Classificação incerta / baixa confiança / sem data — validar antes da abordagem.",
                "status": "Pendente"}
    db.batch_insert_historico(list(historico.values()))
    db.batch_upsert_revisoes(list(revisoes.values()))
    # agrega métricas dos fornecedores
    db.cur.execute(db.q("UPDATE fornecedores SET total_contratos=(SELECT COUNT(*) FROM contratos c WHERE c.fornecedor_id=fornecedores.id), "
                        "valor_total_mapeado=(SELECT COALESCE(SUM(valor_total),0) FROM contratos c WHERE c.fornecedor_id=fornecedores.id)"))
    removidas = db.marcar_removidas(rodada_id) if remove else 0
    db.insert_log(rodada_id, "INFO", "Carga concluída", {"linhas": len(rows), "removidas": removidas})
    db.commit()
    res = {"rodada_id": rodada_id, "data_rodada": meta["data_rodada"], "linhas": len(rows), "removidas": removidas,
           "orgaos_novos": db.count("orgaos") - ins["orgaos0"], "fornecedores_novos": db.count("fornecedores") - ins["forn0"],
           "contratos_novos": db.count("contratos") - ins["contr0"], "oportunidades_novas": db.count("oportunidades") - ins["opp0"],
           "orgaos_total": db.count("orgaos"), "contratos_total": db.count("contratos"), "oportunidades_total": db.count("oportunidades"),
           "historico_total": db.count("oportunidade_historico"), "dialect": db.dialect}
    if verbose:
        print(f"[carga] rodada_id={res['rodada_id']} ({res['data_rodada']}) | dialeto={res['dialect']}")
        print(f"[carga] linhas={res['linhas']} | órgãos +{res['orgaos_novos']} (tot {res['orgaos_total']}) | "
              f"contratos +{res['contratos_novos']} (tot {res['contratos_total']}) | oportunidades +{res['oportunidades_novas']} (tot {res['oportunidades_total']})")
        print(f"[carga] histórico (snapshots) total={res['historico_total']} | removidas={res['removidas']}")
    try:  # notificação best-effort de resumo semanal (não quebra a carga)
        from atlas_notifications import NotifClient
        nc = NotifClient(db_url)
        nc.notify_weekly_summary({"oportunidades": res["oportunidades_total"], "criticas": meta["total_criticas"],
                                  "valor_total": meta["valor_total_mapeado"], "rodada_id": rodada_id})
        nc.close()
    except Exception:
        pass
    db.close()
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rodada"); ap.add_argument("--csv"); ap.add_argument("--db-url"); ap.add_argument("--no-init", action="store_true")
    a = ap.parse_args()
    if not a.rodada and not a.csv:
        ap.error("informe --rodada <pasta> ou --csv <arquivo>")
    carregar(rodada=a.rodada, csv_path=a.csv, db_url=a.db_url, init=not a.no_init)

if __name__ == "__main__":
    main()
