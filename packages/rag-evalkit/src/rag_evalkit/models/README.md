# Model and harness runtime

`ModelAdapter.generate(messages, *, tools=(), limits=None, cancel=None)` returns
`Generation`; `ToolLoopHarness(model)` and `SingleTurnHarness(model)` expose
`run(messages, *, tools=(), handlers=None, limits=None, cancel=None)` and return
`HarnessResult`. A result is complete only when `status == "completed"`.

`Message.provider_state` and `Generation.provider_state` are optional opaque
strings. Only assistant messages may carry them. Raw provider continuation items
stay in the owning model instance's private cache; serializable observations
contain the opaque ID and cleaned evidence. The same instance can continue a
returned message history without sending redacted evidence back to the provider.
Unknown, cross-instance/cross-provider, cleared or evicted IDs fail closed.
`provider_items` is an evidence-only legacy field and is rejected as wire input.
All nonempty assistant outputs are retained, including OpenAI message phase,
annotations and reasoning items, and Anthropic content/citations.

The private cache is bounded by `max_provider_states` (default 128) and
`max_provider_state_bytes` (default 16 MiB), with oldest-first eviction. Long
conversations must configure sufficient retention; eviction never silently
reconstructs a different conversation. `clear_provider_states()` is an explicit
lifecycle boundary. Persisted IDs cannot restore raw state in a new process.

`Message`, `ToolSpec`, `ToolCall`, `Usage`, `TraceEvent`, `RunLimits`, `Generation`
and `HarnessResult` live in `rag_evalkit.runtime`. Tool handlers receive a detached
argument mapping and return text or JSON. Tool schemas support explicit JSON
types, object properties/required/additionalProperties, arrays/items and enum.
Other schema keywords are rejected before a provider request. A full batch is
validated before the first tool is dispatched; unknown handlers fail closed.

## Providers and evidence

`OpenAIResponsesModel` implements Responses HTTP text/function calls, retaining
reasoning continuation items for stateless follow-up. `AnthropicMessagesModel`
implements Messages HTTP text/tool_use/tool_result. Both normalize completion,
length limits, refusal, incomplete responses and usage. They use the Python
standard library and require no provider SDK. Both support incremental HTTP SSE
and portable text/image input. OpenAI also supports configured hosted web search
and file search. Audio/video and Anthropic thinking are explicitly unsupported.

Ordinary tests inject an HTTP transport and set `evidence_kind="protocol_fixture"`.
Their request and response fixtures test wire compatibility, not live model
quality. `ReplayModel(["answer", ...])` always describes itself as
`synthetic_replay`; recorded tokens stay unknown unless supplied. Replay cost is
the zero cost of replay execution; recorded historical model cost is separate.

For actual provider execution, supply an explicit model ID, API key, caller
verified `Pricing(input_per_million, output_per_million, ...)`, and `RunLimits`
with `live_opt_in=True` and positive `max_budget_usd`. No prices or model aliases
are silently selected. Endpoints must be HTTPS and contain no user information,
query string or fragment. HTTP redirects and automatic retries are disabled.
Credential fields and the configured API key are removed from raw evidence.
Known credential echoes in provider text, tool arguments, model identity or
mapping keys fail with `provider_credential_echo`; usage then remains unknown.
Initial history containing the configured key fails before network dispatch with
`credential_input`. A tool returning the key fails before another provider call
with `tool_credential_echo`. Credential-bearing callback error codes normalize to
`runtime_credential_echo`. The harness also produces a separately sanitized typed
copy of its final messages, traces, usage details and metadata as a last boundary.
Its working protocol history is never replaced with sanitized evidence. Normalized
message values preserve legitimate `sk-` identifiers; raw/trace evidence also uses
credential-field and pattern filtering.

## Limits and accounting

Each provider generation first calls the provider's input-token-count endpoint.
This is an observed HTTP request and consumes one of `max_requests`; generation
consumes another. Text length is never presented as measured token usage. Input
count must fit `max_input_tokens`; `max_output_tokens` is sent to the provider.
Pricing reserves the full configured input/output cap before generation, and
the harness checks the cumulative observed model cost before another request.
Tool side effects also wait for a continuation request's budget and request slot.

Anthropic documents token counting as an estimate. This is a client admission
guard, not a provider-enforced billing cap: actual metering can differ. A provider
observation above the configured caps is retained as a failure, and no later
request is dispatched. Missing usage/cache prices remain unknown and stop a live
or budget-constrained run. Cache-token accounting preserves provider differences
(OpenAI cached input is included in input_tokens; Anthropic adds cache read/write
to ordinary input_tokens). Provider transport failures can leave billing unknown.
Arbitrary paid tool handlers must enforce their own budgets; model prices do not
describe external tool fees.

`max_turns` counts model generations; `max_requests` counts provider HTTP requests
(including count endpoints), or one logical request for replay/custom adapters.
For HTTP adapters, `HarnessResult.requests` counts transport starts observed by a
thread-safe ledger shared across bounded workers. Result metadata separates
reserved slots, observed/completed/in-flight HTTP requests and observation
completeness. A timeout during a count request cannot become two observed requests.
Uninstrumented custom adapters are labelled `logical_model_calls` or
`adapter_reported_requests`; their HTTP observation is explicitly unknown.
`timeout_seconds` bounds a whole harness run. Cancellation/timeout prevents
subsequent dispatch and bounds the caller's wait. An in-flight Python callback or
provider operation can continue: `operation_may_continue` is recorded explicitly.
Trusted tools should cooperate with cancellation; untrusted or irreversible tools
need an external process/isolation boundary. Threads are not a tool sandbox.
`tool_requested` records intent, `tool_start` is emitted inside the actual handler
dispatch wrapper, and `tool_result` records completion. A request that times out
before dispatch is never evidence that the tool started or the task succeeded.

