import re, sys
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
sqlf = sys.argv[1]
sql = open(sqlf, encoding="utf-8").read()
try: import psycopg2
except Exception: import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
cur.execute(sql)
print("SQL aplicado OK:", sqlf)
# verifica
for t in ("comissionamentos","condicionamentos"):
    cur.execute("select count(*) from information_schema.columns where table_name=%s",(t,))
    nc=cur.fetchone()[0]
    cur.execute("select count(*) from pg_policies where tablename=%s",(t,))
    np=cur.fetchone()[0]
    cur.execute(f"select count(*) from {t}")
    rows=cur.fetchone()[0]
    print(f"  {t}: {nc} colunas | {np} policies | {rows} linhas")
cur.close(); cn.close()
