# Changes Log

## 2026-03-19

### 本次修改

- 给项目里的每个 `.py` 文件补充了开头说明注释，尽量用量化新手更容易理解的语言解释文件职责和常见微调点
- 重写了 [README.md](README.md)，把它整理成偏“说明书”风格的工程文档
- 保留并说明了新旧两套结构的关系，方便你边学边迁移

### 重点新增说明

- 新架构主入口是 [main.py](main.py)
- 旧版扫描交易入口仍然是 [main/main_scan.py](main/main_scan.py) 和 [main/main_trade.py](main/main_trade.py)
- 推荐优先修改 [config/runtime.yaml](config/runtime.yaml) 和 [config/symbols.txt](config/symbols.txt)，不要一开始就频繁改策略核心逻辑

### 文档修正

- 按你的要求，把 Markdown 文档中的绝对路径链接统一改成了相对路径

### 备注

- 按你的要求，后续我每次做代码修改时都会同步更新这个文件
