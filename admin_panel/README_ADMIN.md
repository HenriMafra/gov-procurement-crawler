# ATLAS B2G — Painel Administrativo (README)

Interface visual **segura** (Streamlit) para operar toda a máquina ATLAS B2G **por botão**, sem terminal: rodar produção/teste, gravar no banco, gerar pacote, abrir arquivos, editar configurações, ver logs/auditoria e gerenciar usuários — com **login, perfis (RBAC), confirmação para ações críticas e auditoria**.

## 1. Instalar
```powershell
pip install streamlit bcrypt python-dotenv      # (o launcher também instala)
```

## 2. Criar o primeiro Administrador
```powershell
python scripts\create_admin_user.py --username admin --password "TroqueEstaSenha!" --role Administrador
```
A senha é gravada como **hash bcrypt** (nunca em texto puro), no banco local `admin_panel/users.db`.

## 3. Abrir o painel
```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_admin_panel.ps1
```
Abre em `http://localhost:8501`. Faça login.

## 4. (Opcional) Conectar o banco
Copie `admin_panel/.env.example` → `config/.env` e defina `DATABASE_URL` (Supabase/PostgreSQL).
Sem banco, o painel opera em **modo arquivo** (gera CSV/Excel/relatório/ZIP normalmente) e os botões de banco ficam desabilitados com aviso.

## 5. Perfis (RBAC)
| Perfil | Pode |
|---|---|
| **Administrador** | tudo: rodar produção, gravar no banco, editar score/concorrentes/responsáveis/config técnica, reprocessar, agendar, gerenciar usuários, auditoria. |
| **Operador de Inteligência** | rodar teste, carregar rodada no banco, gerar pacote, atualizar protótipo, abrir arquivos, ver logs/auditoria, editar config comercial. |
| **Coordenador Comercial** | ver lista de ataque/rodadas/dashboards, distribuir, atribuir vendedor, atualizar status, abrir arquivos. |
| **Vendedor** | ver oportunidades, registrar contato, atualizar status. |
| **Diretoria** | ver dashboards/relatórios. |

**Ações críticas** (rodar produção, rodar+banco, reprocessar, arquivar, editar score/concorrentes/responsáveis/config técnica, agendar, exportar base, gerenciar usuários, configurar banco) exigem **perfil Administrador + confirmação explícita**. Sem permissão: _“Acesso negado. Esta área exige perfil Administrador.”_

## 6. Operações por botão
- **Rodar teste rápido** — valida API/pipeline/arquivos (config de teste, cache).
- **Rodar produção agora** _(crítico)_ — `atlas_weekly_runner --config atlas_config_producao.json --tag PRODUCAO`.
- **Rodar produção + banco** _(crítico)_ — idem com `--write-db` (requer `DATABASE_URL`).
- **Carregar rodada no banco** — `load_weekly_to_db --rodada <pasta>` (upsert idempotente).
- **Atualizar protótipo** — regenera o HTML com os dados da rodada.
- **Abrir** Excel / Relatório / Protótipo / ZIP / pasta — abre no seu computador.

## 7. Páginas
Home · Operação · Rodadas · Arquivos Gerados · Configurações Comerciais · Configurações Técnicas · Banco de Dados · Logs · Auditoria · Usuários e Permissões · Ajuda. (Cada uma aparece conforme o perfil.)

## 8. Editar configuração sem mexer em JSON
Em **Configurações Comerciais/Técnicas**: edite concorrentes (um por linha), score/valor mínimos, UFs, responsáveis (JSON), ou o JSON técnico completo. Ao salvar: **backup automático** (`config/_backups/`), **diff** exibido e **registro em auditoria**. Há restauração de backup.

## 9. Recuperar senha
```powershell
python scripts\reset_admin_password.py --username admin --password "NovaSenha!"
```

## 10. Agendar a rotina semanal (sem painel)
A esteira também roda agendada (segundas 08:00): `scripts\create_windows_task.ps1`. O painel é para operação manual/sob demanda e supervisão.

## 11. Segurança & backup
- Hash bcrypt; permissões por perfil; confirmação dupla; **tudo auditado** (login, execuções, cargas, edições, aberturas).
- Credenciais só em `config/.env` (fora do código). **Service role do Supabase só no servidor**, nunca no frontend.
- Backup: copie `admin_panel/users.db`, a pasta `config/` e `outputs/rodadas/`. No banco, o histórico fica em `oportunidade_historico` + `audit_logs`.

## 12. Erros comuns
- **“Banco não configurado”** → defina `DATABASE_URL`. **PostgreSQL** → `pip install psycopg2-binary`.
- **API do PNCP lenta** → rode fora do horário de pico; o pipeline tem retry/cache.
- **Botão desabilitado** → seu perfil não tem permissão (ou falta confirmar a ação crítica).

## 13. Migrar para o painel online (Fase 2)
Next.js + Supabase Auth + RLS + API Routes + storage. As `vw_*` já alimentam o frontend; veja `docs/database_model.md` e `supabase/README_SUPABASE.md`.
