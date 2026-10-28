"""Run two retrieval implementations against one frozen, fictional corpus.

Install the package first. All vectors and generation below are synthetic; the
output is execution/structural evidence, never semantic or live-model acceptance.
"""

import json
import re
from dataclasses import asdict
from pathlib import Path

from rag_evalkit.contracts import Capabilities
from rag_evalkit.evaluators import citation_check, evaluate_retrieval
from rag_evalkit.harnesses import SingleTurnHarness
from rag_evalkit.rag import (
    LexicalRagPipeline,
    SourceDocument,
    SyntheticFixtureEmbedder,
    VectorRagPipeline,
    chunk_documents,
)
from rag_evalkit.runtime import Generation, Usage
from rag_evalkit.stores.memory import MemoryStore


class EvidenceEchoModel:
    """A protocol fixture that echoes a citation; it has no semantic reasoning."""
    capabilities = Capabilities(frozenset({"text"}))

    def describe(self):
        return {"adapter": "example_echo", "provider": "synthetic", "model": "citation-echo",
                "evidence_kind": "synthetic", "synthetic": True}

    def generate(self, messages, *, tools=(), limits=None, cancel=None):
        source = re.findall(r"\[source:([^\]\n]+)\]", messages[-1].content)[0]
        return Generation(f"Synthetic protocol answer [source:{source}]", usage=Usage(cost_usd=0.0))


def main():
    corpus = json.loads(Path(__file__).with_name("corpus.json").read_text(encoding="utf-8"))
    sources = tuple(SourceDocument(row["id"], row["text"], row["source_id"], row["metadata"])
                    for row in corpus["documents"])
    chunks = chunk_documents(sources, chunk_size=1000, overlap=0)
    vectors = {row["text"]: row["vector"] for row in corpus["documents"]}
    vectors.update({row["query"]: row["query_vector"] for row in corpus["cases"]})
    store = MemoryStore(3)
    try:
        vector = VectorRagPipeline(store, SyntheticFixtureEmbedder(vectors), SingleTurnHarness(EvidenceEchoModel()), top_k=2)
        vector.ingest(chunks)
        lexical = LexicalRagPipeline(chunks, SingleTurnHarness(EvidenceEchoModel()), top_k=2)
        observations = []
        for pipeline in (vector, lexical):
            for case in corpus["cases"]:
                result = pipeline.run(case["query"])
                observations.append({"case_id": case["id"], "pipeline": pipeline.describe(), "result": asdict(result),
                                     "retrieval": [asdict(item) for item in evaluate_retrieval(result, case["relevance"], k=2)],
                                     "citation_membership": asdict(citation_check(result.answer, result.evidence))})
        print(json.dumps({"evidence_kind": "synthetic", "semantic_acceptance": "not_evaluated", "observations": observations}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
