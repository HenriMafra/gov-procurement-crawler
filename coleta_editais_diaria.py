# -*- coding: utf-8 -*-
# Coleta DIÁRIA e LEVE de EDITAIS com proposta ABERTA (o que muda todo dia: licitações
# abertas pra concorrer agora). Grava na tabela 'editais' por UPSERT (id_pncp) — sem
# duplicar, sem rebaixar o flag de aberta. Pensado pra rodar na NUVEM (GitHub Actions):
# lê DATABASE_URL do ambiente (fallback no .env.local local). Não toca no histórico longo.
import os, sys, json, pathlib, datetime

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))   # garante que acha atlas_editais no Linux/CI
import atlas_editais as ed

UFS = tuple((os.environ.get("ATLAS_UFS") or "DF,GO,CE,SP,MT,PR,PE,AM,RS").split(","))

def dburl():
    u = os.environ.get("DATABASE_URL")
    if u:
        return u
    # fallback p/ rodar localmente (não usado na nuvem)
    envf = pathlib.Path(r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local")
    if envf.exists():
        for line in envf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""

def _dt(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try: return datetime.datetime.strptime(s, fmt)
        except Exception: pass
    return None

def _d(s):
    try: return datetime.datetime.strptime((s or "").strip()[:10], "%Y-%m-%d").date()
    except Exception: return None

def gravar(regs, d):
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
              proposta_aberta=(editais.proposta_aberta OR EXCLUDED.proposta_aberta),
              valor_estimado=EXCLUDED.valor_estimado, encerramento_proposta=EXCLUDED.encerramento_proposta,
              categoria=EXCLUDED.categoria, subcategoria=EXCLUDED.subcategoria, atualizado_em=now()
        """, (r["id_pncp"], r["modalidade_cod"], r["modalidade"], r["situacao"], r["proposta_aberta"],
              r["objeto"], r["valor_estimado"], r["srp"], _d(r["data_publicacao"]), _dt(r["abertura_proposta"]),
              _dt(r["encerramento_proposta"]), r["orgao_cnpj"], r["orgao_nome"], r["uf"], r["municipio"],
              r["unidade"], r["link"], r["ano"], r["categoria"], r["subcategoria"], r["confianca"],
              json.dumps(r.get("palavras") or [])))
        n += 1
    cur.close(); cn.close()
    return n

if __name__ == "__main__":
    d = dburl()
    if not d:
        print("ERRO: DATABASE_URL ausente"); sys.exit(1)
    print(f"[editais-diaria] coletando proposta ABERTA | UFs={UFS}", flush=True)
    abertos = ed.coletar(ufs=UFS, abertos=True, max_pag=120)
    n = gravar(abertos, d)
    print(f"[editais-diaria] FIM — {n} editais com proposta aberta gravados/atualizados.", flush=True)
