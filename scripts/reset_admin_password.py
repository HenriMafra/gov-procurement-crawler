# -*- coding: utf-8 -*-
"""Reseta a senha de um usuário do Painel Admin (recuperação de acesso).
  python scripts/reset_admin_password.py --username admin --password "NOVA_SENHA"
"""
import os, sys, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "admin_panel"))
import auth  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    ap.add_argument("--password", required=True)
    a = ap.parse_args()
    if not auth.get_user(a.username):
        print(f"ERRO: usuário '{a.username}' não existe."); sys.exit(1)
    auth.set_password(a.username, a.password)
    auth.set_active(a.username, True)
    print(f"OK: senha de '{a.username}' redefinida e usuário reativado.")

if __name__ == "__main__":
    main()
