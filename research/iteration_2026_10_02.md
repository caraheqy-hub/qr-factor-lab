# 2026-10-02：扩大样本后的因子挖掘迭代

## 结论

本轮**没有发现可用因子**。F17 成交量异常比率在沪深 300 历史成分样本中整体预测力接近零；F08 日内收益反向排序虽有短期毛收益，但日换手使扣费超额每年均为负；月度低波动与低市净率在 2025 年都显著跑输同池等权，2026 年前 8 个可评价月也为负。所有结果属于探索性历史诊断，不构成实盘信号。

## 从原始研究与实务检验学到的规则

| 原始来源 | 与本项目相关的经验 | 落地动作 |
| --- | --- | --- |
| [Harvey、Liu、Zhu，2016](https://www.nber.org/papers/w20592)；[Novy-Marx，2015](https://www.nber.org/papers/w21329) | 大量尝试后只报告赢家会高估因子有效性；多信号组合也容易过拟合 | 记录所有试验及失败；新参数和组合不得使用已看过的时期作盲测 |
| [McLean、Pontiff，2016](https://www.onlinelibrary.wiley.com/doi/full/10.1111/jofi.12365) | 因子在原样本外、发表后的预测力可能下降 | 研报发表日期与我们的首次观察日期分别记录；用后续数据或前瞻观察复核 |
| [Anomalies in the China A-share Market](https://doi.org/10.1016/j.pacfin.2021.101607)；[Li 等，2023](https://ir.pku.edu.cn/handle/20.500.11897/693234) | 等权小盘股票、交易成本和换手会显著影响 A 股异象判断 | 本轮先换成历史沪深 300 成分；同时报告 IC 与扣费多头相对同池等权 |
| [The Volatility Effect in China](https://link.springer.com/article/10.1057/s41260-021-00218-0) | 低风险是有依据的候选，但原文是月度构建、过去三年月收益波动率等口径 | 本轮 60/252 日日收益波动率只是**改编实验**，不能声称复现原文 |
| [Qlib Alpha158 源码](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py) | 公式必须核对符号、窗口和数据字段 | F08、F17 保持项目现有公式，另将 F08 倒向做多明确标记为本轮决策 |

## 数据与时间线

- [BaoStock](https://baostock.com/) 0.9.4；2019-12-31 至 2026-09-30 的 82 个月末沪深 300 成分快照，共 493 个曾入选代码；2019-01-01 至 2026-09-30 的日线与市净率各 882,599 行。分析日按**当日或更早的最近一次月末快照**确定股票池。原始数据保留本地，不随仓库发布；哈希、行数与下载时间见 [`data_manifest.json`](../results/hs300_validation_2020_2026/data_manifest.json)。
- 日线信号在 T 日收盘后形成，1 日收益为 T+1 开盘至 T+2 开盘，5 日收益为 T+1 至 T+6 开盘。月度组合在月末收盘后排序，下月首日开盘买入，再下月首日开盘评价；用同一信号日的有效沪深 300 成分等权作对照。月度年度汇总按**买入年份**归属，避免跨年持仓错位。
- 过滤信号日 `tradestatus != 1` 与 `isST != 0`；缺少选中股票的未来执行价时，组合跳过该期并记录。日线 IC 仅使用同时有因子与标签的股票，覆盖率见 CSV。
- 价格是 BaoStock `adjustflag=2` 的**下载时回溯前复权**。成分仅月末查询，PB 历史修订及财报实际披露时点未独立审计；没有逐笔成交、涨跌停买入可行性、冲击成本、真实持仓停牌延续。即使组合表面上盈利，也不能据此判定可交易。

## 全部本轮试验

| 试验 | 公式与方向 | 主要观察 | 判定 |
| --- | --- | --- | --- |
| F17，1/5 日 | `Mean(volume,20)/volume_t`，高值做多方向 | 2020—2026 全期平均 Rank IC：1 日 **+0.0062**、5 日 **+0.0005**；2022—2023 两个持有期均为负 | 预测方向不稳定，拒绝 |
| F08 倒向，1 日 | `-(close-open)/open`，前 20% 等权，日调仓 | 1 日 Rank IC 按原式为 **-0.0279**；倒向组合毛超额有波动，但换手约 1.55—1.62 倍/日，按每单位成交额 15 基点计费后，**2020—2026 每年净超额都为负** | 成本不通过，拒绝 |
| 低波动，月度 | 过去 60/252 日日收益标准差负向，前 20% 等权 | 2024 年净超额约 **+111/+87 基点每月**，2025 年转为 **-132/-141 基点每月**，2026 年前 8 个可评价月仍为负 | 年份不稳，拒绝 |
| 低 PB，月度 | `-PB_MRQ`，PB>0，前 20% 等权 | 2021—2024 年正超额，2025 年转为约 **-95 基点每月**，2026 年前 8 个月约 **-34 基点每月** | 年份不稳且 PB 点时未核，拒绝 |

源数字和所有年份见 [`ic_summary.csv`](../results/hs300_validation_2020_2026/ic_summary.csv)、[`f08_portfolio_summary.csv`](../results/hs300_validation_2020_2026/f08_portfolio_summary.csv)、[`monthly_lowvol_summary.csv`](../results/hs300_validation_2020_2026/monthly_lowvol_summary.csv)、[`monthly_value_summary.csv`](../results/hs300_validation_2020_2026/monthly_value_summary.csv)。逐日文件本地生成，不提交。2019 年只有一个月末快照，仅用于建立 2020 年起的股票池与滚动窗口。

在仓库根目录复现本轮数据与结果（数据接口可能改变历史快照，因此先核对哈希）：

```powershell
python -m pip install -e ".[bao]"
python research/snapshot/fetch_bao_prices.py
python research/snapshot/fetch_bao_pb.py
python research/snapshot/write_manifest.py
python research/validate_f17_hs300.py --bars data/bao_hs300_2019_2026.csv --members data/bao_hs300_monthly_members.csv --output results/hs300_validation_2020_2026
python research/diagnose_f08_portfolio.py --bars data/bao_hs300_2019_2026.csv --members data/bao_hs300_monthly_members.csv --output results/hs300_validation_2020_2026
python research/monthly_lowvol.py --bars data/bao_hs300_2019_2026.csv --members data/bao_hs300_monthly_members.csv --output results/hs300_validation_2020_2026
python research/monthly_value.py --bars data/bao_hs300_2019_2026.csv --pb data/bao_hs300_pb_2019_2026.csv --members data/bao_hs300_monthly_members.csv --output results/hs300_validation_2020_2026
```

## 试验账本与下一轮门槛

这轮已看过 2020—2026 全部年度结果，包括原仓库已经看过的 2025/2026 小样本。它们**全部是已见数据**，不能再挑其中一段当盲测。F17、F08、低波动 60/252 日、低 PB 共 5 个信号定义；F17/F08 各检查 1 日与 5 日两个标签，低波动检查两个窗口。本轮没有依结果调优窗口或费用。

下一轮先解决以下顺序，随后再谈“可用”：

1. 用真正按公布时点保存的股票池、复权因子与财报/估值快照，核对信号日可见的信息；优先有授权的历史数据库。PB 在没有财报披露时间前只保留为线索。
2. 预先登记新候选的经济机制、公式、方向、样本期、参数范围、费用、评价指标、淘汰标准。新来源不能把已看过的 2020—2026 年当独立验证。
3. 同池同日比较 Rank IC、分位单调性、现有风格暴露和增量信息；之后测真实多头组合的停牌、涨跌停、流动性容量、换手和至少两档成本。
4. 候选只有在未参与选择的后来数据中仍有稳定方向、扣费后相对同池基准的正收益，且有容量与执行证据时才标成“可用”；在此之前状态维持 `待独立验证` 或 `拒绝`。
