# Infraestrutura de coleta — VMs, workers, filas

> Se você chegou aqui vindo do repo `atlas-b2g-online`, este documento é
> a continuação de `docs/HANDOFF_00_LEIA_PRIMEIRO.md` de lá. Leia
> aquele primeiro pra ter o contexto geral do sistema.

## O que roda aqui

Este repositório (`atlas-pncp-pilot`) é o motor de coleta e
classificação. Ele **não serve nenhuma página web** — é só processos
Python rodando em loop infinito, escrevendo direto no banco Postgres
(Supabase, projeto FULL — `abhlinzbzinanxzyqtmz`). O frontend
(`atlas-b2g-online`) lê o que este código escreve.

## As VMs

Duas VMs Oracle Cloud (Ampere/ARM, tier gratuito), rodando os mesmos
tipos de worker em paralelo pra dobrar a capacidade de coleta:

- **VM1**: IP `136.248.82.114`
- **VM2**: IP (ver `.env.handoff` no repo `atlas-b2g-online` ou
  perguntar — não usado nesta sessão de handoff, mas segue o mesmo
  padrão de VM1)

**Acesso**: `ssh -i "C:/caminho/pra/atlas_vm.key" ubuntu@<IP>` — a chave
privada não está neste repo (é local da máquina de quem administra).

**Atenção — SSH às vezes é bloqueado**: dependendo da rede de onde você
está conectando (observado: redes corporativas), o SSH direto na porta
22 pode ser resetado pelo firewall da rede/ISP, com erro
`kex_exchange_identification: read: Connection reset by peer` ou
`banner exchange: Connection to <ip> port 22: Software caused connection
abort`. **Isso não é a VM caindo** — os workers continuam rodando
normalmente dentro dela, só o SEU acesso externo é que fica bloqueado.
Alternativas quando isso acontece:
1. Tentar de outra rede (ex.: um hotspot de celular costuma não ter
   esse bloqueio)
2. Usar o **Console Connection** da Oracle Cloud — acesso via API OCI,
   **sempre rodado a partir do Cloud Shell da própria Oracle** (nunca da
   máquina local — a máquina local é justamente o que está bloqueado; e
   não pela UI do Console, que às vezes não expõe essa opção
   dependendo da região/tier da conta)

Repositório na VM: `~/atlas-pncp-pilot`, ambiente virtual Python em
`.venv`. Variáveis de ambiente da VM ficam em `~/.atlas_env` (não vai
pro git — configurado uma vez na hora do setup da VM).

## Os workers (processos que rodam 24/7)

Todos seguem o mesmo padrão: um script Python com loop `while True`,
iniciado por um script wrapper em `scripts/start_*.sh`, e mantido vivo
por uma entrada de **cron watchdog** que roda a cada 5 minutos e só
inicia o processo se ele não estiver rodando (`pgrep -f <nome> || start`).

| Worker | Arquivo | O que faz |
|---|---|---|
| Chunk worker | `src/atlas_chunk_worker.py` | Puxa a coleta nacional do PNCP, em pedaços (chunks) de UF×trimestre, da fila `atlas_chunks` |
| Job worker | `src/atlas_job_worker.py` | Executa jobs disparados manualmente pelo painel admin |
| Coleta não-PNCP | `src/atlas_nao_pncp_worker.py` | Roda os ~18 coletores de fontes que não são o PNCP (CIASC, SENAC, TCB, etc.) a cada 6h, depois roda a classificação |
| Backfill de órgão | `src/atlas_orgao_backfill_worker.py` | **Novo (2026-07-13)**: corrige sub-coleta histórica por órgão via `cnpjOrgao`, ver seção abaixo |

### Padrão de wrapper + cron (exemplo real, `start_chunk_worker.sh`)

```bash
#!/usr/bin/env bash
set -a; source "$HOME/.atlas_env"; set +a
cd "$HOME/atlas-pncp-pilot" || exit 1
if pgrep -f "atlas_chunk_worker.py" >/dev/null; then exit 0; fi
nohup ./.venv/bin/python "$HOME/atlas-pncp-pilot/src/atlas_chunk_worker.py" \
  >> "$HOME/atlas_chunk_worker.log" 2>&1 &
```

Entrada de crontab correspondente (watchdog a cada 5 min + inicia no boot):
```
*/5 * * * * $HOME/atlas-pncp-pilot/scripts/start_chunk_worker.sh
@reboot $HOME/atlas-pncp-pilot/scripts/start_chunk_worker.sh
```

Pra criar um worker novo, copie esse padrão trocando o nome do script.

## Pool de chunks — como a coleta nacional do PNCP é distribuída

A coleta nacional (`atlas_pncp_ingest.py`) é fatiada em "chunks" (UF ×
trimestre) numa fila (`atlas_chunks`), processada de forma oportunista:
VM1 e VM2 (24/7) e, quando ligado, um PC adicional, disputam a fila com
`FOR UPDATE SKIP LOCKED` — cada worker pega um chunk livre, processa, e
pega o próximo. Isso é **ADD-only seguro**: os parâmetros de coleta são
pinados (`--no-remove --no-init`), então a base nunca encolhe mesmo que
um worker seja interrompido no meio.

## Backfill por órgão (correção de sub-coleta histórica)

Ver `atlas-b2g-online/docs/HANDOFF_PROBLEMAS_CONHECIDOS.md` pra contexto
completo do problema que isso resolve. Resumo técnico:

