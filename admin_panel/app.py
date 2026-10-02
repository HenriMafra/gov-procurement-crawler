# -*- coding: utf-8 -*-
"""ATLAS B2G — Painel Administrativo Seguro (Streamlit).
Login + RBAC + auditoria + operação por botão. Camada administrativa do ATLAS B2G."""
import os, sys, json
import streamlit as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, auth, audit, runner, config_editor
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", ".env"))
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

st.set_page_config(page_title="ATLAS B2G — Painel Admin", page_icon="🎯", layout="wide")
db.init()

# ----------------- LOGIN -----------------
def tela_login():
    c = st.columns([1, 1.4, 1])[1]
    with c:
        st.markdown("## 🎯 ATLAS B2G — Painel Administrativo")
        st.caption("Acesso restrito · autenticação obrigatória · ações auditadas.")
        with st.form("login"):
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", use_container_width=True)
        if entrar:
            user = auth.validate_login((u or "").strip(), p or "")
            if user:
                st.session_state.user = user
                audit.log(user["username"], user["role"], "login", resultado="OK")
                st.rerun()
            else:
                audit.log((u or "(vazio)").strip(), "-", "login", resultado="FALHA", erro="credenciais inválidas")
                st.error("Usuário ou senha inválidos.")
        if auth.count_admins_ativos() == 0:
            st.info("Nenhum administrador cadastrado. Crie o primeiro com:\n\n"
                    "`python scripts/create_admin_user.py --username admin --password \"SUA_SENHA\" --role Administrador`")

if "user" not in st.session_state:
    tela_login(); st.stop()

USER = st.session_state.user
ROLE = USER["role"]
DB_URL = os.environ.get("DATABASE_URL")

def pode(action): return auth.has_permission(ROLE, action)

# ----------------- NAV -----------------
PAGINAS = [
    ("Home", None), ("Automação", "edit_config_tecnica"), ("Operação", "run_test"), ("Rodadas", "view_rodadas"),
    ("Arquivos Gerados", "open_files"), ("Configurações Comerciais", "edit_config_comercial"),
    ("Configurações Técnicas", "edit_config_tecnica"), ("Banco de Dados", "view_db"),
    ("Logs", "view_logs"), ("Auditoria", "view_audit"), ("Usuários e Permissões", "manage_users"),
    ("Ajuda", None),
]
visiveis = [p for p, perm in PAGINAS if perm is None or pode(perm)]

with st.sidebar:
    st.markdown("### 🎯 ATLAS B2G")
    st.markdown(f"**{USER['username']}**")
    st.caption(f"Perfil: **{ROLE}**")
    if not DB_URL:
        st.caption("🟡 Banco: não configurado")
    else:
        st.caption("🟢 Banco: configurado")
    pagina = st.radio("Navegação", visiveis, label_visibility="collapsed")
    st.divider()
    if st.button("🚪 Sair", use_container_width=True):
        audit.log(USER["username"], ROLE, "logout")
        del st.session_state.user; st.rerun()

# ----------------- HELPERS -----------------
def negado():
    st.error(auth.ACESSO_NEGADO)

def botao_critico(label, action, key, help_txt=""):
    """Botão crítico: exige permissão (Admin) + confirmação explícita (checkbox)."""
    if not pode(action):
        st.button(label, key=key, disabled=True, help=auth.ACESSO_NEGADO, use_container_width=True)
        return False
    conf = st.checkbox(f"Confirmo: {label}", key=key + "_chk")
    return st.button(label, key=key, disabled=not conf, type="primary", use_container_width=True, help=help_txt)

def executar(acao_nome, func, *args, **kw):
    with st.spinner("Executando… pode levar alguns minutos. Não feche a janela."):
        res = func(*args, **kw)
    audit.log(USER["username"], ROLE, acao_nome,
              resultado=("OK" if res.get("ok") else "ERRO"),
              detalhes=res.get("resumo", ""), erro=(res.get("err", "") or "")[:800], duracao=res.get("dur"))
    st.session_state.last_op = {"acao": acao_nome, **res}
    return res

