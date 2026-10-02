# ATLAS B2G — Consultas SQL úteis (coordenação e diretoria)

Funcionam em PostgreSQL/Supabase e SQLite (mesmas views).

## Top 10 da semana
```sql
SELECT * FROM vw_top_10_semana;
```

## Dashboard executivo (KPIs da última rodada)
```sql
SELECT * FROM vw_dashboard_executivo;
```

## Oportunidades críticas por responsável
```sql
SELECT COALESCE(responsavel_atribuido, responsavel_sugerido) AS responsavel,
       COUNT(*) AS qtd, SUM(valor_total) AS valor_total
FROM vw_lista_ataque_atual
WHERE urgencia_comercial = 'Crítica'
GROUP BY 1
ORDER BY valor_total DESC;
```

## Contratos vencendo em até 90 dias
```sql
SELECT nome_orgao, categoria_principal, valor_total, fim_vigencia, dias_ate_vencimento
FROM vw_lista_ataque_atual
WHERE dias_ate_vencimento BETWEEN 0 AND 90
ORDER BY dias_ate_vencimento ASC;
```

## Contratos vencidos recentemente (renovação)
```sql
SELECT nome_orgao, categoria_principal, valor_total, fim_vigencia, dias_ate_vencimento
FROM vw_lista_ataque_atual
WHERE dias_ate_vencimento < 0
ORDER BY valor_total DESC;
```

## Fornecedores com maior valor mapeado
```sql
SELECT nome_fornecedor, total_contratos, valor_total_mapeado
FROM fornecedores
ORDER BY valor_total_mapeado DESC
LIMIT 20;
```

## Concorrentes (radar de ataque)
```sql
SELECT * FROM vw_concorrentes;
```

## Itens que precisam de revisão
```sql
SELECT * FROM vw_qualidade_base
ORDER BY score_comercial DESC;
```

## Oportunidades por UF
```sql
SELECT uf, COUNT(*) AS qtd, SUM(valor_total) AS valor_total
FROM vw_lista_ataque_atual
GROUP BY uf ORDER BY valor_total DESC;
```

## Oportunidades por categoria
```sql
SELECT categoria_principal, COUNT(*) AS qtd, SUM(valor_total) AS valor_total
FROM vw_lista_ataque_atual
GROUP BY categoria_principal ORDER BY valor_total DESC;
```

## Evolução de score de uma oportunidade (histórico)
```sql
SELECT r.data_rodada, h.score_comercial, h.urgencia_comercial, h.valor_total,
       h.dias_ate_vencimento, h.status_na_rodada, h.mudanca_score
FROM oportunidade_historico h
JOIN rodadas r ON r.id = h.rodada_id
WHERE h.oportunidade_id = :id
ORDER BY r.data_rodada;
```

## Comparar rodadas (novas/alteradas/removidas na última)
```sql
SELECT status_na_rodada, COUNT(*)
FROM oportunidades
WHERE rodada_id = (SELECT id FROM rodadas ORDER BY data_rodada DESC, id DESC LIMIT 1)
   OR status_na_rodada = 'Removida'
GROUP BY status_na_rodada;
```

## Ficha de um órgão (todas as oportunidades)
```sql
SELECT o.id_oportunidade, c.categoria_principal, c.valor_total, c.dias_ate_vencimento,
       o.score_comercial, o.urgencia_comercial, o.status_comercial
FROM oportunidades o
JOIN orgaos org ON org.id = o.orgao_id
JOIN contratos c ON c.id = o.contrato_id
WHERE org.cnpj_orgao = :cnpj
ORDER BY o.score_comercial DESC;
```

## Atualizar status comercial / atribuir responsável (operação)
```sql
UPDATE oportunidades
SET responsavel_atribuido = 'Fulano de Tal', status_comercial = 'Em abordagem', updated_at = CURRENT_TIMESTAMP
WHERE id_oportunidade = 'ATK-00001';
```
> A próxima carga semanal **preserva** esses campos editados manualmente.
