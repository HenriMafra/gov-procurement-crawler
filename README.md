# 🕷️ Gov Procurement Crawler — Pipeline Assíncrono de Ingestão de Licitações do PNCP

Pipeline de dados de alta performance em Python para **coleta contínua, normalização e ingestão em larga escala de licitações, atas de registro de preços e contratos** do **Portal Nacional de Contratações Públicas (PNCP - Lei 14.133/21)**.

---

## 📌 Que Problema Resolve?

A API aberta do PNCP concentra as contratações públicas de todos os órgãos federais, estaduais e municipais do Brasil. No entanto, coletar dados históricos ou em tempo real de forma massiva apresenta desafios operacionais severos:
- Rate limiting agressivo que derruba requisições concorrentes não coordenadas.
- Paginação profunda com inconsistências eventuais de schema entre municípios.
- Necessidade de conciliar dados cadastrais com itens de compra e anexos documentais.

O **Gov Procurement Crawler** foi desenvolvido como um serviço resiliente de backend para manter bancos de dados analíticos sincronizados 24 horas por dia, 7 dias por semana.

---

## ⚙️ Diferencial Técnico & Arquitetura

- **Controle Dinâmico de Vazão (Token Bucket & Adaptive Rate Limiting):**
  Ajusta dinamicamente a taxa de requisições por segundo para evitar códigos `HTTP 429 (Too Many Requests)`.
- **Estratégia de Retry com Exponential Backoff & Jitter:**
  Recuperação automática de falhas transitórias de rede sem sobrecarregar a infraestrutura governamental.
- **Persistência Dual (Relacional + Parquet):**
  Exporta os dados tanto para banco relacional (PostgreSQL) quanto para arquivos particionados colunares em Apache Parquet para consultas analíticas de baixo custo.

---

## 🏗️ Stack Tecnológica

- **Linguagem:** Python 3.10+
- **Bibliotecas:** `httpx` / `aiohttp` (requisições assíncronas), `pydantic` (validação estrita de contratos de dados), `tenacity` (retries), `pandas` / `pyarrow` (geração de Parquet).
- **Orquestração:** Pronto para execução em cron jobs, Airflow ou GitHub Actions agendadas.

---

## 🚀 Como Executar Localmente

```bash
# 1. Clone o repositório
git clone https://github.com/HenriMafra/gov-procurement-crawler.git
cd gov-procurement-crawler

# 2. Crie e ative o ambiente virtual
python -m venv venv
source venv/bin/activate  # No Windows: .\venv\Scripts\activate

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Inicie a extração de dados
python main.py --data-inicio 2026-01-01 --modalidade 6
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Desenvolvido por **Henri Mafra**.
