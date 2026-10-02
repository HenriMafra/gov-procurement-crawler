import re
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
try:
    import psycopg2
except Exception:
    import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
cur.execute("select column_name from information_schema.columns where table_name='rodadas' order by ordinal_position")
cols=[c[0] for c in cur.fetchall()]
print("colunas rodadas:", cols)
cur.execute("select * from rodadas order by id")
for row in cur.fetchall():
    print(dict(zip(cols,row)))
cur.close(); cn.close()
