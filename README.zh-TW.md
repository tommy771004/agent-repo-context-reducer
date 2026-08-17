# Agent Repo Context Reducer

**先縮減，再讀取。** 為 AI Coding Agent 提供 Provider-aware Repository Context 縮減、Progressive Reading、Agent Handoff 與 deterministic multi-worker Fan-In。

版本：**1.5.0**　Python：**3.10+**　Runtime dependencies：**0**

[English](README.md) · [繁體中文](README.zh-TW.md)

## 專案定位

Agent Repo Context Reducer 讓 Claude Code、Codex、Cursor、OpenCode 與其他 Coding Agent 在不先把整個 Repository 原始碼塞進模型 Context 的情況下理解大型專案。Runtime 先在本機建立結構化 index、dependency graph、symbol index 與 task-aware ranking，再只輸出目前任務最值得讀的 context。

v1.5 進一步處理多 Agent 的另一個成本邊界：**多個 Worker 的結果匯入 Final Agent / Grader 前，先做 deterministic Fan-In reduction**。

```text
User Task
   |
   v
Task Router / Risk / Complexity
   |
   v
Repository Index + Graph + Symbols
   |
   v
Task-aware Ranking + VoI + Budget
   |
   v
Minimal Context
   |
   +-----------------------+
   |                       |
   v                       v
Worker A                Worker B ...
   |                       |
   v                       v
reduce_handoff()       reduce_handoff()
   \                       /
    \                     /
     v                   v
       Fan-In Reducer
       - validation
       - exact/canonical dedupe
       - agreement metadata
       - contradiction surfacing
              |
              v
       Synthesis Packet
       token-budget gate
              |
              v
        Final Agent / Grader
```

Reducer 本身採 **deterministic-first**：不需要 LLM 就能完成 scan、ranking、dedup、budget、handoff 與 fan-in。模型只負責真正需要推理的部分。

## v1.5 新增功能

- `context.fan-in`：多 Worker 結果 validation、exact/canonical grouping、agreement aggregation。
- `context.contradiction`：同一 structured identity 的 value / polarity disagreement 顯式化。
- `context.synthesis-packet`：在 contradictions 保留的前提下建立 bounded final-model input。
- `repo-context-fan-in` CLI。
- `reduce_handoff()` 新增 token-aware selection，可指定必須保留 `summary/tests/risks/open_questions` 等欄位。
- benchmark 新增 Worker → Fan-In → Synthesis 三段 token 與 latency 指標。
- trace/replay 可記錄 reducer stage metrics。
- correctness fix：同一 `canonicalKey` 只代表同一 fact identity；若 Worker 對 value/polarity 看法不同，不會把互相矛盾的 Worker 錯算成 agreement。

## 安裝

### 直接從原始碼執行

```bash
python3 scripts/repo_context.py --version
python3 scripts/repo_context.py map . --top-k 25 --pretty
```

### 安裝 Python CLI

```bash
python3 -m pip install .
```

安裝後：

```bash
repo-context --version
repo-context-fan-in --help
```

### Agent Skill

Repository 根目錄包含 `SKILL.md`，也提供 Claude Code / Codex facade adapter。若環境支援 Open Agent Skills，可將此專案安裝成 Skill；runtime CLI 仍可獨立使用。

## 快速開始

### 1. Repository map

```bash
repo-context map . --top-k 25 --pretty
```

### 2. 依任務查詢

```bash
repo-context query . "payment checkout order" --top-k 20 --pretty
```

### 3. 建立 bounded context pack

```bash
repo-context context . "debug payment status pending" \
  --budget 6000 \
  --session debug-payment \
  --pretty
```

### 4. 只讀取一個 symbol

```bash
repo-context symbol . src/services/payment.py charge --session debug-payment --pretty
```

### 5. 多 Worker Fan-In

```bash
repo-context-fan-in examples/fan-in/worker-outputs.json \
  --max-estimated-tokens 1800 \
  --pretty
```

## Core Reducer

| 能力 | 行為 |
|---|---|
| Repository discovery | Git 可用時優先 `git ls-files`，自然遵守 `.gitignore` |
| Project map | 語言、manifest、framework hints、entry points、workspaces |
| Symbol extraction | Python AST；其他語言使用保守的 language-aware heuristics |
| Dependency graph | 本機 relative/static imports 與 reverse dependencies |
| Ranking | task keywords、entry point、graph centrality、static structure |
| Progressive context | Top-K structure → symbol → full/delta content |
| Session dedup | 已讀且未變更的 symbol 改成 reference-only |
| Delta | symbol 變更時優先提供 diff |
| Context budget | 每次 context pack 有硬上限與估算用量 |
| Artifact store | 大型 Agent/Tool output 放在 `.repo-context/artifacts/` |
| Provider layer | 相容且受信任的外部 provider 可重用，否則 native fallback |
| Safety | secrets、symlink、generated、binary、oversized files 預設略過 |

## Fan-In correctness contract

Fan-In 不把「字面相似」當成可安全合併。

Grouping 優先順序：

1. upstream 提供 `canonicalKey`；
2. 否則只使用保守 normalized exact claim。

若同一 identity 有 structured `value` / `polarity`，會先依 asserted side 分組，再計算 agreement：

```text
Worker A: async
Worker B: async
Worker C: sync

=> async agreement = 2
=> sync  agreement = 1
=> contradiction = true
```

而不是把三個 Worker 誤標成 agreement = 3。

**原則：漏掉 duplicate 只會浪費 token；錯誤 merge 可能破壞答案。** 因此 fuzzy semantic merge 預設關閉。Embedding/LLM similarity 最多只能在上游提出 candidate，不可直接作為 merge proof。

## Synthesis Packet budget

