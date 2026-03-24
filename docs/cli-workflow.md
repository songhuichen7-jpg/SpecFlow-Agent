# CLI 工作流

本文档说明 `SpecFlow-Agent v1` 的命令行使用方式。

## 安装与目录约定

推荐直接安装 CLI：

```bash
uv tool install git+https://github.com/<owner>/specflow-agent.git
```

安装完成后可直接使用 `specflow` 命令。

默认情况下，运行输出会写入你执行命令时所在目录：

- `runs/`
- `.specflow/`

如果需要改变默认位置，可通过环境变量显式指定：

- `SPECFLOW_WORKSPACE_ROOT`
- `SPECFLOW_DATA_ROOT`
- `SPECFLOW_DATABASE_URL`

## 支持的命令

```bash
specflow run "需求描述"
specflow run "需求描述" --template ticket-system --mode debug
specflow status <run_id>
specflow artifacts <run_id>
specflow resume <run_id>
specflow resume <run_id> --approve
specflow resume <run_id> --reject
```

## 模板范围

`v1` 当前只支持：

- `ticket-system`

其他模板值会被明确拒绝，这是当前版本的产品边界，而不是运行时异常。

## 标准模式

`standard` 模式会在人工闸门节点暂停，例如：

- `freeze_spec`
- `deliver`
- 评审修复预算耗尽后的人工仲裁节点

典型流程如下：

1. 执行 `specflow run "需求描述"`
2. 记录返回的 `run_id`
3. 用 `specflow status <run_id>` 查看当前状态
4. 在有待审批节点时，用 `specflow resume <run_id> --approve` 或 `--reject` 继续

## 调试模式

`debug` 模式会自动绕过人工闸门，适合：

- 本地冒烟测试
- CI 风格验证
- 端到端链路自检

示例：

```bash
specflow run "帮我做一个内部工单管理系统" --mode debug
```

## 工件预期

一次成功运行通常至少会生成以下最新工件：

- `spec.md`
- `plan.md`
- `tasks.md`
- `data-model.md`
- `contracts/openapi.yaml`
- `quality-report.json`
- `review-report.md`

代码工作区位于：

- `runs/<run_id>/workspace/`

报告和规格工件位于当前工作目录下，该运行目录对应的工件与报告子目录中。

## 推荐排障步骤

当运行结果不符合预期时，建议按以下顺序检查：

1. `specflow doctor`
2. `specflow status <run_id>`
3. `specflow artifacts <run_id>`
4. 查看 `quality-report.json`
5. 查看 `review-report.md`
