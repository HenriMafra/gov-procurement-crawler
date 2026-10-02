import re, json
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
try: import psycopg2
except Exception: import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
def q(s):
    cur.execute(s); return cur.fetchall()
print("=== MAPPER (destino) ===")
for t in ("comissionamentos","condicionamentos"):
    nc=q(f"select count(*) from information_schema.columns where table_name='{t}'")[0][0]
    np=q(f"select count(*) from pg_policies where tablename='{t}'")[0][0]
    rows=q(f"select count(*) from {t}")[0][0]
    print(f"  {t}: {nc} colunas | {np} policies | {rows} linhas")
print("  RLS ligado:", dict(q("select relname, relrowsecurity from pg_class where relname in ('comissionamentos','condicionamentos')")))
print("  policies condicionamentos:", [r[0] for r in q("select policyname from pg_policies where tablename='condicionamentos' order by 1")])
print("  registro migrado:")
for r in q("select id,perfil,nome_preenchedor,sobrenome_preenchedor,id_bitrix,nome_comissionado,percentual,fases_comissionadas,criado_em from condicionamentos order by criado_em"):
    print("   ", r)
cur.close(); cn.close()
