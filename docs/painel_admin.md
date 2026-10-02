# ATLAS B2G — Painel Administrativo (visão de produto)

O painel transforma o ATLAS numa operação **“de botão”**: o administrador entra com login, clica e o sistema varre o PNCP, classifica, pontua, gera Excel/relatório/protótipo/ZIP, grava no banco e registra auditoria — **sem terminal**.

## Duas camadas
- **Administrativa** (este painel — Streamlit): operar a máquina, configurar, auditar, gerenciar usuários.
- **Comercial** (vendas/coordenação/diretoria): consultar oportunidades, distribuir, registrar contato, ver dashboards — hoje via protótipo/Excel; no futuro, painel online (Fase 2).

## Segurança (resumo)
- Login com **hash bcrypt**; sessão autenticada; logout.
- **RBAC** (5 perfis) — botões/páginas aparecem conforme a permissão.
- **Ações críticas** exigem Administrador + **confirmação explícita**.
- **Auditoria** de tudo (login, execução, carga, edição de config, abertura de arquivo, gestão de usuário).
- Credenciais em `config/.env` (fora do código); **service role do Supabase só no servidor**.

## UX
Cards de status, métricas, status colorido do banco, botões grandes, confirmação dupla, área de logs e mensagens claras de erro com sugestão de ação.

## Como usar
Veja **`admin_panel/README_ADMIN.md`** (instalação, primeiro ADM, login, operação, configuração, recuperação de senha, backup).

## Critérios de aceite (todos cobertos)
Login com hash · RBAC bloqueando ADM para não-admin · botões críticos só p/ ADM + confirmação · rodar teste/produção/produção+banco por botão · aviso quando banco ausente · logs e auditoria · abrir Excel/relatório/protótipo/ZIP · editar config com backup+diff · gerenciar usuários · scripts PowerShell · schema/seed/carga/`--write-db` presentes · upsert sem duplicar · histórico criado · links PNCP e campos manuais preservados.
