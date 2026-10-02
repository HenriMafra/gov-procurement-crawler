# -*- coding: utf-8 -*-
"""
ATLAS B2G — Camada de banco (PostgreSQL/Supabase em produção; SQLite em teste).
O MESMO código roda nos dois: a partir da DATABASE_URL detectamos o dialeto.

  sqlite:///data/atlas_b2g.sqlite          (teste local, sem dependências)
  postgresql://user:pass@host:5432/db      (produção / Supabase — requer psycopg2-binary)

Regras de upsert (ver docs/database_model.md):
  - órgãos/fornecedores/contratos: upsert por chave natural (CNPJ/id_pncp) com fallback.
  - oportunidades: upsert por (contrato + tipo); PRESERVA responsável_atribuído e
    status comercial/validação editados manualmente; sempre grava snapshot no histórico.
"""
import os, re, json, sqlite3

class AtlasDB:
    def __init__(self, url):
        self.url = url
        self.dialect = "sqlite" if url.startswith("sqlite") else "postgres"
        self.ph = "?" if self.dialect == "sqlite" else "%s"
        self.con = self._connect()
        self.cur = self.con.cursor()
        if self.dialect == "sqlite":
            self.cur.execute("PRAGMA foreign_keys=ON")

    # ---------- conexão ----------
    def _connect(self):
        if self.dialect == "sqlite":
            path = re.sub(r"^sqlite:/{2,3}", "", self.url)
            d = os.path.dirname(path)
            if d: os.makedirs(d, exist_ok=True)
            con = sqlite3.connect(path)
            con.row_factory = sqlite3.Row
            return con
        try:
            import psycopg2  # noqa
        except Exception as e:
            raise RuntimeError("Para PostgreSQL/Supabase instale: pip install psycopg2-binary") from e
        import psycopg2
        return psycopg2.connect(self.url)

    def q(self, sql):
        return sql if self.dialect == "sqlite" else sql.replace("?", "%s")

    def _self(self, table):
        """Referência à linha EXISTENTE dentro do DO UPDATE (pg qualifica; sqlite não)."""
        return (table + ".") if self.dialect == "postgres" else ""

    def jsonval(self, obj):
        if obj is None: return None
        if self.dialect == "postgres":
            from psycopg2.extras import Json
            return Json(obj if not isinstance(obj, str) else json.loads(obj))
        return obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)

    # ---------- schema ----------
    def _to_sqlite(self, ddl):
        ddl = re.sub(r"BIGSERIAL\s+PRIMARY\s+KEY", "INTEGER PRIMARY KEY AUTOINCREMENT", ddl, flags=re.I)
        ddl = re.sub(r"\bBIGSERIAL\b", "INTEGER", ddl, flags=re.I)
        ddl = re.sub(r"\bBIGINT\b", "INTEGER", ddl, flags=re.I)
        ddl = re.sub(r"\bJSONB\b", "TEXT", ddl, flags=re.I)
        ddl = re.sub(r"\bTIMESTAMPTZ\b", "TEXT", ddl, flags=re.I)
        ddl = re.sub(r"NUMERIC\(\d+,\s*\d+\)", "REAL", ddl, flags=re.I)
        ddl = re.sub(r"\bNUMERIC\b", "REAL", ddl, flags=re.I)
        return ddl

    def init_schema(self, schema_path, seed_path=None):
        ddl = open(schema_path, encoding="utf-8").read()
        if self.dialect == "sqlite":
            self.con.executescript(self._to_sqlite(ddl))
        else:
            self.cur.execute(ddl)
        if seed_path and os.path.exists(seed_path):
            seed = open(seed_path, encoding="utf-8").read()
            if self.dialect == "sqlite":
                self.con.executescript(self._to_sqlite(seed))
            else:
                self.cur.execute(seed)
        self.con.commit()

    # ---------- helpers de escrita ----------
    def _insert_get_id(self, table, conflict, data, no_update=(), touch=False, json_cols=()):
        cols = list(data.keys())
        vals = [self.jsonval(data[c]) if c in json_cols else data[c] for c in cols]
        ph = ",".join([self.ph] * len(cols))
        sets = [f"{c}=excluded.{c}" for c in cols if c != conflict and c not in no_update]
        if touch: sets.append("updated_at=CURRENT_TIMESTAMP")
        sql = f"INSERT INTO {table} ({','.join(cols)}) VALUES ({ph}) ON CONFLICT({conflict}) DO UPDATE SET {','.join(sets)}"
        self.cur.execute(self.q(sql), vals)
        self.cur.execute(self.q(f"SELECT id FROM {table} WHERE {conflict}=?"), [data[conflict]])
        return self.cur.fetchone()[0]

    def upsert_orgao(self, d):
        return self._insert_get_id("orgaos", "orgao_key", d, touch=True)

    def upsert_fornecedor(self, d):
        return self._insert_get_id("fornecedores", "forn_key", d, touch=True)

    def upsert_contrato(self, d):
        return self._insert_get_id("contratos", "contrato_key", d, touch=True)

    def upsert_responsavel(self, d):
        return self._insert_get_id("responsaveis", "nome", d, no_update=("nome",), touch=True)

    def insert_rodada(self, d):
        # conflito por (tag, data_rodada): permite recarregar a mesma rodada
        cols = list(d.keys())
        vals = [self.jsonval(d[c]) if c == "config_json" else d[c] for c in cols]
        ph = ",".join([self.ph] * len(cols))
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("tag", "data_rodada"))
        sql = (f"INSERT INTO rodadas ({','.join(cols)}) VALUES ({ph}) "
               f"ON CONFLICT(tag,data_rodada) DO UPDATE SET {sets}")
        self.cur.execute(self.q(sql), vals)
        self.cur.execute(self.q("SELECT id FROM rodadas WHERE tag=? AND data_rodada=?"),
                         [d.get("tag", ""), d["data_rodada"]])
        return self.cur.fetchone()[0]

    def upsert_oportunidade(self, d):
        """Preserva responsável_atribuído e status comercial/validação manuais."""
        s = self._self("oportunidades")
        cols = list(d.keys())
        ph = ",".join([self.ph] * len(cols))
        manual = {"responsavel_atribuido", "status_comercial", "status_validacao",
                  "data_primeira_ocorrencia", "op_key", "created_at"}
        sets = [f"{c}=excluded.{c}" for c in cols if c not in manual]
        sets.append(f"responsavel_atribuido=COALESCE({s}responsavel_atribuido, excluded.responsavel_atribuido)")
        sets.append(f"data_primeira_ocorrencia=COALESCE({s}data_primeira_ocorrencia, excluded.data_primeira_ocorrencia)")
        sets.append(f"status_comercial=CASE WHEN {s}status_comercial IS NULL OR {s}status_comercial IN ('Novo','') "
                    f"THEN excluded.status_comercial ELSE {s}status_comercial END")
        sets.append(f"status_validacao=CASE WHEN {s}status_validacao IS NULL OR {s}status_validacao='Pendente' "
                    f"THEN excluded.status_validacao ELSE {s}status_validacao END")
        sets.append("updated_at=CURRENT_TIMESTAMP")
        sql = f"INSERT INTO oportunidades ({','.join(cols)}) VALUES ({ph}) ON CONFLICT(op_key) DO UPDATE SET {','.join(sets)}"
        self.cur.execute(self.q(sql), [d[c] for c in cols])
        self.cur.execute(self.q("SELECT id FROM oportunidades WHERE op_key=?"), [d["op_key"]])
        return self.cur.fetchone()[0]

    def insert_historico(self, d):
        cols = list(d.keys()); ph = ",".join([self.ph] * len(cols))
        sql = (f"INSERT INTO oportunidade_historico ({','.join(cols)}) VALUES ({ph}) "
               f"ON CONFLICT(oportunidade_id,rodada_id) DO NOTHING")
        self.cur.execute(self.q(sql), [d[c] for c in cols])

    def upsert_revisao(self, d):
        cols = list(d.keys()); ph = ",".join([self.ph] * len(cols))
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("oportunidade_id", "tipo_revisao", "criado_em"))
        sql = (f"INSERT INTO revisoes ({','.join(cols)}) VALUES ({ph}) "
               f"ON CONFLICT(oportunidade_id,tipo_revisao) DO UPDATE SET {sets}")
        self.cur.execute(self.q(sql), [d[c] for c in cols])

    # ---------- escrita EM LOTE (rápida) — Postgres usa execute_values + RETURNING;
    #            SQLite (teste) cai no caminho linha-a-linha. Cada lista já vem deduplicada por chave. ----------
    def batch_upsert(self, table, conflict, rows, no_update=(), touch=False, page_size=1000):
        """Upsert em lote por chave única `conflict`. Retorna {valor_da_chave: id}."""
        if not rows: return {}
        ded = {}
        for d in rows: ded[d[conflict]] = d
        rows = list(ded.values())
        if self.dialect == "sqlite":
            return {d[conflict]: self._insert_get_id(table, conflict, d, no_update=no_update, touch=touch) for d in rows}
        from psycopg2.extras import execute_values
        cols = list(rows[0].keys())
        sets = [f"{c}=excluded.{c}" for c in cols if c != conflict and c not in no_update]
        if touch: sets.append("updated_at=CURRENT_TIMESTAMP")
        setclause = (" DO UPDATE SET " + ",".join(sets)) if sets else " DO NOTHING"
        sql = (f"INSERT INTO {table} ({','.join(cols)}) VALUES %s "
               f"ON CONFLICT({conflict}){setclause} RETURNING {conflict}, id")
        tmpl = "(" + ",".join(["%s"] * len(cols)) + ")"
        vals = [[d[c] for c in cols] for d in rows]
        res = execute_values(self.cur, sql, vals, template=tmpl, page_size=page_size, fetch=True)
        return {r[0]: r[1] for r in res}

    def batch_upsert_oportunidades(self, rows, page_size=500):
        """Como upsert_oportunidade, mas em lote. Preserva responsável/status manuais. Retorna {op_key: id}."""
        if not rows: return {}
        ded = {}
        for d in rows: ded[d["op_key"]] = d
        rows = list(ded.values())
        if self.dialect == "sqlite":
            return {d["op_key"]: self.upsert_oportunidade(d) for d in rows}
        from psycopg2.extras import execute_values
        s = self._self("oportunidades")
        cols = list(rows[0].keys())
        manual = {"responsavel_atribuido", "status_comercial", "status_validacao",
                  "data_primeira_ocorrencia", "op_key", "created_at"}
        sets = [f"{c}=excluded.{c}" for c in cols if c not in manual]
        sets.append(f"responsavel_atribuido=COALESCE({s}responsavel_atribuido, excluded.responsavel_atribuido)")
        sets.append(f"data_primeira_ocorrencia=COALESCE({s}data_primeira_ocorrencia, excluded.data_primeira_ocorrencia)")
        sets.append(f"status_comercial=CASE WHEN {s}status_comercial IS NULL OR {s}status_comercial IN ('Novo','') "
                    f"THEN excluded.status_comercial ELSE {s}status_comercial END")
        sets.append(f"status_validacao=CASE WHEN {s}status_validacao IS NULL OR {s}status_validacao='Pendente' "
                    f"THEN excluded.status_validacao ELSE {s}status_validacao END")
        sets.append("updated_at=CURRENT_TIMESTAMP")
        sql = (f"INSERT INTO oportunidades ({','.join(cols)}) VALUES %s "
               f"ON CONFLICT(op_key) DO UPDATE SET {','.join(sets)} RETURNING op_key, id")
        tmpl = "(" + ",".join(["%s"] * len(cols)) + ")"
        vals = [[d[c] for c in cols] for d in rows]
        res = execute_values(self.cur, sql, vals, template=tmpl, page_size=page_size, fetch=True)
        return {r[0]: r[1] for r in res}

    def batch_insert_historico(self, rows, page_size=1000):
        if not rows: return
        if self.dialect == "sqlite":
            for d in rows: self.insert_historico(d)
            return
        from psycopg2.extras import execute_values
        cols = list(rows[0].keys())
        sql = (f"INSERT INTO oportunidade_historico ({','.join(cols)}) VALUES %s "
               f"ON CONFLICT(oportunidade_id,rodada_id) DO NOTHING")
        tmpl = "(" + ",".join(["%s"] * len(cols)) + ")"
        execute_values(self.cur, sql, [[d[c] for c in cols] for d in rows], template=tmpl, page_size=page_size)

    def batch_upsert_revisoes(self, rows, page_size=500):
        if not rows: return
        if self.dialect == "sqlite":
            for d in rows: self.upsert_revisao(d)
            return
        from psycopg2.extras import execute_values
        cols = list(rows[0].keys())
        sets = ",".join(f"{c}=excluded.{c}" for c in cols if c not in ("oportunidade_id", "tipo_revisao", "criado_em"))
        sql = (f"INSERT INTO revisoes ({','.join(cols)}) VALUES %s "
               f"ON CONFLICT(oportunidade_id,tipo_revisao) DO UPDATE SET {sets}")
        tmpl = "(" + ",".join(["%s"] * len(cols)) + ")"
        execute_values(self.cur, sql, [[d[c] for c in cols] for d in rows], template=tmpl, page_size=page_size)

    def insert_log(self, rodada_id, nivel, mensagem, detalhes=None):
        sql = f"INSERT INTO logs_execucao (rodada_id,nivel,mensagem,detalhes_json) VALUES ({self.ph},{self.ph},{self.ph},{self.ph})"
        self.cur.execute(self.q(sql), [rodada_id, nivel, mensagem, self.jsonval(detalhes)])

    def marcar_removidas(self, rodada_id):
        sql = (f"UPDATE oportunidades SET status_na_rodada='Removida', updated_at=CURRENT_TIMESTAMP "
               f"WHERE rodada_id<>{self.ph} AND (status_na_rodada IS NULL OR status_na_rodada<>'Removida')")
        self.cur.execute(self.q(sql), [rodada_id])
        return self.cur.rowcount

    # ---------- leitura ----------
    def fetch(self, sql, params=()):
        self.cur.execute(self.q(sql), params)
        cols = [c[0] for c in self.cur.description]
        return [dict(zip(cols, row)) for row in self.cur.fetchall()]

    def count(self, table):
        self.cur.execute(f"SELECT COUNT(*) FROM {table}")
        return self.cur.fetchone()[0]

    def commit(self): self.con.commit()
    def close(self):
        try: self.con.commit()
        finally: self.con.close()
