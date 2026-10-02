# QR 因子研究小框架

这是一个先求**能跑通、能看懂、能复现**的 A 股因子研究起点。基础实验计算动量和低波动两个示例因子，检查每天的截面 Rank IC，再做扣除交易成本的简易多头回测。另有 11 条公开公式的探索性批量筛查。它不会发出真实委托。

## 现在能做什么

1. 从掘金 `gm.api` 下载指定股票的日线，保存成 CSV，同时记录来源和下载时间。以后也可以把同格式的 CSV 放进来，不必绑定掘金。
2. 每天收盘后算因子；假设**下一交易日开盘**买入，再持有到再下一交易日开盘。这样不会拿当天收盘才知道的信号去赚当天收益。
3. 输出发现期和留出期的 IC、收益、波动、回撤和换手。改参数时先看发现期，留出期用于最后检验。

这里的分工很简单：Python 代码负责因子计算、回测和留存实验结果；掘金接口只负责取历史行情；Agent 负责找研报原文、核实公式和数据可得时间，再决定怎样实现。已安装的官方 Jupyter skill 只在需要交互检查数据时辅助使用，不是运行框架的依赖。

已完成的一次真实数据试跑及其局限见 [实验记录](experiment_report.md)。公开仓库只附汇总统计与方法记录；逐日衍生数据和原始行情保留在本地。用自己的授权数据重跑后，程序会在本地生成逐日文件。

另有一项 [华福证券研报单因子复现与调参记录](reports/huafu_2026_03_10.md)：用报告发布后的 2026 年行情检验“20 日平均成交量”这一项可核实的公式。它明确记录了与原报告股票池、调仓频率和组合模型的差别。

[因子线索库](research/README.md)登记了 19 份券商报告、34 条候选以及哪些公式和数据尚未核实。批量筛查仅使用现有快照支持的 11 条日线公式，包含全部候选的结果，没有宣称找到了可交易的新因子。

## 先跑通公开版

公开仓库不附带掘金原始行情。先用固定随机种子的**合成数据**走通完整流程。安装项目所需的 NumPy 和 pandas 后，在项目目录运行：

```powershell
python -m pip install -e .
python -m qr_factor_lab.cli demo-data --output data\demo.csv
python -m qr_factor_lab.cli analyze --input data\demo.csv `
  --output results\demo --split-date 2025-04-01
```

运行后打开 `results\demo\summary.json` 看总结果，打开 `*_daily.csv` 看逐日收益与持仓。合成数据只能验证程序能跑，**不能说明因子有收益能力**。`python` 应指向你准备使用的同一个 Python 3.11+ 环境；若使用 Conda，先激活环境。你可以改变 `--momentum-window`、`--momentum-skip`、`--volatility-window` 和 `--cost-bps`；每次换一个输出目录，保留实验记录。

若你有自己的真实行情 CSV，把它放在 `data/`（或使用其他路径），列名需为 `date,symbol,open,close,volume`；日期格式为 `YYYY-MM-DD`，每只股票每个交易日一行。下文的真实行情文件名是本地实验所用的例子，公开仓库里没有这些文件。

如果要试一小组动量参数，用下面的命令。程序只用 **7 月前已完成的收益**挑参数，选定后才计算 7 月起的留出期；`discovery_trials.csv` 留下所有尝试，`selection.json` 记录选中方案和留出期结果。

```powershell
python -m qr_factor_lab.cli sweep `
  --input data\gm_a_share_2025.csv --output results\momentum_sweep `
  --split-date 2025-07-01 --windows 20,40 --skips 5,10
```

## 自己更新掘金数据

先在**当前 PowerShell 窗口**设置 `GM_TOKEN`。它是私密凭证，不要写进代码、README 或提交到 GitHub。然后运行：

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
python -m pip install -e ".[gm]"
python -m qr_factor_lab.cli fetch-gm `
  --symbols symbols.txt --start 2025-01-01 --end 2025-12-31 `
  --output data\my_snapshot.csv
```

下载命令只调用历史行情查询，不会运行策略或下单。原始 CSV 和旁边的 `.source.json` 请一起保存。代码格式检查可运行：

```powershell
python -m unittest discover -s tests
```

## 怎样用它复现研报

先填 [研报复现记录模板](research_template.md)，写清报告发布日期、原始公式、股票池、数据可得时间和评价口径。再把新因子写成 `src/qr_factor_lab/research.py` 里的小函数，在 `cli.py` 增加对应实验入口和参数记录。**不要根据留出期表现反复挑参数**，否则留出期也变成了调参数据。

本次华福证券单因子实验可以这样重跑：

```powershell
python -m qr_factor_lab.cli report-volume `
  --input data\gm_tech_2026.csv --output results\huafu_volume_2026 `
  --split-date 2026-07-01 --windows 20,10,40
```

筛查其他公开公式：

```powershell
python -m qr_factor_lab.factor_screen `
  --input data\gm_a_share_2025.csv --output results\bulk_screen_2025
```

## 当前边界

- 附带股票池是今天选定的固定样本，存在幸存者偏差。结果仅用于验证研究流程，不可当作全 A 股策略绩效。
- `ADJUST_PREV` 价格是回溯调整后的历史快照。严谨的实盘可复现研究还需要按历史时点还原复权、股票池、停牌、涨跌停和退市。
- 简易回测按目标权重与固定成本计算，没有订单簿、冲击成本、涨跌停成交和真实容量模型。
- 发现期和留出期都短，因子数和股票数都少；这份结果不构成稳健的有效性证据。股票池内任何停牌造成的执行价缺失会直接报错，留待更完整的可交易性模型处理。
- 目前只有日线与少量可核对的量价公式；批量筛查没有组合交易成本模型，不能把 Rank IC 当净收益。财务因子的公告时间对齐、行业市值中性化、机器学习都留到有合适数据后再做。

掘金 API 的用法以[官方 Python SDK 文档](https://www.myquant.cn/docs2/sdk/python/)为准。

## 为什么保持这个小框架

动手前我比较了 [Qlib](https://github.com/microsoft/qlib)、[Alphalens](https://github.com/quantopian/alphalens) 和 [vectorbt](https://github.com/polakowo/vectorbt)。它们分别适合更完整的数据与模型工作流、因子分析图表和大量参数回测；当前任务只有一个可读的日线因子实验，所以先维持 pandas/NumPy 的短代码和 CSV/JSON 结果。需要全市场历史股票池、更多实验或机器学习时，再按具体缺口引入成熟工具。
