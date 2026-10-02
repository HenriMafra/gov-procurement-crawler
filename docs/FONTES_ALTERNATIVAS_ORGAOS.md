# Fontes alternativas de contratos (fora do PNCP)

Nem todo órgão/empresa publica contratos no PNCP (Portal Nacional de Contratações Públicas). Este documento
registra, por família de fonte, como coletar contratos desses órgãos — método descoberto, validado e
reproduzível. Cada seção documenta: por que o PNCP não serve, como a fonte real foi descoberta e o script
usado.

## Como este documento é usado

A lista completa de ~221 órgãos/empresas a mapear está em `docs/lista_orgaos_alvo.txt`. O cruzamento contra
a base já coletada do PNCP (tabela `orgaos` do Supabase, MAPPER) mostrou que **57/221 já estão cobertos**
pelo cache PNCP existente. Os **164 restantes** precisam de fonte alternativa — este doc cresce conforme cada
família de fontes é resolvida.

---

## 1. Portal Transparência do GDF (`transparencia.df.gov.br`)

**Cobre:** qualquer órgão/autarquia/fundo do Governo do Distrito Federal (SIGGO/SEEC) — inclusive os que
**não aparecem no PNCP** por serem contratantes estaduais/distritais, não federais.

**Como foi descoberto:** o site é uma SPA AngularJS. Usando Playwright para interceptar requisições de rede
enquanto se navega pelo filtro "Órgão" na tela de Contratos, foi capturada a chamada real:

```
GET https://www.transparencia.df.gov.br/api/licitacoes-contratos/contrato
    ?anoInicio={ANO}&listaCodigoUnidadeGestora={CODIGO_UG}&page={N}&size=100
```

Sem autenticação, sem CAPTCHA, paginado, com filtro por ano (1998–2026) e por código de Unidade Gestora
(UG). A lista completa de UGs (134 códigos) vem de:

```
GET https://www.transparencia.df.gov.br/api/licitacoes-contratos/unidade-gestora
```

**Campos retornados:** `numeroContrato`, `numeroOriginal`, `unidadeGestora`, `credor` (fornecedor),
`codigoCredorMascarado` (CNPJ mascarado em CPF, completo em CNPJ), `objeto`, `valorContrato`, `dataInicio`,
`dataFim`, `especie` (modalidade).

**Script:** `scripts/coleta_gdf_generico.py` (adaptado de `coleta_adasa_gdf.py`) — recebe `(sigla, codigo_ug,
nome_orgao, cnpj_orgao)` e devolve todos os contratos daquele UG em todos os anos.

**Órgãos já coletados por esta via** (2026-07-01):

| Sigla | UG | Contratos | Vigentes | Valor Total |
|---|---|---|---|---|
| ADASA | 150206 | 226 | 158 | R$ 77,9 mi |
| TERRACAP | 190203 | 1 | 0 | R$ 500 mi |
| PCDF | 220105 | 43 | 4 | R$ 184,1 mi |
| PMDF | 220103 | 94 | 55 | R$ 343,3 mi |
| SEEC | 130101 | 4 | 0 | R$ 3,3 mi |
| SES-DF | 170101 | 1.944 | 429 | R$ 25,4 bi |
| Defensoria-DF | 480101 | 147 | 41 | R$ 112,8 mi |
| CBMDF | 220104 | 33 | 13 | R$ 115,4 mi |
| DETRAN-DF | 220201 | 380 | 114 | R$ 1,55 bi |
| DER-DF | 200202 | 1.034 | 165 | R$ 3,48 bi |
| PGDF | 120101 | 15 | 1 | R$ 5,3 mi |

**Pendente:** CAESB, "Companhia Metropolitana do DF" e "Instituto de Gestão Estratégica de Saúde do DF
(IGES)" não aparecem na lista de 134 UGs do SIGGO — provavelmente publicam fora do sistema central (CAESB é
empresa pública com portal próprio; IGES é OS/organização social, sujeita a outro regime de transparência).
Precisa investigação individual.

**Generalização:** este mesmo padrão (SPA Angular/Vue + API JSON sem auth, descoberta via interceptação de
rede no Playwright) deve ser testado em TODOS os portais estaduais de transparência antes de partir para
scraping HTML — é ordens de magnitude mais rápido e confiável.

---

## 2. SEST SENAT (`transparencia.sestsenat.org.br`)

Não é órgão público — não está no PNCP. SPA Angular. Endpoint descoberto via engenharia reversa do bundle
JS: `POST /api/edital/pesquisar/` com `{PAGINA, QtdItensPagina}`. Servidor sempre retorna 5 itens por página
independente do `QtdItensPagina` pedido → paginação de fato precisa varrer ~20.000 páginas.

