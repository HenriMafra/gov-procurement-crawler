import os, re, sys
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
cur.execute("select column_name, data_type from information_schema.columns where table_name='contratos' order by ordinal_position")
for c,t in cur.fetchall(): print("  %-30s %s"%(c,t))
cur.close(); cn.close()
