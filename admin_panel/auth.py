# -*- coding: utf-8 -*-
"""Autenticação e autorização (RBAC) do Painel Admin ATLAS B2G."""
import bcrypt
from db import conn, init

ROLES = ["Administrador", "Operador de Inteligência", "Coordenador Comercial", "Vendedor", "Diretoria"]

# Ações que exigem perfil Administrador + confirmação explícita
CRITICAL = {
    "run_prod", "run_prod_db", "reprocess", "archive_round", "edit_config_tecnica",
    "edit_score", "edit_concorrentes", "edit_responsaveis", "schedule", "pause_automation",
    "export_full", "manage_users", "configure_db", "edit_credentials",
}

# Conjunto completo de ações
ALL_ACTIONS = CRITICAL | {
    "run_test", "load_db", "gen_package", "update_prototype", "open_files", "view_logs",
    "view_audit", "view_rodadas", "view_db", "view_commercial", "view_dashboards",
    "edit_config_comercial", "distribute", "assign_vendor", "update_status", "register_contact",
}

PERMS = {
    "Administrador": set(ALL_ACTIONS),
    "Operador de Inteligência": {
        "run_test", "load_db", "gen_package", "update_prototype", "open_files", "view_logs",
        "view_audit", "view_rodadas", "view_db", "view_commercial", "view_dashboards", "edit_config_comercial",
    },
    "Coordenador Comercial": {
        "open_files", "view_rodadas", "view_commercial", "view_dashboards", "distribute",
        "assign_vendor", "update_status",
    },
    "Vendedor": {"view_commercial", "register_contact", "update_status"},
    "Diretoria": {"view_commercial", "view_dashboards", "open_files"},
}

ACESSO_NEGADO = "Acesso negado. Esta área exige perfil Administrador."

def is_admin(role): return role == "Administrador"
def has_permission(role, action): return action in PERMS.get(role, set())
def is_critical(action): return action in CRITICAL

# ---------- senhas ----------
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(pw: str, h: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False

# ---------- usuários ----------
def create_user(username, password, role, email="", nome=""):
    if role not in ROLES:
        raise ValueError(f"Perfil inválido. Use um de: {ROLES}")
    if not username or not password or len(password) < 6:
        raise ValueError("Usuário obrigatório e senha com pelo menos 6 caracteres.")
    init(); c = conn()
    try:
        c.execute("INSERT INTO users (username,password_hash,role,email,nome,ativo) VALUES (?,?,?,?,?,1)",
                  (username, hash_password(password), role, email, nome))
        c.commit()
    except Exception as e:
        c.close()
        raise ValueError(f"Não foi possível criar usuário: {e}")
    c.close()
    return True

def get_user(username):
    init(); c = conn()
    r = c.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    c.close()
    return dict(r) if r else None

def validate_login(username, password):
    """Retorna o dict do usuário se ok; None caso contrário. Atualiza last_login."""
    u = get_user(username)
    if not u or not u["ativo"] or not verify_password(password, u["password_hash"]):
        return None
    c = conn(); c.execute("UPDATE users SET last_login=datetime('now','localtime') WHERE username=?", (username,)); c.commit(); c.close()
    return {k: u[k] for k in ("id", "username", "role", "email", "nome")}

def set_password(username, new_password):
    if len(new_password) < 6:
        raise ValueError("Senha deve ter pelo menos 6 caracteres.")
    init(); c = conn()
    c.execute("UPDATE users SET password_hash=? WHERE username=?", (hash_password(new_password), username))
    n = c.total_changes; c.commit(); c.close()
    return n > 0

def set_active(username, ativo):
    init(); c = conn()
    c.execute("UPDATE users SET ativo=? WHERE username=?", (1 if ativo else 0, username))
    c.commit(); c.close()

def set_role(username, role):
    if role not in ROLES: raise ValueError("Perfil inválido.")
    init(); c = conn()
    c.execute("UPDATE users SET role=? WHERE username=?", (role, username)); c.commit(); c.close()

def list_users():
    init(); c = conn()
    rows = c.execute("SELECT username, role, email, nome, ativo, created_at, last_login FROM users ORDER BY username").fetchall()
    c.close()
    return [dict(r) for r in rows]

def count_admins_ativos():
    init(); c = conn()
    n = c.execute("SELECT COUNT(*) FROM users WHERE role='Administrador' AND ativo=1").fetchone()[0]
    c.close(); return n
