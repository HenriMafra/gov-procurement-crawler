# ATLAS B2G — Coleta de Contratos: 7 Órgãos Específicos

> **Última atualização:** 2026-06-30  
> **Status:** ✅ Funcional — roda na VM1 (Oracle Cloud)

---

## 🎯 Objetivo

Coletar contratos públicos de **2021 até hoje** para 7 órgãos específicos, consolidar em uma planilha Excel com abas por órgão e enviar ao Supabase Storage para download pelo painel administrativo.

### Órgãos cobertos

| Sigla | Nome Completo | Fonte |
|---|---|---|
| **PRF** | Polícia Rodoviária Federal | PNCP + CGU |
| **MPF** | Ministério Público Federal | PNCP + CGU |
| **MPM** | Ministério Público Militar | PNCP + CGU |
| **MDA** | Ministério do Desenvolvimento Agrário e Agricultura Familiar | PNCP + CGU |
| **ADASA** | Agência Reguladora de Águas, Energia e Saneamento do DF | PNCP + CGU |
| **SEST SENAT** | Serviço Social do Transporte | Portal próprio (sem API pública) |
| **POSTALIS** | Instituto de Seguridade Social dos Correios | Portal próprio (sem API pública) |

---

## 📂 Arquivos Relevantes

```
atlas-pncp-pilot/
├── scripts/
│   ├── coleta_orgaos_especificos.py   ← SCRIPT PRINCIPAL (crawler multi-fonte)
│   └── git_pull.py                    ← Script de atualização do código nas VMs
├── src/
│   ├── atlas_job_runner.py            ← Executor de jobs (lê fila do Supabase)
│   ├── atlas_job_client.py            ← Cliente da fila de jobs (Supabase)
│   └── atlas_chunk_worker.py          ← Worker de chunks paralelos
└── docs/
    └── COLETA_7_ORGAOS.md             ← Este arquivo
```

---

## 🖥️ Infraestrutura

### VM1 — sempre ligada (Oracle Cloud Free Tier)
- **IP:** `136.248.82.114`
- **Usuário:** `ubuntu`
- **Chave SSH:** `atlas_key` (na raiz do Oracle Cloud Shell)
- **Repositório:** `/home/ubuntu/atlas-pncp-pilot/`
- **Python venv:** `/home/ubuntu/atlas-pncp-pilot/.venv/bin/python`
- **Variáveis de ambiente:** `~/.atlas_env` (Supabase URL, chaves, etc.)
- **Worker sempre rodando:** `atlas_job_worker.py` (iniciado por `~/start_job_worker.sh`)

### VM2 — somente mencionada (não usada neste script)
- **IP:** `147.15.8.105` — sem acesso SSH configurado atualmente

---

## ⚡ Como Disparar a Coleta

### Opção A: Pelo Painel Web (recomendado)

