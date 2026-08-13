<p align="center">
  <strong>先縮減，再讀取。</strong>
</p>

<p align="center">
  為 AI Coding Agent 提供 Provider-aware Repository Context 縮減與資訊編排。
</p>

<p align="center">
  <a href="https://github.com/tommy771004/agent-repo-context-reducer/actions"><img src="https://github.com/tommy771004/agent-repo-context-reducer/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen" alt="Zero runtime dependencies">
</p>

<p align="center">
  <a href="#reducer-短指令">短指令</a> &bull;
  <a href="#安裝">安裝</a> &bull;
  <a href="#快速開始">快速開始</a> &bull;
  <a href="#運作原理">運作原理</a> &bull;
  <a href="#指令">指令</a> &bull;
  <a href="#安全性">安全性</a> &bull;
  <a href="#限制">限制</a>
</p>

<p align="center">
  <a href="README.md">English</a> &bull;
  <a href="README.zh-TW.md"><strong>繁體中文</strong></a>
</p>

---

**Agent Repo Context Reducer** 協助 Claude Code、Codex、Cursor、OpenCode 與其他 Coding Agent 在**不先把整個 Repository 的原始碼全部讀進模型 Context** 的情況下理解大型專案。

它在本機掃描程式碼、建立輕量 Dependency Graph 與 Symbol Index、依目前任務排序檔案，最後只輸出最有價值的結構化 Context。模型再針對真正需要深入推理的地方選擇性讀取完整 Source。

```text
沒有 Reducer

User Prompt
   |
   v
Agent 讀取數百／數千個檔案
   |
   v
形成巨大的 Context Wall
   |
   v
Reasoning


使用 Reducer

User Prompt
   |
   v
repo-context map/query
   |
   +-- Git-aware file index
   +-- Symbol extraction
   +-- Dependency graph
   +-- Task-aware ranking
   +-- Top-K context
   |
   v
Agent 只完整讀取真正相關的檔案
   |
   v
Reasoning
```

Reducer 屬於 **deterministic preprocessing（確定性前處理）**，本身不會呼叫 LLM。

## 它做什麼

| 功能 | Reducer 的處理方式 |
|---|---|
| Repository discovery | Git 可用時優先使用 Git，因此自動遵守 `.gitignore` |
| Project map | 偵測語言、manifest、framework hints、entry points 與 workspaces |
| Source structure | 擷取 imports、classes、types、functions、exports 與 routes |
| Python source | 使用 Python 標準函式庫 AST |
| 其他語言 | 使用輕量、語言感知的結構擷取 |
| Dependency graph | 解析本機 relative imports 與 reverse dependencies |
| Ranking | 綜合 entry point、graph centrality、程式結構與 task keywords |
| Progressive context | 預設回傳 Top-K summaries，不回傳全部掃描結果 |
| Changed mode | 找出 Git changes 與鄰近受影響檔案 |
| Module mode | 將 Context 限制在指定 subtree / workspace |
| Cache | 重用未變更檔案的 structural summaries |
| Safety | 預設略過疑似 secrets、symlink、generated code、oversized/binary files |

## v1.3 Harness 優化

Reducer 現在把 Repository Context 視為更大的 **Information Orchestration（資訊編排）** 問題，而不是把 Kimi、OpenHands、GraphRAG 或任何特定 Stack 寫死進核心。Runtime 會依 capability 分層；有相容且受信任的 Provider 就重用，沒有時才使用自己真正具備的 fallback。

```text
User Task
   |
   v
Task Complexity Router
   |
   +-- 小任務 ---------> 單一 bounded worker
   |
   +-- 複雜任務 -------> dependency-aware schedule
                          |
                          +-- repository.*      -> code graph/index/search
                          +-- knowledge.*       -> docs/history/knowledge provider
                          +-- executor.*        -> 外部 coding/autonomous agent
                          +-- orchestration.*   -> multi-agent framework
                          +-- context.*         -> budget/dedup/handoff/artifact
                                                   |
                                                   v
                                             Minimal Context
```

新增核心能力：

