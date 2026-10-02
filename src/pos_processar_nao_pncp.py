# -*- coding: utf-8 -*-
"""
ATLAS B2G — Pós-processamento: liga contratos coletados fora do PNCP
(CIASC, SENAC/SESC SC, SENAC PR, FIEG, EBC, BBTS, ...) ao mesmo classificador
de TI e motor de score comercial usados na coleta PNCP, gerando linhas em
`oportunidades` — sem isso, os contratos ficam gravados em `contratos` mas
INVISÍVEIS na Lista de Ataque / Painel Tático (que leem de `oportunidades`).

Reaproveita as funções puras de atlas_pncp_ingest.py (classifica_ti,
status_contrato, eh_concorrente, score_oportunidade, faixa_prioridade,
motivo_prioridade, proxima_acao) — mesmas 236 keywords e mesma lógica de
score do pipeline PNCP, aplicadas a QUALQUER fonte.

Idempotente: pode rodar de novo a qualquer momento (upsert por op_key);
roda automaticamente depois de cada coletor não-PNCP.

Uso:
  python src/pos_processar_nao_pncp.py --db-url postgresql://...
  python src/pos_processar_nao_pncp.py --db-url ... --fontes CIASC-SC,EBC
"""
import os, sys, argparse, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import atlas_pncp_ingest as core
from atlas_db import AtlasDB

core.CONFIG["CONCORRENTES_CONHECIDOS"] = core.CONFIG.get("CONCORRENTES_CONHECIDOS") or []
core.CONFIG["UFS"] = ["DF", "GO", "PR", "RS", "SC"]

FONTES_NAO_PNCP_PADRAO = ["CIASC-SC", "SENAC-SC", "SESC-SC", "BBTS", "FIEG", "EBC", "SENAC-PR",
                          "PREGAO-BANRISUL", "ABDI", "SENAC-DF", "NOVACAP", "CODHAB-DF",
                          "CAESB", "METRO-DF", "TCB", "EMATER-DF", "TERRACAP", "CEASA-DF"]


def tipo_oportunidade(dias, fim, eh_conc):
    if eh_conc: return "Substituição de concorrente"
    if fim is None: return "Relacionamento (validar dados)"
    if dias is not None and dias < 0: return "Renovação / nova licitação"
    if dias is not None and dias <= 90: return "Renovação antecipada"
    return "Relacionamento / expansão"