def mostra_resultado():
    res = st.session_state.get("last_op")
    if not res: return
    st.divider()
    if res.get("ok"):
        st.success(f"✅ {res['acao']} concluído em {res.get('dur','?')}s.")
        if res.get("resumo"): st.code(res["resumo"])
    else:
        st.error(f"❌ {res['acao']} falhou (código {res.get('code')}).")
        st.caption("Sugestão: verifique a conexão de internet / API do PNCP e tente novamente, ou veja o log completo.")
    with st.expander("Ver saída técnica (stdout / stderr)"):
        st.text((res.get("out", "") or "")[-4000:])
        if res.get("err"): st.text("STDERR:\n" + res["err"][-2000:])

# ===================================================== HOME
def page_home():
    st.title("Home Administrativa")
    s = runner.obter_status_ultima_rodada()
    st.subheader("Status da última rodada")
    if not s.get("existe"):
        st.info("Nenhuma rodada encontrada ainda. Rode um teste ou a produção na página **Operação**.")
    else:
        c = st.columns(5)
        c[0].metric("Rodada", s.get("data", "—"))
        c[1].metric("Modo", s.get("tag") or "—")
        c[2].metric("Oportunidades", s.get("oportunidades", "—"))
        c[3].metric("Críticas", s.get("criticas", "—"))
        c[4].metric("Valor mapeado", s.get("valor", "—"))
        bstat = runner.obter_status_banco(DB_URL)
        st.caption(("🟢 Banco: " + bstat.get("msg", "")) if bstat.get("configurado") else "🟡 " + bstat.get("msg", ""))
    st.divider()
    st.subheader("Ações rápidas")
    col = st.columns(3)
    with col[0]:
        if pode("run_test") and st.button("▶️ Rodar teste rápido", use_container_width=True):
            executar("run_test", runner.rodar_teste); st.rerun()
        if pode("load_db") and st.button("🗄️ Carregar última rodada no banco", use_container_width=True):
            rd = runner._ultima_rodada_dir()
            executar("load_db", runner.carregar_rodada_no_banco, rd, DB_URL); st.rerun()
    with col[1]:
        if botao_critico("🚀 Rodar produção agora", "run_prod", "h_prod",
                         "Executa a rodada de produção (pode levar minutos)."):
            executar("run_prod", runner.rodar_producao); st.rerun()
    with col[2]:
        if not DB_URL:
            st.button("💾 Rodar produção + banco", disabled=True, use_container_width=True,
                      help="Banco não configurado. Defina DATABASE_URL.")
        elif botao_critico("💾 Rodar produção + banco", "run_prod_db", "h_proddb",
                           "Roda produção e grava no banco."):
            executar("run_prod_db", runner.rodar_producao_com_banco, DB_URL); st.rerun()
    mostra_resultado()

# ===================================================== OPERAÇÃO
def page_operacao():
    st.title("Operação")
    st.caption("Execute a máquina ATLAS. Ações críticas exigem perfil Administrador e confirmação.")
    a, b = st.columns(2)
    with a:
        st.markdown("#### Coleta / Geração")
        if pode("run_test") and st.button("▶️ Rodar teste rápido", use_container_width=True):
            executar("run_test", runner.rodar_teste); st.rerun()
        if botao_critico("🚀 Rodar produção agora", "run_prod", "op_prod"):
            executar("run_prod", runner.rodar_producao); st.rerun()
        if not DB_URL:
            st.button("💾 Rodar produção + banco", disabled=True, use_container_width=True, help="Banco não configurado.")
        elif botao_critico("💾 Rodar produção + banco", "run_prod_db", "op_proddb"):
            executar("run_prod_db", runner.rodar_producao_com_banco, DB_URL); st.rerun()
    with b:
        st.markdown("#### Pós-processamento")
        rd = runner._ultima_rodada_dir()
        if pode("load_db"):
            if st.button("🗄️ Carregar última rodada no banco", use_container_width=True):
                executar("load_db", runner.carregar_rodada_no_banco, rd, DB_URL); st.rerun()
        else:
            st.button("🗄️ Carregar última rodada no banco", disabled=True, help=auth.ACESSO_NEGADO, use_container_width=True)
        if pode("update_prototype") and st.button("🖥️ Atualizar protótipo (dados reais)", use_container_width=True):
            executar("update_prototype", runner.atualizar_prototipo, rd); st.rerun()
        if pode("gen_package") and st.button("📦 Localizar pacote comercial", use_container_width=True):
            r = runner.gerar_pacote(rd); st.session_state.last_op = {"acao": "gen_package", "ok": r.get("ok"), "resumo": (r.get("zip") or r.get("err"))}; st.rerun()
    st.info("Etapas de uma rodada: preparar → coletar PNCP → classificar TI → calcular score → "
            "gerar Excel → relatório → protótipo → ZIP → (banco) → auditoria.")
    mostra_resultado()

