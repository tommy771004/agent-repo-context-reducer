# Agent Repo Context Reducer

**縮減 → 驗證 → 召回（Reduce → Verify → Recall）。** 為 AI Coding Agent 提供 dependency-free、deterministic-first 的 Repository Context 縮減與恢復層。

版本：**2.4.0**　Python：**3.10+**　核心 Runtime dependencies：**0**

[English](README.md) · [繁體中文](README.zh-TW.md)

## 專案定位

Coding Agent 不應把整個 Repository、完整 provenance 或所有歷史 evidence 都付成 model token；但縮減也不能等同刪除。v2.4 延續同一個核心問題：**模型現在必須讀哪些 Repository Context，哪些可以先留在本機、需要時再找回？**

多問題任務會保留每一個問題；只對相同 `context_id` 的重複 evidence 去重。Workflow 分析另建立精簡維度帳本（入口/狀態、持久化、授權、錯誤重試、跨層契約、裝置交付、即時返回）；跨層契約必須同時有 client 與 server evidence 才算覆蓋。完整候選與 provenance 留在 sidecar，模型只收到 bounded evidence references；由於 output 費用較高，模型回覆預設要求 compact、evidence-first 且不重複敘述 context，但仍必須列出未解決項目。

```text
Repository
  -> Persistent Index / Graph / Symbols             [WARM：本機，不花 Model Token]
  -> Rank + Filter + Verify + Context Budget
  -> HOT Active Context                             [Model-visible]
  -> Thin Model Context
  -> Agent
       │
       ├─ Evidence 足夠 ───────────────────────────> 繼續
       │
       └─ Context Gap
             -> Deterministic Recall
             -> Exact locator / Local text / Graph
             -> Bounded Symbol Span / Source Snippet
             -> Rehydrate HOT
             -> 繼續

Optional Harness：Direct / Light / Full Runtime、Fan-In、Grader、Sandbox、Durable Run。
```

Repository Index 是唯一的 WARM / Recallable locator source。Context Store **不複製整份 Index，也不保存完整 Source**；只保存目前 HOT overlay、bounded rejected tombstone 與 invalidation history。Runtime/Multi-Agent 仍保留，但不再主導 Core。

## v2.4 重點：Claim-Aware Verification Recall

- **針對 provisional claim 做驗證式召回**：新增 `repo-context claim-recall`，先推導要確認或反駁該 claim 所需的 Repository evidence，再決定是否需要補 Context。
- **不是只找相關資料，而是找可驗證資料**：針對 responsive/breakpoint、import≠實際呼叫、localization、accessibility、persistence、motion、dependency 等常見 Coding/UI claim 產生 deterministic verification requirements。
- **Recall 本身 0 model call**：requirements、scoped source search、negative-search observation、ranking、rehydration 全部由程式執行。
- **允許不知道**：只輸出 `challenged`、`provisionally-supported`、`inconclusive`，並固定 `semantic_truth_claimed=false`；regex/search 不會被包裝成語意真相。
- **負證據也能被壓縮表示**：例如檔案有 import、但 scoped search 找不到實際 invocation，可回傳 compact negative observation，不必把整檔交給模型。
- **找不到指定 path 不會偷改成全 Repo 搜尋**，避免 unrelated evidence 造成錯誤對齊。
- **Evidence + observations + policy 共用同一個 model-visible hard budget**。
- Release Gate 加入真實 UI repository 類型的 partial-context traps；Schema 總數為 **31**。

這個能力只在 claim 真的需要驗證時使用，不應每一輪、每一句固定執行。

```bash
repo-context claim-recall \
  "`src/components/SettingsPanel.tsx` uses getModalMotion on desktop" \
  --repo . --path src/components/SettingsPanel.tsx --budget 1200 --pretty
```

## v2.3 重點：Context Safety & Recall

