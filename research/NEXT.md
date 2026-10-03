# 续接记录（2026-10-03）

- 当前分支：`research/hs300-validation-2026-10-02`；首轮提交 `959635651122fca1f3bf54663b32ac1fab5fb0a0`，已推送到 origin。`main` 未改动。GitHub 集成创建草稿 PR 返回 403；独立分支可直接审阅。
- 本轮结论：**没有可用因子**。完整数据、公式、结果与限制见 [`iteration_2026_10_02.md`](iteration_2026_10_02.md)。BaoStock 原始数据位于本地 `data/` 且被 Git 忽略；哈希与行数见 [`data_manifest.json`](../results/hs300_validation_2020_2026/data_manifest.json)。
- 测试：`$env:PYTHONPATH=(Resolve-Path .\src).Path; python -m unittest discover -s tests -q`，7 个测试通过；`python -m compileall -q src research` 和 `git diff --check` 通过。
- 用户已说明本机安装掘金，并希望用它继续数据与回测；当前会话环境曾检查 `GM_TOKEN=False`、`gm` Python 模块不可导入。这不代表掘金未安装，可能只是当前 Python 环境未连接。不要要求或记录密钥。
- 下一步：核对本机掘金 SDK/运行 Python、版本和账户可访问字段；只用历史查询做一组小范围探针，先验证历史成分、复权、财务实际披露/修订、停牌/ST、涨跌停与成交额。官方入口为 <https://www.myquant.cn/docs/python/python_overview>，具体函数以当前官方文档和本机返回值为准。
- 2026-10-03 更新：`GM_TOKEN` 已在当前进程可读；`gm==3.0.187` 与 `protobuf==3.20.3` 装于忽略的 `deps/`。历史日线、当日沪深300成分、历史涨跌停/复权/停牌元数据、含 `pub_date` 的财报截面探针均成功；详情见 [`gm_access_2026_10_03.md`](gm_access_2026_10_03.md)。下一步为长期覆盖和字段语义审计，不能因小样本可查询就宣称已具备可交易回测。
- 若这些点时字段缺失，继续把公开数据结果标为探索性；若齐全，再**预先登记新候选**、未见评价期和费用/成交规则，随后回测。不要把已看过的 2020—2026 结果重新称作盲测，也不要根据这些时期再优化 F17/F08/低波动/低 PB。