# ===================================================== RODADAS
def page_rodadas():
    st.title("Rodadas")
    rs = runner.listar_rodadas()
    if not rs:
        st.info("Nenhuma rodada gerada ainda."); return
    st.dataframe([{"Pasta": r["pasta"], "Data": r["data"], "Tag": r["tag"], "Oportunidades": r.get("oportunidades"),
                   "Críticas": r.get("criticas"), "Valor": r.get("valor"),
                   "Excel": "✓" if r["tem_excel"] else "", "Relatório": "✓" if r["tem_relatorio"] else "",
                   "Protótipo": "✓" if r["tem_prototipo"] else "", "ZIP": "✓" if r["tem_zip"] else ""} for r in rs],
                 use_container_width=True, hide_index=True)
    nomes = [r["pasta"] for r in rs]
    sel = st.selectbox("Selecionar rodada", nomes)
    rd = next(r["caminho"] for r in rs if r["pasta"] == sel)
    cam = runner.caminhos_rodada(rd)
    cols = st.columns(5)
    if cols[0].button("📂 Abrir pasta"): runner.abrir_caminho(rd); audit.log(USER["username"], ROLE, "open_files", detalhes="pasta " + sel)
    if cols[1].button("📊 Abrir Excel", disabled=not (pode("open_files") and cam["excel"])): runner.abrir_caminho(cam["excel"]); audit.log(USER["username"], ROLE, "open_files", detalhes="excel " + sel)
    if cols[2].button("📄 Abrir relatório", disabled=not (pode("open_files") and cam["relatorio"])): runner.abrir_caminho(cam["relatorio"]); audit.log(USER["username"], ROLE, "open_files", detalhes="relatorio " + sel)
    if cols[3].button("🖥️ Abrir protótipo", disabled=not (pode("open_files") and cam["prototipo"])): runner.abrir_caminho(cam["prototipo"]); audit.log(USER["username"], ROLE, "open_files", detalhes="prototipo " + sel)
    if cols[4].button("📦 Abrir ZIP", disabled=not (pode("open_files") and cam["zip"])): runner.abrir_caminho(cam["zip"]); audit.log(USER["username"], ROLE, "open_files", detalhes="zip " + sel)
    c2 = st.columns(3)
    if pode("load_db") and c2[0].button("🗄️ Carregar esta rodada no banco"):
        executar("load_db", runner.carregar_rodada_no_banco, rd, DB_URL); st.rerun()
    if c2[1].button("📋 Ver log desta rodada"):
        st.code(runner.ler_logs(rd))
    if pode("reprocess"):
        if botao_critico("♻️ Reprocessar (rodar de novo nesta data)", "reprocess", "rep_" + sel):
            st.warning("Reprocessar regenera os arquivos da rodada. Use a página Operação para rodar produção.")
    mostra_resultado()

# ===================================================== ARQUIVOS
def page_arquivos():
    st.title("Arquivos Gerados")
    rd = runner._ultima_rodada_dir()
    if not rd: st.info("Sem rodadas."); return
    cam = runner.caminhos_rodada(rd)
    st.caption("Última rodada: " + os.path.basename(rd))
    for label, key in [("📊 Excel executivo", "excel"), ("📄 Relatório semanal", "relatorio"),
                       ("🖥️ Protótipo (dados reais)", "prototipo"), ("📦 Pacote ZIP", "zip"),
                       ("🧭 Mapa de distribuição", "mapa"), ("🧪 Relatório de calibração", "calibracao"),
                       ("📋 Log de execução", "log")]:
        c1, c2 = st.columns([3, 1])
        c1.write(f"{label}: `{os.path.basename(cam[key]) if cam[key] else '— ausente —'}`")
        if c2.button("Abrir", key="open_" + key, disabled=not (pode("open_files") and cam[key])):
            runner.abrir_caminho(cam[key]); audit.log(USER["username"], ROLE, "open_files", detalhes=key)