- **HOT / WARM 分離，但不建立第二份 Index**：`.repo-context/index.json` 是唯一 Recallable locator source；`.repo-context/context-stores/<session>.json` 只保存 active overlay 與 bounded safety state。
- **Repository Recall 預設 0 次 Model Call**：先 exact path/symbol，再 bounded local source search 與 dependency-neighbor ranking；不需要額外 Memory Provider 或 LLM query rewrite。
- **精準 Rehydrate**：Symbol 命中只讀該 source span；module-level 常數/錯誤字串只回命中行 ±2 行 snippet，不退化成整檔注入。
- **Recall 有硬 Token Budget**：本機可以探索較多 candidate，但只有 bounded evidence 能 promotion 到 HOT。
- **Stale Context Invalidation**：HOT evidence 綁 revision；有 Git 時優先 blob identity。來源變更或消失後不能靜默沿用舊 Context。
- **Index Reconciliation**：檔案/符號重新出現時會解除 missing tombstone；refreshed index 已不存在的 logical locator 不能繼續留在 HOT。
- **Repository-scoped `ContextEvidence` Contract**：只做 deterministic `proven-same / proven-different / revision-conflict / conflict / compatible / unknown`；semantic similarity 不能當 proof。
- **Context Sufficiency Gate**：只根據可明確觀察的本機 signal 建議 Recall，不宣稱能證明語意完整。
- **Critical Evidence Recall Benchmark**：正式量 initial/final recall、false-filter rate 與 Recall 新增的 model calls。
- **架構減法**：Sandbox/Runtime/Multi-Agent 功能仍是 native，但不再列為 Core。Core 鎖定 `Reduce → Verify → Recall`。

核心安全原則：**不送模型 ≠ 刪除資訊**。無法確定是否重要的 Repository Evidence 應留在 Recallable 層，而不是因 token optimization 永久丟棄。

## v2.2 重點：Unified Filter & Dedup Engine

- **安全預設的 canonical dedup**：`canonicalKey` 只代表 fact identity；缺少 `value/polarity` 時，預設 `exact-claim`，不同 wording 不再因 canonicalKey 相同就直接合併。舊語意保留為明確的 `--unstructured-canonical-policy legacy-merge`。
- **Agreement integrity**：`occurrence_count`、`agreement_count`、`independent_source_count`、`independent_evidence_count` 分開計算；同一 Worker 重複輸出不會灌高 agreement。
- **Provenance-preserving dedup**：External Context 相同內容只在相同 path/symbol identity（或完全沒有 location）下合併，provider/source/provenance support 聚合後保留。
- **Verified near-dedup 真正落地**：Similarity 只能產生 candidate；pair verifier 通過後還要經 component-level identity/assertion guard，防止 identity-less bridge 造成傳遞式錯誤合併或 order-dependent support attribution。
- **Cross-layer filtering**：已選 Symbol 的結構項目不再於 file structure 重複；session 已讀 External Context 改為 reference-only，而不是再次傳全文。
- **Handoff 安全去重**：只對 evidence/tests/risks/targets 等 set-like 頂層 list 做 exact JSON dedup；巢狀步驟/事件序列不會被遞迴刪除。
- **Contradiction 單次表示**：conflict sides 的 support metadata 直接進 contradiction；Synthesis Packet 不再把同一 fact identity 同時放在 contradictions 與一般 findings。
- **Bounded diagnostics**：JSON Batch 與 NDJSON Streaming 都套用 malformed/filtered detail limits；計數完整保留，但診斷 payload 有上限。
- **Filter Audit Gate**：新增 `repo-context filter-audit`，Runtime 在 Grader/Integrator 前及 final reduction 後都檢查 reducer invariants；失敗時阻止 finalize。
- 新增 Filter Summary、Dedup Support、Filter Audit 三份正式 Contract，總計 **21 份 Draft 2020-12 Schema**。

四個不可破壞的 invariant：

```text
1. Duplicate content 可以消失；support/provenance 不可以靜默消失。
2. 同一 Worker 重複輸出不增加 agreement。
3. Similarity 只有 candidate authority；沒有 merge authority。
4. Contradiction 永遠不能被 dedup/budget filter 吃掉。
```

## v2.1 重點

