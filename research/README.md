# 因子线索库

扩大样本及重点候选的记录见[2026-10-02 迭代](iteration_2026_10_02.md)、[2026-10-03 掘金试验](iteration_2026_10_03.md)和[2026-10-04 Alpha5 深挖](iteration_2026_10_04.md)。F17、F08 倒向、低波动、低 PB、WorldQuant Alpha 101、方正日间波动翻转及完整“球队硬币”、方正现金流质量的股票迁移、国君 Alpha1/Alpha5、总资产增长率迁移均未通过当前可用性门槛。

这是一份**研究待办清单**，不是“有效因子库”。截至 2026-10-04，已登记 30 份报告/论文和 43 条因子线索。`report_index.csv` 记报告与可访问程度；`factor_catalog.csv` 记可核实公式、数据缺口与进度。报告只有摘要或题录时，只能提研究想法，不能标成完整复现。

当前判定方法的[失败复盘与改进流程](evaluation_v2.md)明确区分信号、乐观扣费、完整历史成交和冻结后的前向验证。[统一试验账本](../results/trial_store/records.jsonl)收录现有 42 个结果文件的 5,470 条结构化记录；以后通过 `python research\trial_store.py run research\脚本名.py` 运行研究脚本，保存运行事件与变更过的派生结果。掘金 SDK 的[权限与连接故障](sdk_debug_2026_10_04.md)另有记录。

## 来源怎么用

- 原始券商 PDF 优先；第三方托管的带券商品牌 PDF 要核对封面、日期、作者和页码。付费站摘要只用于发现报告，不补写看不到的公式。
- [Qlib Alpha158 源码](https://github.com/microsoft/qlib/blob/main/qlib/contrib/data/loader.py)提供一批可逐行核对的公开公式；其在 A 股使用的 T+1/T+2 标签见[数据文档](https://github.com/microsoft/qlib/blob/main/docs/component/data.rst)。本项目保留了下一开盘进、再下一开盘出的时间线。
- [聚宽官方因子分析工具](https://github.com/JoinQuant/jqfactor_analyzer)和[聚宽数据 SDK](https://github.com/JoinQuant/jqdatasdk)可作社区/平台因子库线索，访问因子数据要另有账号与权限；目前项目不依赖它们。[BigQuant 因子平台](https://bigquant.com/wiki/doc/EOVmVtJMS5)同样只列为线索，不自动安装或混用数据口径。
- [101 Formulaic Alphas 原论文](https://arxiv.org/abs/1601.00991)给出大量公式，但其原市场、频率与持有期不等于 A 股可交易策略。[上交所实际披露日](https://www.sse.com.cn/disclosure/listedinfo/periodic/)用于财务因子时点核验。

## 本次筛查

`python -m qr_factor_lab.factor_screen --input data/gm_a_share_2025.csv --output results/bulk_screen_2025`，对 11 条有真实日线字段的候选做统一日期的逐日 Rank IC 筛查；另对 `data/gm_tech_2026.csv` 做同样筛查。两份数据的样本股票池不同，不能把年份差异解释成因子衰减。因子用当天收盘已知字段计算，标签为 T+1 开盘至 T+2 开盘收益。

| 因子 | 2025 小样本 Rank IC | 2026 静态科技池 Rank IC | 判断 |
| --- | ---: | ---: | --- |
| F17 20日均量/当日量 | +0.0442 | +0.0109 | 同向但幅度明显变化；需要新的历史股票池和交易成本测试 |
| F08 日内实体比例 | -0.0596 | +0.0205 | 方向翻转，不能直接使用 |
| F01 低20日均量 | -0.0153 | +0.0042 | 当前两个小样本不稳定；此前专项报告已有更详细测试 |

其余完整结果见 `results/bulk_screen_2025/screen_summary.csv` 和 `results/bulk_screen_2026_tech/screen_summary.csv`，包括 F09/10/11/12/14/15/18/19；每组 `manifest.json` 记录输入哈希、日期与标签口径。11 项都记录了，未把最大 IC 条目当“发现新 alpha”。两组都是方便演示的静态小样本；复权数据在获取时回顾性调整，未建历史动态股票池、涨跌停可成交性、市场冲击、费用或容量。筛查包含已发表报告的历史，不是独立盲测。下一步优先取得有实际披露日、历史成分和成交约束的数据，再作同池、同日期、分期验证。

## 先做什么

1. 对 R02/R03 的附录逐页确认具体公式并建立风格对照组；不要因为写了“48 个细分因子”就把 48 个当已复现。
2. 为 F17 做更大且按当时可投资条件生成的股票池，比较 F01、普通流动性/市值暴露和费用后的增量信息。
3. 若取得带实际披露时间的财务快照，再开展盈利、现金流、估值、成长因子；没有时点数据时不做“PIT 已验证”声明。
4. 高频研报、行业轮动和 A/H 择时各需独立数据工程，暂不塞进日线选股框架。
