# rag-evalkit

可獨立安裝的 Python 3.11+ 評測套件，將 vector store、RAG pipeline、模型與 harness 分開替換。核心無 NewsCout、Firebase、專案路徑或 provider SDK 依賴。

## 安裝與第一輪執行

在本目錄執行：

```sh
python -m pip install -e ".[test]"
python -m pytest tests -q
python examples/basic.py
rag-eval validate examples/experiment.json
rag-eval run examples/experiment.json --output runs
rag-eval compare runs/<run-id> --baseline vector --candidate lexical --axes rag
rag-eval status runs
rag-eval resume runs/<run-id>
rag-eval benchmark examples/experiment.json --variant vector --output runs/benchmark.json --repeats 10 --warmup 2 --concurrency 1
```

`basic.py` 會讓 vector retrieval 與獨立 BM25 retrieval 跑同一份文件及問題。CLI 會保存資料與設定指紋、每題結果、重複輪次、軌跡及比較資料。`corpus.json` 是虛構實驗室資料，向量是固定的 synthetic fixture，生成是 replay／echo fixture；成功僅代表這些執行路徑與結構契約通過。範例只有 dev 題目，沒有 holdout 或人工語意驗收。

`run` 會印出本輪實際路徑；將 `<run-id>` 換成該目錄名稱。`resume` 續跑尚未完成的 trial，完整 trial 保留原證據。`benchmark` 只測 store，輸出本次硬體／程序的量測；範例 memory fixture 不能代表網路 DB 的效能。設定檔會拒絕未知欄位，例如 lexical RAG 不接受 vector 專用的 `metric`／`exact`。自訂 adapters 可註冊至 `Registry`；已安裝 entry point plugins 必須經 `rag-eval --plugin <name> ...` 明確載入。

程序中斷時，只有內建 memory／fixture／replay 組合能自動重試當時正在執行的題目。Live model、網路 DB 或自訂 pipeline 的該題會保留 `InterruptedOutcomeUnknown`、未知費用與清理狀態，避免重複付費或副作用；尚未開始的題目仍可續跑。程序被強制終止後，遠端資源可能需要由管理者依 ownership 另行核對清理。

## 五個可替換接口

| 接口 | 內建實作 | 自訂實作需要提供 |
|---|---|---|
| Vector store | Memory exact oracle、Elasticsearch、PostgreSQL＋pgvector | `capabilities`、`describe()`、`upsert()`、`search()`、`delete()`、`close()` |
| Embedding | OpenAI-compatible HTTP、TEI HTTP、凍結向量 fixture | `describe()`、`embed(text)`；真實 HTTP adapters 另提供 batch、usage 與 close |
| RAG | `VectorRagPipeline`、`LexicalRagPipeline` | `describe()`、`run(query) -> RagResult` |
| Model | Replay、OpenAI Responses、Anthropic Messages | `capabilities`、`describe()`、`generate(messages, tools, limits, cancel)` |
| Harness | `SingleTurnHarness`、`ToolLoopHarness`、OpenAI Agents SDK bridge | `describe()`、`run(messages, tools, handlers, limits, cancel) -> HarnessResult` |

換同一 provider 的 model id、換 provider、換 harness 是不同實驗軸。比較時宣告允許改變的軸，其餘條件必須一致；不可為了讓比較成立而移除資料、設定與版本檢查。模型的實際有效設定及未知成本都應如實保留。

## 文件、chunk 與來源證據

`SourceDocument(id, text, source_id, metadata)` 進入純函式 `chunk_documents()`，得到保留 `document_id`、`source_id`、字元 `start/end` 的 `Chunk`。`VectorRagPipeline.ingest(chunks)` 明確寫入注入的 store；建構 pipeline 不會偷偷寫資料。BM25 pipeline 直接接收同一批 chunks，不需要 embedding 或資料庫。

```python
from rag_evalkit.rag import SourceDocument, chunk_documents, VectorRagPipeline

chunks = chunk_documents(
    [SourceDocument("manual-1", "Your source text", "manual:v1")],
    chunk_size=800, overlap=80,
)
pipeline = VectorRagPipeline(store, embedder, harness, top_k=5)
pipeline.ingest(chunks)
result = pipeline.run("Your question")
```

這裡的 `store`、`embedder`、`harness` 是呼叫端注入的物件；完整可執行範例見 `examples/basic.py`。實際 embedding 實作提供 `describe()` 與 `embed(text)`，並記錄模型、維度、設定與版本。`SyntheticFixtureEmbedder` 只接受凍結文本，未知文本會拒絕，不能替代真正 embedding 品質評測。

### 真實 embedding 與純文字資料集

