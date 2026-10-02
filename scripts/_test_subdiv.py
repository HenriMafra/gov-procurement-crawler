import sys, os, time
sys.path.insert(0,'src')
os.environ["ATLAS_FETCH_WORKERS"]="2"
import atlas_pncp_ingest as core
import atlas_ataque_comercial as atk
core.CONFIG["USAR_CACHE"]=True
core.CONFIG["RETRIES"]=3
core.CONFIG["SLEEP"]=0.4
core.CONFIG["TIMEOUT"]=45
# janela 2021 inteira, teto baixo p/ forcar subdivisao por data
atk.ATK["JANELAS"]=[("20210101","20211231")]
atk.ATK["MAX_PAG_POR_JANELA"]=3
t0=time.time()
regs=atk.coletar()
print("=== RESULTADO: %d registros DF/GO em %.0fs ==="%(len(regs), time.time()-t0))