# ===================================================== CONFIG COMERCIAL
def _edit_config(nome, titulo, campos_comerciais=True):
    st.subheader(titulo + f"  ·  `{nome}`")
    try:
        cfg = config_editor.load(nome)
    except Exception as e:
        st.error(f"Não foi possível ler {nome}: {e}"); return
    novo = dict(cfg)
    if campos_comerciais:
        crit_ok = pode("edit_concorrentes")
        st.markdown("**Concorrentes conhecidos** (um por linha) — _marca Ameaça Alta e eleva o score; valide com o comercial_")
        txt = st.text_area("concorrentes", "\n".join(cfg.get("concorrentes_conhecidos", [])), height=160,
                           disabled=not crit_ok, label_visibility="collapsed")
        novo["concorrentes_conhecidos"] = [l.strip() for l in txt.splitlines() if l.strip()]
        c = st.columns(2)
        novo["score_minimo"] = c[0].number_input("Score mínimo", 0, 100, int(cfg.get("score_minimo", 45)), disabled=not pode("edit_score"))
        novo["valor_minimo"] = c[1].number_input("Valor mínimo (R$)", 0, 10_000_000, int(cfg.get("valor_minimo", 0)), step=10000)
        novo["ufs"] = [u.strip().upper() for u in st.text_input("UFs (vírgula)", ",".join(cfg.get("ufs", []))).split(",") if u.strip()]
        st.markdown("**Responsáveis (JSON por UF × categoria)**")
        rtxt = st.text_area("responsaveis", json.dumps(cfg.get("responsaveis", {}), ensure_ascii=False, indent=2),
                           height=180, disabled=not pode("edit_responsaveis"))
        try: novo["responsaveis"] = json.loads(rtxt)
        except Exception: st.warning("JSON de responsáveis inválido — não será salvo até corrigir.")
        acao = "edit_config_comercial"
    else:
        st.markdown("**Configuração técnica (JSON completo)** — _Administrador apenas_")
        full = st.text_area("json", json.dumps(cfg, ensure_ascii=False, indent=2), height=420, disabled=not pode("edit_config_tecnica"))
        ok, data, err = config_editor.validar(full)
        if not ok: st.warning(err)
        else: novo = data
        acao = "edit_config_tecnica"

    pode_salvar = pode(acao)
    conf = st.checkbox("Confirmo a alteração (gera backup + auditoria)", disabled=not pode_salvar)
    if st.button("💾 Salvar configuração", disabled=not (pode_salvar and conf), type="primary"):
        mudancas, bkp = config_editor.salvar(nome, novo)
        audit.log(USER["username"], ROLE, acao, detalhes=f"{nome}: {len(mudancas)} alteração(ões)", parametros=json.dumps(mudancas, ensure_ascii=False)[:900])
        st.success(f"Salvo. Backup: {os.path.basename(bkp) if bkp else '—'}")
        if mudancas: st.write("Alterações:", mudancas)
    if not pode_salvar: st.info(auth.ACESSO_NEGADO)
    bks = config_editor.listar_backups(nome)
    if bks:
        with st.expander("Backups / restaurar"):
            b = st.selectbox("Backup", [os.path.basename(x) for x in bks])
            if pode(acao) and st.button("↩️ Restaurar backup selecionado"):
                config_editor.restaurar(nome, os.path.join(config_editor.BKP_DIR, b))
                audit.log(USER["username"], ROLE, acao, detalhes="restaurar " + b); st.success("Restaurado.")

def page_config_comercial():
    st.title("Configurações Comerciais")
    _edit_config("atlas_config_producao.json", "Produção", campos_comerciais=True)

def page_config_tecnica():
    st.title("Configurações Técnicas")
    if not pode("edit_config_tecnica"): negado(); return
    alvo = st.selectbox("Arquivo", ["atlas_config_producao.json", "atlas_config_teste.json", "atlas_config.json"])
    _edit_config(alvo, "Técnica", campos_comerciais=False)

