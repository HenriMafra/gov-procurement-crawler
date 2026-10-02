# Fontes de dados de licitações/contratos no Brasil — roadmap de integração

> Pesquisa feita em 2026-06 para expandir o MAPPER além do PNCP.
> Foco: DF + GO exaustivos; depois capitais das filiais (CE, SP, MT, PR, PE, AM, RS).

## Resumo estratégico
- **PNCP é a espinha nacional obrigatória** (Lei 14.133/2021): desde 2021/2023 todo órgão
  federal/estadual/municipal publica editais, contratos e atas no PNCP. Para dados **recentes**,
  o PNCP já cobre quase tudo de todos os estados — basta filtrar por `uf`.
- Valor das fontes secundárias: (a) histórico pré-2021, (b) campos que o PNCP não expõe
  (propostas, licitantes, resultados, empenhos), (c) redundância/validação.

## Ordem recomendada de integração
1. **PNCP** (já usado) — `https://pncp.gov.br/api/consulta`. Endpoints: `/v1/contratacoes/publicacao`
   (loop por `codigoModalidadeContratacao` × janelas de data × `uf`), `/v1/contratacoes/proposta`
   (abertas), `/v1/contratos`, `/v1/atas`. **AÇÃO IMEDIATA: adicionar uf=CE,SP,MT,PR,PE,AM,RS.**
2. **Compras.gov.br Dados Abertos (SIASG)** — `https://dadosabertos.compras.gov.br` (módulos
   `modulo-contratacoes`, `modulo-arp`, `modulo-contratos`, `modulo-legado` p/ pré-2021). JSON/CSV, sem chave.
3. **Goiás**: CKAN `https://dadosabertos.go.gov.br/api/3/action/` + scrape ComprasNet.GO (`comprasnet.go.gov.br`) / SISLOG.
4. **DF**: CKAN `https://www.dados.df.gov.br/api/3/action/` + scrape Portal de Compras DF (`portal.compras.df.gov.br`).
5. **TCE-CE** (melhor API TCE do país) — `https://api.tce.ce.gov.br/` métodos `licitacao`, `contratos`, `contratados`, `propostas`.
6. **TCE-PE** — `https://sistemas.tce.pe.gov.br/DadosAbertos/` recursos `LicitacaoUG`, `Contratos`, `ContratoItemObjeto` (sufixo `!json`).
7. **TCE-RS LicitaCon** — bulk `http://dados.tce.rs.gov.br/group/licitacoes` (CSV/JSON, todo o estado+municípios).
8. **TCE-PR** — bases `https://www1.tce.pr.gov.br/conteudo/dados-abertos-tce-pr-consulta-de-bases/318736/area/54` + Mural.

## Cross-cutting (cauda longa de municípios)
- **Querido Diário** — `https://api.queridodiario.ok.org.br/gazettes` (params `territory_ids`, `querystring`, `published_since/until`).

## Auth / limites
- Só precisam de chave: Portal da Transparência Federal (token grátis no header `chave-api-dados`) e parte do Comprasnet Contratos.
- CKAN (DF/GO/RS) compartilham `/api/3/action/{package_search|datastore_search|datastore_search_sql}` — um cliente, 3 hosts.
- TCEs (CE/PE/PR/RS) cobrem TODOS os municípios do estado — 4 integrações ≈ cobertura municipal quase total desses estados.

## Dedup
- Chave: CNPJ do órgão + nº processo/contratação + ano; guardar `numeroControlePNCP` quando houver.
