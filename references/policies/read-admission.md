# Policy: Read Admission

Whole-file reads are the exception for large files.

Before reading a large or low-relevance file, use `repo-context admit`.

Prefer:
1. graph metadata,
2. structural file summary,
3. one symbol body,
4. dependency neighborhood,
5. whole file only when the task requires cross-symbol semantics.

`admit` is advisory policy. An Agent Skill cannot technically block every built-in Read/Grep tool in every coding agent.
