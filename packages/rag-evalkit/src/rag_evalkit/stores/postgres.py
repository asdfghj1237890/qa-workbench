"""psycopg/pgvector adapter with transactional, exclusively owned tables.

SQL contract: https://github.com/pgvector/pgvector#querying and #hnsw.
The vector extension must already be installed by the database administrator.
Exact queries disable index scans; ANN queries require the owned HNSW index in
the PostgreSQL plan. A planner fallback is an unsupported observation, not ANN.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

from ..contracts import (
    Capabilities,
    ContractError,
    Document,
    SearchHit,
    SearchSpec,
    UnsupportedCapability,
)
from ._common import (
    FEATURES,
    StoreError,
    StoreLifecycle,
    description,
    dimensions_checked,
    documents_checked,
    identifier,
    ids_checked,
    json_value,
    spec_checked,
)


class PostgresStore(StoreLifecycle):
    def __init__(self, dsn: str, dimensions: int, *, table_name: str | None = None, schema: str = "public",
                 ann_metric: str | None = None, hnsw_m: int = 16, hnsw_ef_construction: int = 64,
                 hnsw_ef_search: int = 40, timeout: float = 10):
        self.dimensions = dimensions_checked(dimensions)
        if ann_metric not in {None, "cosine", "l2", "inner_product"}:
            raise UnsupportedCapability("unsupported ANN metric")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ContractError("timeout must be positive and finite")
        for label, value, minimum in (("hnsw_m", hnsw_m, 2), ("hnsw_ef_construction", hnsw_ef_construction, 4), ("hnsw_ef_search", hnsw_ef_search, 1)):
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ContractError(label + " is invalid")
        if hnsw_ef_construction < 2 * hnsw_m:
            raise ContractError("hnsw_ef_construction must be at least twice hnsw_m")
        if ann_metric and dimensions > 2000:
            raise UnsupportedCapability("pgvector vector HNSW supports at most 2000 dimensions")
        self.schema = identifier(schema)
        self.table_name = identifier(table_name or "rag_evalkit_" + uuid4().hex)
        if not self.table_name.startswith("rag_evalkit_"):
            raise ContractError("ephemeral table names must start with rag_evalkit_")
        self._table = '"' + self.schema + '"."' + self.table_name + '"'
        self._index = "rei_" + uuid4().hex
        self._owner = "rag_evalkit:" + uuid4().hex
        self._ann_metric, self._timeout = ann_metric, timeout
        self._hnsw_m, self._hnsw_ef_construction, self._hnsw_ef_search = hnsw_m, hnsw_ef_construction, hnsw_ef_search
        self._closed, self._created = False, False
        self.capabilities = Capabilities(FEATURES | ({"ann"} if ann_metric else set()))
        try:
            import psycopg
        except ImportError:
            raise UnsupportedCapability("PostgreSQL requires rag-evalkit[postgres]") from None
        try:
            self._connection = psycopg.connect(dsn, connect_timeout=max(1, math.ceil(timeout)))
        except Exception:
            raise StoreError("PostgreSQL connection failed") from None
        try:
            # ConnectionInfo reflects libpq defaults, environment/service files
            # and the selected endpoint, unlike parsing the input DSN alone.
            info = self._connection.info
            identity = {key: value for key, value in info.get_parameters().items() if key not in {"password", "passfile", "sslpassword", "sslkey"}}
            identity.update({key: getattr(info, key) for key in ("host", "port", "dbname", "user")})
            identity["schema"] = self.schema
            self._target_sha = hashlib.sha256(json_value(identity).encode()).hexdigest()
            with self._transaction() as cursor:
                cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cursor.fetchone()
                if not row:
                    raise UnsupportedCapability("the database must already have the pgvector extension")
                self._vector_version = str(row[0])
                cursor.execute("SHOW server_version")
                self._server_version = str(cursor.fetchone()[0])
                cursor.execute("CREATE TABLE " + self._table + " (id TEXT PRIMARY KEY, text TEXT NOT NULL, embedding vector(" + str(dimensions) + ") NOT NULL, metadata JSONB NOT NULL)")
                # COMMENT's grammar does not accept a bind placeholder. A random
                # internally generated hex marker is the only interpolated value.
                cursor.execute("COMMENT ON TABLE " + self._table + " IS '" + self._owner + "'")
                if ann_metric:
                    operator_class = {"cosine": "vector_cosine_ops", "l2": "vector_l2_ops", "inner_product": "vector_ip_ops"}[ann_metric]
                    cursor.execute('CREATE INDEX "' + self._index + '" ON ' + self._table + " USING hnsw (embedding " + operator_class + ") WITH (m = " + str(hnsw_m) + ", ef_construction = " + str(hnsw_ef_construction) + ")")
            self._created = True
        except Exception as error:
            # DDL and marker creation share one transaction. Verify ownership
            # again in case commit succeeded but its acknowledgement was lost.
            try:
                self.close()
            except Exception:
                error.add_note("owned-table cleanup could not be confirmed; no foreign resource was dropped")
            finally:
                self._connection.close()
                self._closed = True
            raise

    @contextmanager
    def _transaction(self):
        try:
            with self._connection.transaction():
                with self._connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)", (str(math.ceil(self._timeout * 1000)),))
                    yield cursor
        except (ContractError, UnsupportedCapability, StoreError):
            raise
        except Exception:
            raise StoreError("PostgreSQL transaction failed") from None

    def describe(self) -> dict:
        return description("postgres", self.dimensions, algorithm="hnsw" if self._ann_metric else "exact",
                           target_sha=self._target_sha,
                           pgvector_version=self._vector_version, server_version=self._server_version,
                           ann_metric=self._ann_metric, hnsw_m=self._hnsw_m if self._ann_metric else None,
                           hnsw_ef_construction=self._hnsw_ef_construction if self._ann_metric else None,
                           hnsw_ef_search=self._hnsw_ef_search if self._ann_metric else None,
                           precision="float32", timeout_seconds=self._timeout)

    @staticmethod
    def _vector(values: Sequence[float]) -> str:
        return json_value(list(values))

    def upsert(self, documents: Sequence[Document]) -> None:
        self._check_open()
        documents = documents_checked(documents, self.dimensions)
        with self._transaction() as cursor:
            for document in documents:
                cursor.execute("INSERT INTO " + self._table + " (id, text, embedding, metadata) VALUES (%s, %s, %s::vector, %s::jsonb) ON CONFLICT (id) DO UPDATE SET text = EXCLUDED.text, embedding = EXCLUDED.embedding, metadata = EXCLUDED.metadata",
                               (document.id, document.text, self._vector(document.vector), json_value(document.metadata)))

    def search(self, spec: SearchSpec) -> list[SearchHit]:
        self._check_open()
        spec_checked(spec, self.dimensions)
        if not spec.exact and self._ann_metric != spec.metric:
            raise UnsupportedCapability("ANN requires an index configured for the requested metric")
        operator = {"cosine": "<=>", "l2": "<->", "inner_product": "<#>"}[spec.metric]
        vector = self._vector(spec.vector)
        query = "SELECT id, text, embedding::text, metadata, embedding " + operator + " %s::vector AS distance FROM " + self._table
        params: list[Any] = [vector]
        if spec.filters:
            query += " WHERE metadata @> %s::jsonb"
            params.append(json_value(dict(spec.filters)))
        query += " ORDER BY embedding " + operator + " %s::vector"
        params.append(vector)
        if spec.exact:
            query += ", id"
        query += " LIMIT %s"
        params.append(spec.top_k)
        with self._transaction() as cursor:
            if spec.exact:
                cursor.execute("SET LOCAL enable_indexscan = off")
                cursor.execute("SET LOCAL enable_bitmapscan = off")
            else:
                cursor.execute("SET LOCAL enable_seqscan = off")
                cursor.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(self._hnsw_ef_search),))
                cursor.execute("EXPLAIN (FORMAT JSON) " + query, tuple(params))
                explain = cursor.fetchone()[0]
                if isinstance(explain, str):
                    explain = json.loads(explain)
                if not self._uses_owned_index(explain):
                    raise UnsupportedCapability("PostgreSQL planner did not select the owned HNSW index")
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        observations = []
        if len(rows) > spec.top_k:
            raise StoreError("PostgreSQL returned invalid search evidence")
        seen = set()
        for row in rows:
            try:
                document = Document(str(row[0]), row[1], tuple(json.loads(row[2])), row[3])
                documents_checked([document], self.dimensions)
                if document.id in seen:
                    raise ValueError()
                seen.add(document.id)
                raw = float(row[4])
                canonical = 1.0 - raw if spec.metric == "cosine" else -raw
                if not math.isfinite(canonical):
                    raise ValueError()
            except (IndexError, TypeError, ValueError):
                raise StoreError("PostgreSQL returned invalid search evidence") from None
            observations.append((canonical, document, raw))
        observations.sort(key=lambda item: (-item[0], item[1].id))
        return [SearchHit(document, score, raw, "pgvector_" + {"cosine": "cosine_distance", "l2": "l2_distance", "inner_product": "negative_inner_product"}[spec.metric], rank)
                for rank, (score, document, raw) in enumerate(observations, 1)]

    def _uses_owned_index(self, value: Any) -> bool:
        if isinstance(value, dict):
            return value.get("Index Name") == self._index or any(self._uses_owned_index(child) for child in value.values())
        return isinstance(value, list) and any(self._uses_owned_index(child) for child in value)

    def delete(self, ids: Sequence[str]) -> None:
        self._check_open()
        ids = ids_checked(ids)
        with self._transaction() as cursor:
            cursor.execute("DELETE FROM " + self._table + " WHERE id = ANY(%s)", (ids,))

    def close(self) -> None:
        if self._closed:
            return
        with self._transaction() as cursor:
            cursor.execute("SELECT to_regclass(%s), obj_description(to_regclass(%s), 'pg_class')", (self._table, self._table))
            row = cursor.fetchone()
            exists, owner = row if row else (None, None)
            if exists and owner != self._owner:
                # Missing and unowned tables both require investigation. In
                # particular, never issue DROP against an unowned identifier.
                raise StoreError("refusing to delete a table without the expected ownership marker")
            if exists:
                cursor.execute("DROP TABLE " + self._table)
        self._connection.close()
        self._closed = True
