# ATLAS B2G — Modelo de Banco (Fase Banco)

A operação deixa de ser baseada em arquivos e passa a ter uma **base histórica centralizada** (PostgreSQL/Supabase), alimentada pela esteira semanal. O mesmo código roda em **SQLite** (teste local) e **PostgreSQL** (produção) — o dialeto é detectado pela `DATABASE_URL`.

## Visão geral do fluxo
```
Esteira semanal (atlas_weekly_runner.py)
      │  gera CSV/Excel/relatórios (como hoje)
      ▼
load_weekly_to_db.py  →  atlas_db.py  →  PostgreSQL/Supabase (ou SQLite)
      │  upsert idempotente + snapshot de histórico por rodada
      ▼
Views (vw_*)  →  Painel online / consultas da coordenação e diretoria
```
Rodar com banco: `python src/atlas_weekly_runner.py --config config/atlas_config_producao.json --tag PRODUCAO --write-db`
Carregar uma rodada já gerada: `python src/load_weekly_to_db.py --rodada outputs/rodadas/PRODUCAO_2026-05-31`

## Tabelas
| Tabela | Papel |
|---|---|
| `rodadas` | Cada execução semanal (KPIs, config, tempos, status). |
| `orgaos` | Cadastro único de órgãos (dedupe por CNPJ; fallback nome+UF+município). |
| `fornecedores` | Cadastro único de fornecedores; flags de concorrência e totais. |
| `contratos` | Contratos do PNCP (dedupe por `id_pncp`; fallback chave composta). |
| `oportunidades` | **Tabela principal** — estado comercial atual de cada oportunidade. |
| `oportunidade_historico` | Snapshot por rodada (evolução de score/urgência/valor/status). |
| `responsaveis` | Cadastro dos responsáveis comerciais (por UF e categoria). |
| `tarefas` | Tarefas comerciais (validar renovação, mapear decisores, etc.). |
| `contatos` | Histórico de relacionamento (registro de contatos). |
| `logs_execucao` | Logs técnicos por rodada. |
| `revisoes` | Fila de validação manual (classificação incerta / baixa confiança). |
| `parametros_sistema` | Listas de referência e parâmetros (categorias, UFs, pesos do score…). |

## Relacionamentos
`oportunidades` → `contratos` → (`orgaos`, `fornecedores`); `oportunidades` → `rodadas`; `oportunidade_historico` → (`oportunidades`, `rodadas`); `tarefas`/`contatos`/`revisoes` → `oportunidades`; `logs_execucao` → `rodadas`.

## Regras de upsert (idempotência)
- **Órgãos:** chave `orgao_key` = CNPJ (só dígitos) **ou** `norm(nome|UF|município)`.
- **Fornecedores:** `forn_key` = CNPJ **ou** `norm(nome)`.
- **Contratos:** `contrato_key` = `id_pncp` **ou** `norm(órgão|nº contrato|processo|valor|fim vigência)`.
- **Oportunidades:** `op_key` = `contrato_key | tipo_oportunidade`. No conflito:
  - **Atualiza** score, urgência, prioridade, janela, próxima ação, responsável **sugerido**, rodada, `data_ultima_ocorrencia`, `status_na_rodada`.
  - **Preserva** `responsavel_atribuido` (manual), `status_comercial` e `status_validacao` quando já editados; preserva `data_primeira_ocorrencia`.
  - **Sempre** insere snapshot em `oportunidade_historico` (1 por rodada).
  - Oportunidade que **some** da rodada vira `status_na_rodada='Removida'` (não é apagada).

Rodar duas vezes a mesma rodada **não duplica** registros.

## Views (para o painel)
`vw_oportunidades_ativas`, `vw_lista_ataque_atual`, `vw_top_10_semana`, `vw_oportunidades_por_responsavel`, `vw_concorrentes`, `vw_qualidade_base`, `vw_dashboard_executivo`.

## Como conectar ao site
- **Supabase:** o frontend lê as `vw_*` via API REST/PostgREST com a **anon key** + **RLS** (somente leitura nas views internas). A esteira grava com a **service role** (somente no servidor).
- **Self-hosted:** uma API (FastAPI/Next API) consulta as views e expõe endpoints (`/lista-ataque`, `/oportunidade/:id`, `/orgao/:id`, `/dashboard`).
- O protótipo HTML atual pode passar a buscar `vw_lista_ataque_atual` em vez do `.js` estático.

## Segurança (Supabase)
- Ativar **RLS** nas tabelas; expor apenas **views de leitura** ao papel anon.
- **Service role** somente no servidor da esteira (nunca no frontend).
- Dados de contratos são públicos (PNCP); **responsáveis e contatos** são internos → proteger por RLS/políticas.
- Alterações manuais (status, responsável) devem ser logadas (trigger/audit — evolução futura).
