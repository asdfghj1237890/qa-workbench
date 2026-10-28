"""Installable factories using real frameworks and the experiment's own harness.

The example retriever is deliberately a fixed corpus slice, not a relevance
model. Replace this factory with your application's Runnable/query engine when
evaluating retrieval quality. Generation uses the selected harness/model factor.
The JSON manifest contains names/options, never arbitrary Python import paths.
"""

from dataclasses import asdict

from rag_evalkit.contracts import ContractError, UnsupportedCapability
from rag_evalkit.integrations import (
    LangChainRagPipeline,
    LlamaIndexRagPipeline,
    build_openai_agents_harness,
)
from rag_evalkit.runtime import Message, RuntimeFailure


def _rows(config, context):
    variant = context.get("variant", {})
    if variant.get("prompt") or variant.get("tools"):
        raise UnsupportedCapability("example framework factories use a fixed prompt and no custom tools")
    unknown = set(config) - {"type", "top_k"}
    if unknown:
        raise ContractError("unknown example RAG options: " + ", ".join(sorted(unknown)))
    top_k = config.get("top_k", 3)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ContractError("top_k must be a positive integer")
    return context["dataset"]["documents"][:top_k]


class _ReportedPipeline:
    def __init__(self, pipeline, context):
        self.pipeline, self.context = pipeline, context

    def run(self, query):
        return self.pipeline.run(query)

    def describe(self):
        return {**self.pipeline.describe(), "retriever": {"adapter": "example_fixed_corpus_slice", "semantic_quality": "not_evaluated"},
                "harness": self.context["harness"].describe(),
                "model": self.context["model"].describe(), "prompt": {"template": "external_example_source_only_v1"}}


def langchain(config, **context):
    from langchain_core.documents import Document
    from langchain_core.retrievers import BaseRetriever
    from langchain_core.runnables import (
        RunnableLambda,
        RunnableParallel,
        RunnablePassthrough,
    )

    rows = _rows(config, context)

    class Retriever(BaseRetriever):
        def _get_relevant_documents(self, query, *, run_manager):
            return [Document(id=row["id"] + ":0", page_content=row["text"],
                             metadata={**row.get("metadata", {}), "source_id": row["source_id"], "document_id": row["id"]})
                    for row in rows]

    def generate(value):
        source_text = "\n\n".join("[source:" + doc.metadata["source_id"] + "]\n" + doc.page_content for doc in value["context"])
        result = context["harness"].run([Message("system", "Answer only using supplied sources and cite [source:ID]."),
                                        Message("user", value["query"] + "\n\n" + source_text)], limits=context["limits"])
        if result.status != "completed":
            raise RuntimeFailure(result.status)
        return {"answer": result.answer, "context": value["context"], "usage": asdict(result.usage)}

    chain = RunnableParallel(context=Retriever(), query=RunnablePassthrough()) | RunnableLambda(generate)
    pipeline = LangChainRagPipeline(chain, input_key=None, limits=context["limits"])
    return _ReportedPipeline(pipeline, context)


def llamaindex(config, **context):
    from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
    from llama_index.core.query_engine import RetrieverQueryEngine
    from llama_index.core.retrievers import BaseRetriever
    from llama_index.core.schema import NodeWithScore, TextNode

    rows = _rows(config, context)
    generation_usage = []

    class Retriever(BaseRetriever):
        def _retrieve(self, query_bundle):
            return [NodeWithScore(node=TextNode(id_=row["id"] + ":0", text=row["text"],
                                     metadata={**row.get("metadata", {}), "source_id": row["source_id"], "document_id": row["id"]}))
                    for row in rows]

    class HarnessLLM(CustomLLM):
        @property
        def metadata(self):
            return LLMMetadata(context_window=context["limits"].max_input_tokens,
                               num_output=context["limits"].max_output_tokens, model_name="selected-evalkit-harness")

        def complete(self, prompt, formatted=False, **kwargs):
            result = context["harness"].run([Message("user", prompt)], limits=context["limits"])
            if result.status != "completed":
                raise RuntimeFailure(result.status)
            generation_usage.append(result.usage)
            return CompletionResponse(text=result.answer)

        def stream_complete(self, prompt, formatted=False, **kwargs):
            raise RuntimeFailure("streaming_not_supported_by_example")
            yield

    class Engine(RetrieverQueryEngine):
        async def _aquery(self, query_bundle):
            generation_usage.clear()
            response = await super()._aquery(query_bundle)
            if generation_usage:
                usage = generation_usage[0]
                for item in generation_usage[1:]:
                    usage = usage.plus(item)
                response.metadata = {**(response.metadata or {}), "usage": asdict(usage)}
            return response

    engine = Engine.from_args(retriever=Retriever(), llm=HarnessLLM(), response_mode="simple_summarize")
    return _ReportedPipeline(LlamaIndexRagPipeline(engine, limits=context["limits"]), context)


def register(registry):
    registry.register("rag", "example_langchain", langchain)
    registry.register("rag", "example_llamaindex", llamaindex)
    registry.register("harness", "example_openai_agents", build_openai_agents_harness)
