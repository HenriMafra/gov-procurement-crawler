import os, re, sys
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
print("DATABASE_URL OK (len=%d)"%len(dburl))
try:
    import psycopg2
except Exception:
    import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
def q(sql):
    cur.execute(sql); return cur.fetchall()
print("contratos total      :", q("select count(*) from contratos")[0][0])
print("rodadas              :", q("select count(*) from rodadas")[0][0])
print("orgaos               :", q("select count(*) from orgaos")[0][0])
print("fornecedores         :", q("select count(*) from fornecedores")[0][0])
r=q("select min(data_assinatura), max(data_assinatura) from contratos where data_assinatura is not null")[0]
print("assinatura min/max   :", r[0], "->", r[1])
r=q("select min(fim_vigencia), max(fim_vigencia) from contratos where fim_vigencia is not null")[0]
print("fim_vigencia min/max :", r[0], "->", r[1])
print("a vencer 0..180d     :", q("select count(*) from contratos where fim_vigencia >= current_date and fim_vigencia <= current_date + 180")[0][0])
print("vigentes (fim>=hoje) :", q("select count(*) from contratos where fim_vigencia >= current_date")[0][0])
print("--- por ano de assinatura ---")
for ano,c in q("select extract(year from data_assinatura)::int, count(*) from contratos where data_assinatura is not null group by 1 order by 1"):
    print("  %s: %s"%(ano,c))
print("--- ENTERPRISECORE (fornecedor) ---")
rows=q("select f.nome_padronizado, count(c.id) from fornecedores f join contratos c on c.fornecedor_id=f.id where f.nome_padronizado ilike '%enterprisecore%' group by 1")
if rows:
    for n,c in rows: print("  %s: %s contratos"%(n,c))
else:
    print("  (nenhum fornecedor 'enterprisecore' com contrato)")
    # tenta achar variações
    alt=q("select nome_padronizado from fornecedores where nome_padronizado ilike '%enterprisecore%' or nome_padronizado ilike '%n t sec%' limit 10")
    print("  fornecedores ~enterprisecore:", [a[0] for a in alt])
cur.close(); cn.close()
