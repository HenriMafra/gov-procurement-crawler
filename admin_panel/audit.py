# -*- coding: utf-8 -*-
"""Auditoria do Painel Admin: registra quem fez o quê, quando e o resultado."""
from db import conn, init

def log(usuario, perfil, acao, detalhes="", parametros="", resultado="OK", erro="", duracao=None, local="painel-local"):
    init(); c = conn()
    c.execute("""INSERT INTO audit_logs (usuario,perfil,acao,detalhes,parametros,resultado,erro,duracao,local)
                 VALUES (?,?,?,?,?,?,?,?,?)""",
              (usuario, perfil, acao, str(detalhes)[:2000], str(parametros)[:1000], resultado, str(erro)[:2000], duracao, local))
    c.commit(); c.close()

def read(usuario=None, acao=None, resultado=None, perfil=None, limit=300):
    init(); c = conn()
    q = "SELECT data_hora,usuario,perfil,acao,resultado,duracao,detalhes,erro FROM audit_logs WHERE 1=1"
    p = []
    if usuario: q += " AND usuario=?"; p.append(usuario)
    if acao: q += " AND acao=?"; p.append(acao)
    if resultado: q += " AND resultado=?"; p.append(resultado)
    if perfil: q += " AND perfil=?"; p.append(perfil)
    q += " ORDER BY id DESC LIMIT ?"; p.append(limit)
    rows = c.execute(q, p).fetchall(); c.close()
    return [dict(r) for r in rows]

def acoes_distintas():
    init(); c = conn()
    rows = c.execute("SELECT DISTINCT acao FROM audit_logs ORDER BY acao").fetchall(); c.close()
    return [r["acao"] for r in rows]
