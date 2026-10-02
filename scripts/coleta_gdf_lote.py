# -*- coding: utf-8 -*-
"""
Coleta em lote de contratos via Portal Transparência GDF (mesma API usada p/ ADASA).
Cobre órgãos do Distrito Federal da lista de 221 entidades que NÃO estão no cache PNCP.
"""
import urllib.request, ssl, json, re, datetime, time
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
BASE = 'https://www.transparencia.df.gov.br/api/licitacoes-contratos/contrato'
EXCEL_PATH = r"C:\Users\henri\Desktop\coleta_orgaos_lista_completa_DF.xlsx"
HOJE = datetime.date.today()

ORGAOS_DF = [
    ("TERRACAP", "190203", "Companhia Imobiliária de Brasília - TERRACAP", "00.359.877/0001-73"),
    ("PCDF", "220105", "Polícia Civil do Distrito Federal", "00.000.000/0001-00"),
    ("PMDF", "220103", "Polícia Militar do Distrito Federal", "00.000.000/0001-00"),
    ("SEEC", "130101", "Secretaria de Estado de Economia do DF", "00.000.000/0001-00"),
    ("SES-DF", "170101", "Secretaria de Estado de Saúde do DF", "00.000.000/0001-00"),
    ("DEFENSORIA-DF", "480101", "Defensoria Pública do Distrito Federal", "04.171.128/0001-59"),
    ("CBMDF", "220104", "Corpo de Bombeiros Militar do DF", "00.000.000/0001-00"),
    ("DETRAN-DF", "220201", "Departamento de Trânsito do DF", "00.000.000/0001-00"),
    ("DER-DF", "200202", "Departamento de Estradas e Rodagem do DF", "00.000.000/0001-00"),
    ("PGDF", "120101", "Procuradoria-Geral do Distrito Federal", "00.000.000/0001-00"),
]

ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
def san(v):
    if isinstance(v, str):
        return ILLEGAL.sub("", v).strip()
    return v

def get_json(url, timeout=20):
    try:
        req = urllib.request.Request(url, headers=UA)
        r = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return json.loads(r.read().decode('utf-8', errors='replace'))
    except Exception as e:
        print(f"    ERRO {url[-60:]}: {e}")
        return {}

