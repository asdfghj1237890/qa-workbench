"""Synthetic protocol fixtures and opt-in isolated backend wiring.

Contract: ES mapping/script_score/knn HTTP APIs documented in stores/elasticsearch.py;
psycopg transaction/cursor and pgvector SQL documented in stores/postgres.py.
Fixtures emulate those protocols, never claim to be a running ES/PostgreSQL server.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
import threading
import types
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

from rag_evalkit.contracts import Document, SearchSpec
from rag_evalkit.stores import ElasticsearchStore, MemoryStore, PostgresStore


def _distance(left, right, metric):
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    if metric == "l2":
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))
    if metric == "inner_product":
        return -dot
    return 1 - dot / (math.sqrt(sum(x * x for x in left)) * math.sqrt(sum(x * x for x in right)))


class _HTTPFixture:
    def __init__(self):
        self.indices, self.requests, self.fault = {}, [], None
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _handle(self):
                path = urlsplit(self.path).path
                segments = path.strip("/").split("/")
                index = segments[0]
                size = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(size)) if size else None
                fixture.requests.append({"method": self.command, "path": self.path, "body": body})
                status, response = 200, {}
                if self.command == "GET" and path == "/":
                    response = {"version": {"number": "synthetic-protocol-9.5.5"}}
                elif self.command == "PUT" and len(segments) == 1:
                    if index in fixture.indices:
                        status, response = 400, {"error": "resource_already_exists_exception"}
                    else:
                        fixture.indices[index] = {"mappings": body["mappings"], "documents": {}}
                        response = {"acknowledged": fixture.fault != "create_unacknowledged"}
                elif index not in fixture.indices:
                    status, response = 404, {"error": "index_not_found_exception"}
                elif segments[1:] == ["_mapping"]:
                    response = {index: {"mappings": fixture.indices[index]["mappings"]}}
                elif self.command == "DELETE" and len(segments) == 1:
                    del fixture.indices[index]
                    response = {"acknowledged": True}
                elif len(segments) == 3 and segments[1] == "_doc":
                    documents = fixture.indices[index]["documents"]
                    document_id = unquote(segments[2])
                    if self.command == "PUT":
                        documents[document_id] = body
                        response = {"result": "created"}
                    else:
                        missing = documents.pop(document_id, None) is None
                        status = 404 if missing else 200
                        response = {"result": "not_found" if missing else "deleted"}
                elif segments[1:] == ["_search"]:
                    exact = "query" in body
                    if exact:
                        scoring = body["query"]["script_score"]
                        query = scoring["script"]["params"]["vector"]
                        script = scoring["script"]["source"]
                        metric = "cosine" if "cosineSimilarity" in script else "l2" if "l2norm" in script else "inner_product"
                        filters = scoring["query"].get("bool", {}).get("filter", [])
                    else:
                        query = body["knn"]["query_vector"]
                        metric = {"cosine": "cosine", "l2_norm": "l2", "max_inner_product": "inner_product"}[fixture.indices[index]["mappings"]["properties"]["vector"]["similarity"]]
                        filters = body["knn"]["filter"].get("bool", {}).get("filter", [])
                    hits = []
                    for document in fixture.indices[index]["documents"].values():
                        if not all(item["term"]["filter_tokens"] in document["filter_tokens"] for item in filters):
                            continue
                        distance = _distance(query, document["original_vector"], metric)
                        score = ((2 - distance) / (1 if exact else 2) if metric == "cosine" else
                                 1 / (1 + (distance if exact else distance ** 2)) if metric == "l2" else
                                 1 - distance if distance <= 0 else 1 / (1 + distance))
                        hits.append({"_score": score, "_source": document})
                    hits.sort(key=lambda hit: (-hit["_score"], hit["_source"]["document_id"]))
                    response = {"timed_out": fixture.fault == "timeout", "_shards": {"failed": int(fixture.fault == "partial")}, "hits": {"hits": hits[:body["size"]]}}
                    if fixture.fault == "malformed":
                        response = {}
                else:
                    status, response = 400, {"error": "unsupported fixture request"}
                payload = json.dumps(response).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_PUT = do_POST = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True)
        self.thread.start()

    @property
    def url(self):
        return "http://127.0.0.1:" + str(self.server.server_port)

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


class _Transaction:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        self.before = copy.deepcopy(self.connection.tables)

    def __exit__(self, kind, value, traceback):
        if kind:
            self.connection.tables.clear()
            self.connection.tables.update(self.before)


class _Cursor:
    def __init__(self, connection):
        self.connection, self.rows = connection, []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def execute(self, query, params=None):
        self.connection.requests.append({"sql": query, "params": list(params or ())})
        self.rows = []
        tables = self.connection.tables
        table_match = re.search(r'"[a-z0-9_]+"\."[a-z0-9_]+"', query)
        table = table_match.group() if table_match else None
        if query.startswith("SELECT extversion"):
            self.rows = [("0.8.1",)]
        elif query == "SHOW server_version":
            self.rows = [("17.6-protocol-fixture",)]
        elif query.startswith("CREATE TABLE"):
            if table in tables:
                raise RuntimeError("duplicate table")
            tables[table] = {"owner": None, "documents": {}, "index": None}
        elif query.startswith("COMMENT ON TABLE"):
            tables[table]["owner"] = query.split(" IS '")[1][:-1]
        elif query.startswith("CREATE INDEX"):
            if self.connection.fault == "create_index":
                raise RuntimeError("synthetic DDL failure")
            tables[table]["index"] = query.split('"')[1]
        elif query.startswith("INSERT INTO"):
            document_id, text, vector, metadata = params
            tables[table]["documents"][document_id] = (document_id, text, vector, json.loads(metadata))
        elif query.startswith("DELETE FROM"):
            for document_id in params[0]:
                tables[table]["documents"].pop(document_id, None)
        elif query.startswith("SELECT to_regclass"):
            self.rows = [(params[0] if params[0] in tables else None, tables.get(params[0], {}).get("owner"))]
        elif query.startswith("DROP TABLE"):
            del tables[table]
        elif query.startswith("EXPLAIN"):
            index = tables[table]["index"]
            plan = {"Node Type": "Seq Scan"} if self.connection.fault == "fallback" else {"Node Type": "Index Scan", "Index Name": index}
            self.rows = [([{"Plan": plan}],)]
        elif query.startswith("SELECT id, text"):
            metric = "cosine" if "<=>" in query else "l2" if "<->" in query else "inner_product"
            vector = json.loads(params[0])
            filters = json.loads(params[1]) if " WHERE " in query else {}
            rows = []
            for document_id, text, embedding, metadata in tables[table]["documents"].values():
                def equal(key, value, metadata=metadata):
                    if key not in metadata:
                        return False
                    actual = metadata[key]
                    if isinstance(actual, bool) != isinstance(value, bool):
                        return False
                    return actual == value
                if all(equal(key, value) for key, value in filters.items()):
                    rows.append((document_id, text, embedding, metadata, _distance(vector, json.loads(embedding), metric)))
            rows.sort(key=lambda row: (row[4], row[0]))
            self.rows = rows[:params[-1]]

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.tables, self.requests, self.fault, self.closed = {}, [], None, False
        self.info = types.SimpleNamespace(host="fixture", port=5432, dbname="db", user="synthetic", get_parameters=lambda: {"host": "fixture", "user": "synthetic", "dbname": "db"})

    def transaction(self):
        return _Transaction(self)

    def cursor(self):
        return _Cursor(self)

    def close(self):
        self.closed = True


def resolved_postgres_targets():
    first, second = _Connection(), _Connection()
    second.info.host = "different-effective-libpq-host"
    connections = iter((first, second))
    with patch.dict("sys.modules", {"psycopg": types.SimpleNamespace(connect=lambda *args, **kwargs: next(connections))}):
        with PostgresStore("", 3) as left, PostgresStore("", 3) as right:
            return {"left": left.describe(), "right": right.describe()}


def redirect_observation(status):
    target = _HTTPFixture()
    observed = {"source_authorization": None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            observed["source_authorization"] = self.headers.get("Authorization")
            self.send_response(status)
            self.send_header("Location", target.url.replace("127.0.0.1", "localhost") + "/")
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=lambda: server.serve_forever(poll_interval=.02), daemon=True)
    thread.start()
    try:
        try:
            store = ElasticsearchStore("http://127.0.0.1:" + str(server.server_port), 3, api_key="synthetic-redirect-test")
            store.close()
            observed["error_type"] = None
        except RuntimeError as exc:
            observed["error_type"], observed["error"] = type(exc).__name__, str(exc)
        observed["target_requests"] = len(target.requests)
        return observed
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        target.close()


class StoreDriver:
    def __init__(self, backend, dimensions=3, ann_metric=None):
        self.backend, self.fixture, self.store = backend, None, None
        if backend == "memory":
            self.store = MemoryStore(dimensions)
        elif backend == "es_protocol":
            self.fixture = _HTTPFixture()
            try:
                self.store = ElasticsearchStore(self.fixture.url, dimensions, ann_metric=ann_metric, api_key="synthetic-test-key")
            except Exception:
                self.fixture.close()
                raise
        elif backend == "postgres_protocol":
            self.fixture = _Connection()
            module = types.SimpleNamespace(connect=lambda *args, **kwargs: self.fixture, conninfo=types.SimpleNamespace(conninfo_to_dict=lambda value: {"host": "fixture", "user": "synthetic", "dbname": "db"}))
            with patch.dict("sys.modules", {"psycopg": module}):
                self.store = PostgresStore("postgres://synthetic:private@fixture/db", dimensions, ann_metric=ann_metric)
        elif backend in {"es_live", "postgres_live"}:
            if os.environ.get("EVALKIT_INTEGRATION") != "1":
                raise RuntimeError("live database tests require EVALKIT_INTEGRATION=1")
            if backend == "es_live":
                self.store = ElasticsearchStore(os.environ["EVALKIT_ES_URL"], dimensions, ann_metric=ann_metric,
                                               api_key=os.environ.get("EVALKIT_ES_API_KEY"), username=os.environ.get("EVALKIT_ES_USERNAME"), password=os.environ.get("EVALKIT_ES_PASSWORD"))
            else:
                self.store = PostgresStore(os.environ["EVALKIT_POSTGRES_DSN"], dimensions, ann_metric=ann_metric)
        else:
            raise ValueError("unknown fixture backend")

    def upsert(self, documents):
        self.store.upsert([Document(item["id"], item.get("text", item["id"]), tuple(item["vector"]), item.get("metadata", {})) for item in documents])

    def search(self, vector, **settings):
        return [asdict(hit) for hit in self.store.search(SearchSpec(tuple(vector), **settings))]

    def describe(self):
        return self.store.describe()

    def delete(self, ids):
        self.store.delete(ids)

    def fault(self, kind):
        self.fixture.fault = kind

    def tamper_owner(self, owner):
        if self.backend == "es_protocol":
            self.fixture.indices[self.store.index_name]["mappings"]["_meta"]["rag_evalkit_owner"] = owner
        elif self.backend == "postgres_protocol":
            self.fixture.tables[self.store._table]["owner"] = owner

    def owner(self):
        return self.store._owner

    def capture(self):
        if self.backend == "es_protocol":
            return {"evidence": "synthetic_http_protocol", "requests": self.fixture.requests,
                    "resources_remaining": len(self.fixture.indices)}
        if self.backend == "postgres_protocol":
            return {"evidence": "synthetic_dbapi_protocol", "requests": self.fixture.requests,
                    "resources_remaining": len(self.fixture.tables), "connection_closed": self.fixture.closed}
        return {"evidence": "live_backend" if self.backend.endswith("live") else "in_memory_oracle"}

    def close(self):
        if self.store:
            self.store.close()

    def dispose(self):
        try:
            self.close()
        finally:
            if self.backend == "es_protocol":
                self.fixture.close()


def integration_available(backend):
    variable = "EVALKIT_ES_URL" if backend == "es_live" else "EVALKIT_POSTGRES_DSN"
    return os.environ.get("EVALKIT_INTEGRATION") == "1" and bool(os.environ.get(variable))


def construction_failure(backend):
    """Observe constructor rollback/cleanup without deriving a test verdict."""
    if backend == "es_protocol":
        fixture = _HTTPFixture()
        fixture.fault = "create_unacknowledged"
        try:
            try:
                ElasticsearchStore(fixture.url, 3)
            except Exception as error:
                return {"error_type": type(error).__name__, "error": str(error),
                        "resources_remaining": len(fixture.indices), "requests": fixture.requests}
            return {"error_type": None, "resources_remaining": len(fixture.indices)}
        finally:
            fixture.close()
    fixture = _Connection()
    fixture.fault = "create_index"
    with patch.dict("sys.modules", {"psycopg": types.SimpleNamespace(connect=lambda *args, **kwargs: fixture, conninfo=types.SimpleNamespace(conninfo_to_dict=lambda value: {"host": "fixture", "user": "synthetic", "dbname": "db"}))}):
        try:
            PostgresStore("postgres://synthetic:private@fixture/db", 3, ann_metric="cosine")
        except Exception as error:
            return {"error_type": type(error).__name__, "error": str(error),
                    "resources_remaining": len(fixture.tables), "connection_closed": fixture.closed,
                    "requests": fixture.requests}
    return {"error_type": None, "resources_remaining": len(fixture.tables)}


def existing_index_collision():
    fixture = _HTTPFixture()
    first = ElasticsearchStore(fixture.url, 3)
    try:
        try:
            ElasticsearchStore(fixture.url, 3, index_name=first.index_name)
        except Exception as error:
            return {"error_type": type(error).__name__, "resources_remaining": len(fixture.indices),
                    "delete_requests": [request for request in fixture.requests if request["method"] == "DELETE"]}
        return {"error_type": None, "resources_remaining": len(fixture.indices)}
    finally:
        first.close()
        fixture.close()
