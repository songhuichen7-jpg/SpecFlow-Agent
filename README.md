# SpecFlow-Agent

[![CI](https://github.com/songhuichen7-jpg/SpecFlow-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/songhuichen7-jpg/SpecFlow-Agent/actions/workflows/ci.yml)

SpecFlow-Agent 是一个“规格优先”的多阶段智能研发流水线。  
它接收一段相对模糊的业务需求，围绕冻结后的规格工件，依次完成需求澄清、规格生成、任务拆解、项目脚手架生成、质量检查、评审和交付。

当前仓库已经完成 `v1` 范围实现，并可作为一个可运行、可演示、可继续扩展的基础版本直接发布到 GitHub。

## 特性

- 规格优先：以 `spec.md`、`plan.md`、`tasks.md` 等工件作为协作真源
- 多阶段流水线：`Supervisor -> Architect -> Coder -> Reviewer -> Deliver`
- 可恢复执行：支持人工闸门、恢复执行和调试模式
- 工件化沉淀：规格、合同、数据模型、质量报告、评审报告全部可追踪
- 安装即用：安装后可直接执行 `specflow ...`
- 模型可接入：已支持 OpenRouter，用于 Architect 和 Reviewer 的模型增强

## 当前范围

`v1` 当前已包含：

- CLI 入口
- 运行状态管理、阶段推进、检查点与工件存储
- `Architect / Coder / Reviewer / Supervisor` 协作
- `ReviewFixLoop` 评审修复闭环
- MCP 工具层：脚手架、模板读取、工作区读写、质量工具、规格工具
- OpenRouter 配置与连通能力

当前明确边界：

- 仅支持 `ticket-system` 模板
- `Coder` 仍以确定性脚手架和模板生成为主
- `Reviewer` 的问题发现和阻断判定以规则为主，模型主要用于报告叙述增强
- Web UI、多模板平台化、多用户权限不在当前版本范围内

## 架构概览

```text
CLI
  -> Supervisor
    -> Architect
    -> Coder
    -> Reviewer
    -> ReviewFixLoop
  -> Artifact Repository / Run State / Workspace Sandbox
```

核心输出包括：

- `spec.md`
- `plan.md`
- `tasks.md`
- `data-model.md`
- `contracts/openapi.yaml`
- `quality-report.json`
- `review-report.md`

## 快速开始

### 1. 安装 CLI

```bash
uv tool install git+https://github.com/songhuichen7-jpg/SpecFlow-Agent.git
```

### 2. 在当前工作目录创建 `.env`

```env
SPECFLOW_LLM_PROVIDER=openrouter
SPECFLOW_LLM_MODEL=openai/gpt-4.1-mini
OPENROUTER_API_KEY=<your-key>
```

`specflow` 会从你执行命令的当前目录读取 `.env`，并把运行数据默认写入当前目录下的 `runs/` 与 `.specflow/`。

### 3. 检查运行环境

```bash
specflow doctor
```

### 4. 启动一次运行

```bash
specflow run "帮我做一个内部工单管理系统" --mode debug
```

## 模型配置

最少需要配置以下变量：

```env
SPECFLOW_LLM_PROVIDER=openrouter
SPECFLOW_LLM_MODEL=<openrouter-model-id>
OPENROUTER_API_KEY=<your-key>
```

配置完成后可再次执行：

```bash
specflow doctor
```

正常情况下会看到：

- `working_directory=...`
- `llm_provider=openrouter`
- `llm_model=...`
- `llm_ready=true`

注意：

- `.env` 需要放在你准备运行 `specflow` 的目录里
- `.env`、`runs/` 与 `.specflow/` 都不应提交
- 如果你是在本地开发仓库，`.env.example` 可作为参考模板

## 使用方式

### 标准模式

标准模式会在人工闸门节点暂停：

```bash
specflow run "帮我做一个内部工单管理系统"
specflow status <run_id>
specflow resume <run_id> --approve
specflow artifacts <run_id>
```

### 调试模式

调试模式会自动绕过人工闸门，适合本地冒烟验证：

```bash
specflow run "帮我做一个内部工单管理系统" --mode debug
```

### 模板参数

当前仅支持：

```bash
--template ticket-system
```

不支持的模板值会被 CLI 明确拒绝。

## 输出目录

默认情况下，`specflow` 会把运行输出写到你执行命令时所在目录。一次成功运行后，常见目录如下：

```text
runs/<run_id>/
  artifacts/
  reports/
  workspace/
```

其中：

- `workspace/` 保存生成的项目代码
- `artifacts/` 保存规格、计划、合同等工件
- `reports/` 保存质量报告和评审报告

本地运行态数据位于：

```text
.specflow/
```

## 项目状态

当前版本已完成 `v1` 范围开发，并通过完整回归验证。

最近一次验证包括：

- `uv run black --check .`
- `uv run ruff check .`
- `uv run mypy src tests`
- `uv run pytest`

安装态烟测已验证：

- `uv tool install --force .`
- 在新目录执行 `specflow doctor`
- 在新目录执行 `specflow run "帮我做一个内部工单管理系统" --mode debug`

最近一次全量测试结果：`43 passed`

## 文档

- [CLI 工作流](./docs/cli-workflow.md)
- [系统架构设计](./docs/system-architecture.md)
- [v1 发布说明](./docs/v1-release.md)

## 贡献

贡献方式请参考：

- [贡献指南](./CONTRIBUTING.md)