`OpenAIEmbedding` 與 `TEIEmbedding` 接受任意新文字，實際發送 HTTP 請求；兩者都不會退回 fixture。設定 `vector_policy: "runtime"`、`dimensions` 並省略 document `vector`／case `query_vector`，runner 才會使用真實 embedding 產生向量。provided 與 runtime 向量不能混用。已提供可驗證的範例：

```sh
rag-eval validate examples/tei-experiment.json
# Set TEI_ENDPOINT, served model, deployment revision and dimensions first.
rag-eval run examples/tei-experiment.json --allow-live-embeddings --output runs
```

此範例仍使用虛構語料及 Replay，不能當作真模型品質驗收。TEI 是呼叫端自行提供的服務，不會下載或安裝模型。HTTP adapters 記錄 declared model revision、有效設定與去機密後的 target fingerprint；revision 宣告不等於已證明 provider alias 不可變。

計費 embedding 必須有顯式 opt-in、費率、每 trial 預算及足額的 `--max-total-usd`；總預留同時計入 embedding 與生成模型。自訂 OpenAI-compatible 計費服務還需 `token_bound: "utf8_bytes"`，明確宣告 tokenizer token 數不超過 UTF-8 bytes 的保守上界；不符合此契約的服務不得使用此計價保證。self-hosted 且未提供費率時保留 unknown cost。ingest、query、失敗與暖機的已知費用都保留，未知部分另外列示。詳細 API 見 [embedding contracts](src/rag_evalkit/embeddings/README.md)。

內建 RAG 也可比較 `prompt: {"system": "..."}` 與 `tools: {"type": "retrieved_sources"}`。後者提供 `read_source`，只能讀取該次已檢索的來源；工具由所選 harness 實際派送。其他工具 handlers 透過明確安裝的 plugin 提供。

`RagResult` 包含答案、逐筆 evidence（document／chunk／source id、原文、rank、normalized／raw score）、normalized traces、usage 與 metadata。`metadata.status != "completed"` 的結果不能算成功。無檢索證據時直接回覆明確棄答，不發送模型請求。

## Elasticsearch 與 PostgreSQL＋pgvector

兩個網路 adapter 都只建立本輪專用資源，拒絕接管既有 index／table；結束時驗證 ownership 再清理。請使用獨立測試資料庫與帳號。PostgreSQL 的 `vector` extension 需由資料庫管理者事先安裝；核心不會建立 extension。

ES adapter 拒絕 HTTP redirects，認證不會隨重新導向傳往另一個目標。比較指紋保留去除機密後的實際連線目標雜湊及服務版本；PostgreSQL 會使用連線成功後的有效參數，包含 libpq 從環境或 service 設定補入的值。

```sh
python -m pip install -e ".[postgres,test]"
```

Python 接法：

```python
import os
from rag_evalkit.stores.elasticsearch import ElasticsearchStore
from rag_evalkit.stores.postgres import PostgresStore

with ElasticsearchStore(os.environ["TEST_ES_URL"], dimensions=3) as store:
    # upsert/search/delete; credentials are separate constructor parameters
    pass

with PostgresStore(os.environ["TEST_POSTGRES_DSN"], dimensions=3) as store:
    pass
```

搜尋契約提供 cosine、L2、inner product、scalar equality AND filters，以及明確的 exact／ANN 模式。分數統一為越大越相關，同時保留 backend 原始分數。ANN 必須事先配置相符 metric；不支援的能力或 PostgreSQL planner 未使用要求的 HNSW index 會明確拒絕，不會把 exact fallback 記成 ANN 成果。

共同語料拒絕零文件向量，以及 float32 溢位或轉換後全部歸零的向量；cosine query 也必須非零，L2／inner product 可使用零 query。這是跨 backend 的明確限制，不能將它解讀為所有 DB 都不支援零向量。

真 DB 測試需顯式設定 `EVALKIT_INTEGRATION=1` 與 `EVALKIT_ES_URL`／`EVALKIT_POSTGRES_DSN`，再執行：

```sh
python -m pytest tests/test_store_integration.py -m integration -q
```

ES 認證可另設 `EVALKIT_ES_API_KEY` 或 `EVALKIT_ES_USERNAME`／`EVALKIT_ES_PASSWORD`。未設定的 backend 會 skip；測試只對本輪 `rag_evalkit_<uuid>` 資源讀寫。真 DB 是否通過以該次 integration 產物為準，HTTP／SQL protocol fixture 通過不能代替 live integration。

比較 DB 時固定文件、向量、維度、filter、K 與 gold labels，再用 exact oracle 算 ANN recall。零向量、數值精度、同分排序與 filtered ANN 的不足 K 筆都需要保留原始觀測。服務版本、硬體、索引參數、冷暖 cache、並行度、延遲與建索引成本必須一起記錄，不能拿小型 fixture 的延遲推論 production 效能。