- **Deterministic-first Sorter**：intent／complexity／risk／capability routing 優先由程式碼完成，預設 0 model call；只有 deterministic routing 不足時才考慮模型 escalation。
- **Vendor-neutral Model Tier Router**：用 `cheap`／`standard`／`strong` 抽象層級，而不是把 Claude、GPT、Kimi、Gemini 等具體型號寫死。
- **Risk / Ambiguity Escalation**：依風險、blast radius、ambiguity、novelty 與 cost of error 提升 planner／worker／grader tier。
- **Per-lane Budget**：Planner、Worker、Tester、Grader 各自拿 child budget，但總和不會突破原本 task-wide budget。
- **Independent Quality Gate**：Grader 只收到 reduced handoff／tests／evidence／risks，不直接吞 Worker 的完整 conversation。
- **Bounded Retry**：Reject loop 有最大 attempt；需要時升 tier，耗盡後交回 human review，不允許無限重試。
- **Task Complexity Router**：小型任務維持 single-agent；只有跨模組、整合、重構等較複雜任務才建議 multi-agent。
- **Dependency-aware Scheduler**：產生依賴 wave，只有互相獨立的階段才能平行。
- **Agent Handoff Reducer**：不把完整 subagent conversation 傳給下一個 Agent，只保留 decisions、evidence、targets、constraints、tests、risks、open questions。
- **Artifact Store**：大型 Agent／Tool output 存在 `.repo-context/artifacts/`，主模型先拿 compact metadata 或 reduced handoff。
- **Knowledge Provider Layer**：把長期 Project Memory 與 native static Code Graph 分離；內建 fallback 只做本機 docs／ADR lexical search，**不是 GraphRAG**。
- **Executor Provider Layer**：Kimi、OpenHands、Codex、Claude 等都應透過 capability provider 接入，而不是核心 dependency。沒有 trusted provider 時，unsupported executor capability 會保持 unresolved，不會假裝 native 可執行。

### Model Tier Routing 與 Quality Gate

```text
User Task
   |
   v
Deterministic Router (0 model calls)
   |
   +-- complexity
   +-- risk / ambiguity / novelty
   +-- required capabilities
   |
   v
Abstract model tier
   +-- cheap     -> 高頻、低風險、bounded work
   +-- standard  -> 一般 implementation / reasoning
   +-- strong    -> 高風險、模糊、架構決策、final grading
   |
   v
Dependency-aware lanes
   |
   v
Artifact + Handoff Reducer
   |
   v
Independent Grader
   +-- PASS
   +-- RETRY (bounded)
   +-- HUMAN REVIEW
```

`cheap`／`standard`／`strong` 是抽象 tier，不是模型名稱。只有 Host 或已註冊 Provider 真的提供 `model.*` capability 時，Reducer 才能解析到具體模型；否則保持 advisory/unresolved，不會假裝自動切模型。

Sorter 預設不用 cheap model，因為 deterministic code 更便宜。只有 deterministic 規則無法處理且 Host 支援 tier routing 時，才把模型當 fallback。

### Code Graph 與 Knowledge Graph 分離

| Layer | 內容例子 | Reducer 行為 |
|---|---|---|
| `repository.graph` | file、import、reverse import、symbol definition | 有 native static fallback |
| `knowledge.search` | README、docs、ADR、architecture notes、changelog | 有 native lexical fallback |
| `knowledge.graph` | 決策／實體／歷史關係 | 沒有真實相容實作時只使用 external provider |
| `executor.code` / `executor.autonomous` | Coding／Autonomous engineering execution | external provider only |

因此即使環境已經有更強的 Graph 或 Memory Skill，Reducer 也不需要再建立第二套相同能力。

`examples/provider-layers/` 內附 capability manifest 範本，但刻意不附可執行 command。要接入外部工具時，先把範本放到 `.repo-context/providers.d/`，再加入真正符合該工具的 adapter，確認 command contract 後才加入 trust。

## Reducer 短指令

對外介面刻意保持簡單：使用者只需要表達 intent；Skill 負責選 workflow；共用 runtime 再處理 Provider 偵測／重用、fallback、graph/index、去重與 budget。