**Limitação conhecida:** os campos `a2_NOME` (fornecedor) e `periodO_DE/ATE` (vigência) vêm sempre `null` na
API — só existem dentro dos PDFs de contrato (`arquivosContratos[].diretorio`). Extração desses dois campos
requer pipeline de OCR/parse de PDF (`scripts/ocr_sest_pdfs.py`, em execução).

**Resultado:** 60.538 contratos coletados, R$ 3,1 bi.

---

## 3. MPM — Ministério Público Militar (`transparencia.mpm.mp.br`)

Publica ODS (LibreOffice Calc) mensais em
`/wp-content/uploads/sites/2/{ano}/{mes:02d}/Contratos-{MêsNome}-{ano}.ods`. Estrutura: título na linha 1,
cabeçalho na linha 4 (detectado por conter "objeto" E "vig" no texto), dados a partir da linha 5. Coluna de
vigência é texto livre `"dd/mm/aa a dd/mm/aa"`, parseado via regex `\s+a\s+`.

**Lacuna conhecida:** 9 meses sem arquivo (404): jan–mai/2021, jul/2022, set/2022, nov/2022, jun/2026.
Próximo passo: fuzzing de padrões de URL alternativos + consulta ao Wayback Machine (CDX API) antes de
recorrer a LAI.

**Resultado:** 8.958 contratos, R$ 1,54 bi.

---

## 4. MPF — histórico pré-2021 (`apps.mpf.mp.br`, Oracle APEX)

Não tem API REST pública, mas o formulário `Contratos Vigentes no Ano` × `Unidade Gestora` renderiza uma
tabela HTML acessível via Playwright headless — sem precisar de token/sessão além do cookie normal de APEX.
Como não existe opção "todas as UGs", a coleta itera **(ano × UG)** — 29 anos × ~35 procuradorias regionais.

**Resultado:** 8.907 contratos, R$ 8,5 bi.

---

## 5. POSTALIS (`www.postalis.org.br`, Umbraco CMS)

Entidade privada (EFPC — fundo de pensão dos Correios), não obrigada a publicar no PNCP/Comprasnet.
Site é SPA Vue/Nuxt sobre **Umbraco Headless CMS**, API "Delivery" v2 descoberta no bundle JS:

```
GET /umbraco/delivery/api/v2/content/item/{slug}/?expand=properties[...]
```

Só expõe **processos licitatórios em andamento/abertos** (não há endpoint de contratos assinados
publicamente acessível). Alternativas ainda não tentadas: Diário Oficial da União (extratos de contrato),
acórdãos do TCU (auditorias no POSTALIS), varredura de diretório `/media/` do Umbraco por PDFs órfãos.

**Resultado:** 40 processos em aberto (não são contratos firmados).

---

## Backlog — 164 entidades sem fonte resolvida

Lista completa em `docs/lista_orgaos_alvo.txt`, com a coluna de match contra o cache PNCP.
Categorias observáveis no backlog:
- **Tribunais estaduais/regionais (TRE-*, TRT-*, TJ-*)**: cada estado tem portal de transparência próprio do
  Judiciário — padrão de API a ser descoberto órgão por órgão ou por tribunal "raiz" (ex.: TSE pode cobrir
  todos os TREs).
- **Empresas privadas fornecedoras** (Banco do Brasil, Caixa, Grendene, etc.): não são contratantes — são
  CONTRATADAS em licitações de terceiros. Para estas, a busca correta é "contratos onde esta empresa aparece
  como fornecedora" dentro das bases já coletadas (PNCP + GDF + demais), não uma fonte de publicação própria.
- **Estatais/autarquias estaduais (PR, SC, RS, GO)**: cada estado provavelmente tem um portal de
  transparência centralizado nos moldes do GDF — validar hipótese testando 1 portal por estado antes de ir
  órgão por órgão.

## Pipeline de execução contínua (VMs Oracle)

A partir de 2026-07-01, a extração desta lista roda como job incremental nas VMs `atlas-coletor` (VM1) e
`atlas-coletor-2` (VM2) — mesmo padrão de fila (`atlas_chunks`) já usado para o PNCP, adaptado para
`(fonte, orgao)` como unidade de chunk em vez de `(uf, mês)`. Cada chunk processado grava direto no Supabase
(tabela `contratos`), sem depender do notebook local ligado. O notebook, quando ligado, participa do mesmo
pool (mais um worker), e tudo fica consolidado automaticamente — nada a sincronizar manualmente.
