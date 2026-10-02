# -*- coding: utf-8 -*-
"""
ATLAS B2G — Rotina diária das fontes não-PNCP (estatais/fundações do DF).

Roda todos os coletores dedicados (--write-db) em sequência e depois
`pos_processar_nao_pncp.py` para classificar as oportunidades de TI.
Idempotente (upsert por contrato_key) — pode rodar todo dia sem duplicar
nem sem repetir trabalho: cada fonte só grava o que for novo/mudou.

Pensado para cron diário (~5-10 min de execução total, a maioria das
fontes é scraping leve; CEASA-DF via Playwright é a mais pesada).

Uso:
  python src/coleta_nao_pncp_diaria.py --db-url postgresql://...
  python src/coleta_nao_pncp_diaria.py --db-url ... --pular CEASA-DF
"""
import os, sys, argparse, subprocess, datetime, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# nome amigável -> módulo do coletor (todos seguem o mesmo contrato:
# --write-db --db-url grava direto no banco via upsert)
COLETORES = [
    ("CIASC-SC", "collectors/coletor_ciasc_sc.py"),
    ("SENAC-SC", "collectors/coletor_senac_sc.py"),
    ("SESC-SC", "collectors/coletor_sesc_sc.py"),
    ("BBTS", "collectors/coletor_bbts.py"),
    ("FIEG", "collectors/coletor_fieg.py"),
    ("EBC", "collectors/coletor_ebc.py"),
    ("SENAC-PR", "collectors/coletor_senac_pr.py"),
    ("PREGAO-BANRISUL", "collectors/coletor_pregao_banrisul.py"),
    ("ABDI", "collectors/coletor_abdi.py"),
    ("SENAC-DF", "collectors/coletor_senac_df.py"),
    ("NOVACAP", "collectors/coletor_novacap.py"),
    ("CODHAB-DF", "collectors/coletor_codhab.py"),
    ("CAESB", "collectors/coletor_caesb.py"),
    ("METRO-DF", "collectors/coletor_metro_df.py"),
    ("TCB", "collectors/coletor_tcb.py"),
    ("EMATER-DF", "collectors/coletor_emater_df.py"),
    ("TERRACAP", "collectors/coletor_terracap.py"),
    ("CEASA-DF", "collectors/coletor_ceasa_df.py"),  # Playwright — mais pesado, roda por último
]

ROOT = os.path.dirname(os.path.abspath(__file__))
_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")


def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def rodar(nome, script_rel, db_url, timeout_s=900):
    script = os.path.join(ROOT, script_rel)
    log(f"=== {nome} ===")
    try:
        r = subprocess.run(
            [sys.executable, script, "--write-db", "--db-url", db_url],
            cwd=ROOT, capture_output=True, text=True, timeout=timeout_s, env=_ENV,
            encoding="utf-8", errors="replace",
        )
        tail = "\n".join((r.stdout or "").splitlines()[-6:])
        if r.returncode != 0:
            log(f"  FALHOU (rc={r.returncode}): {(r.stderr or r.stdout or '')[-800:]}")
            return False
        log(f"  OK: {tail}")
        return True
    except subprocess.TimeoutExpired:
        log(f"  TIMEOUT após {timeout_s}s — pulando")
        return False
    except Exception as e:
        log(f"  ERRO inesperado: {e}\n{traceback.format_exc()[-500:]}")
        return False


def rodar_pos_processar(db_url):
    log("=== pos_processar_nao_pncp (classificação TI) ===")
    try:
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "pos_processar_nao_pncp.py"), "--db-url", db_url],
            cwd=ROOT, capture_output=True, text=True, timeout=1800, env=_ENV,
            encoding="utf-8", errors="replace",
        )
        log(r.stdout[-1500:] if r.stdout else "(sem saída)")
        if r.returncode != 0:
            log(f"  FALHOU: {(r.stderr or r.stdout or '(sem detalhes)')[-800:]}")
    except Exception as e:
        log(f"  ERRO: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--pular", nargs="*", default=[], help="Nomes de fontes a pular nesta execução")
    ap.add_argument("--apenas", nargs="*", default=None, help="Rodar só estas fontes (nome)")
    args = ap.parse_args()
    if not args.db_url:
        print("ERRO: informe --db-url ou defina $DATABASE_URL"); sys.exit(1)

    t0 = datetime.datetime.now()
    log(f"=== ATLAS B2G — coleta não-PNCP diária ({t0:%Y-%m-%d %H:%M}) ===")
    ok, falhas = 0, []
    for nome, script in COLETORES:
        if nome in args.pular:
            log(f"=== {nome} (pulado por --pular) ==="); continue
        if args.apenas and nome not in args.apenas:
            continue
        # CEASA-DF (Playwright, ~70 navegações) e CIASC-SC/PREGAO-BANRISUL (centenas de
        # registros gravados um a um) são as mais lentas, sobretudo na VM 24/7 (CPU/rede
        # mais fracas que uma máquina local) — testado: CIASC-SC estourou os 300s antigos.
        if nome == "CEASA-DF":
            timeout_s = 1200
        elif nome in ("CIASC-SC", "PREGAO-BANRISUL", "SENAC-SC"):
            timeout_s = 700
        else:
            timeout_s = 350
        if rodar(nome, script, args.db_url, timeout_s):
            ok += 1
        else:
            falhas.append(nome)

    rodar_pos_processar(args.db_url)

    dt = (datetime.datetime.now() - t0).total_seconds()
    log(f"=== concluído em {dt:.0f}s — {ok}/{len(COLETORES)} fontes OK "
        f"{'(falhas: ' + ', '.join(falhas) + ')' if falhas else ''} ===")


if __name__ == "__main__":
    main()