Final Agent 前的 packet 先保留 contradictions，再依 confidence / agreement 排序 findings。

若 mandatory contradiction evidence 本身已超過 budget：

```json
{
  "budget": {
    "overflow": true
  }
}
```

系統不會為了顯示「成功縮減」而偷偷刪掉矛盾證據。

## Handoff Reducer

單一 Worker 的完整 conversation 不應直接傳給下一個 Agent。`reduce_handoff()` 會選擇：

- `summary`
- `decisions`
- `evidence`
- `targets`
- `constraints`
- `open_questions`
- `changed_files`
- `tests`
- `risks`

並保留 source SHA256、source token estimate、reduction ratio 與 lossy provenance。

## Provider-aware runtime

Capability 分層：

| Layer | 例子 | Native 行為 |
|---|---|---|
| `repository.*` | graph/index/search/symbols | 有 native fallback |
| `context.*` | budget/dedup/handoff/fan-in | Core native |
| `knowledge.*` | docs/history/search | 本機 lexical fallback；不是 GraphRAG |
| `executor.*` | coding/autonomous agent | external provider only |
| `model.*` | cheap/standard/strong | abstract tier；無 provider 時 unresolved |
| `quality.*` | grader/gate | gate native；真正 model grader 可 external |

Provider manifest schema：

```json
{
  "schema": "repo-context-capabilities/v1",
  "provider": {"name": "my-provider", "type": "external"},
  "provides": ["repository.graph"]
}
```

Machine-invokable provider 必須有相容 command contract，且需 trust/policy 授權；單靠 Skill description 推測出的 overlap 不會自動執行。

## Advisory Harness Planner

這個層是 **advisory**，不會自行 spawn Agent 或偷換模型：

- Task Complexity Router
- Risk / ambiguity / novelty routing
- Vendor-neutral `cheap / standard / strong` model tier
- Dependency-aware schedule
- Per-lane child budget
- Independent quality gate
- Bounded retry
- Human-review fallback

```bash
repo-context plan "Refactor authentication across the repo" --repo . --pretty
```

## Facade commands

| Facade | 用途 |
|---|---|
| `reducer-repo` | 一般 repository 任務 |
| `reducer-debug` | debug workflow |
| `reducer-impact` | change-impact |
| `reducer-review` | review workflow |
| `reducer-doctor` | provider overlap / runtime doctor |

Claude Code：

```bash
repo-context host-install --host claude-code --scope project --repo .
```

Codex：

```bash
repo-context host-install --host codex --scope project --repo .
```

Project scope shortcut 使用可攜式 `repo-context`，不寫入開發者機器的絕對 Python 路徑。

## 支援語言

| Tier | 語言 | Extraction |
|---|---|---|
| AST | Python | imports/classes/functions/symbol ranges |
| Structured heuristic | JS/TS/JSX/TSX/Vue/Svelte | imports/functions/classes/types/routes |
| Structured heuristic | C/C++ | `#include`、definitions、local dependency edges |
| Structured heuristic | Shell | `source`、function definitions |
| Structured heuristic | PowerShell | `Import-Module`、dot-source、functions |
| Structured heuristic | SQL | table/view/type/procedure/function |
| Heuristic | C#, Java, Kotlin, Rust, Go, Ruby, PHP, Swift | imports + common definitions |

## Benchmark

Repository benchmark：

```bash
repo-context benchmark examples/benchmark-tasks.json examples/sample-project --budget 1800 --pretty
```

指標包含：

- raw repository token estimate
- selected context token estimate
- structural reduction ratio
- expected-path recall（若 task fixture 有提供）
- correctness claim 明確標為 false，除非另外有真正 correctness evaluation

Fan-In benchmark 另外可量：

- raw worker-output tokens
- reduced fan-in tokens
- synthesis packet tokens
- reducer latency
- malformed / duplicate / agreement / contradiction counts

Token estimator 採 UTF-8 bytes / 4，只是輕量估算，不是 tokenizer，也不是 billing 保證。

## 測試

```bash
python3 -m unittest discover -s tests -v
```

完整包包含 Core、Provider、Handoff、Harness、Language tier、Maintenance、Fan-In regression tests。

## Runtime state

所有 persistent runtime state 收斂到：

```text
.repo-context/
├── index.json
├── cache/
├── sessions/
├── runs/
├── budgets/
├── lifecycle/
├── artifacts/
├── providers.d/
└── config.json
```

`.repo-context/` 預設會被加入 `.gitignore`。刪除 state 時，provider trust、手寫 provider manifests 與 artifacts 屬於不可重建資料，除非明確要求，否則不會刪除。

## Repository layout

```text
agent-repo-context-reducer/
├── repo_context/
│   ├── scanner.py
│   ├── parsers.py
│   ├── graph.py
│   ├── ranking.py
│   ├── context_planner.py
│   ├── handoff.py
│   ├── fan_in.py
│   ├── contradiction.py
│   ├── synthesis_packet.py
│   ├── artifact_store.py
│   ├── capabilities.py
│   ├── orchestration.py
│   └── ...
├── scripts/
├── tests/
├── examples/
├── references/
├── adapters/
├── .claude/
├── .github/
├── SKILL.md
├── pyproject.toml
└── package.json
```

## 安全性與限制

- Static graph 不是 runtime call graph。
- Heuristic parser 不是完整 compiler frontend。
- Local knowledge search 是 deterministic lexical fallback，不是 GraphRAG。
- `confidence` 是 Worker metadata，不是真實機率。
- Token estimate 是 bytes/4 approximation。
- Fan-In 不替 final model 判斷 contradiction 哪一方正確。
- Harness Planner 不會自動 spawn external Agent。
- Unknown external commands 不會因為被偵測到就自動執行。

## License

MIT
