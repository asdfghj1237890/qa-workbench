# Real text embeddings

`OpenAIEmbedding` sends arbitrary nonempty text to an OpenAI-compatible
`POST /embeddings` endpoint. `TEIEmbedding` sends `POST /embed` to a separately
deployed Hugging Face Text Embeddings Inference server. Neither adapter creates
hash vectors, downloads models, retries, follows redirects, or falls back to
fixtures. Imports use only the Python standard library.

```python
import os
from rag_evalkit.embeddings import EmbeddingLimits, TEIEmbedding

embedder = TEIEmbedding(
    model="BAAI/bge-small-en-v1.5", dimensions=384,
    model_version=os.environ["EMBEDDING_MODEL_REVISION"],
    endpoint=os.environ["TEI_ENDPOINT"], normalize=True, truncate=False,
    limits=EmbeddingLimits(max_requests=20, max_input_tokens=100000),
)
try:
    vectors = embedder.embed_many(["Any new passage", "Another passage"])
    print(embedder.usage)
finally:
    embedder.close()
```

Pass an endpoint base (`https://host/v1` for OpenAI-compatible services,
`https://host` for TEI), not the final method path. HTTPS is required except for
literal loopback IPs and `localhost`; credentials in URLs, query strings,
fragments, control characters, and redirects are rejected. Bearer credentials
are accepted through `api_key` and omitted/redacted from all observations.

The declared `model_version` must identify the caller's deployment revision.
It is recorded as caller-declared, not claimed to have been verified against
the server. OpenAI response model identifiers are recorded and changes within
one adapter lifetime fail closed. TEI `/embed` does not return a model ID; its
deployment identity remains caller-declared. Pin the actual serving deployment
when comparing experiments. Dimensions are validated, not inferred. Set
`send_dimensions=False` for an OpenAI-compatible model that does not accept the
`dimensions` request option. TEI requests set `normalize` and `truncate`
explicitly; `prompt_name` is optional and recorded.

All returned numbers are rounded to IEEE float32; dimension errors, nonfinite,
zero, overflowed and fully underflowed vectors fail closed. Optional client L2
normalization operates on float32 values and rounds the normalized output to
float32 again. OpenAI batch indices must form a unique complete permutation;
response row order does not control input alignment. TEI array order follows
its documented input ordering.

`embed(text)` returns one tuple; `embed_many(texts)` returns tuples in input
order; `embed_batch(texts)` returns an `EmbeddingBatch` containing `vectors`,
`Usage`, and provenance. `usage` provides detached lifetime counters for
ingestion plus query calls. `close()` prevents later dispatch; it cannot kill
already submitted remote work. Cancellation and the wall timeout bound client
waiting, prevent further batch dispatch, and retain incomplete HTTP/cost
observations. Late responses can still update lifetime usage. A timeout does
not establish that the remote service stopped computing.

`EmbeddingLimits` defines `timeout_seconds`, `max_requests`, `max_input_tokens`,
`max_input_bytes`, `max_budget_usd`, and `live_opt_in`. Request, token and budget
caps apply to the entire adapter lifetime; call-level overrides can only
tighten configured caps. Byte limits apply per batch call. Concurrent calls
are rejected while an operation is active or an earlier timed-out response
remains unobserved. Each call has a separately closed HTTP admission ledger;
timeouts close this child gate even when the caller supplies a shared parent
ledger. Parent request observations remain usable by the surrounding trial.
Use a new adapter per trial. A call cannot extend the constructor's timeout.
`live_opt_in=True` is explicit authorization at construction or call time;
the CLI additionally enforces its own `--allow-live-embeddings` authorization.

OpenAI defaults to `billing="metered"`, which requires `live_opt_in=True`,
caller-supplied `EmbeddingPricing(input_per_million=...)`, and an explicit
budget before dispatch. Reserve the full configured input-token cap at that
rate for the lifetime. Metered input is rejected before any HTTP request when
its UTF-8 byte count plus previously observed lifetime tokens can exceed the
cap. This is a conservative token upper bound for the known OpenAI byte BPE
embedding models. Only the official endpoint with `text-embedding-ada-002`,
`text-embedding-3-small` or `text-embedding-3-large` automatically receives this
contract. A custom OpenAI-compatible service must explicitly declare
`token_bound="utf8_bytes"`, meaning its billed input-token count never exceeds
the input UTF-8 bytes and it adds no hidden prompt overhead. Other tokenization
contracts are unsupported and fail before dispatch. A misbehaving provider can
still report usage over its declared contract; actual observed cost and the
failure are retained. This is a client admission guarantee under that provider
contract, not a provider-enforced hard spending cap. Metered TEI with prompts
has no such bound contract in this adapter and is rejected before dispatch.
A self-hosted OpenAI-compatible service can explicitly
use `billing="self_hosted"`. TEI defaults to self-hosted. Missing pricing or
usage remains unknown, never fabricated as zero. Budgeted calls with missing
usage fail closed and cannot continue with a guessed remaining budget. Token
counts come from OpenAI `usage.prompt_tokens` or TEI `x-compute-tokens`.

Default tests use real loopback HTTP sockets with protocol fixture responses;
they do not prove model quality. Actual service tests require
`EVALKIT_LIVE_EMBEDDINGS=1` and the following variables:

| Prefix | Required suffixes |
| --- | --- |
| `EVALKIT_OPENAI_EMBEDDING_` | `ENDPOINT`, `MODEL`, `VERSION`, `DIMENSIONS`, `API_KEY`, `PRICE_PER_MILLION`, `MAX_BUDGET_USD` |
| `EVALKIT_TEI_EMBEDDING_` | `ENDPOINT`, `MODEL`, `VERSION`, `DIMENSIONS` |

Optional TEI suffixes are `API_KEY`, `PRICE_PER_MILLION`, `MAX_BUDGET_USD`.
Custom metered OpenAI-compatible services additionally require suffix
`TOKEN_BOUND=utf8_bytes` to explicitly declare the tokenizer contract.
Run `python -m pytest tests/test_embeddings.py -m integration -q` only after
explicitly authorizing the selected service and its cost. Live checks validate
shape, distinct output and provenance; semantic retrieval quality needs a
labeled corpus experiment.

Protocol sources: [OpenAI embeddings reference](https://developers.openai.com/api/reference/resources/embeddings/methods/create),
[TEI quick tour](https://huggingface.co/docs/text-embeddings-inference/quick_tour),
[TEI HTTP request/response types](https://github.com/huggingface/text-embeddings-inference/blob/main/router/src/http/types.rs).
