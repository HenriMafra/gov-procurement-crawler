# Gov Procurement Crawler: Asynchronous Ingestion Pipeline with Adaptive Token Bucket Rate Limiting

**Author:** Henri Mafra  
**License:** MIT License  
**Domain:** Distributed Systems, Data Engineering, Asynchronous Network I/O  

---

## 1. Overview

Gov Procurement Crawler is a high-throughput Python data extraction pipeline engineered for continuous ingestion, schema normalization, and archival of public bidding notices from the Brazilian National Portal of Public Procurement (PNCP API). The architecture implements **adaptive token-bucket rate limiting**, exponential backoff with decorrelated jitter, and dual-layer persistence (PostgreSQL and Apache Parquet).

---

## 2. Rate Limiting and Resilience Algorithms

Upstream government endpoints enforce strict traffic quotas. The crawler coordinates concurrent asynchronous workers using a **Token Bucket Rate Limiter**:

### 2.1. Token Bucket Specification
Let bucket capacity be $C$ tokens with fill rate $r$ tokens/second. A request consumes 1 token. At timestamp $t$, available tokens $T(t)$ update as:

$$T(t) = \min\left(C, \; T(t_{\text{last}}) + r \times (t - t_{\text{last}})\right)$$

### 2.2. Decorrelated Jitter Retry Formulation
Upon encountering transient network faults or HTTP 429 status codes, retry sleep duration $t_{\text{wait}}$ is computed using Full Jitter:

$$t_{\text{wait}} = \text{Uniform}\left(0, \; \min(t_{\max}, \; t_{\text{base}} \times 2^{\text{attempt}})\right)$$

This prevents synchronized retry storms across concurrent worker coroutines.

---

## 3. Dual-Layer Storage Architecture

- **Operational Relational Tier (PostgreSQL):** Stores current state, run logs, and document references.
- **Analytical Columnar Tier (Apache Parquet):** Historical datasets partitioned by year and month (`year=YYYY/month=MM/part-*.parquet`) using Snappy compression for analytical workloads.

---

## 4. Setup and Execution

```bash
# 1. Clone repository
git clone https://github.com/HenriMafra/gov-procurement-crawler.git
cd gov-procurement-crawler

# 2. Setup virtual environment
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Execute ingestion
python main.py --start-date 2026-01-01 --modality 6
```

---

## 5. References

- Tanenbaum, A. S., & Van Steen, M. (2017). *Distributed Systems: Principles and Paradigms* (3rd ed.). CreateSpace.
- Vohra, D. (2016). *Apache Parquet: Columnar Storage for Big Data Analytics*. Apress.

---

## 6. License

Licensed under the MIT License. Copyright (c) Henri Mafra.