# ===================================================== BANCO
def page_banco():
    st.title("Banco de Dados")
    bstat = runner.obter_status_banco(DB_URL)
    if not bstat.get("configurado"):
        st.warning(bstat["msg"])
        st.markdown("**Para configurar:**\n1. Crie um projeto no Supabase.\n2. Rode `supabase/schema_atlas_b2g.sql` e `seed_atlas_b2g.sql` no SQL Editor.\n"
                    "3. Defina `DATABASE_URL` em `config/.env` (veja `database.example.env`).\n4. `pip install psycopg2-binary`.\n5. Reabra o painel e teste a conexão.")
        return
    if bstat.get("erro"):
        st.error(bstat["msg"] + " — " + bstat["erro"]);
    else:
        st.success(f"{bstat['msg']} (dialeto: {bstat.get('dialeto')})")
        t = bstat.get("tabelas", {})
        c = st.columns(6)
        for i, (k, v) in enumerate(t.items()):
            c[i % 6].metric(k, v)
        if bstat.get("ultima_rodada"):
            st.caption("Última rodada no banco: " + str(bstat["ultima_rodada"]))
    if pode("load_db"):
        rd = runner._ultima_rodada_dir()
        if st.button("🗄️ Carregar última rodada no banco"):
            executar("load_db", runner.carregar_rodada_no_banco, rd, DB_URL); st.rerun()
    st.caption("Consultas úteis: veja docs/sql_queries_exemplos.md")
    mostra_resultado()

# ===================================================== LOGS
def page_logs():
    st.title("Logs Técnicos")
    rs = runner.listar_rodadas()
    if not rs: st.info("Sem rodadas."); return
    sel = st.selectbox("Rodada", [r["pasta"] for r in rs])
    rd = next(r["caminho"] for r in rs if r["pasta"] == sel)
    st.code(runner.ler_logs(rd, n=400))

# ===================================================== AUDITORIA
def page_auditoria():
    st.title("Auditoria")
    c = st.columns(3)
    fu = c[0].text_input("Usuário (filtro)")
    fa = c[1].selectbox("Ação", [""] + audit.acoes_distintas())
    fr = c[2].selectbox("Resultado", ["", "OK", "ERRO", "FALHA"])
    linhas = audit.read(usuario=fu or None, acao=fa or None, resultado=fr or None, limit=400)
    st.caption(f"{len(linhas)} registro(s)")
    st.dataframe(linhas, use_container_width=True, hide_index=True)

# ===================================================== USUÁRIOS
def page_usuarios():
    st.title("Usuários e Permissões")
    if not pode("manage_users"): negado(); return
    st.dataframe(auth.list_users(), use_container_width=True, hide_index=True)
    st.divider()
    with st.expander("➕ Criar usuário"):
        with st.form("novo_user"):
            nu = st.text_input("Usuário"); npw = st.text_input("Senha", type="password")
            nr = st.selectbox("Perfil", auth.ROLES); nm = st.text_input("Nome"); ne = st.text_input("E-mail")
            if st.form_submit_button("Criar"):
                try:
                    auth.create_user(nu.strip(), npw, nr, ne, nm)
                    audit.log(USER["username"], ROLE, "manage_users", detalhes=f"criou {nu} ({nr})")
                    st.success("Usuário criado."); st.rerun()
                except Exception as e:
                    st.error(str(e))
    with st.expander("✏️ Alterar perfil / status / senha"):
        users = [u["username"] for u in auth.list_users()]
        alvo = st.selectbox("Usuário", users)
        nr = st.selectbox("Novo perfil", auth.ROLES, key="role2")
        cset = st.columns(3)
        if cset[0].button("Aplicar perfil"):
            auth.set_role(alvo, nr); audit.log(USER["username"], ROLE, "manage_users", detalhes=f"perfil {alvo}->{nr}"); st.success("Perfil atualizado.")
        if cset[1].button("Desativar"):
            if alvo == USER["username"] or (auth.get_user(alvo)["role"] == "Administrador" and auth.count_admins_ativos() <= 1):
                st.error("Não é possível desativar o último administrador ou a si mesmo.")
            else:
                auth.set_active(alvo, False); audit.log(USER["username"], ROLE, "manage_users", detalhes=f"desativou {alvo}"); st.success("Desativado.")
        if cset[2].button("Ativar"):
            auth.set_active(alvo, True); audit.log(USER["username"], ROLE, "manage_users", detalhes=f"ativou {alvo}"); st.success("Ativado.")
        np2 = st.text_input("Nova senha (reset)", type="password", key="resetpw")
        if st.button("Resetar senha") and np2:
            auth.set_password(alvo, np2); audit.log(USER["username"], ROLE, "manage_users", detalhes=f"reset senha {alvo}"); st.success("Senha redefinida.")

