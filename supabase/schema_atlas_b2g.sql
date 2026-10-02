-- =====================================================================
-- ATLAS B2G — Fase Banco — Schema (PostgreSQL / Supabase)
-- Fonte única do modelo. Rode no SQL Editor do Supabase ou via psql.
-- Compatível com SQLite no modo de teste (tradução automática em atlas_db.py).
-- Dados públicos do PNCP; dados internos (responsáveis/contatos) exigem RLS.
-- =====================================================================

-- ------------------------- RODADAS (execuções semanais) -------------------------
CREATE TABLE IF NOT EXISTS rodadas (
  id                  BIGSERIAL PRIMARY KEY,
  data_rodada         DATE NOT NULL,
  tag                 TEXT DEFAULT '',
  tipo                TEXT DEFAULT 'semanal',
  config_hash         TEXT,
  config_json         JSONB,
  inicio_execucao     TIMESTAMPTZ,
  fim_execucao        TIMESTAMPTZ,
  status_execucao     TEXT DEFAULT 'concluida',
  total_coletado      INTEGER DEFAULT 0,
  total_ti            INTEGER DEFAULT 0,
  total_oportunidades INTEGER DEFAULT 0,
  total_criticas      INTEGER DEFAULT 0,
  valor_total_mapeado NUMERIC(16,2) DEFAULT 0,
  caminho_pacote      TEXT,
  observacoes         TEXT,
  created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (tag, data_rodada)
);

