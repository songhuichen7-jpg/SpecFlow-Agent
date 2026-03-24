# 贡献指南

本文档面向后续继续维护 `SpecFlow-Agent` 的开发者。

## 本地开发准备

```bash
uv sync --group dev
uv run specflow doctor
```

CLI 在本地运行时会自动初始化默认 SQLite 运行库。
如果你需要验证迁移链路，再额外执行：

```bash
uv run alembic upgrade head
```

如果需要启用模型能力，请额外准备本地 `.env`：

```bash
cp .env.example .env
```

如果你希望在开发仓库里模拟“安装后直接输入 `specflow`”的体验，可以执行：

```bash
uv tool install --force --editable .
specflow version
```

## 日常开发检查

提交前建议至少执行：

```bash
uv run black --check .
uv run ruff check .
uv run mypy src tests
uv run pytest
```

## 开发约定

- 优先通过持久化工件推进 Agent 协作，而不是依赖隐式对话上下文
- 影响 CLI、编排层、工件格式或状态机的修改，必须补测试
- 测试应保持确定性，避免依赖真实线上模型结果作为断言
- 本地真实 `.env` 不应影响测试，测试应显式隔离运行环境
- 不要提交 `.env`、`runs/`、`.specflow/` 等运行态产物
- 不要使用破坏性 Git 操作去覆盖他人改动

## 文档维护约定

- `README.md` 面向外部使用者，重点写清楚：是什么、怎么跑、当前支持范围
- `docs/` 面向实现说明、架构细节和发布信息
- 当实现边界发生变化时，优先同步更新 README 和相关 docs
- 若当前实现与设计文档不完全一致，应在文档中明确“当前版本范围”和“未来规划”区别

## 当前版本边界

为避免误导，当前 `v1` 请默认遵守以下边界：

- 仅支持 `ticket-system` 模板
- Web UI 与平台化能力不在当前版本范围内
- 多模板平台、多用户权限、组织级记忆属于后续阶段能力