- **原生 Container Sandbox Adapter**：支援 Podman / Docker，預設 `network=none`、Repository read-only mount、container root read-only、drop ALL capabilities、`no-new-privileges`、PID / memory / CPU limit、non-root user 與 bounded tmpfs。
- **預設禁止隱性 image pull**：`container.pull=never`；若改成 `missing` / `always`，必須另外授權 runtime network。
- **權限拆開授權**：外部程式執行、Container network、Repository write 分別需要不同 CLI flag，不因允許 subprocess 就順便取得網路或寫入權限。
- **Process-tree cancellation**：POSIX 使用 process group/session，timeout / cancellation 會終止 descendants；Windows 採 best-effort process-tree cleanup。
- **Durable Runtime Checkpoint**：每個完成節點/波次原子寫入 `.repo-context/runtime-runs/<run-id>/checkpoint.json`。
- **Resume 不重跑已成功節點**，並延續 model-call / token / telemetry 累積值。
- **Repository Drift Guard**：使用 bounded Git identity（HEAD + changed path + index/working blob SHA）檢查續跑前程式碼是否改變；預設 drift 即阻擋。
- 新增 `runtime list`、`runtime inspect`、`runtime resume`，以及 Runtime State / Sandbox Policy Schema。

Container 能降低 Host 暴露，但不是 VM，也不是 container/kernel escape 的安全保證。同一 `run_id` 應由單一 controller 執行；checkpoint 是 durable state，不是 distributed lock。

## v2.0 重點

- **可執行 Runtime Adapter**：Host 可註冊 in-process adapter；內建 subprocess adapter 使用 JSON stdin/stdout contract。
- **真正執行 dependency waves**：bounded parallelism、fail-fast cancellation、wall/model/token backpressure、bounded retry 與 model-tier escalation。
- **Lane Context Slicing**：每個 worker 只取得已排序 context pack 的 bounded slice，不再把整份 context 複製給每個 lane。
- **Fan-In 真正位於 Grader / Integrator 前**：兩者收到 contradiction-preserving synthesis packet，而不是執行完後才事後計算 reducer。
- **Grader Gate 真正生效**：`reject` / `uncertain` 會阻止後續 finalize。
- **Usage Telemetry**：每次 attempt 記錄 latency/token；只有 provider/runtime 明確回報時才記錄 USD cost，不使用靜態價目表猜費用。
- **Final Answer Deterministic Invariants**：可檢查 required/forbidden claims、required fields、expected decision，但不宣稱等同語意正確性。
- subprocess stdout 改成 bounded streaming drain，超限立即 terminate。
- 新增 Runtime Config / Invocation / Result / Telemetry / Final Answer Evaluation 五份 Draft 2020-12 Schema。

v2.0 完整保留 v1.7 的 Streaming Fan-In、Tokenizer、Git Provenance、candidate-only similarity、Deterministic Verifier 與 contradiction preservation。

## 安裝

```bash
python3 -m pip install .
repo-context --version
repo-context-fan-in --help
```

或直接執行：

```bash
python3 scripts/repo_context.py map . --top-k 25 --pretty
```


### Filter / Dedup Audit

```bash
repo-context fan-in workers.ndjson --format ndjson --budget 4000 --pretty
repo-context filter-audit reduction.json --pretty
```

Production 預設使用 `--unstructured-canonical-policy exact-claim`。只有需要重現 v1.5–v2.1 的 legacy canonical grouping 時才指定 `legacy-merge`；Audit 會對這類 ambiguous unstructured canonical group 發出 warning。

## 實際執行 Runtime

`plan` / `context` 仍是安全的 advisory surface；真正 spawn worker 必須明確呼叫 `runtime execute`。

```bash
repo-context runtime status --pretty

repo-context runtime execute \
  "Autonomously implement an end-to-end payment migration across the entire project and ship production-ready integration" \
  --repo . \
  --config examples/runtime/subprocess-runtime.json \
  --allow-external-commands \
  --no-context \
  --model-calls 12 \
  --final-case examples/runtime/final-answer-case.json \
  --pretty
```

subprocess adapter 固定 `shell=False`。Runtime 透過 stdin 傳入 `repo-context-runtime-invocation/v1` JSON，Worker 必須在 stdout 回傳單一 JSON。未提供 `--allow-external-commands` 時，外部 subprocess 執行會被封鎖。

執行期間會真正套用 dependency waves、bounded concurrency、retry/tier escalation、grader gate、cancel/backpressure 與 call/token/wall budget。Repository / Handoff 內容仍是 untrusted data，不會取得 instruction authority。

