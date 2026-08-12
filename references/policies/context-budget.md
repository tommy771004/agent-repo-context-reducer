# Policy: Context Budget

The context budget limits what the gateway returns before reasoning.

- Default: 6000 estimated tokens.
- Estimation: UTF-8 bytes / 4; approximate only.
- Spend a minority of the budget on project/file structure and the rest on task-relevant symbols.
- Do not fill the budget merely because capacity remains.
- If a useful symbol does not fit, prefer its signature/structure and request it explicitly later.
- A larger model context window is not a reason to increase the budget automatically.
