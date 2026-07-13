# Security Policy

## 报告漏洞

发现安全问题请通过 GitHub [Private vulnerability reporting](https://github.com/R-jed/Subtap/security/advisories/new) 提交。

**不要**通过公开 Issue 报告安全漏洞。

## 响应时间

- 确认收到：48 小时内
- 初步评估：7 天内
- 修复发布：根据严重程度，30 天内

## 适用范围

Subtap 是本地优先的 CLI 工具，不涉及网络服务。以下属于安全关切：

- 模型文件下载过程中的供应链攻击（SHA256 校验绕过）
- 本地文件路径穿越（如 `--output` 参数注入 `../`）
- 热词/配置文件的代码注入
- 依赖链中的已知漏洞

## 不适用

- 本地模型推理结果的准确性问题
- 非最新版本的问题（请先升级）
- 需要物理访问本地机器的攻击场景

## 致谢

感谢负责任地披露安全问题的研究人员。
