# 贡献指南

感谢你对 Subtap 的关注。

## 开发环境

```bash
git clone https://github.com/<your-org>/subtap.git
cd subtap
uv sync --extra dev
```

## 运行测试

```bash
pytest
```

## 代码规范

- 格式化：`ruff format`
- Lint：`ruff check`
- 类型检查：`mypy src/`

## 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
feat(scope): 新增功能
fix(scope): 修复问题
docs(scope): 文档变更
refactor(scope): 重构
test(scope): 测试相关
chore(scope): 构建/工具链
```

## Pull Request

1. Fork 本仓库
2. 从 `main` 创建功能分支
3. 确保 `pytest` 通过
4. 提交 PR 并描述变更内容