## 模型與 harness

Live provider adapter 使用明確 endpoint／model／credentials 與費率；請由環境變數載入機密，不要寫入 manifest 或 artifacts。`RunLimits` 提供 live opt-in、預算、輸入／輸出 token、請求／turn 上限、逾時及取消。缺少可計價用量時保留 unknown／失敗證據，不捏造零成本。普通測試與內建範例不發付費請求。

`SingleTurnHarness` 只執行單輪生成；`ToolLoopHarness` 接受 tool specs 與 handlers，保存 dispatch／result／usage／end 狀態。Python 無法強制停止任意 in-process handler：逾時／取消會停止等待及後續 dispatch，已在執行的 callback 可能繼續。具副作用的工具需要合作式取消或獨立程序邊界。

HTTP 模型 adapters 現在提供真正增量 SSE：`model.stream(...)` 逐步產生事件，或使用 `streaming=True` 讓 `generate()` 消費同一路徑。只有合法 terminal、完整工具參數與使用量觀測才形成完成結果；取消、截斷、錯誤與未知費用會保留證據。文字與圖片區塊可混合輸入；圖片能力必須明確 `image_input=True`，不會依任意 model id 猜測。此處多模態範圍為文字／圖片，沒有音訊、影片或 Realtime 協定。

OpenAI Responses 可設定 hosted `web_search`／`file_search`；服務端工具與 client function dispatch 分開記錄。計費 hosted tools 需要每次費率及最大呼叫次數，並納入保守預留。不是所有 provider 都共享 tool、stream、usage 或錯誤語意，新服務仍需通過自己的協定及實際 API 驗證。完整型別與例子見 [model contracts](src/rag_evalkit/models/README.md)。

### 實際外部框架

```sh
# Optional framework integration is tested on Python 3.13; core stays dependency-free.
python -m pip install -e ".[test,integrations]"
python -m pip install --no-deps examples/integrations-plugin
rag-eval --plugin external_integrations adapters
python examples/external_integrations.py
```

內建 `LangChainRagPipeline` 接 Runnable chain，`LlamaIndexRagPipeline` 接 query engine；兩者正規化實際 Document／NodeWithScore 的來源、原文及 rank，沒有回報的 score／usage 保留 unknown。不需再重寫整個 adapter。範例 plugin 示範把現有 chain／engine 註冊成 manifest 的名稱，不允許 manifest 任意 import Python。範例 retriever 是固定 corpus slice，且會拒絕不支援的 prompt/tools 設定，不能把它當作檢索品質的實證。

`harness.type: "openai_agents"` 使用真實 SDK Agent／Runner，並橋接選定的 portable model，以保留 request、turn、token 及金額預算。工具執行前會先確認還有可完成後續模型回合的預留。任意原生 SDK model／外部 RAG 若無法控制內部 provider 成本，要求金額上限時會明確拒絕；不捏造硬預算保證。SDK bridge 目前限定文字與 client function tools，hosted／MCP／nested agent 工具需另有可控制成本的實作。

## 評分與校準邊界

- `evaluate_retrieval()`：Recall@K／nDCG@K，可指定 document、chunk 或 source 身份；沒有正相關 gold 時回 unknown，不當作滿分。
- `citation_check()`：只查 `[source:ID]` 是否出現在檢索證據。存在引用不代表答案受到來源支持。
- `source_lineage_check()`：檢查來源身份與重複 chunk；不驗證原文真偽。
- `abstention_check()`：檢查明確棄答格式與標籤一致；不判斷證據是否真的充分。
- `tool_task_check()`：只計入 handler 真正開始的 `tool_start` 名稱與順序；`tool_requested` 不代表已執行，也不等於任務完成。
- `Judge`／`blinded_calibration()`：保留 rubric decision、盲化順序／身份、獨立人工評分入口、agreement 與誤差。未提供足夠人工評分就保持 pending；即使已有比較資料，也需要獨立審查才能給語意驗收結論。

盲化會移除候選標籤、人工分數與 retrieval metadata；答案風格仍可能透露模型身份。測試中的 synthetic reviewer labels 只驗校準程式，不能當作真實人工審核。

### 可完成的品質驗收流程

對獨立 dev 校準 run 與 holdout 品質 run 分別執行 `quality-prepare`。只將 `blind/` 交給評審，`private/` 與含完整輸入的校準 artifact 應保留在私人位置。人工檔案必須由真人填寫；`quality-judge` 的模型評分不能填成人工評分。