- `src/backfill_orgao_cnpj.py` — busca EXAUSTIVA de contratos de UM
  órgão, via `cnpjOrgao` (parâmetro da API PNCP que filtra por órgão,
  sem teto de páginas), ano a ano desde 2021 (limite de 365 dias por
  chamada da API). Tem backoff exponencial pra lidar com o rate-limit
  agressivo do PNCP (HTTP 429 sob uso intenso — confirmado
  empiricamente).
- `src/atlas_orgao_backfill_worker.py` — worker de fila que roda isso
  pra todos os órgãos de origem PNCP no banco (tabela
  `atlas_orgao_backfill`, 5.734 linhas, priorizadas por volume atual
  de contratos — quem tem mais hoje processa primeiro, por ser sinal
  de maior sub-coleta relativa).

**Status (2026-07-14): rodando 24/7 na VM1**, via
`scripts/start_orgao_backfill_worker.sh` + watchdog cron (mesmo padrão
dos outros workers, `*/5 * * * *` + `@reboot`). A IMBEL (órgão de teste,
`orgao_id=739`) foi processada primeiro, manualmente, fora da fila —
confirmou 2021=0, 2022=0, 2023=108, 2024=96, 2025=1.838, 2026=957
contratos brutos do PNCP (2.999 total, deduplicados em 2.098 contratos
únicos por `contrato_key`/`numeroControlePNCP`) — bate exatamente com o
número real confirmado via consulta direta à API do PNCP. A linha da
IMBEL na fila foi marcada `status='done'` manualmente pra não
reprocessar. Os outros 5.733 órgãos processam via fila normal, um por
vez, respeitando o rate-limit do PNCP — espere **dias**, não horas, pra
fila esvaziar (é intencional, ver `PAUSA_BASE_S` em
`backfill_orgao_cnpj.py`).

**Bug já corrigido nesse mecanismo**: a primeira versão de
`para_registros_db()` em `backfill_orgao_cnpj.py` não preenchia o campo
`forn_key` (obrigatório, `NOT NULL`) no dict de fornecedor, o que
quebrava a gravação no meio depois de já ter buscado todos os
contratos da API (retrabalho de rede desperdiçado, mas nenhum dado
gravado incorretamente — o erro acontecia antes do `commit()`). Corrigido
no commit `26c269a`.

Acompanhar o progresso da fila:
```sql
SELECT status, count(*) FROM atlas_orgao_backfill GROUP BY status;
SELECT orgao_id, cnpj, contratos_antes, contratos_depois, finished_at
FROM atlas_orgao_backfill WHERE status='done' ORDER BY finished_at DESC LIMIT 20;
```

Ver log ao vivo na VM: `tail -f ~/atlas_orgao_backfill_worker.log`.

Uso manual (um órgão específico, fora da fila):
```bash
python src/backfill_orgao_cnpj.py --cnpj <cnpj-sem-mascara> --orgao-id <id> \
  --ano-inicio 2021 --rodada-id <id-da-rodada-atual> --db-url "$DATABASE_URL"
# adicione --dry-run pra só simular sem gravar
```

Acompanhar progresso da fila:
```sql
SELECT status, count(*) FROM atlas_orgao_backfill GROUP BY status;
SELECT orgao_id, cnpj, contratos_antes, contratos_depois
FROM atlas_orgao_backfill WHERE status='done' ORDER BY finished_at DESC LIMIT 20;
```

## O motor de classificação (compartilhado por TUDO)

Não importa a fonte (PNCP ou não-PNCP, coleta nacional ou backfill por
órgão) — todo mundo usa as MESMAS funções puras em `atlas_pncp_ingest.py`:

- `classifica_ti(objeto_contrato)` — 236 palavras-chave, decide se um
  contrato é relevante pra TI e em qual categoria/subcategoria
- `status_contrato(data_fim_vigencia)` — calcula se está vigente,
  vencido, a vencer, e em quantos dias
- `eh_concorrente(nome_fornecedor, eh_ti)` — detecta se o fornecedor é
  um concorrente conhecido da ENTERPRISECORE
- `score_oportunidade(...)` — calcula o score comercial (0-100) a
  partir de urgência, valor, categoria, concorrência, qualidade do dado
- `faixa_prioridade(score)` — converte o score numérico em faixa
  (Máxima/Alta/Média/Baixa)

Isso garante que uma oportunidade calculada pela coleta nacional do
PNCP e uma calculada pelo coletor do CIASC-SC são comparáveis — mesmo
critério, mesmo peso. **Se for mexer na lógica de score/classificação,
mexa aqui, uma vez só** — não duplique a lógica em cada coletor.

## Coletores não-PNCP (pasta `src/collectors/`)

18 fontes institucionais que publicam contratos fora do PNCP (SC, PR,
GO, DF, bancos públicos, federais). Cada arquivo `coletor_<sigla>.py`
segue o mesmo contrato: raspa o site, monta um dict de contrato/
fornecedor no formato esperado por `atlas_db.py`, grava com
`contrato_key` prefixado pelo nome da fonte (ex.: `CIASC-SC|...`) pra
nunca colidir com chaves do PNCP.

Depois de cada rodada de coleta não-PNCP,
`src/pos_processar_nao_pncp.py` roda automaticamente e liga esses
contratos ao mesmo classificador/score do PNCP — sem isso, os contratos
ficam gravados em `contratos` mas invisíveis nas telas comerciais
(que leem de `oportunidades`).

## Ferramenta administrativa (`admin_panel/`)

Um painel Flask separado (`admin_panel/app.py`) pra disparar
coletas/jobs manualmente e ver logs — usado durante desenvolvimento,
não é parte do fluxo automático 24/7. Ver `admin_panel/README_ADMIN.md`.
