# v1 发布说明

版本：`v1.0.0`  
状态：已完成开发并通过测试  
最后更新：`2026-03-24`

## 1. 发布结论

当前仓库已完成 `v1` 范围交付，可以作为首个可运行版本发布到 GitHub。

本版本已经具备：

- 端到端运行链路
- 多阶段工件化协作
- CLI 入口
- 人工闸门与恢复执行
- 基础质量检查与评审闭环
- OpenRouter 模型接入

## 2. 当前实现范围

`v1` 当前实际落地范围为：

- 单模板：`ticket-system`
- 单仓库、本地运行模式
- CLI 驱动的完整流水线
- 基于工件的 Architect / Coder / Reviewer 协作

## 3. 当前未纳入范围

以下能力未纳入本次 `v1` 发布：

- Web UI
- 多用户与权限体系
- 多模板平台化
- 组织级长期记忆
- Brownfield 改造能力

## 4. 验证结果

发布前已完成以下验证：

```bash
uv run black --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
uv tool install --force .
specflow doctor
```

最近一次全量测试结果：

- `43 passed`

## 5. 发布前检查清单

推送到 GitHub 前建议再次确认：

- `.env` 未提交
- `runs/` 未提交
- `.specflow/` 未提交
- `uv.lock`、`pyproject.toml`、`README.md` 已同步
- `README.md` 中的范围说明与当前实现一致

## 6. 版本边界说明

为避免误解，建议在仓库首页和后续发布说明中保持以下表述：

- “当前版本已完成 v1 范围”
- “当前仅支持 `ticket-system` 模板”
- “Web UI 和多模板能力属于后续阶段”
