# ATLAS B2G — Supabase / PostgreSQL (setup)

Como colocar a base operacional do ATLAS no Supabase (ou em qualquer PostgreSQL).

## Passo a passo
1. **Crie o projeto** no [supabase.com](https://supabase.com).
2. **SQL Editor** → cole e rode, nesta ordem:
   - `supabase/schema_atlas_b2g.sql` (tabelas, índices, views — é re-executável).
   - `supabase/seed_atlas_b2g.sql` (parâmetros, categorias, UFs, responsáveis padrão).
3. **Connection string**: em *Project Settings → Database → Connection string (URI)*. Copie e coloque em `config/.env`:
   ```
   DATABASE_URL=postgresql://postgres:SUA_SENHA@db.SEU-PROJETO.supabase.co:5432/postgres
   ```
4. **Dependência**: `pip install psycopg2-binary`.
5. **Carregar uma rodada**:
   ```
   python src/load_weekly_to_db.py --rodada outputs/rodadas/PRODUCAO_2026-05-31
   ```
   ou rode a esteira com `--write-db`.
6. **Conferir** no SQL Editor: `SELECT * FROM vw_dashboard_executivo;` e `SELECT * FROM vw_top_10_semana;`.

## Tabelas (14) e Views (8)
Tabelas: `rodadas, orgaos, fornecedores, contratos, oportunidades, oportunidade_historico, responsaveis, tarefas, contatos, logs_execucao, revisoes, parametros_sistema, usuarios, audit_logs`.
Views: `vw_oportunidades_ativas, vw_lista_ataque_atual, vw_top_10_semana, vw_oportunidades_por_responsavel, vw_concorrentes, vw_qualidade_base, vw_dashboard_executivo, vw_historico_rodadas`.

## Segurança (RLS)
- Ative **Row Level Security** nas tabelas.
- Exponha ao papel **anon** (frontend) **apenas as views de leitura** (`vw_*`).
- Use a **service role** somente no servidor da esteira (gravação) — **nunca no frontend**.
- Dados de contratos são públicos (PNCP); **responsáveis e contatos** são internos → políticas restritivas.

## Upsert (idempotente)
Órgãos/fornecedores/contratos por chave natural (CNPJ/`id_pncp`) com fallback; oportunidades por `contrato|tipo`, **preservando** campos manuais (`responsavel_atribuido`, `status_comercial`, `status_validacao`); histórico sempre cria snapshot por rodada; o que some vira `Removida` (não é apagado). Rodar 2× a mesma rodada **não duplica**. Validado em `docs/database_model.md`.
