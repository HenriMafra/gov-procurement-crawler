# -*- coding: utf-8 -*-
"""Cria o primeiro usuário do Painel Admin (senha armazenada como hash bcrypt).
  python scripts/create_admin_user.py --username admin --password "SENHA_SEGURA" --role Administrador
"""
import os, sys, argparse
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "admin_panel"))
import auth  # noqa

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--role", default="Administrador", choices=auth.ROLES)
    ap.add_argument("--email", default="")
    ap.add_argument("--nome", default="")
    a = ap.parse_args()
    auth.create_user(a.username, a.password, a.role, a.email, a.nome)
    print(f"OK: usuário '{a.username}' criado com perfil '{a.role}'. Senha armazenada como hash bcrypt (nunca em texto puro).")

if __name__ == "__main__":
    main()