`describe()` includes model, endpoint, settings, adapter/API versions, supplied
prices and evidence kind. Resolved provider model and effective per-run limits
are retained in traces/result metadata. Generation raw evidence preserves safe
request, token count and provider response beside normalized observations.

`describe().model` is the requested model or alias. `Generation.model` and each
`model_end.resolved_model` contain only the provider response's actual `model`
field. A missing, null or empty field remains the unknown empty string; the
requested alias is never substituted as an observed identity. Invalid identity
types fail explicitly, and configured credential echoes remain rejected.
`model_end` also records `requested_model` and `resolved_model_observed`, so
experiments and calibrated quality review can distinguish an observed snapshot
from an alias or an unavailable identity, including streamed responses.

Protocol sources:

- [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI token counting](https://developers.openai.com/api/docs/guides/token-counting)
- [Anthropic tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- [Anthropic token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting)

## Incremental streaming

Set `streaming=True` on either HTTP adapter for harness runs. `generate()` reads
the SSE body progressively and returns a final `Generation` with normalized
`traces`. For an application that consumes progress, iterate `model.stream(...)`:

```python
for event in model.stream([Message("user", "Explain the evidence")], limits=limits):
    if event.kind == "text_delta":
        print(event.data["text"], end="", flush=True)
    elif event.kind == "generation":
        generation = event.generation
```

The final generation is available only after a provider terminal event. Text,
client function argument fragments, hosted tool progress and citations are
observable during receipt; fragments never dispatch a client handler. The
default transport returns headers immediately and calls incremental bounded
`readline`, rather than decoding a buffered JSON response. Tests include a real
loopback HTTP server that withholds the terminal until its first text is read.
Injected streaming fixtures require a separate `stream_transport` returning
`HTTPStreamResponse(status, chunks, close)`; `chunks` yields bytes progressively.

`max_stream_bytes` and `max_stream_events` bound wire input, including malformed
or never-terminated events. Truncation, malformed JSON, provider error events,
inconsistent terminal text/arguments, timeout and cancellation fail explicitly.
Missing terminal usage stays unknown. Partial text, observed partial usage,
normalized traces and exact request starts survive failures as evidence; a
partial token count is never promoted to a complete bill. Close the iterator
when abandoning a stream. Socket reads already in flight can continue until
their timeout; later provider dispatch is prevented.

Public text/refusal and tool argument deltas retain only a suffix that could
complete the configured credential. Tool JSON escapes are decoded incrementally
for this check while preserving the original argument spelling. A credential
split across events fails before its final characters become public; unrelated
safe text continues to arrive immediately. Benign retained suffixes are flushed
only after a valid terminal. Failure evidence does not expose held credentials.

## Text and image input

`Message.content` remains a string for existing callers. For images use a tuple
of `TextBlock` and `ImageBlock` values and explicitly configure `image_input=True`
on a model that supports vision:

```python
message = Message("user", (
    TextBlock("Describe this image"),
    ImageBlock(url="https://example.org/image.png"),
))
```

Alternatively use `ImageBlock(base64_data=payload, media_type="image/png")`.
HTTPS image URLs and base64 JPEG/PNG/GIF/WebP are portable; the provider enforces
image sizes, content and model availability. No local files or URLs are fetched
by the adapter. Images require a user message. OpenAI accepts `detail` auto/low/
high; Anthropic accepts the portable default auto and rejects other values.
The capability declaration is the caller's assertion about the selected model,
not an inferred guarantee for arbitrary model IDs. Undeclared image support,
audio/video blocks and image input to ReplayModel fail explicitly. Raw evidence
redacts inline images and encrypted reasoning; exact opaque continuation data
stays only in the model instance's bounded private state cache.

## Provider hosted search

Configure OpenAI `hosted_tools` with `HostedToolSpec`. These definitions are
separate from client `ToolSpec`/handlers:

```python
hosted_tools = (
    HostedToolSpec("web_search", price_per_call_usd=verified_web_price, max_calls=2),
    HostedToolSpec("file_search", {"vector_store_ids": ["vs_example"]},
                   price_per_call_usd=verified_file_price, max_calls=1),
)
```

`config` accepts documented search location/filter/context options or file search
vector stores/ranking/result options. Generation includes the configured tools,
an aggregate `max_tool_calls`, web source inclusion and file result inclusion.
`Generation.hosted_calls`, `citations`, `usage.details` and harness traces retain
calls, results, citation offsets and counts. A hosted call never becomes a client
tool dispatch. All service prices are explicit caller supplied complete per-call
rates, including applicable non-token search charges; the adapter invents none.
Live execution rejects unknown hosted rates before either HTTP request. Fixtures
may preserve unknown cost. Incomplete hosted observations also leave cost unknown.

Reservation adds the aggregate allowed call count times the highest supplied
service rate, since the API bounds total hosted calls across tool types. Observed
token charges and hosted service charges are reported separately and summed.
Per-tool call-bound violations retain evidence and fail the harness. This is an
admission guard; provider-side metering and hosted search input can differ from
preflight counts, so it is not a provider billing cap.

Additional protocol sources:

- [OpenAI streaming](https://developers.openai.com/api/docs/guides/streaming-responses)
- [OpenAI image inputs](https://developers.openai.com/api/docs/guides/images-vision)
- [OpenAI web search](https://developers.openai.com/api/docs/guides/tools-web-search)
- [OpenAI file search](https://developers.openai.com/api/docs/guides/tools-file-search)
- [Anthropic streaming](https://platform.claude.com/docs/en/build-with-claude/streaming)
- [Anthropic vision](https://platform.claude.com/docs/en/build-with-claude/vision)
