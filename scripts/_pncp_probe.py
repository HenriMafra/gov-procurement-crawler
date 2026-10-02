import urllib.request, json
def total(di, df):
    url=f"https://pncp.gov.br/api/consulta/v1/contratos?dataInicial={di}&dataFinal={df}&pagina=1&tamanhoPagina=10"
    try:
        req=urllib.request.Request(url, headers={"Accept":"application/json","User-Agent":"atlas/1.0"})
        with urllib.request.urlopen(req, timeout=45) as r:
            body=r.read().decode("utf-8","replace")
            if not body.strip(): return "(corpo vazio - throttle)"
            d=json.loads(body)
            return d.get("totalRegistros", d.get("totalElementos","?"))
    except Exception as e:
        return f"ERRO {type(e).__name__}: {e}"
for label,di,df in [
    ("2021 ano","20210101","20211231"),
    ("2022 ano","20220101","20221231"),
    ("2023 ano","20230101","20231231"),
    ("2024 ano","20240101","20241231"),
    ("2025 ano","20250101","20251231"),
    ("2026 parcial","20260101","20260601"),
]:
    print(f"{label:14s} totalRegistros(nacional) = {total(di,df)}")
