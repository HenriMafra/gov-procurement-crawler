import re
envp = r"C:\Users\henri\Desktop\atlas-b2g-online\.env.local"
dburl=None
for ln in open(envp, encoding="utf-8"):
    m=re.match(r'\s*DATABASE_URL\s*=\s*"?([^"\r\n]+)"?', ln)
    if m: dburl=m.group(1).strip()
try: import psycopg2
except Exception: import psycopg as psycopg2
cn=psycopg2.connect(dburl); cn.autocommit=True; cur=cn.cursor()
# orgao com mais contratos
cur.execute("select orgao_id, count(*) c from contratos where orgao_id is not null group by 1 order by c desc limit 1")
oid,c = cur.fetchone()
cur.execute("select nome_padronizado, nome_orgao from orgaos where id=%s",(oid,))
on=cur.fetchone()
print(f"orgao_id={oid} ({on[0] or on[1]}) | {c} contratos")
# replica a logica do getOrgao: contrato.fornecedor_id -> fornecedor.nome_padronizado
cur.execute("""select c.numero_contrato, c.fornecedor_id, f.nome_padronizado
               from contratos c left join fornecedores f on f.id=c.fornecedor_id
               where c.orgao_id=%s order by c.valor_total desc nulls last limit 8""",(oid,))
print("  contrato            | fornecedor_id | nome_padronizado")
nomes=0; total=0
for nc,fid,nome in cur.fetchall():
    total+=1
    if nome: nomes+=1
    print(f"  {str(nc)[:18]:18s} | {str(fid):13s} | {nome or '(sem nome)'}")
# cobertura geral
cur.execute("""select count(*) tot, count(f.nome_padronizado) com_nome
               from contratos c left join fornecedores f on f.id=c.fornecedor_id where c.orgao_id=%s""",(oid,))
t,cn2=cur.fetchone()
print(f"  cobertura neste orgao: {cn2}/{t} contratos com nome resolvido")
cur.close(); cn.close()