| 短指令 | 用途 | 內部 Routing |
|---|---|---|
| `/reducer-repo <task>` | 一般 Repository 任務 | 自動判斷 workflow |
| `/reducer-debug <task>` | 除錯、找 bug | 強制 `debug` workflow |
| `/reducer-impact <task>` | 分析修改影響 | 強制 `change-impact` workflow |
| `/reducer-review <task>` | Code / change review | 強制 `review` workflow |
| `/reducer-doctor` | 檢查 Skill／Plugin／Provider 重疊 | Provider capability doctor |

這些短指令**不會各自建立第二套 index 或 graph**；全部共用同一個 `repo-context` runtime 與同一份 persistent state。

### Claude Code Slash Commands

只要安裝一次專案層級的快捷指令：

```bash
repo-context host-install --host claude-code --scope project --repo .
```

若只有安裝 Skill、沒有把 Python CLI 裝到 PATH，也可以：

```bash
python scripts/repo_context.py host-install --host claude-code --scope project --repo .
```

之後即可：

```text
/reducer-debug payment 成功但 order status 一直 pending
/reducer-impact 我修改了 PaymentService，會影響哪些地方？
/reducer-review review 目前的修改
```

要全域安裝可改成 `--scope global`。

### Codex Named Skills

把相同的 facade 名稱安裝到 Codex Skills 目錄：

```bash
repo-context host-install --host codex --scope project --repo .
```

會建立 `reducer-repo`、`reducer-debug`、`reducer-impact`、`reducer-review`、`reducer-doctor` 五個命名 Skill。若目前使用的 Codex 客戶端有把已安裝 Skill 暴露成 `@` mention，就可以使用 `@reducer-debug` 這類形式；否則請使用該客戶端正式提供的 Skill 選擇／呼叫方式。

檢查安裝狀態：

```bash
repo-context host-status --host claude-code --scope project --repo .
repo-context host-status --host codex --scope project --repo .
```

其他 host adapter 也可以直接使用穩定的 facade API：

```bash
repo-context run reducer-debug "payment 成功但 order status 一直 pending" --repo .
```

## 安裝

### Agent Skill — 建議方式

使用 Open Agent Skills CLI 直接從 GitHub 安裝：

```bash
npx skills add tommy771004/agent-repo-context-reducer
```

全域安裝：

```bash
npx skills add tommy771004/agent-repo-context-reducer -g
```

Claude Code：

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a claude-code
```

Codex：

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a codex
```

Cursor：

```bash
npx skills add tommy771004/agent-repo-context-reducer -g -a cursor
```

同時安裝到多個 Agent：

```bash
npx skills add tommy771004/agent-repo-context-reducer -g \
  -a claude-code \
  -a codex \
  -a cursor
```

### Python CLI — 選用

不安裝即可 clone 後直接執行：

```bash
git clone https://github.com/tommy771004/agent-repo-context-reducer.git
cd agent-repo-context-reducer
python scripts/repo_context.py map . --pretty
```

或直接安裝 `repo-context` 指令：

```bash
python -m pip install git+https://github.com/tommy771004/agent-repo-context-reducer.git
repo-context --version
```

Runtime 不需要任何第三方 Python dependency。

## 快速開始

安裝 Host 快捷入口後，直接使用 intent facade，不需要自己串接低階指令：

```text
/reducer-repo 解釋這個專案的架構
/reducer-debug payment 成功但 order status 偶爾沒有更新
/reducer-impact 我修改了 PaymentService，會影響哪些地方？
/reducer-review review 目前的修改
```

Facade 會透過同一個 Runtime 完成 task／complexity routing、capability detection、Provider 重用、真正具備能力時的 native fallback，以及 bounded context planning。

如果 Host 沒有提供 slash command／named Skill shortcut，也可以直接呼叫穩定 facade API：

```bash
repo-context run reducer-debug \
  "payment succeeds but order status is not updated" \
  --repo . --pretty
```

`map`、`query`、`deps`、`symbol`、`knowledge`、`handoff` 等低階命令仍保留給 adapter 與進階 workflow 使用。

## 運作原理

核心原則是 **Progressive Disclosure of Code Context（程式 Context 的漸進揭露）**。

### Level 0 — 本機建立 Index

工具在本機掃描 Repository，不會把原始 Source 送進模型。

