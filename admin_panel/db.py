# -*- coding: utf-8 -*-
"""Banco local (SQLite) do Painel Admin: usuários, auditoria, sessões e settings.
Separado do banco operacional (Supabase/PostgreSQL) — aqui só vive o controle de acesso."""
import os, sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("ATLAS_ADMIN_DB", os.path.join(HERE, "users.db"))

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      role TEXT NOT NULL DEFAULT 'Vendedor',
      email TEXT, nome TEXT,
      ativo INTEGER DEFAULT 1,
      created_at TEXT DEFAULT (datetime('now','localtime')),
      last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS audit_logs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      usuario TEXT, perfil TEXT, acao TEXT, detalhes TEXT, parametros TEXT,
      resultado TEXT, erro TEXT, duracao REAL, local TEXT,
      data_hora TEXT DEFAULT (datetime('now','localtime'))
    );
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT, token TEXT, criado_em TEXT DEFAULT (datetime('now','localtime')),
      expira_em TEXT, ativo INTEGER DEFAULT 1
    );
    CREATE TABLE IF NOT EXISTS app_settings (
      chave TEXT PRIMARY KEY, valor TEXT, updated_at TEXT DEFAULT (datetime('now','localtime'))
    );
    """)
    c.commit(); c.close()

def get_setting(chave, default=None):
    init(); c = conn()
    r = c.execute("SELECT valor FROM app_settings WHERE chave=?", (chave,)).fetchone()
    c.close()
    return r["valor"] if r else default

def set_setting(chave, valor):
    init(); c = conn()
    c.execute("INSERT INTO app_settings(chave,valor) VALUES(?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor, updated_at=datetime('now','localtime')", (chave, valor))
    c.commit(); c.close()
