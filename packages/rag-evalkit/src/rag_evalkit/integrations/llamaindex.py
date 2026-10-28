"""LlamaIndex BaseQueryEngine bridge retaining source node and parent lineage.

API: developers.llamaindex.ai/python/framework-api-reference/query_engine/retriever/
"""

from __future__ import annotations

from ..contracts import ContractError
from ..runtime import TraceEvent
from ._common import FrameworkRag, evidence, sdk_import, usage_from_mapping


class LlamaIndexRagPipeline(FrameworkRag):
    name = "llamaindex"

    def __init__(self, query_engine, *, limits=None, secrets=()):
        super().__init__(limits=limits, secrets=secrets)
        base = sdk_import("llama_index.core.base.base_query_engine", "llamaindex")
        if not isinstance(query_engine, base.BaseQueryEngine):
            raise ContractError("LlamaIndex adapter requires a real BaseQueryEngine")
        self._engine = query_engine

    def describe(self):
        return {"pipeline": self.name, "framework_type": type(self._engine).__name__,
                "usage": "response_metadata_reported_only", "scores": "reported_or_unknown",
                "cancellation": "cooperative_async", "budget": "unsupported_fail_closed"}

    async def _invoke(self, query, traces):
        schema = sdk_import("llama_index.core.schema", "llamaindex")
        response = await self._engine.aquery(query)
        if hasattr(response, "async_response_gen") or hasattr(response, "response_gen"):
            raise ContractError("use a non-streaming LlamaIndex query engine for normalized RAG results")
        answer = getattr(response, "response", None)
        if not isinstance(answer, str):
            raise ContractError("LlamaIndex response must contain a text response")
        nodes = getattr(response, "source_nodes", None)
        if not isinstance(nodes, (list, tuple)):
            raise ContractError("LlamaIndex response must expose source_nodes")
        sources = []
        for rank, source in enumerate(nodes, 1):
            if not isinstance(source, schema.NodeWithScore):
                raise ContractError("LlamaIndex sources must be NodeWithScore objects")
            node = source.node
            sources.append(evidence(node.get_content(metadata_mode=schema.MetadataMode.NONE), node.metadata, rank,
                                    identity=node.node_id, parent=node.ref_doc_id, score=source.score,
                                    secrets=self._secrets))
        metadata = response.metadata or {}
        usage = usage_from_mapping(metadata.get("usage"), secrets=self._secrets)
        traces.append(TraceEvent("retrieval", {"framework": self.name, "node_ids": [item.chunk_id for item in sources],
                                               "source_ids": [item.source_id for item in sources]}))
        return answer, sources, usage, {"source_count": len(sources), "provenance": "response_source_nodes"}