## Sandbox Worker 與 Durable Resume

預先存在於本機的 container image 可在不開放 worker network 的情況下執行：

```bash
repo-context runtime execute "<task>" \
  --repo . \
  --config examples/runtime/container-runtime.json \
  --allow-external-commands \
  --pretty
```

若真的需要 Container network 或允許 image pull，必須再加 `--allow-runtime-network`。若要 writable repository bind mount，設定 `container.repo_mode=rw` 之外還要再加 `--allow-runtime-write`。

查看與續跑：

```bash
repo-context runtime list --repo . --pretty
repo-context runtime inspect <run-id> --repo . --pretty
repo-context runtime resume <run-id> --repo . --config runtime.json --allow-external-commands --pretty
```

Resume 不會重跑成功節點；runtime config、plan、budget/tokenizer policy 必須一致。若 Git source 已 drift，預設拒絕續跑；人工確認後才可明確使用 `--allow-repo-drift`。

## Repository Context

```bash
repo-context query . "payment checkout" --top-k 20 --pretty
repo-context context . "debug payment status pending" \
  --budget 6000 \
  --session payment-debug \
  --pretty
repo-context symbol . src/services/payment.py charge --session payment-debug --pretty
```

Git 可用時，selected file / symbol 的 provenance 會包含：

```json
{
  "git": {
    "commit": "...",
    "head_blob_sha": "...",
    "working_blob_sha": "...",
    "dirty": false,
    "content_identity": {
      "path": "src/services/payment.py",
      "blob_sha": "...",
      "source": "HEAD"
    }
  }
}
```

如果工作目錄已修改，`content_identity.blob_sha` 會指向 working-tree blob，不會假裝 evidence 還是 HEAD 的內容。

## Streaming Fan-In

相容 JSON：

```bash
repo-context fan-in examples/fan-in/worker-outputs.json \
  --budget 1800 \
  --pretty
```

大量 Worker 建議使用 NDJSON：

```bash
repo-context fan-in examples/fan-in/worker-outputs.ndjson \
  --format ndjson \
  --budget 1800 \
  --pretty
```

也可從 stdin：

```bash
cat workers.ndjson | repo-context-fan-in - --format ndjson --pretty
```

NDJSON 會逐筆 validation、group、aggregate。Reducer 只保留 surviving groups 與有上限的 malformed diagnostics，不保留全部 raw payload。`stats.peak_reducer_group_count` 可觀察 aggregation state 的大小。

## Tokenizer

預設仍是 dependency-free：

```bash
repo-context tokenizer status --pretty
repo-context tokenizer estimate "hello world" --provider native --pretty
```

`native` = UTF-8 bytes / 4 approximation，不是 billing truth。

Host 已安裝 `tiktoken` 時可選：

```bash
repo-context tokenizer estimate "hello world" \
  --provider tiktoken \
  --model gpt-4o \
  --pretty
```

Host Runtime 也可透過 Python API 註冊自己的 estimator；CLI 不允許任意 import module path，避免把 token adapter 變成任意程式執行入口。

Budget-sensitive commands：

```bash
repo-context context . "debug auth" --budget 6000 --tokenizer native
repo-context fan-in workers.json --budget 4000 --tokenizer native
repo-context synthesis-packet reduction.json --budget 4000 --tokenizer native
repo-context handoff worker grader payload.json --token-budget 1200 --tokenizer native
```

即使 token counter 是 exact，也不代表供應商實際 billing 完全相同；chat framing、provider rules、hidden overhead 仍可能不同。

## Candidate Detection：可以找近似，但不能直接合併

```bash
repo-context fan-in workers.json \
  --candidate-provider lexical \
  --candidate-threshold 0.72 \
  --pretty
```

或獨立分析：

```bash
repo-context candidate-detect reduction.json --provider lexical --pretty
```

權限模型：

```text
Similarity
   -> Candidate Pair
   -> Deterministic Verifier
        exact normalized claim
        OR exact canonical/structured identity
        AND exact structured assertion side
   -> merge-authorized candidate / contradiction candidate / reject
```

Similarity 本身永遠不能 merge。Host 即使註冊真正 embedding-based provider，也只能得到相同的 candidate-only 權限。

