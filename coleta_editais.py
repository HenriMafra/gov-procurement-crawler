# -*- coding: utf-8 -*-
# Coleta de EDITAIS/LICITAÇÕES (PNCP /contratacoes) e grava na tabela 'editais'.
# Fonte de NEGÓCIO NOVO. DF/GO, todas as modalidades, filtro TI.
#  - proposta ABERTA (oportunidades pra concorrer agora)
#  - publicados no intervalo (histórico)
# Resumível por upsert (id_pncp). Lê DATABASE_URL do .env.local (sem segredo aqui).
import os, sys, datetime, pathlib
sys.path.insert(0, str(pathlib.Path(r"C:\Users\henri\Desktop\ATLAS-PNCP-Pilot") / "src"))
import atlas_editais as ed

ROOT = pathlib.Path(r"C:\Users\henri\Desktop\ATLAS-PNCP-Pilot")
ENVF = pathlib.Path(r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local")
ANOS = 6

def dburl():
    for line in ENVF.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def _dt(s):
    s = (s or "").strip()
    if not s: return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(s, fmt)
        except Exception: pass
    return None

def _d(s):
    s = (s or "").strip()[:10]
    try: return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception: return None

def gravar(regs, d):
    import json as _j
    try: import psycopg2
    except Exception: import psycopg as psycopg2
    cn = psycopg2.connect(d); cn.autocommit = True; cur = cn.cursor()
    n = 0
    for r in regs:
        if not r.get("id_pncp"): continue
        cur.execute("""
            INSERT INTO editais (id_pncp,modalidade_cod,modalidade,situacao,proposta_aberta,objeto,
              valor_estimado,srp,data_publicacao,abertura_proposta,encerramento_proposta,orgao_cnpj,
              orgao_nome,uf,municipio,unidade,link,ano,categoria,subcategoria,confianca,palavras,atualizado_em)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now())
            ON CONFLICT (id_pncp) DO UPDATE SET
              situacao=EXCLUDED.situacao,
              -- nunca rebaixa: se já estava aberta, continua aberta (histórico não apaga o flag)
              proposta_aberta=(editais.proposta_aberta OR EXCLUDED.proposta_aberta),
              valor_estimado=EXCLUDED.valor_estimado, encerramento_proposta=EXCLUDED.encerramento_proposta,
              categoria=EXCLUDED.categoria, subcategoria=EXCLUDED.subcategoria, atualizado_em=now()
        """, (r["id_pncp"], r["modalidade_cod"], r["modalidade"], r["situacao"], r["proposta_aberta"],
              r["objeto"], r["valor_estimado"], r["srp"], _d(r["data_publicacao"]), _dt(r["abertura_proposta"]),
              _dt(r["encerramento_proposta"]), r["orgao_cnpj"], r["orgao_nome"], r["uf"], r["municipio"],
              r["unidade"], r["link"], r["ano"], r["categoria"], r["subcategoria"], r["confianca"],
              _j.dumps(r.get("palavras") or [])))
        n += 1
    cur.close(); cn.close()
    return n

if __name__ == "__main__":
    d = dburl()
    if not d: print("ERRO: DATABASE_URL"); sys.exit(1)
    hoje = datetime.date.today()
    total = 0
    # 1) PROPOSTA ABERTA primeiro (o mais valioso: dá pra concorrer agora) — grava IMEDIATAMENTE,
    #    assim a aba Licitações já enche com oportunidades reais antes do histórico longo.
    print("[editais] (1/2) coletando proposta ABERTA (DF/GO, todas modalidades)...", flush=True)
    try:
        abertos = ed.coletar(ufs=("DF", "GO"), abertos=True, max_pag=80)
        n = gravar(abertos, d); total += n
        print(f"[editais] ABERTAS gravadas: {n} (proposta aberta agora). Total no banco até aqui: ~{total}.", flush=True)
    except Exception as e:
        print(f"[editais] ERRO nas abertas: {type(e).__name__}: {str(e)[:120]} — sigo p/ o histórico.", flush=True)
    # 2) HISTÓRICO por ANO — grava A CADA ANO (resiliente: se cair, o já coletado fica salvo;
    #    o flag de proposta aberta nunca é rebaixado pelo upsert).
    print("[editais] (2/2) histórico publicado, ano a ano...", flush=True)
    for y in range(hoje.year - ANOS + 1, hoje.year + 1):
        di = f"{y}0101"; df = (hoje.strftime("%Y%m%d") if y == hoje.year else f"{y}1231")
        print(f"[editais] -> publicados {y} ({di}..{df})...", flush=True)
        try:
            hy = ed.coletar(ufs=("DF", "GO"), abertos=False, di=di, df=df, max_pag=400)
            n = gravar(hy, d); total += n
            print(f"[editais] {y}: +{n} gravados/atualizados (acumulado ~{total}).", flush=True)
        except Exception as e:
            print(f"[editais] ERRO no ano {y}: {type(e).__name__}: {str(e)[:120]} — sigo p/ o próximo ano.", flush=True)
    print(f"[editais] FIM — ~{total} editais gravados/atualizados no total.", flush=True)