Git 可用時會優先使用 Git 列舉檔案，因此 ignored files 不會被 index；如果 Git 不可用，則使用具安全限制的 filesystem walk。

### Level 1 — Project Map

```bash
repo-context map . --top-k 25
```

回傳：

- languages
- framework hints
- manifests
- workspaces / monorepo modules
- entry points
- directory hot spots
- graph-central files
- Top-K structural summaries

預設**不會**為每個檔案都輸出 summary。

### Level 2 — Task-aware Query

```bash
repo-context query . "authentication refresh token failure" --top-k 20
```

Ranking 會綜合：

```text
static structure
+ entry-point distance
+ imported-by/imports centrality
+ filename/symbol/import/query matches
```

目前使用 deterministic lexical ranking，不需要 embedding，也不會呼叫模型。

### Level 3 — Module / Dependency Drill-down

```bash
repo-context module . src/services --query "payment" --pretty
repo-context deps . src/services/payment.ts --depth 2 --pretty
```

Agent 可以只檢查一個 logical area，不必重新讀取整份 Project Map。

### Level 4 — 真正需要時才讀完整 Source

```bash
repo-context inspect src/services/payment.ts --pretty
```

Structural Map 的目的是幫助 Agent 判斷「是否真的需要全文」。真正涉及 implementation semantics 的推理仍由 Coding Agent 負責。

## 指令

### `run` — 短指令 Facade API

Host adapter 只呼叫一個穩定 facade，不把底層 workflow 暴露給使用者：

```bash
repo-context run reducer-repo "理解這個 repository" --repo .
repo-context run reducer-debug "payment 成功但 order 一直 pending" --repo .
repo-context run reducer-impact "我修改了 PaymentService" --repo .
repo-context run reducer-review "review 目前修改" --repo .
repo-context run reducer-doctor --repo .
```

列出全部 facade：

```bash
repo-context commands --pretty
```

### `host-install` / `host-status`

安裝或檢查人類可直接使用的快捷入口：

```bash
repo-context host-install --host claude-code --scope project --repo .
repo-context host-install --host codex --scope project --repo .
repo-context host-status --host claude-code --scope project --repo .
```

以下底層命令仍保留給 runtime 除錯、自訂 integration 與進階 workflow 使用。

### Harness Planning、Handoff、Artifact 與 Knowledge

以下屬於進階 Runtime API；一般使用者仍只需要 `/reducer-*`。

```bash
# 判斷是否值得啟動 multi-agent
repo-context complexity "重構整個專案的 authentication" --pretty

# 建立 provider-aware harness plan（包含 risk / model tier / lane budget / quality gate / retry policy）
repo-context plan "重構整個專案的 authentication" --repo . --context-budget 6000 --pretty

# 產生 dependency-aware execution waves
repo-context schedule "在整個 app 加入 OAuth" --pretty

# Planner → Implementer 前先縮減 handoff
repo-context handoff planner implementer planner-result.json --repo . --store-artifact --pretty

# 產生 reduced grader packet，不把 Worker 原始 conversation 直接塞給 Grader
repo-context quality packet "review payment change" worker-result.json --intent review --pretty

# 驗證 Grader JSON 結果
repo-context quality evaluate grader-result.json --risk-level high --pretty

# 套用 bounded retry / tier escalation
repo-context retry-decision reject --attempt 1 --worker-tier standard --risk-level high --complexity-level complex --pretty

# 大型 output 存到 context 外
repo-context artifact put research-result.json --repo . --producer researcher --pretty
repo-context artifact list --repo . --pretty

# 本機 docs／ADR knowledge fallback
repo-context knowledge index --repo . --pretty
repo-context knowledge search "為什麼當初選 event queue？" --repo . --pretty
```

`plan` 與 `schedule` 只產生 advisory plan；Reducer 不會偷偷 spawn Agent，也不會自行假設某個具體模型對應 `cheap`／`standard`／`strong`。外部 Model／Executor／Orchestrator 仍必須透過相容 manifest/adapter，並通過既有 trust policy。

### `map`

建立精簡 Top-K Repository Map：