def processar(db, fontes, log=print):
    # Evita depender de índice em `contratos.fonte` (tabela grande, sem esse índice):
    # todo contrato dos coletores dedicados tem contrato_key prefixado com "FONTE|...",
    # e contrato_key já é UNIQUE (índice btree existente) — LIKE 'FONTE|%' usa esse
    # índice via range scan em vez de fazer sequential scan na tabela inteira.
    rows = []
    for fonte in fontes:
        sql = db.q("""
            SELECT c.id AS contrato_id, c.contrato_key, c.objeto_original, c.valor_total,
                   c.fim_vigencia, c.fornecedor_id, c.orgao_id,
                   o.uf, o.esfera, o.nome_padronizado AS orgao_nome,
                   f.nome_fornecedor
            FROM contratos c
            JOIN orgaos o ON o.id = c.orgao_id
            LEFT JOIN fornecedores f ON f.id = c.fornecedor_id
            WHERE c.contrato_key LIKE ? AND c.objeto_original IS NOT NULL AND c.objeto_original <> ''
        """)
        rs = db.fetch(sql, [f"{fonte}|%"])
        log(f"  {fonte}: {len(rs)} contrato(s).")
        rows.extend(rs)
    log(f"pos_processar: {len(rows)} contrato(s) das fontes {fontes} para classificar.")

    # CRÍTICO: nunca criar uma rodada "nova" aqui. A Lista de Ataque / Painel Tático /
    # Terreno Conquistado só leem a rodada com a data_rodada mais recente (mesma regra da
    # view `vw_lista_ataque_atual_lenta_bak`) — se este processo criasse uma rodada própria
    # com a data de hoje, ela "venceria" por data e ESCONDERIA as ~196 mil oportunidades do
    # PNCP (só ficariam visíveis as poucas centenas destas fontes dedicadas). Já aconteceu
    # em produção (2026-07-12/13) e apagou o Terreno Conquistado/Painel Tático até ser
    # corrigido manualmente. Em vez disso, reaproveita a rodada "atual" que já existe.
    hoje = datetime.date.today()
    atual = db.fetch(db.q("SELECT id FROM rodadas ORDER BY data_rodada DESC, id DESC LIMIT 1"), [])
    if atual:
        rodada_id = atual[0]["id"]
    else:
        meta = {"data_rodada": hoje.isoformat(), "tag": "NAO-PNCP", "tipo": "coleta-dedicada",
                "status_execucao": "concluida", "total_coletado": len(rows), "total_ti": 0,
                "total_oportunidades": 0, "total_criticas": 0, "valor_total_mapeado": 0}
        rodada_id = db.insert_rodada(meta)

    n_ti, n_opp, n_criticas, valor_total = 0, 0, 0, 0.0
    opps, historico = [], []
    for r in rows:
        objeto = r["objeto_original"] or ""
        cl = core.classifica_ti(objeto)
        if cl["eh_ti"] != "Sim":
            continue
        n_ti += 1
        fim = None
        if r["fim_vigencia"]:
            try:
                fim = datetime.date.fromisoformat(str(r["fim_vigencia"])[:10])
            except Exception:
                fim = None
        status, dias = core.status_contrato(fim)
        valor = float(r["valor_total"] or 0)
        eh_conc, grau = core.eh_concorrente(r["nome_fornecedor"] or "", cl["eh_ti"])
        checks = [bool(r["fornecedor_id"]), valor > 0, fim is not None, bool(objeto.strip())]
        qual_frac = sum(checks) / len(checks)
        score, _ = core.score_oportunidade(dias, status, valor, cl["categoria"], eh_conc,
                                            r["esfera"] or "", r["uf"] or "", qual_frac)
        prio = core.faixa_prioridade(score)
        if prio in ("Máxima", "Alta"):
            n_criticas += 1
        valor_total += valor
        tipo = tipo_oportunidade(dias, fim, eh_conc)
        opk = f"{r['contrato_key']}|{tipo}"
        opps.append({
            "op_key": opk, "contrato_id": r["contrato_id"], "orgao_id": r["orgao_id"],
            "fornecedor_id": r["fornecedor_id"], "rodada_id": rodada_id,
            "id_oportunidade": None, "tipo_oportunidade": tipo,
            "janela_comercial": ("Ataque imediato" if dias is not None and dias <= 30 else
                                  "Preparação comercial" if dias is not None and dias <= 90 else
                                  "Monitoramento"),
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
        # também grava a classificação de volta no contrato bruto (pra busca/filtro funcionar)
        db.cur.execute(db.q(
            "UPDATE contratos SET categoria_principal=?, subcategoria=?, "
            "palavras_chave_encontradas=?, status_contrato=?, dias_ate_vencimento=? WHERE id=?"),
            [cl["categoria"], cl["subcategoria"], ", ".join(cl["palavras"][:8]), status, dias, r["contrato_id"]])

    if opps:
        opp_ids = db.batch_upsert_oportunidades(opps)
        for o in opps:
            oid = opp_ids.get(o["op_key"])
            if not oid:
                continue
            historico.append({
                "oportunidade_id": oid, "rodada_id": rodada_id,
                "score_comercial": o["score_comercial"], "prioridade": o["prioridade"],
                "urgencia_comercial": o["urgencia_comercial"], "valor_total": 0,
                "dias_ate_vencimento": None, "status_contrato": None, "status_na_rodada": "Nova",
            })
        db.batch_insert_historico(historico)
        n_opp = len(opps)

    db.cur.execute(db.q(
        "UPDATE rodadas SET total_ti=?, total_oportunidades=?, total_criticas=?, valor_total_mapeado=? WHERE id=?"),
        [n_ti, n_opp, n_criticas, round(valor_total, 2), rodada_id])
    db.commit()
    log(f"-> {n_ti} classificados como TI / {n_opp} oportunidades geradas / {n_criticas} críticas / "
        f"valor mapeado {valor_total:,.2f}".replace(",", "."))
    return {"total": len(rows), "ti": n_ti, "oportunidades": n_opp, "criticas": n_criticas}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--fontes", default=",".join(FONTES_NAO_PNCP_PADRAO),
                     help="Lista separada por vírgula de valores de `contratos.fonte` a processar.")
    args = ap.parse_args()
    if not args.db_url:
        print("ERRO: informe --db-url ou defina $DATABASE_URL"); sys.exit(1)
    fontes = [f.strip() for f in args.fontes.split(",") if f.strip()]
    db = AtlasDB(args.db_url)
    processar(db, fontes)
    db.close()


if __name__ == "__main__":
    main()