## Agreement / Contradiction

```text
Worker A -> async
Worker B -> async
Worker C -> sync

async agreement = 2
sync  agreement = 1
contradiction    = true
```

Contradictions 是 mandatory synthesis evidence。若 mandatory sections 自己就超過 budget，會回傳：

```json
{"budget":{"overflow":true}}
```

不會為了漂亮的 reduction ratio 偷刪衝突。

## Git Provenance CLI

```bash
repo-context provenance repo . --pretty
repo-context provenance file . src/services/payment.py --pretty
repo-context provenance symbol . src/services/payment.py charge \
  --start-line 10 --end-line 32 --pretty
```

這讓跨 Worker 的版本漂移可被觀察：兩個 Worker 即使都說讀了同一路徑，如果 blob identity 不同，就不是同一份 source evidence。

## Formal Schema

```bash
repo-context schema list --pretty
repo-context schema get finding --pretty
repo-context schema validate finding \
  '{"claim":"x","evidence":"y","source":"a.py"}' \
  --pretty
```

內建 Draft 2020-12 contract：Finding、Worker Output、Handoff、Fan-In、Contradiction、Synthesis Packet、Trace Event、Benchmark Case、Token Estimate、Provenance、Candidate Analysis。

Runtime 自己維持 zero dependency，只檢查核心 invariant；需要完整 JSON Schema validation 時可用外部 validator。

## Trust Boundary

Repository、Provider、Worker text 都是 evidence，不具有 instruction authority。

```bash
repo-context trust-scan README.md --source repository --pretty
```

會標記 instruction override、role spoofing、destructive command、credential access、network exfiltration 等訊號，但不會偷偷刪 source evidence。

沒有偵測到訊號，也不代表 Repository text 可以變成高優先級指令。

## Provider-aware Runtime

Capability namespace 包含：

- `repository.*`
- `context.*`
- `knowledge.*`
- `executor.*`
- `model.*`
- `quality.*`
- `runtime.*`
- `orchestration.*`

受信任且相容的 provider 可以被重用；沒有真正 implementation 的 executor/model capability 維持 unresolved，不假裝 native 已支援。

## Planner 與 Executable Runtime

`plan` 會 deterministic 產生：

- task complexity
- risk / ambiguity / novelty
- abstract model tier
- dependency-aware schedule
- lane budget
- quality gate
- bounded retry / human review fallback

`plan` 本身不 spawn Agent；真正執行必須明確使用 `runtime execute`。Runtime 可以透過已授權 adapter spawn Worker、執行 dependency waves、套用 retry/backpressure/grader gate，但仍不偷偷選 vendor model；`cheap` / `standard` / `strong` 的實際模型映射由 adapter/provider 決定。

## Host Facades

```bash
repo-context host-install --host claude-code --scope project --repo .
repo-context host-install --host codex --scope project --repo .
```

Facade：`reducer-repo`、`reducer-debug`、`reducer-impact`、`reducer-review`、`reducer-doctor`。

## Benchmark

Repository selection：

```bash
repo-context benchmark examples/benchmark-tasks.json examples/sample-project --budget 1800 --pretty
```

Reducer deterministic correctness：

```bash
repo-context benchmark-e2e examples/benchmark-e2e.json --budget 6000 --pretty
```

可以驗證 required claim、forbidden claim、source preservation、contradiction count、malformed limit、budget overflow 等 deterministic invariant。Final payload 也可另外執行：

```bash
repo-context evaluate-final answer.json case.json --pretty
```

這些檢查都不宣稱等同語意、事實或真實世界 correctness。

## Correctness 原則

1. false negative duplicate 比 false-positive merge 安全。
2. similarity 只能提升 candidate recall，不能取得 merge authority。
3. contradiction 不為 token target 犧牲。
4. repository/provider/worker content 不進入 instruction authority chain。
5. static graph / heuristic parser 的限制必須明確標示。
6. token counting 與 provider billing claim 分開。
7. Git 可用時，evidence 綁定 commit/blob content identity。

## 測試

```bash
python3 -m unittest discover -s tests -v
```

詳細設計見 `references/` 與 `docs/audits/`。

## License

MIT