```bash
repo-context map . --pretty
repo-context map . --top-k 15 --query "checkout payment" --pretty
```

`scan` 保留為向下相容 alias：

```bash
repo-context scan . --pretty
```

### `query`

依目前任務為檔案排序：

```bash
repo-context query . "login sometimes fails after token refresh" --top-k 20 --pretty
```

### `module`

限制在特定 subtree 或 monorepo module：

```bash
repo-context module . src/services --pretty
repo-context module . packages/auth --query "session" --pretty
```

### `deps`

顯示 dependency relationships：

```bash
repo-context deps . src/services/payment.ts --pretty
repo-context deps . src/services/payment.ts --depth 2 --pretty
```

輸出包含：

- local imports
- imported-by files
- dependency neighborhood
- unresolved local imports

### `changed`

以 Git 變更作為 seed set，並納入鄰近 dependencies / callers：

```bash
repo-context changed . --pretty
```

與指定 base branch/ref 比較：

```bash
repo-context changed . --base main --depth 2 --pretty
```

這很適合 Agent 已修改程式後使用，避免下一輪重新對無關區域建立 reasoning context。

### `inspect`

擷取單一檔案的結構資訊：

```bash
repo-context inspect src/services/order.ts --pretty
```

### 常用掃描控制

```bash
repo-context map . \
  --top-k 25 \
  --max-files 10000 \
  --max-file-bytes 512000 \
  --pretty
```

其他選項：

```text
--no-cache            停用 incremental structural-summary cache
--include-hidden      在安全範圍內納入 hidden files/directories
--include-generated   納入偵測為 generated 的檔案
```

## Task-aware Ranking

對整個 Repository 很重要的檔案，不一定對目前 Prompt 最重要。

例如：

```text
src/main.ts                    全域重要
src/services/payment.ts        對目前任務重要
src/models/order-status.ts     對目前任務重要
```

執行：

```bash
repo-context query . "payment completed order status" --top-k 10
```

path、symbol、import 中與 query 相符的項目會在 dependency graph signals 之外獲得額外權重。

因此 Reducer 的角色不是單純 Source Summarizer，而是 Repository Navigation Engine。

## Dependency Graph

Local relative imports 會在可能的情況下解析到已 index 的 Source files。

```text
src/index.js
    |
    v
src/routes/order.js
    |
    v
src/services/order.js
    |
    v
src/services/payment.js
```

Graph 用於：

- centrality ranking
- entry-point distance
- reverse dependency lookup
- changed-file impact neighborhoods
- task-aware file selection

External package imports 會與 local edges 分開保存。

## Git-aware Scanning

在 Git Repository 中，Reducer 優先使用：

```bash
git ls-files --cached --others --exclude-standard
```

因此會自動遵守專案 `.gitignore`，包含掃描 Repository subtree 的情境。

Git 未安裝或目前目錄不是 Git Repository 時，會安全 fallback 到 filesystem walk，並排除常見 build/cache/vendor 目錄。

## Monorepo 支援

Project Map 可偵測常見 workspace layout：

- `package.json` workspaces
- `pnpm-workspace.yaml`
- Cargo workspaces
- `apps/`
- `packages/`
- `services/`

例如：

```text
repo/
├── apps/web
├── apps/api
├── packages/auth
├── packages/ui
└── services/payment
```

可使用 `module` 限縮 Context：

```bash
repo-context module . services/payment --pretty
```

## Incremental Cache

Structural summaries 會快取在：

```text
.repo-context-cache/
```

每個 cache entry 由 file path、modification time 與 size 決定。沒有改變的檔案，下次掃描不需要重新 parse。

Cache 儲存的是 structural summaries，不是完整 source text。

停用方式：

```bash
repo-context map . --no-cache
```

## 安全性

Reducer 的設計目標之一，是掃描 Repository 時不要盲目把敏感或高雜訊內容送進 Agent Context。

預設略過：

- `.env` 與 `.env.*`
- 檔名疑似 `secret` / `credentials`
- private key / certificate key files（`.pem`、`.key`、`.p12`、`.pfx` 等）
- symlinks
- binary files
- oversized files
- generated/minified code
- 常見 build/cache/vendor directories

`inspect` 同樣會拒絕 secret-like path。

