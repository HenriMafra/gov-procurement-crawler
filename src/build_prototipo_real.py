# -*- coding: utf-8 -*-
"""Regera o protótipo a partir de um CSV de lista de ataque (uso manual/avulso).
Por padrão usa o CSV da rodada mais recente em outputs/rodadas/.
  python src/build_prototipo_real.py [--csv caminho.csv] [--out pasta]"""
import os, sys, csv, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import atlas_weekly_runner as R  # reusa gerar_prototipo/to_js (main() é guardado)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--csv"); ap.add_argument("--out")
    a = ap.parse_args()
    csvp = a.csv
    if not csvp:
        cands = sorted(glob.glob(R.P("outputs", "rodadas", "*", "atlas_lista_ataque_comercial_*.csv")))
        if not cands:
            print("Nenhum CSV de rodada encontrado em outputs/rodadas/."); return
        csvp = cands[-1]
    rows = list(csv.DictReader(open(csvp, encoding="utf-8-sig")))
    for r in rows:
        try: r["Valor Total"] = float(r["Valor Total"])
        except Exception: r["Valor Total"] = 0
        try: r["Score de Oportunidade"] = int(float(r["Score de Oportunidade"]))
        except Exception: r["Score de Oportunidade"] = 0
    base = a.out or os.path.dirname(csvp)
    html = os.path.join(base, "ATLAS-B2G_Prototipo-Dados-Reais-PNCP.html")
    js = os.path.join(base, "atlas_dados_reais_prototipo.js")
    R.gerar_prototipo(rows, html, js)
    print("Protótipo gerado:", html)

if __name__ == "__main__":
    main()