# ===================================================== AUTOMAÇÃO (ZERO-TOUCH)
def page_automacao():
    import automation
    st.title("Automação (Zero-Touch)")
    st.caption("Instala, configura, aplica SQL, cria usuários, carrega dados, valida e agenda — via scripts atlas_* do projeto online. Ações críticas: Admin + confirmação + auditoria.")
    root = automation.locate_online_root()
    if not root:
        st.error("Projeto online (atlas-b2g-online) não encontrado. Defina ATLAS_ONLINE_ROOT no .env do painel."); return
    st.caption(f"Projeto online: `{root}`")
    dburl = automation.default_dburl(root)

    def roda(acao, script, args=None, timeout=900):
        with st.spinner(f"Executando {acao}… não feche a janela."):
            r = automation.run_script(root, script, args, timeout)
        audit.log(USER["username"], ROLE, "auto:" + acao, resultado=("OK" if r["ok"] else "ERRO"),
                  detalhes=r.get("resumo", "")[:300], duracao=r.get("dur"))
        st.session_state.last_op = {"acao": "auto:" + acao, "ok": r["ok"], "code": r["code"], "out": r["out"], "dur": r["dur"]}
        st.rerun()

    st.subheader("Diagnóstico & validação (seguro — não altera dados)")
    c = st.columns(3)
    if c[0].button("🩺 Doctor (--fix)", use_container_width=True): roda("doctor", "atlas_doctor.py", ["--fix"])
    if c[1].button("✅ Validar sistema", use_container_width=True): roda("validate", "atlas_validate_online.py", ["--db-url", dburl])
    if c[2].button("🔒 Secrets-check", use_container_width=True): roda("secrets", "atlas_secrets_check.py")
    c2 = st.columns(3)
    if c2[0].button("🗂️ Validar Storage (artefatos)", use_container_width=True): roda("test_storage", "test_storage_artifacts.py")
    if c2[1].button("📡 Validar Realtime (evento)", use_container_width=True): roda("test_realtime", "test_realtime.py")
    if c2[2].button("🔔 Validar notificações", use_container_width=True): roda("test_notifications", "test_notifications.py")
    if st.button("📡 Validar Radar Comercial", use_container_width=True): roda("test_radar", "test_radar.py")

    st.subheader("Setup automático")
    cc = st.columns(3)
    with cc[0]:
        if botao_critico("🚀 Setup completo (full)", "edit_config_tecnica", "auto_full"): roda("full", "atlas_auto_setup.py", ["--mode", "full"], 1800)
    with cc[1]:
        if botao_critico("🧪 Setup local (SQLite)", "edit_config_tecnica", "auto_local"): roda("local", "atlas_auto_setup.py", ["--mode", "local"], 1200)
    with cc[2]:
        if botao_critico("🛠️ Corrigir (repair)", "edit_config_tecnica", "auto_repair"): roda("repair", "atlas_auto_setup.py", ["--mode", "repair"], 1200)

    st.subheader("Etapas individuais")
    e = st.columns(3)
    with e[0]:
        if botao_critico("☁️ Criar/Configurar Supabase", "edit_config_tecnica", "auto_supa"): roda("create_supabase", "atlas_create_supabase_project.py")
        if botao_critico("🗃️ Aplicar SQL", "edit_config_tecnica", "auto_sql"): roda("apply_sql", "atlas_apply_sql.py", ["--db-url", dburl])
    with e[1]:
        if botao_critico("👤 Criar usuários", "manage_users", "auto_users"): roda("create_users", "atlas_create_users.py")
        if botao_critico("📥 Carregar dados reais", "load_db", "auto_load"): roda("load_data", "atlas_load_data.py", ["--latest", "--db-url", dburl, "--no-init"])
    with e[2]:
        if botao_critico("📅 Agendar rotina semanal", "schedule", "auto_sched"): roda("schedule", "atlas_schedule.py", ["--weekly"])
        if st.button("📂 Abrir painel online (instruções)", use_container_width=True):
            st.info("Suba o app: `npm run dev` em " + root + " → http://localhost:3000")

    st.subheader("Fila de jobs / Worker (Opção B)")
    w = st.columns(3)
    if w[0].button("🧵 Testar fila (e2e)", use_container_width=True): roda("test_queue", "test_job_queue.py", timeout=300)
    with w[1]:
        if botao_critico("⚙️ Instalar worker (serviço)", "edit_config_tecnica", "wk_install"):
            with st.spinner("Instalando worker…"):
                r = automation.run_ps1(root, "install_worker_service.ps1")
            audit.log(USER["username"], ROLE, "auto:install_worker", resultado=("OK" if r["ok"] else "ERRO"), detalhes=r.get("resumo", "")[:300])
            st.session_state.last_op = {"acao": "auto:install_worker", "ok": r["ok"], "code": r["code"], "out": r["out"], "dur": r["dur"]}; st.rerun()
    with w[2]:
        if botao_critico("🗑️ Remover worker", "edit_config_tecnica", "wk_remove"):
            r = automation.run_ps1(root, "remove_worker_service.ps1")
            audit.log(USER["username"], ROLE, "auto:remove_worker", resultado=("OK" if r["ok"] else "ERRO"))
            st.session_state.last_op = {"acao": "auto:remove_worker", "ok": r["ok"], "code": r["code"], "out": r["out"], "dur": r["dur"]}; st.rerun()
    st.caption("Ver jobs/progresso/logs no painel online: **/admin/jobs**. Rodar worker manual: `powershell scripts\\run_worker.ps1`.")
    mostra_resultado()

