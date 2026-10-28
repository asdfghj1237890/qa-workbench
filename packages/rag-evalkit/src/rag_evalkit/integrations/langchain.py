"""LangChain Runnable/LCEL RAG bridge, without a LangSmith dependency.

API anchors: reference.langchain.com/python/langchain-core/runnables/ and
reference.langchain.com/python/langchain-core/callbacks/base/AsyncCallbackHandler.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..contracts import ContractError
from ..runtime import RuntimeFailure, TraceEvent, Usage
from ._common import FrameworkRag, evidence, sdk_import, usage_from_mapping


class LangChainRagPipeline(FrameworkRag):
    name = "langchain"

    def __init__(self, runnable, *, input_key="input", answer_key="answer", context_key="context",
                 config=None, limits=None, secrets=()):
        super().__init__(limits=limits, secrets=secrets)
        base = sdk_import("langchain_core.runnables", "langchain")
        if not isinstance(runnable, base.Runnable):
            raise ContractError("LangChain adapter requires a real Runnable")
        self._runnable = runnable
        self._input_key, self._answer_key, self._context_key = input_key, answer_key, context_key
        self._config = dict(config or {})

    def describe(self):
        return {"pipeline": self.name, "framework_type": type(self._runnable).__name__,
                "input_key": self._input_key, "answer_key": self._answer_key, "context_key": self._context_key,
                "usage": "reported_only", "scores": "reported_or_unknown", "cancellation": "cooperative_async",
                "budget": "unsupported_fail_closed"}

    async def _invoke(self, query, traces):
        callbacks = sdk_import("langchain_core.callbacks", "langchain")
        messages = sdk_import("langchain_core.messages", "langchain")
        documents = sdk_import("langchain_core.documents", "langchain")
        retrieved, reported = [], []
        secrets = self._secrets

        class Observer(callbacks.AsyncCallbackHandler):
            async def on_retriever_end(self, documents, *, run_id, **kwargs):
                retrieved.extend(documents)
                traces.append(TraceEvent("retrieval", {"framework": "langchain", "run_id": str(run_id), "count": len(documents)}))

            async def on_llm_end(self, response, *, run_id, **kwargs):
                output = response.llm_output or {}
                raw_usage = output.get("token_usage", output.get("usage"))
                if raw_usage is None:
                    for batch in response.generations:
                        for generation in batch:
                            raw_usage = getattr(getattr(generation, "message", None), "usage_metadata", None)
                            if raw_usage:
                                break
                        if raw_usage:
                            break
                reported.append(usage_from_mapping(raw_usage, secrets=secrets))
                traces.append(TraceEvent("model_end", {"framework": "langchain", "run_id": str(run_id),
                                                        "usage_reported": raw_usage is not None}))

        config = {**self._config, "callbacks": [*(self._config.get("callbacks") or []), Observer()]}
        value = query if self._input_key is None else {self._input_key: query}
        output = await self._runnable.ainvoke(value, config=config)
        selected = output.get(self._answer_key) if isinstance(output, Mapping) else output
        if isinstance(selected, messages.BaseMessage):
            if selected.additional_kwargs.get("refusal"):
                raise RuntimeFailure("refusal")
            answer = selected.content
            direct_usage = getattr(selected, "usage_metadata", None)
        else:
            answer, direct_usage = selected, None
        if not isinstance(answer, str):
            raise ContractError("LangChain answer must be text or a text BaseMessage")
        sources = output.get(self._context_key, retrieved) if isinstance(output, Mapping) else retrieved
        if sources is None:
            sources = []
        if not isinstance(sources, (list, tuple)):
            raise ContractError("LangChain context must be a document sequence")
        normalized = []
        for rank, source in enumerate(sources, 1):
            score = None
            if isinstance(source, tuple) and len(source) == 2:
                source, score = source
            if not isinstance(source, documents.Document):
                raise ContractError("LangChain context must contain real Document objects")
            score = source.metadata.get("score", score)
            normalized.append(evidence(source.page_content, source.metadata, rank,
                                       identity=source.id, score=score, secrets=secrets))
        if reported:
            usage = reported[0]
            for part in reported[1:]:
                usage = usage.plus(part)
        else:
            raw = output.get("usage", direct_usage) if isinstance(output, Mapping) else direct_usage
            usage = usage_from_mapping(raw, secrets=secrets) if raw is not None else Usage(details={"reported": False})
        return answer, normalized, usage, {"source_count": len(normalized), "provenance": "returned_documents"}