1. Acesse **[mapper-full.henri-afly.workers.dev](https://mapper-full.henri-afly.workers.dev)**
2. Login: `henri.mafra@grupoenterprisecore.com` / `PasswordENTERPRISECORE2026!`
3. Menu lateral → **Admin → Atualizações da base**
4. Role até o final → abra **`⚙️ Forçar atualização manual (avançado)`**
5. Clique em **`📊 Coletar Contratos (7 Órgãos)`**
6. Acompanhe em **Admin → Jobs** — quando status = `success`, baixe a planilha na aba **Artefatos**

### Opção B: Pelo Oracle Cloud Shell

```bash
# 1. Acessar o Cloud Shell em https://cloud.oracle.com (região sa-saopaulo-1)

# 2. Atualizar código na VM e reiniciar worker
ssh -i atlas_key ubuntu@136.248.82.114 \
  "git -C ~/atlas-pncp-pilot pull && pkill -f 'atlas_job_worker.py' ; sleep 1 && ~/start_job_worker.sh"

# 3. Rodar a coleta diretamente na VM (sem fila de jobs)
ssh -i atlas_key ubuntu@136.248.82.114 \
  "cd ~/atlas-pncp-pilot && source ~/.atlas_env && .venv/bin/python scripts/coleta_orgaos_especificos.py"
```

### Opção C: Rodar Localmente (apenas para testes)

> ⚠️ **Atenção:** O IP local pode estar bloqueado pelo WAF do PNCP (erro 400/422/timeout).  
> Para coleta real, sempre use a VM.

```bash
# No diretório C:\temp_atlas ou clone do atlas-pncp-pilot
pip install openpyxl requests
python scripts/coleta_orgaos_especificos.py
# Saída: outputs/coleta_orgaos_especificos_YYYY-MM-DD.xlsx
```

---

## 🔧 Configuração de Ambiente (`.atlas_env` na VM)

O script lê as seguintes variáveis de ambiente (já configuradas em `~/.atlas_env` na VM):

```bash
SUPABASE_URL=https://...supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
SUPABASE_BUCKET=atlas-artifacts    # bucket no Storage para upload do Excel
CGU_API_TOKEN=                     # opcional — chave da API de Dados Abertos do Portal da Transparência
```

> A coleta funciona **sem** `CGU_API_TOKEN`, mas coleta apenas do PNCP.  
> Com o token, enriquece os dados com a API da CGU (Portal da Transparência).  
> Obtenha em: https://portaldatransparencia.gov.br/api-de-dados/cadastrar-email

---

## 📊 Estrutura da Planilha Excel Gerada

```
coleta_orgaos_especificos_YYYY-MM-DD.xlsx
├── Painel de Coleta       ← Resumo estatístico: total por órgão e fonte
├── Todos os Contratos     ← Base completa consolidada e deduplicada
├── PRF                    ← Contratos somente da PRF
├── MPF                    ← Contratos somente do MPF
├── MPM                    ← Contratos somente do MPM
├── MDA                    ← Contratos somente do MDA
├── ADASA                  ← Contratos somente da ADASA
├── SEST SENAT             ← Contratos somente do SEST SENAT
└── POSTALIS               ← Contratos somente do POSTALIS
```

### Colunas em cada aba:

| Coluna | Descrição |
|---|---|
| Órgão Sigla | Ex: MPM, PRF |
| Órgão Contratante | Razão social completa |
| CNPJ Órgão | CNPJ do órgão contratante |
| Número Contrato | Número sequencial |
| Fornecedor Contratado | Razão social do fornecedor |
| CNPJ Fornecedor | CNPJ do fornecedor |
| Objeto do Contrato | Descrição do objeto |
| **Valor Total (R$)** | Valor global do contrato |
| Data Assinatura | Data de assinatura |
| Início Vigência | Data de início da vigência |
| Fim Vigência | Data de fim da vigência |
| **Status Vigência** | `Vigente`, `Expirado` ou `N/D` |
| Link da Fonte | Link direto no PNCP |
| Fonte de Coleta | PNCP, CGU Transparência, etc. |

---

## 🐛 Problemas Conhecidos e Soluções

### SEST SENAT e POSTALIS retornam poucos ou nenhum dado
- **Causa:** Esses órgãos são do **Sistema S** e **fundos de previdência privada** — não têm obrigação legal de publicar no PNCP nem possuem API pública de dados abertos.
- **Solução atual:** Script tenta o portal deles, e retorna lista vazia se inacessível (sem dados inventados).
- **Alternativa futura:** Coletar manualmente PDFs do Diário Oficial ou contato direto.

### MPF retorna erro 422
- **Causa:** O PNCP mudou o CNPJ ou estrutura do endpoint para o MPF.
- **CNPJs tentados:** `26989715000102` — pode ser necessário atualizar.
- **Para verificar:** Acessar `https://pncp.gov.br/app/orgaos` e buscar "Ministério Público Federal".

### Erro 400/422/timeout no IP local
- **Causa:** O WAF do PNCP bloqueia IPs domésticos/corporativos.
- **Solução:** Rodar sempre pela VM (Oracle Cloud).

### Job timeout de 15 minutos
- **Causa:** Versão antiga do `atlas_job_runner.py` tinha timeout de 900s.
- **Solução aplicada:** Timeout aumentado para 1800s (30 minutos) no runner.

---

## 🔄 Como Continuar em Outro PC

### 1. Clonar os repositórios
```bash
git clone https://github.com/HenriMafra/atlas-pncp-pilot.git
git clone https://github.com/HenriMafra/atlas-b2g-online.git
```

### 2. Instalar dependências Python (script de coleta)
```bash
cd atlas-pncp-pilot
pip install openpyxl requests
```

### 3. Instalar dependências Node (painel web)
```bash
cd atlas-b2g-online
npm install
cp .env.example .env.local  # preencher com as chaves do Supabase
```

### 4. Credenciais necessárias
As credenciais estão em `C:\Users\henri.mafra\Documents\ORACLEVMS.env` na máquina atual.  
Você vai precisar de:
- **Chave SSH da VM:** `atlas_key` (baixar no Oracle Cloud Console → Identity → SSH Keys)
- **Supabase URL + Service Role Key** (no dashboard do Supabase → projeto `atlas-b2g-medflow`)
- **Cloudflare API Token** (para deploy — em `wrangler secret put`)

### 5. Variáveis do `.env.local`
```bash
NEXT_PUBLIC_SUPABASE_URL=https://hgczpdwhjqaqiravorrg.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...   # via wrangler secret put no deploy
```

---

## 📝 Histórico de Mudanças

| Data | Mudança |
|---|---|
| 2026-06-30 | Fix: `valor_total` mapeado para `valorGlobal`/`valorInicial` (PNCP mudou campo) |
| 2026-06-30 | Fix: `fim_vigencia` mapeado para `dataVigenciaFim`/`dataVigenciaInicio` |
| 2026-06-30 | Fix: Removidos dados de fallback inventados de SEST e POSTALIS |
| 2026-06-30 | Perf: Delay entre requisições reduzido de 1.2s para 0.7s (~40% mais rápido) |
| 2026-06-30 | Feat: Timeout do job aumentado de 900s para 1800s |
| 2026-06-30 | Feat: Botões de disparo adicionados ao painel Admin (Operação → Opções avançadas) |
| 2026-06-29 | Feat: Script `coleta_orgaos_especificos.py` criado com suporte a 7 órgãos |