# ===================================================== AJUDA
def page_ajuda():
    st.title("Ajuda")
    st.markdown("""
**O que cada botão faz**
- **Rodar teste rápido**: roda o pipeline com config de teste (cache, rápido) — valida que tudo funciona.
- **Rodar produção agora** _(crítico, Admin)_: varre o PNCP, classifica, pontua e gera Excel/relatório/protótipo/ZIP.
- **Rodar produção + banco** _(crítico, Admin)_: o mesmo + grava no banco (precisa de `DATABASE_URL`).
- **Carregar rodada no banco**: envia uma rodada já gerada para o banco (upsert idempotente).
- **Abrir Excel/Relatório/Protótipo/ZIP**: abre os arquivos da rodada no seu computador.

**Segurança**: senhas com hash (bcrypt), permissões por perfil, ações críticas exigem Administrador + confirmação, tudo auditado. Credenciais ficam em `config/.env` (nunca no código).

**Erros comuns**: API do PNCP lenta → rode novamente fora do pico; banco não configurado → defina `DATABASE_URL`. Veja o log completo no resultado da operação.

Documentação: `admin_panel/README_ADMIN.md`, `docs/painel_admin.md`, `docs/operacao_semanal.md`.
""")

# ----------------- ROTEAMENTO -----------------
PAGES = {
    "Home": page_home, "Automação": page_automacao, "Operação": page_operacao, "Rodadas": page_rodadas, "Arquivos Gerados": page_arquivos,
    "Configurações Comerciais": page_config_comercial, "Configurações Técnicas": page_config_tecnica,
    "Banco de Dados": page_banco, "Logs": page_logs, "Auditoria": page_auditoria,
    "Usuários e Permissões": page_usuarios, "Ajuda": page_ajuda,
}
# proteção contra acesso por seleção indevida
_perm_da_pagina = {p: perm for p, perm in PAGINAS}
_alvo = _perm_da_pagina.get(pagina)
if _alvo and not pode(_alvo):
    negado()
else:
    PAGES.get(pagina, page_home)()
