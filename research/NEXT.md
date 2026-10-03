# 续接记录（2026-10-03）

- 分支：`research/hs300-validation-2026-10-02`。数据和代码位于 `work/qr-factor-lab`；本地 `data/`、`deps/` 被 Git 忽略。不要读取、输出或提交 `GM_TOKEN`。
- 数据：掘金 2020-01 至 2026-09 沪深300历史动态成分、原价日线、成交额、复权因子、涨跌停/停牌元数据与换手率均已采集 81 个月。490,800 个成分股日位置中 584 个缺日线，全部标记停牌。逐月哈希和覆盖在 [`gm_snapshot_audit.json`](../results/gm_snapshot_audit.json)。财报披露日只做过单点查询，ST 与复权修订史未核实。
- 已试并拒绝：WorldQuant Alpha 101，方正日间波动翻转及完整“球队硬币”，国君 Alpha1。原式、参数网格、逐年 IC、乐观扣费筛查及问题见 [`iteration_2026_10_03.md`](iteration_2026_10_03.md)。完整“球队硬币”20 日窗口 2025 年 IC 变正，2023/2025 扣费月均超额为负；2026 均值受 2 个极端月主导，不能报可用。
- 下一步：从原文核验另一组券商或论文因子，先登记公式及有限参数网格，再按相同日期和股票池做 IC、简单基准增量、逐年稳定性检查。通过后再建真实成交状态机、行业/市值暴露、ST、成本敏感性与容量检查。旧候选不要根据已看过的 2020—2026 年结果反复调参。真正的前向确认需要 2026-10 以后新数据。
- 运行检查：`$env:PYTHONPATH=(Resolve-Path .\src).Path; python -m unittest discover -s tests -q`，`python -m compileall -q src research`，`git diff --check`。掘金 SDK 在忽略的 `deps/`，需要时设置 `$env:PYTHONPATH=(Resolve-Path .\deps).Path`。SDK 的只读接口和失败记录见 [`gm_access_2026_10_03.md`](gm_access_2026_10_03.md)。
