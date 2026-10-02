# -*- coding: utf-8 -*-
"""
ATLAS B2G — Coletor de EDITAIS / LICITAÇÕES (PNCP consulta API).
Fonte NOVA (complementa o coletor de contratos assinados): traz oportunidades de
NEGÓCIO NOVO — licitações publicadas e, principalmente, com PROPOSTA ABERTA.

Endpoints:
  /v1/contratacoes/publicacao  -> editais por data de publicação (aceita uf!)
  /v1/contratacoes/proposta    -> editais com período de proposta ABERTO (uf!)

Filtra TI reusando core.classifica_ti(objetoCompra). uf=DF/GO filtrado no servidor
(muito mais eficiente que /contratos). Itera as modalidades.
"""
import sys, os, time, json, urllib.request, urllib.error, datetime
sys.path.insert(0, os.path.dirname(__file__))
import atlas_pncp_ingest as core

BASE = "https://pncp.gov.br/api/consulta"
UA = {"User-Agent": "Mozilla/5.0 ATLAS-B2G/1.0", "Accept": "application/json"}
# modalidades de contratação (codigoModalidadeContratacao). Iteramos as principais.
MODALIDADES = {
    1: "Leilão - Eletrônico", 4: "Concorrência - Eletrônica", 5: "Concorrência - Presencial",
    6: "Pregão - Eletrônico", 7: "Pregão - Presencial", 8: "Dispensa de Licitação",
    9: "Inexigibilidade", 12: "Credenciamento", 13: "Leilão - Presencial",
}

def _req(path, params, retries=5, sleep=0.5, timeout=45):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE}{path}?{qs}"
    last = None
    for t in range(1, retries + 1):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                b = r.read().decode("utf-8", "replace")
                if not b.strip():
                    last = "corpo vazio";
                else:
                    return json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 422):  # parâmetro inválido p/ essa modalidade — desiste em silêncio
                return {"data": [], "totalPaginas": 0, "totalRegistros": 0, "_skip": e.code}
            last = f"HTTP {e.code}"
        except Exception as e:
            last = f"{type(e).__name__}: {str(e)[:60]}"
        time.sleep(sleep * (2 ** (t - 1)))
    return {"data": [], "totalPaginas": 0, "totalRegistros": 0, "_erro": last}

def _normaliza(it, modalidade_cod, aberto):
    org = it.get("orgaoEntidade") or {}
    uo = it.get("unidadeOrgao") or {}
    cl = core.classifica_ti(it.get("objetoCompra") or "")
    return {
        "id_pncp": it.get("numeroControlePNCP"),
        "tipo": "edital",
        "modalidade_cod": modalidade_cod,
        "modalidade": it.get("modalidadeNome") or MODALIDADES.get(modalidade_cod, str(modalidade_cod)),
        "situacao": it.get("situacaoCompraNome"),
        "proposta_aberta": bool(aberto),
        "objeto": (it.get("objetoCompra") or "").strip(),
        "valor_estimado": it.get("valorTotalEstimado"),
        "srp": bool(it.get("srp")),
        "data_publicacao": (it.get("dataPublicacaoPncp") or "")[:10],
        "abertura_proposta": (it.get("dataAberturaProposta") or "")[:16].replace("T", " "),
        "encerramento_proposta": (it.get("dataEncerramentoProposta") or "")[:16].replace("T", " "),
        "orgao_cnpj": org.get("cnpj"),
        "orgao_nome": org.get("razaoSocial"),
        "uf": uo.get("ufSigla"),
        "municipio": uo.get("municipioNome"),
        "unidade": uo.get("nomeUnidade"),
        "link": it.get("linkSistemaOrigem") or it.get("linkProcessoEletronico"),
        "ano": it.get("anoCompra"),
        # classificação TI
        "eh_ti": cl["eh_ti"], "categoria": cl["categoria"], "subcategoria": cl["subcategoria"],
        "confianca": cl["confianca"], "palavras": cl["palavras"],
    }

def coletar(ufs=("DF", "GO"), modalidades=None, di=None, df=None, abertos=True,
            max_pag=40, somente_ti=True, log=print):
    """Coleta editais. Se 'abertos': usa /proposta (proposta em aberto agora).
       Senão: usa /publicacao no intervalo di..df (YYYYMMDD)."""
    mods = list((modalidades or MODALIDADES).keys()) if isinstance(modalidades, dict) else list(modalidades or MODALIDADES.keys())
    vistos, regs = set(), []
    for uf in ufs:
        for mod in mods:
            if abertos:
                path = "/v1/contratacoes/proposta"
                base_params = {"dataFinal": df or datetime.date.today().strftime("%Y%m%d"),
                               "codigoModalidadeContratacao": mod, "uf": uf}
            else:
                path = "/v1/contratacoes/publicacao"
                base_params = {"dataInicial": di, "dataFinal": df,
                               "codigoModalidadeContratacao": mod, "uf": uf}
            p1 = _req(path, {**base_params, "pagina": 1, "tamanhoPagina": 50})
            if p1.get("_skip"): continue
            tot = p1.get("totalRegistros") or 0
            npag = min(int(p1.get("totalPaginas") or 1), max_pag)
            if tot: log(f"   {uf} mod {mod} ({MODALIDADES.get(mod,mod)}): {tot} editais | {npag} págs")
            for pag in range(1, npag + 1):
                d = p1 if pag == 1 else _req(path, {**base_params, "pagina": pag, "tamanhoPagina": 50})
                for it in (d.get("data") or []):
                    k = it.get("numeroControlePNCP")
                    if not k or k in vistos: continue
                    r = _normaliza(it, mod, abertos)
                    if somente_ti and r["eh_ti"] != "Sim": continue
                    vistos.add(k); regs.append(r)
                if pag > 1: time.sleep(0.25)
    log(f"Editais coletados: {len(regs)} (TI{' apenas' if somente_ti else ''}; UFs {list(ufs)}).")
    return regs

if __name__ == "__main__":
    # TESTE pequeno: editais com proposta ABERTA em DF/GO, TI, principais modalidades
    regs = coletar(ufs=("DF", "GO"), modalidades={6: "", 8: "", 9: "", 4: ""}, abertos=True, max_pag=6)
    print(f"\n=== {len(regs)} editais de TI com proposta aberta ===")
    for r in sorted(regs, key=lambda x: x.get("encerramento_proposta") or "")[:12]:
        v = core.brl(r["valor_estimado"]) if r["valor_estimado"] else "—"
        print(f"  [{r['uf']}] {r['categoria']:18.18} | {v:>14} | encerra {r['encerramento_proposta'] or '?'} | {r['objeto'][:60]}")
