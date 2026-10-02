import re, json
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
try: import psycopg2
except Exception: import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
# 1) garante coluna percentual
cur.execute("ALTER TABLE condicionamentos ADD COLUMN IF NOT EXISTS percentual NUMERIC;")
print("ALTER ok (percentual)")
# 2) importa o registro (idempotente: nao duplica se ja existir mesmo bitrix+comissionado+criado_em)
reg = {
  "perfil":"Pre-Vendas","nome_preenchedor":"Henri","sobrenome_preenchedor":"Mafra",
  "id_bitrix":"123456","nome_comissionado":"Henri Felipe Marques Mafra","percentual":15,
  "fases_comissionadas":["6 - Projeto Ganho"],"criado_em":"2026-05-19T13:17:27.427+00:00",
}
cur.execute("""select count(*) from condicionamentos
               where id_bitrix=%s and nome_comissionado=%s and criado_em=%s""",
            (reg["id_bitrix"],reg["nome_comissionado"],reg["criado_em"]))
if cur.fetchone()[0]==0:
    cur.execute("""insert into condicionamentos
      (perfil,nome_preenchedor,sobrenome_preenchedor,id_bitrix,nome_comissionado,percentual,fases_comissionadas,criado_em,criado_por)
      values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,NULL)""",
      (reg["perfil"],reg["nome_preenchedor"],reg["sobrenome_preenchedor"],reg["id_bitrix"],
       reg["nome_comissionado"],reg["percentual"],json.dumps(reg["fases_comissionadas"]),reg["criado_em"]))
    print("registro importado")
else:
    print("registro ja existia (skip)")
# 3) confere
cur.execute("select id,perfil,nome_preenchedor,sobrenome_preenchedor,id_bitrix,nome_comissionado,percentual,fases_comissionadas,criado_em from condicionamentos order by criado_em")
for r in cur.fetchall(): print("  ", r)
cur.close(); cn.close()
