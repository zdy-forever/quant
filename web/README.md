# Quant Local Workbench

这个目录是一个独立的本地前端工作台，不会改动仓库里原有的量化/交易代码。

## 能做什么

- 在浏览器里选择研究流程
- 勾选因子、策略和关键参数
- 通过本地桥接脚本调用现有 `main.py`
- 查看运行日志
- 浏览 `artifacts/reports` 里的 JSON / Markdown 报告

## 启动方式

建议在能运行量化项目依赖的 Python 环境里启动：

```bash
cd web
python server.py
```

Windows 新手更建议直接双击：

```text
web/start_workbench.bat
```

默认地址：

```text
http://127.0.0.1:8765
```

## 可选环境变量

- `QUANT_WEB_PORT`
- `QUANT_WEB_PYTHON`

如果不传 `QUANT_WEB_PYTHON`，脚本会优先尝试：

1. `C:\ProgramData\miniconda3\envs\quant\python.exe`
2. 当前启动 `server.py` 的 Python

## 说明

- 页面触发的研究任务，底层还是调用仓库根目录的 `main.py`
- 这个版本是本地单机工作台，不做登录、权限隔离或并发控制
- `deploy` 页面默认只保留 `dry-run`