-- ------------------------- ÓRGÃOS -------------------------
CREATE TABLE IF NOT EXISTS orgaos (
  id                        BIGSERIAL PRIMARY KEY,
  orgao_key                 TEXT UNIQUE NOT NULL,   -- CNPJ (só dígitos) OU norm(nome|uf|municipio)
  cnpj_orgao                TEXT,
  nome_orgao                TEXT,
  nome_padronizado          TEXT,
  uf                        TEXT,
  municipio                 TEXT,
  poder                     TEXT,
  esfera                    TEXT,
  unidade_compradora        TEXT,
  segmento_presumido        TEXT,
  fonte_primeira_ocorrencia TEXT,
  created_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at                TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- FORNECEDORES -------------------------
CREATE TABLE IF NOT EXISTS fornecedores (
  id                    BIGSERIAL PRIMARY KEY,
  forn_key              TEXT UNIQUE NOT NULL,        -- CNPJ (só dígitos) OU norm(nome)
  cnpj_fornecedor       TEXT,
  nome_fornecedor       TEXT,
  nome_padronizado      TEXT,
  possivel_concorrente  BOOLEAN DEFAULT FALSE,
  concorrente_conhecido BOOLEAN DEFAULT FALSE,
  grau_ameaca           TEXT,
  categorias_detectadas TEXT,
  total_contratos       INTEGER DEFAULT 0,
  valor_total_mapeado   NUMERIC(16,2) DEFAULT 0,
  created_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at            TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- CONTRATOS -------------------------
CREATE TABLE IF NOT EXISTS contratos (
  id                         BIGSERIAL PRIMARY KEY,
  contrato_key               TEXT UNIQUE NOT NULL,   -- id_pncp OU chave composta
  id_pncp                    TEXT,
  numero_contrato            TEXT,
  numero_processo            TEXT,
  fonte                      TEXT DEFAULT 'PNCP',
  link_fonte                 TEXT,
  orgao_id                   BIGINT REFERENCES orgaos(id),
  fornecedor_id              BIGINT REFERENCES fornecedores(id),
  objeto_original            TEXT,
  objeto_normalizado         TEXT,
  categoria_principal        TEXT,
  subcategoria               TEXT,
  palavras_chave_encontradas TEXT,
  valor_total                NUMERIC(16,2) DEFAULT 0,
  valor_mensal_estimado      NUMERIC(16,2),
  data_assinatura            DATE,
  inicio_vigencia            DATE,
  fim_vigencia               DATE,
  dias_ate_vencimento        INTEGER,
  status_contrato            TEXT,
  situacao_pncp              TEXT,
  modalidade                 TEXT,
  created_at                 TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at                 TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- OPORTUNIDADES (tabela principal) -------------------------
CREATE TABLE IF NOT EXISTS oportunidades (
  id                            BIGSERIAL PRIMARY KEY,
  op_key                        TEXT UNIQUE NOT NULL,  -- contrato_key + '|' + tipo_oportunidade
  contrato_id                   BIGINT REFERENCES contratos(id),
  orgao_id                      BIGINT REFERENCES orgaos(id),
  fornecedor_id                 BIGINT REFERENCES fornecedores(id),
  rodada_id                     BIGINT REFERENCES rodadas(id),   -- última rodada em que apareceu
  id_oportunidade               TEXT,
  tipo_oportunidade             TEXT,
  janela_comercial              TEXT,
  urgencia_comercial            TEXT,
  score_comercial               INTEGER,
  prioridade                    TEXT,
  explicacao_score              TEXT,
  motivo_prioridade             TEXT,
  argumento_comercial_sugerido  TEXT,
  proxima_acao_recomendada      TEXT,
  responsavel_sugerido          TEXT,
  responsavel_atribuido         TEXT,            -- preenchido manualmente; nunca sobrescrito pela carga
  carteira_sugerida             TEXT,
  status_comercial              TEXT DEFAULT 'Novo',
  status_validacao              TEXT DEFAULT 'Pendente',
  necessita_revisao             BOOLEAN DEFAULT FALSE,
  observacoes_revisao           TEXT,
  data_primeira_ocorrencia      DATE,
  data_ultima_ocorrencia        DATE,
  status_na_rodada              TEXT,
  created_at                    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at                    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- HISTÓRICO SEMANAL DA OPORTUNIDADE -------------------------
CREATE TABLE IF NOT EXISTS oportunidade_historico (
  id                  BIGSERIAL PRIMARY KEY,
  oportunidade_id     BIGINT REFERENCES oportunidades(id),
  rodada_id           BIGINT REFERENCES rodadas(id),
  score_comercial     INTEGER,
  prioridade          TEXT,
  urgencia_comercial  TEXT,
  valor_total         NUMERIC(16,2),
  dias_ate_vencimento INTEGER,
  status_contrato     TEXT,
  status_na_rodada    TEXT,
  mudanca_score       TEXT,
  mudanca_urgencia    TEXT,
  mudanca_valor       NUMERIC(16,2),
  mudanca_status      TEXT,
  created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (oportunidade_id, rodada_id)
);

-- ------------------------- RESPONSÁVEIS -------------------------
CREATE TABLE IF NOT EXISTS responsaveis (
  id               BIGSERIAL PRIMARY KEY,
  nome             TEXT UNIQUE NOT NULL,
  email            TEXT,
  uf               TEXT,
  categoria        TEXT,
  tipo_responsavel TEXT,
  ativo            BOOLEAN DEFAULT TRUE,
  created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- TAREFAS -------------------------
CREATE TABLE IF NOT EXISTS tarefas (
  id              BIGSERIAL PRIMARY KEY,
  oportunidade_id BIGINT REFERENCES oportunidades(id),
  responsavel_id  BIGINT REFERENCES responsaveis(id),
  titulo          TEXT,
  descricao       TEXT,
  tipo            TEXT,
  prazo           DATE,
  status          TEXT DEFAULT 'Aberta',
  prioridade      TEXT,
  created_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  concluida_em    TIMESTAMPTZ
);

-- ------------------------- CONTATOS -------------------------
CREATE TABLE IF NOT EXISTS contatos (
  id               BIGSERIAL PRIMARY KEY,
  oportunidade_id  BIGINT REFERENCES oportunidades(id),
  orgao_id         BIGINT REFERENCES orgaos(id),
  responsavel_id   BIGINT REFERENCES responsaveis(id),
  data_contato     DATE,
  canal            TEXT,
  pessoa_contatada TEXT,
  cargo            TEXT,
  resumo           TEXT,
  resultado        TEXT,
  proxima_acao     TEXT,
  created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- LOGS DE EXECUÇÃO -------------------------
CREATE TABLE IF NOT EXISTS logs_execucao (
  id            BIGSERIAL PRIMARY KEY,
  rodada_id     BIGINT REFERENCES rodadas(id),
  nivel         TEXT DEFAULT 'INFO',
  mensagem      TEXT,
  detalhes_json JSONB,
  created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- REVISÕES (fila de validação manual) -------------------------
CREATE TABLE IF NOT EXISTS revisoes (
  id                  BIGSERIAL PRIMARY KEY,
  oportunidade_id     BIGINT REFERENCES oportunidades(id),
  tipo_revisao        TEXT,
  motivo              TEXT,
  status              TEXT DEFAULT 'Pendente',
  responsavel_revisao TEXT,
  criado_em           TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  resolvido_em        TIMESTAMPTZ,
  resultado           TEXT,
  UNIQUE (oportunidade_id, tipo_revisao)
);

-- ------------------------- PARÂMETROS DO SISTEMA -------------------------
CREATE TABLE IF NOT EXISTS parametros_sistema (
  id         BIGSERIAL PRIMARY KEY,
  chave      TEXT UNIQUE NOT NULL,
  valor_json JSONB,
  descricao  TEXT,
  ativo      BOOLEAN DEFAULT TRUE,
  updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------- USUÁRIOS (painel online — Fase 2) -------------------------
CREATE TABLE IF NOT EXISTS usuarios (
  id            BIGSERIAL PRIMARY KEY,
  username      TEXT UNIQUE NOT NULL,
  email         TEXT,
  nome          TEXT,
  role          TEXT NOT NULL DEFAULT 'Vendedor',  -- Administrador|Operador de Inteligência|Coordenador Comercial|Vendedor|Diretoria
  uf            TEXT,
  ativo         BOOLEAN DEFAULT TRUE,
  ultimo_login  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
-- Obs.: a senha NÃO fica no banco da aplicação; no Supabase use Supabase Auth (auth.users).

-- ------------------------- AUDIT LOGS (trilha de ações) -------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
  id          BIGSERIAL PRIMARY KEY,
  usuario     TEXT,
  perfil      TEXT,
  acao        TEXT,
  detalhes    TEXT,
  parametros  TEXT,
  resultado   TEXT,
  erro        TEXT,
  duracao     NUMERIC(10,2),
  local       TEXT,
  created_at  TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- ============================= ÍNDICES =============================
CREATE INDEX IF NOT EXISTS idx_contratos_id_pncp        ON contratos (id_pncp);
CREATE INDEX IF NOT EXISTS idx_contratos_categoria      ON contratos (categoria_principal);
CREATE INDEX IF NOT EXISTS idx_contratos_orgao          ON contratos (orgao_id);
CREATE INDEX IF NOT EXISTS idx_contratos_fornecedor     ON contratos (fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_orgaos_cnpj              ON orgaos (cnpj_orgao);
CREATE INDEX IF NOT EXISTS idx_orgaos_uf                ON orgaos (uf);
CREATE INDEX IF NOT EXISTS idx_fornecedores_cnpj        ON fornecedores (cnpj_fornecedor);
CREATE INDEX IF NOT EXISTS idx_oport_rodada             ON oportunidades (rodada_id);
CREATE INDEX IF NOT EXISTS idx_oport_orgao              ON oportunidades (orgao_id);
CREATE INDEX IF NOT EXISTS idx_oport_fornecedor         ON oportunidades (fornecedor_id);
CREATE INDEX IF NOT EXISTS idx_oport_score              ON oportunidades (score_comercial);
CREATE INDEX IF NOT EXISTS idx_oport_urgencia           ON oportunidades (urgencia_comercial);
CREATE INDEX IF NOT EXISTS idx_oport_status_com         ON oportunidades (status_comercial);
CREATE INDEX IF NOT EXISTS idx_oport_status_val         ON oportunidades (status_validacao);
CREATE INDEX IF NOT EXISTS idx_rodadas_data             ON rodadas (data_rodada);
CREATE INDEX IF NOT EXISTS idx_hist_rodada              ON oportunidade_historico (rodada_id);

-- ============================= VIEWS =============================
DROP VIEW IF EXISTS vw_historico_rodadas;
DROP VIEW IF EXISTS vw_dashboard_executivo;
DROP VIEW IF EXISTS vw_qualidade_base;
DROP VIEW IF EXISTS vw_concorrentes;
DROP VIEW IF EXISTS vw_oportunidades_por_responsavel;
DROP VIEW IF EXISTS vw_top_10_semana;
DROP VIEW IF EXISTS vw_lista_ataque_atual;
DROP VIEW IF EXISTS vw_oportunidades_ativas;

-- Oportunidades atuais (não removidas) com dados de órgão/fornecedor/contrato
CREATE VIEW vw_oportunidades_ativas AS
SELECT o.id, o.id_oportunidade, o.rodada_id, o.tipo_oportunidade, o.janela_comercial,
       o.urgencia_comercial, o.score_comercial, o.prioridade, o.status_comercial, o.status_validacao,
       o.responsavel_sugerido, o.responsavel_atribuido, o.carteira_sugerida,
       o.proxima_acao_recomendada, o.argumento_comercial_sugerido, o.motivo_prioridade,
       o.necessita_revisao, o.status_na_rodada,
       org.nome_orgao, org.nome_padronizado AS orgao_padronizado, org.uf, org.municipio, org.esfera, org.poder,
       f.nome_fornecedor, f.possivel_concorrente, f.concorrente_conhecido, f.grau_ameaca,
       c.categoria_principal, c.subcategoria, c.valor_total, c.dias_ate_vencimento, c.status_contrato,
       c.fim_vigencia, c.link_fonte, c.id_pncp
FROM oportunidades o
JOIN orgaos org           ON org.id = o.orgao_id
LEFT JOIN fornecedores f  ON f.id = o.fornecedor_id
LEFT JOIN contratos c     ON c.id = o.contrato_id
WHERE o.status_na_rodada <> 'Removida';

-- Lista de ataque da ÚLTIMA rodada
CREATE VIEW vw_lista_ataque_atual AS
SELECT * FROM vw_oportunidades_ativas
WHERE rodada_id = (SELECT id FROM rodadas ORDER BY data_rodada DESC, id DESC LIMIT 1);

-- Top 10 da semana
CREATE VIEW vw_top_10_semana AS
SELECT * FROM vw_lista_ataque_atual
ORDER BY score_comercial DESC, valor_total DESC
LIMIT 10;

-- Oportunidades por responsável (rodada atual)
CREATE VIEW vw_oportunidades_por_responsavel AS
SELECT COALESCE(responsavel_atribuido, responsavel_sugerido) AS responsavel,
       COUNT(*) AS qtd,
       SUM(CASE WHEN urgencia_comercial = 'Crítica' THEN 1 ELSE 0 END) AS criticas,
       SUM(valor_total) AS valor_total
FROM vw_lista_ataque_atual
GROUP BY COALESCE(responsavel_atribuido, responsavel_sugerido);

-- Concorrentes / fornecedores
CREATE VIEW vw_concorrentes AS
SELECT nome_fornecedor, cnpj_fornecedor, grau_ameaca, concorrente_conhecido,
       categorias_detectadas, total_contratos, valor_total_mapeado
FROM fornecedores
WHERE possivel_concorrente = TRUE
ORDER BY valor_total_mapeado DESC;

-- Qualidade da base (itens que precisam revisão na rodada atual)
CREATE VIEW vw_qualidade_base AS
SELECT id_oportunidade, orgao_padronizado AS orgao, uf, categoria_principal, valor_total,
       score_comercial, necessita_revisao, fim_vigencia, status_validacao, motivo_prioridade
FROM vw_lista_ataque_atual
WHERE necessita_revisao = TRUE OR fim_vigencia IS NULL OR status_validacao = 'Pendente';

-- Dashboard executivo (KPIs da última rodada)
CREATE VIEW vw_dashboard_executivo AS
SELECT
  (SELECT data_rodada FROM rodadas ORDER BY data_rodada DESC, id DESC LIMIT 1) AS data_rodada,
  COUNT(*)                                                            AS oportunidades,
  SUM(CASE WHEN urgencia_comercial = 'Crítica' THEN 1 ELSE 0 END)     AS criticas,
  SUM(valor_total)                                                    AS valor_total_mapeado,
  SUM(CASE WHEN dias_ate_vencimento < 0 THEN 1 ELSE 0 END)            AS vencidos,
  SUM(CASE WHEN dias_ate_vencimento BETWEEN 0 AND 30 THEN 1 ELSE 0 END) AS vencendo_30d,
  SUM(CASE WHEN uf = 'DF' THEN 1 ELSE 0 END)                          AS df,
  SUM(CASE WHEN uf = 'GO' THEN 1 ELSE 0 END)                          AS go
FROM vw_lista_ataque_atual;

-- Histórico de rodadas (para o painel de histórico)
CREATE VIEW vw_historico_rodadas AS
SELECT r.id, r.data_rodada, r.tag, r.tipo, r.status_execucao,
       r.total_oportunidades, r.total_criticas, r.valor_total_mapeado, r.caminho_pacote, r.created_at,
       (SELECT COUNT(*) FROM oportunidade_historico h WHERE h.rodada_id = r.id) AS snapshots
FROM rodadas r
ORDER BY r.data_rodada DESC, r.id DESC;
