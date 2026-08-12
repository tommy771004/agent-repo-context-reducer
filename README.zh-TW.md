<p align="center">
  <strong>先縮減，再讀取。</strong>
</p>

<p align="center">
  為 AI Coding Agent 提供任務導向的 Repository 導航與 Context 縮減。
</p>

<p align="center">
  <a href="https://github.com/tommy771004/agent-repo-context-reducer/actions"><img src="https://github.com/tommy771004/agent-repo-context-reducer/actions/workflows/test.yml/badge.svg" alt="Tests"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/runtime%20dependencies-0-brightgreen" alt="Zero runtime dependencies">
</p>

<p align="center">
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

安裝 Skill 後，可以照平常方式向 Agent 下 Prompt：

```text
Read this entire project and explain its architecture.
```

Skill 會要求 Agent 優先執行：

```bash
python scripts/repo_context.py map <repo> --pretty
```

針對特定任務：

```text
Find why payment succeeds but order status is sometimes not updated.
```

建議先執行：

```bash
python scripts/repo_context.py query <repo> \
  "payment succeeds but order status is not updated" \
  --top-k 20 --pretty
```

接著只深入讀取排名結果中真正相關的檔案。

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
│   └── util.py
├── scripts/
│   └── repo_context.py
├── references/
│   └── architecture.md
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

它不宣稱直接回答：

> 這個 implementation 一定正確嗎？

> 這份程式碼一定安全嗎？

> 原本預期的 business behavior 是什麼？

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