def normalizar_data(s):
    if not s:
        return ""
    try:
        return datetime.datetime.strptime(str(s).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except:
        return str(s)

def processar_item(item, sigla, nome_orgao, cnpj_orgao):
    dt_ini = normalizar_data(item.get("dataInicio"))
    dt_fim = normalizar_data(item.get("dataFim"))
    valor = float(item.get("valorContrato") or 0)
    status = "N/D"
    if dt_fim:
        try:
            df_date = datetime.datetime.strptime(dt_fim[:10], "%Y-%m-%d").date()
            status = "Vigente" if df_date >= HOJE else "Expirado"
        except:
            pass
    return {
        "grupo": sigla, "sigla": sigla,
        "orgao": f"{sigla} - {nome_orgao}",
        "cnpj_orgao": cnpj_orgao,
        "unidade": san(item.get("unidadeGestora") or ""),
        "num_contrato": san(item.get("numeroOriginal") or item.get("numeroContrato") or ""),
        "fornecedor": san(item.get("credor") or ""),
        "cnpj_fornecedor": san(item.get("codigoCredorMascarado") or ""),
        "objeto": san(item.get("objeto") or ""),
        "valor": valor,
        "dt_assinatura": "", "dt_inicio": dt_ini, "dt_fim": dt_fim,
        "status": status,
        "modalidade": san(item.get("especie") or ""),
        "link": "https://www.transparencia.df.gov.br/#/licitacoes-contratos/contratos",
        "fonte": "Portal Transparência GDF (SIGGO)",
    }

def coletar_orgao(sigla, ug, nome_orgao, cnpj_orgao):
    contratos = {}
    for ano in range(1998, 2027):
        pagina = 0
        while True:
            url = f"{BASE}?anoInicio={ano}&listaCodigoUnidadeGestora={ug}&page={pagina}&size=100"
            r = get_json(url)
            content = r.get("content", [])
            if not content:
                break
            for item in content:
                chave = item.get("numeroContrato", "") + "_" + item.get("numeroOriginal", "")
                if chave not in contratos:
                    contratos[chave] = processar_item(item, sigla, nome_orgao, cnpj_orgao)
            total_pages = r.get("totalPages", 1)
            pagina += 1
            if pagina >= total_pages:
                break
            time.sleep(0.15)
        time.sleep(0.2)
    return list(contratos.values())

HDRS = ["Grupo","Sigla","Orgao Contratante","CNPJ Orgao","Unidade",
        "Num Contrato","Fornecedor Contratado","CNPJ Fornecedor",
        "Objeto do Contrato","Valor Total (R$)","Assinatura",
        "Inicio Vigencia","Fim Vigencia","Status","Modalidade","Link"]
WIDTHS = [14,14,42,18,30,15,35,18,60,16,13,13,13,10,20,50]

def write_header(ws, fh, ac, fill_hdr):
    for ci, h in enumerate(HDRS, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = fh; c.alignment = ac; c.fill = fill_hdr
    ws.row_dimensions[1].height = 22

def write_row(ws, ri, r, fb, al, ac, ar, brd, fill_vg, fill_ex):
    vals = [r["grupo"],r["sigla"],r["orgao"],r["cnpj_orgao"],r["unidade"],
            r["num_contrato"],r["fornecedor"],r["cnpj_fornecedor"],
            r["objeto"],r["valor"],r["dt_assinatura"],r["dt_inicio"],
            r["dt_fim"],r["status"],r["modalidade"],r["link"]]
    fr = fill_vg if r["status"]=="Vigente" else (fill_ex if r["status"]=="Expirado" else None)
    for ci, v in enumerate(vals, 1):
        c = ws.cell(row=ri, column=ci, value=v)
        c.font = fb; c.border = brd
        c.alignment = ar if ci==10 else (al if ci in (3,5,7,9,15,16) else ac)
        if ci == 10: c.number_format = "R$ #,##0.00"
        if fr: c.fill = fr
    ws.row_dimensions[ri].height = 28

if __name__ == "__main__":
    print("=== Coleta em lote — órgãos DF via Portal Transparência GDF ===")
    wb = Workbook()
    wb.remove(wb.active)

    fh = Font(name="Segoe UI", size=10, bold=True, color="FFFFFF")
    fb = Font(name="Segoe UI", size=10)
    al = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ac = Alignment(horizontal="center", vertical="center")
    ar = Alignment(horizontal="right", vertical="center")
    fill_hdr = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    fill_vg  = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    fill_ex  = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    brd = Border(left=Side(style="thin",color="D0D0D0"),right=Side(style="thin",color="D0D0D0"),
                 top=Side(style="thin",color="D0D0D0"),bottom=Side(style="thin",color="D0D0D0"))

    ws_all = wb.create_sheet("Todos")
    write_header(ws_all, fh, ac, fill_hdr)
    nxt_all = 2

    resumo = []
    for sigla, ug, nome_orgao, cnpj_orgao in ORGAOS_DF:
        print(f"Coletando {sigla} (UG {ug})...")
        contratos = coletar_orgao(sigla, ug, nome_orgao, cnpj_orgao)
        vg = sum(1 for c in contratos if c["status"]=="Vigente")
        val = sum(c["valor"] for c in contratos)
        print(f"  {sigla}: {len(contratos)} contratos ({vg} vigentes), R$ {val:,.0f}")
        resumo.append((sigla, len(contratos), vg, val))

        ws = wb.create_sheet(sigla[:31])
        write_header(ws, fh, ac, fill_hdr)
        rows_sorted = sorted(contratos, key=lambda x: -x["valor"])
        for ri, r in enumerate(rows_sorted, 2):
            write_row(ws, ri, r, fb, al, ac, ar, brd, fill_vg, fill_ex)
            write_row(ws_all, nxt_all, r, fb, al, ac, ar, brd, fill_vg, fill_ex)
            nxt_all += 1
        for ci, w in enumerate(WIDTHS, 1):
            ws.column_dimensions[get_column_letter(ci)].width = w

    for ci, w in enumerate(WIDTHS, 1):
        ws_all.column_dimensions[get_column_letter(ci)].width = w

    # Painel resumo
    ws_p = wb.create_sheet("Painel", 0)
    ws_p.cell(row=1, column=1, value=f"Órgãos DF — coletados via Portal Transparência GDF — {HOJE}").font = Font(bold=True, size=13)
    hdrs_p = ["Sigla", "Qtd Contratos", "Vigentes", "Valor Total (R$)"]
    for ci, h in enumerate(hdrs_p, 1):
        c = ws_p.cell(row=2, column=ci, value=h)
        c.font = fh; c.fill = fill_hdr; c.alignment = ac
    for ri, (sigla, qtd, vg, val) in enumerate(resumo, 3):
        ws_p.cell(row=ri, column=1, value=sigla)
        ws_p.cell(row=ri, column=2, value=qtd)
        ws_p.cell(row=ri, column=3, value=vg)
        c = ws_p.cell(row=ri, column=4, value=val)
        c.number_format = "R$ #,##0.00"
    for ci, w in enumerate([20,15,12,20], 1):
        ws_p.column_dimensions[get_column_letter(ci)].width = w

    wb.save(EXCEL_PATH)
    total = sum(r[1] for r in resumo)
    print(f"\n=== TOTAL: {total} contratos coletados de {len(ORGAOS_DF)} órgãos DF ===")
    print(f"Salvo em: {EXCEL_PATH}")