一般 `map/query/module/deps` 輸出不會嘗試印出完整 Source contents。

詳見 [SECURITY.md](SECURITY.md)。

## Context 節省

`map` 輸出包含「掃描納入的 source bytes」與「輸出 JSON bytes」的粗略比較。

Token 估算使用：

```text
UTF-8 bytes / 4
```

這只是相對估算，**不是 tokenizer，也不是 billing estimate**。

對很小的 Repository，metadata overhead 可能讓縮減效果不明顯。此設計主要針對中大型 codebase，重點是避免不必要的全文讀取。

本專案不宣稱固定的 token、latency 或 cost reduction 百分比。

## 支援語言

目前 structural extraction 可辨識：

- Python
- JavaScript / TypeScript / JSX / TSX
- C#
- Rust
- Go
- Java
- Kotlin
- Ruby
- PHP
- Swift
- C / C++
- Vue
- Svelte
- SQL
- shell / PowerShell

Python 使用標準函式庫 AST。其他語言目前採 lightweight language-aware extraction；語法不明確時會保守 fallback。

## Repository 結構

```text
agent-repo-context-reducer/
├── SKILL.md
├── README.md
├── README.zh-TW.md
├── SECURITY.md
├── CONTRIBUTING.md
├── CHANGELOG.md
├── pyproject.toml
├── repo_context/
│   ├── cli.py
│   ├── scanner.py
│   ├── parsers.py
│   ├── graph.py
│   ├── ranking.py
│   ├── git_utils.py
│   ├── workspaces.py
│   ├── cache.py
│   ├── complexity.py
│   ├── risk.py
│   ├── model_router.py
│   ├── lane_budget.py
│   ├── scheduler.py
│   ├── grader.py
│   ├── retry_policy.py
│   ├── handoff.py
│   ├── artifact_store.py
│   ├── knowledge.py
│   ├── orchestration.py
│   └── util.py
├── scripts/
│   └── repo_context.py
├── references/
│   ├── architecture.md
│   ├── harness/
│   └── providers/
├── examples/
│   └── sample-project/
└── tests/
    └── test_repo_context.py
```

## 開發

執行測試：

```bash
python -m unittest discover -s tests -v
```

執行 sample project map：

```bash
python scripts/repo_context.py map examples/sample-project --pretty
```

Task-aware example：

```bash
python scripts/repo_context.py query examples/sample-project \
  "payment checkout" --top-k 5 --pretty
```

Runtime 刻意維持零第三方 dependency，讓 Skill 能直接在 Coding Agent 環境中使用，不需要額外 setup phase。

## 設計邊界

本專案回答的是：

> Agent 下一步應該看哪裡？

> 這個 Task 應維持 single-agent，還是依 dependency 展開？

> Agent handoff 邊界應該傳哪些資訊？

> 依 complexity／risk，應使用哪個抽象 model tier，以及每個 lane 可用多少 budget？

> Independent Grader 的結果應 PASS、RETRY 還是 ESCALATE？

它不宣稱直接回答：

> 這個 implementation 一定正確嗎？

> 這份程式碼一定安全嗎？

> 原本預期的 business behavior 是什麼？

> Host 沒有提供 model mapping 時，`cheap`／`standard`／`strong` 應該硬對應到哪個廠商模型？

這些問題仍需要對選中的完整 Source、Tests 與 Runtime Evidence 進行推理。

## 限制

- Dependency graph 主要反映可解析的靜態 dependency；dynamic dispatch、reflection、runtime DI 與 generated code 可能無法完整表示。
- 其他語言的 lightweight parser 不等同完整 compiler frontend。
- Task-aware ranking 屬於 heuristic，不代表對答案正確性的保證。
- Context token 數量為估算值，而不是特定模型 tokenizer 的精確結果。
- Skill 本身是 Agent instruction，不能保證攔截所有 Agent 內建的 Read/Grep/Glob 行為。

## 理念

```text
Discover with code.
Rank with code.
Reduce with code.
Reason with the model.
```

不要把 deterministic local tooling 可以先完成的 Repository 導航工作，浪費在昂貴的模型 Context 上。

## License

MIT