兩份資料集需記錄可追溯的實際語料來源，例如 `"provenance": {"evidence_kind": "real_corpus", "source": "your-corpus-location", "version": "your-immutable-revision"}`；缺少這些宣告時，品質驗收保持 pending。dev 與 holdout 的 case／family 必須互不重疊，也不可將範例 synthetic 語料改標為真實語料。

先將 [judge 設定範本](examples/judge-model.template.json) 複製為 `model-config.json`，填入已核准的模型、查證過的每百萬 token 費率及每筆預算。範本中的 `REPLACE_...` 是必填占位文字，不能直接執行。`model` 使用與實驗 manifest 相同的 provider 設定；`limits` 是 `RunLimits` 欄位，`max_budget_usd` 限制單筆 judge，`--max-total-usd` 限制整份 bundle。請先設定 `OPENAI_API_KEY`／`OPENAI_BASE_URL` 環境變數，並將下列 `$APPROVED_BUDGET_USD` 設為該輪已核准的總額。

```sh
rag-eval quality-prepare runs/<dev-run> --output reviews/calibration
rag-eval quality-prepare runs/<holdout-run> --output reviews/holdout
# Copy each human-template.json to human.json at the paths below.
# A human fills reviewer.id/attestation and every sample's rubric scores/rationale.
# Each rubric score is a JSON true/false decision.
# Empty templates cannot pass. Keep sample IDs and bundle fingerprints intact.
cp reviews/calibration/blind/human-template.json reviews/calibration/human.json
cp reviews/holdout/blind/human-template.json reviews/holdout/human.json
rag-eval quality-judge reviews/calibration/blind/bundle.json model-config.json --allow-live-models --max-total-usd "$APPROVED_BUDGET_USD" --output reviews/calibration/judge.json
rag-eval quality-calibrate reviews/calibration/blind/bundle.json reviews/calibration/private/key.json runs/<dev-run> --human reviews/calibration/human.json --judge reviews/calibration/judge.json --output reviews/calibration/private/calibration.json
rag-eval quality-judge reviews/holdout/blind/bundle.json model-config.json --allow-live-models --max-total-usd "$APPROVED_BUDGET_USD" --output reviews/holdout/judge.json
rag-eval quality-audit-template reviews/holdout/blind/bundle.json --human reviews/holdout/human.json --judge reviews/holdout/judge.json --calibration reviews/calibration/private/calibration.json --output reviews/holdout/audit.json
# A distinct human auditor fills the empty audit fields after reviewing the evidence.
rag-eval quality-score reviews/holdout/blind/bundle.json reviews/holdout/private/key.json runs/<holdout-run> --human reviews/holdout/human.json --judge reviews/holdout/judge.json --calibration reviews/calibration/private/calibration.json --audit reviews/holdout/audit.json --output reviews/holdout/quality.json
```

gate 重新核對原始 run／dataset、設定與 annotation 指紋。校準需要獨立正負例、逐 rubric 的 class support 與 case-clustered balanced accuracy，且不得與 holdout 的 case／family 重疊；全正例不能校準 always-approve judge。缺資料、真模型證據、真人標註、足額獨立樣本或獨立審核時維持 pending（CLI exit 2），品質未達門檻為 failed（exit 1），已宣告的審核通過才是 passed（exit 0）。外部 reviewer 與 corpus/provider 身份仍是 self-attested，工具不能驗證人類身份；synthetic 標籤或 audit 明確拒絕。預設至少 20 獨立 cases、每類 5 cases、最低 agreement／balanced accuracy 與 pass rate 0.8；調整門檻會記入報告。

### 端到端負載量測

```sh
rag-eval benchmark examples/experiment.json --variant vector --scope pipeline --repeats 10 --warmup 2 --concurrency 4 --output runs/pipeline-load.json
```

`--scope store` 保留既有 DB benchmark；`--scope pipeline` 實際執行完整 RAG／harness／模型，分開記錄 setup、query、cleanup 與總延遲、p50/p95/p99、成功／失敗、throughput、暖機及未知費用。每個請求擁有獨立 pipeline，避免共用可變 provider ledger；計費 workload 的總預留包含暖機及所有並行請求。合成 corpus 的本機結果只證明執行路徑；真語料、真硬體與外部服務的品質／效能需各自量測，不能把套件測試通過解讀為其效能已驗收。

## 測試與實證範圍

測試採 `script → action → physical`：斷言在 scripts 可見，actions 回傳 detached observations，實際 adapter／SDK／fixture 佈線在 physical。網路 DB integration 必須顯式開啟，使用獨立資源並保留清理結果；未執行的 integration 是 skip，不能列為 pass。Live model 品質、跨領域 judge 校準、真實流量效能與不同外部 harness 的語意一致性，需要各自的實跑證據。
