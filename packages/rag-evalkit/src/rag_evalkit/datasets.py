"""Versioned project-neutral datasets and experiment manifests."""

from collections.abc import Mapping
from pathlib import Path

from .contracts import ContractError, Document, checked_vector
from .serialization import digest, plain, read_json

FACTORS = frozenset({"store", "embedding", "rag", "model", "harness", "prompt", "tools", "environment"})


def validate_dataset(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("id"), str) or not data["id"]:
        raise ContractError("dataset requires schema_version=1 and an id")
    documents, cases = data.get("documents"), data.get("cases")
    if not isinstance(documents, list) or not documents or not isinstance(cases, list) or not cases:
        raise ContractError("dataset requires nonempty documents and cases")
    policy = data.get("vector_policy", "provided")
    if policy not in {"provided", "runtime"}:
        raise ContractError("vector_policy must be provided or runtime")
    configured_dimensions = data.get("dimensions")
    if policy == "runtime" and (type(configured_dimensions) is not int or configured_dimensions < 1):
        raise ContractError("runtime embedding requires positive dataset dimensions")
    ids, sources, dimensions = set(), set(), set()
    for row in documents:
        if not isinstance(row, dict):
            raise ContractError("invalid document")
        if policy == "provided":
            doc = Document(row.get("id"), row.get("text"), row.get("vector", ()), row.get("metadata", {}))
            dimensions.add(len(doc.vector))
        else:
            if "vector" in row:
                raise ContractError("runtime embedding dataset must not contain provided vectors")
            if not isinstance(row.get("id"), str) or not row["id"] or not isinstance(row.get("text"), str) or not isinstance(row.get("metadata", {}), Mapping):
                raise ContractError("document requires id, text and mapping metadata")
            dimensions.add(configured_dimensions)
        if row["id"] in ids or not isinstance(row.get("source_id"), str) or not row["source_id"]:
            raise ContractError("duplicate document ID or missing source_id")
        ids.add(row["id"])
        sources.add(row["source_id"])
    if len(dimensions) != 1:
        raise ContractError("dataset vectors must have identical dimensions")
    families, case_ids = {}, set()
    for row in cases:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in case_ids:
            raise ContractError("duplicate or invalid case ID")
        case_ids.add(row["id"])
        family, split = row.get("family"), row.get("split")
        if not isinstance(family, str) or not family or split not in {"dev", "holdout"}:
            raise ContractError("case requires family and dev/holdout split")
        if families.setdefault(family, split) != split:
            raise ContractError("case family leaks across dev/holdout")
        if not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ContractError("case query must be nonempty")
        if policy == "runtime":
            if "query_vector" in row:
                raise ContractError("runtime embedding dataset must not contain query vectors")
        elif len(checked_vector(row.get("query_vector", ()))) not in dimensions:
            raise ContractError("query dimension differs from corpus")
        relevance = row.get("relevance")
        if not isinstance(relevance, dict) or set(relevance) - ids:
            raise ContractError("relevance references unknown documents")
        from .metrics import recall_at_k
        recall_at_k([], relevance, 1)
        expected = row.get("expected_source_ids", [])
        if not isinstance(expected, list) or any(not isinstance(value, str) for value in expected) or set(expected) - sources:
            raise ContractError("expected sources reference unknown sources")
        if type(row.get("should_abstain", False)) is not bool:
            raise ContractError("should_abstain must be boolean")
        if not isinstance(row.get("expected_tools", []), list) or any(not isinstance(value, str) for value in row.get("expected_tools", [])):
            raise ContractError("expected_tools must be tool names")
    return plain(data)


def validate_manifest(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ContractError("manifest requires schema_version=1")
    allowed = {"schema_version", "dataset", "seed", "repeats", "split", "comparison_axes", "variants", "description"}
    if set(data) - allowed:
        raise ContractError("unknown manifest fields: " + ", ".join(sorted(set(data) - allowed)))
    if not isinstance(data.get("dataset"), str) or not data["dataset"]:
        raise ContractError("manifest requires a dataset path")
    for key, default, minimum in (("seed", 0, 0), ("repeats", 1, 1)):
        value = data.get(key, default)
        if type(value) is not int or value < minimum or (key == "repeats" and value > 1000):
            raise ContractError("invalid " + key)
    if data.get("split", "dev") not in {"dev", "holdout", "all"}:
        raise ContractError("invalid selected split")
    axes = data.get("comparison_axes", [])
    if not isinstance(axes, list) or len(axes) != len(set(axes)) or set(axes) - FACTORS:
        raise ContractError("invalid comparison axes")
    variants = data.get("variants")
    if not isinstance(variants, list) or not variants:
        raise ContractError("manifest requires variants")
    ids = set()
    for row in variants:
        if not isinstance(row, dict) or set(row) - (FACTORS | {"id"}):
            raise ContractError("unknown variant fields")
        if not isinstance(row.get("id"), str) or not row["id"] or row["id"] in ids:
            raise ContractError("duplicate/invalid variant id")
        ids.add(row["id"])
        for factor in ("store", "embedding", "rag", "model", "harness"):
            if not isinstance(row.get(factor), dict) or not isinstance(row[factor].get("type"), str):
                raise ContractError("variant requires typed " + factor)
        for factor in FACTORS & row.keys():
            if not isinstance(row[factor], dict):
                raise ContractError("factors must be configuration objects")
        # Secrets belong in environment variables. Config only names those variables.
        def no_secrets(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.lower() in {"api_key", "password", "token", "authorization", "dsn", "url", "endpoint"}:
                        raise ContractError("use an environment variable reference for " + key)
                    no_secrets(item)
            elif isinstance(value, list):
                for item in value:
                    no_secrets(item)
        no_secrets(row)
    return plain({"seed": 0, "repeats": 1, "split": "dev", "comparison_axes": [], **data})


def load_experiment(path):
    path = Path(path).resolve()
    manifest = validate_manifest(read_json(path))
    dataset = validate_dataset(read_json(path.parent / manifest["dataset"]))
    return manifest, dataset


def dataset_metadata(dataset):
    dimensions = dataset["dimensions"] if dataset.get("vector_policy") == "runtime" else len(dataset["documents"][0]["vector"])
    return {"dataset_id": dataset["id"], "dataset_sha": digest(dataset), "corpus_sha": digest(dataset["documents"]), "dimensions": dimensions}
