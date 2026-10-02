"""
Debug: Verifica campos da API do PNCP - endpoint correto com datas no formato YYYYMMDD
"""
import urllib.request
import ssl
import json

UA = {"User-Agent": "Mozilla/5.0 ATLAS-B2G-Debug/1.0", "Accept": "application/json"}
_SSL = ssl.create_default_context()

# MPM - CNPJ
cnpj = "26989715000102"

# Endpoint que funcionou na coleta (formato com dataInicial/dataFinal YYYYMMDD)
url = f"https://pncp.gov.br/api/consulta/v1/contratos?dataInicial=20230101&dataFinal=20231231&cnpjOrgao={cnpj}&pagina=1&tamanhoPagina=2"

print(f"Consultando: {url}")
try:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30, context=_SSL) as r:
        raw = r.read().decode("utf-8", "replace")
        print(f"Status: {r.status}")
        data = json.loads(raw)
    
    results = data.get("data", [])
    if results:
        print(f"\nTotal de contratos disponíveis: {data.get('totalRegistros', 'N/A')}")
        print(f"\nCampos do PRIMEIRO contrato:")
        item = results[0]
        for k, v in item.items():
            print(f"  {k}: {repr(v)[:100]}")
    else:
        print("Sem dados. Resposta bruta:")
        print(raw[:1000])
except Exception as e:
    print(f"Erro: {e}")
