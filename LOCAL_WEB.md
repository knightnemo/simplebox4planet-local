# SimpleBox4Planet 本地网页

双击 `启动本地网页.command`，浏览器访问 http://127.0.0.1:8765。
双击 `停止本地网页.command` 停止本启动器开启的后台服务。

本地网页具备稳态、动态、归趋因子、物质比较、敏感性情景表五组功能，以及完整参数编辑、CSV 导入、CSV/Excel/JSON 导出与情景保存/加载。
这是独立实现，**尚未认证与官方服务完全一致**。详细方法、单位、上游问题与差异可在 `/guide` 查看。

## 环境与启动

当前电脑已安装依赖，服务不需要 Excel、云端账号或 API Key。

```sh
.venv/bin/python server.py
```

迁移到其他电脑：安装 Python 3.14 和 LibreOffice，然后：

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python server.py
```

若 LibreOffice 不在 PATH，设置 `SOFFICE=/path/to/soffice`。
本机也会自动探测已安装的 Codex LibreOffice runtime。可通过 `--port 8766` 更改端口（双击启动器默认固定为 8765）。

## 计算过程

1. `web/catalog.py` 从公开工作簿读取 3,993 种 PFAS + 默认物质、19 个环境情景，映射官方页面的 79 个数值输入。
2. `web/model.py` 在临时目录复制工作簿，以 XML 定点写入输入，保留其他公式/图形结构，并清除公式缓存以强制重算。
3. 本地 LibreOffice 无界面重算工作簿。读取 33×33 传输矩阵 K、排放 E、体积与分子量，用 NumPy 求解稳态质量，检查质量守恒。
4. 动态模型使用 SciPy 矩阵指数求解 `dM/dt=KM+E`；归趋因子为 `-inverse(K)/86400`，单位 day。
5. 所有情景保存在 `runtime/cache`，日志保存在 `runtime/server.log`。原始仓库和 `local/SimpleBox4Planet.xlsx` 均不修改。

## 已知差异

- 官方网页后端未公开，UI 和计算扩展为本地重新实现；未完成对其所有结果/算法/默认值的逐项对照。
- 本地修复上游 `engine!E5,N5` 的湖水排放断开问题，将其连接到 `E.w0R,E.w0C`。
- 工作簿原有辅助错误保留。默认 `engine` 两处 `#DIV/0!`、`formulas` 121 处 `#NAME?`。这些辅助错误不用于质量矩阵求解。
- 部分 PFAS 原始数据不完整，类别文本也可能不符合模型枚举；遵循原模型回退/估算规则，未伪造数据或重写科学假设。
- 库中为 3,993 条 PFAS 记录加默认物质，共 3,980 个唯一名称。重复名称按 Excel VLOOKUP 行为匹配第一条，未把重复记录视作额外独立物质。
- 动态默认初始质量为 0，恒定排放，201 个时间点。网页未提供任意时变排放。
- 比较和敏感性一次上限 50 行。无效情景明确显示错误。
- 输入校验允许负 pKa 和低温；面积比例容许 1% 舍入差异，以兼容原始环境预设。
- 本地页面默认恢复按钮恢复初始配置；界面经过重新排版，并非官方页面的像素复刻。

## 测试

```sh
uv pip install --python .venv/bin/python pytest
.venv/bin/python -m pytest -q
```

模型测试比较 33 箱体默认值与 Excel 缓存基准，并验证 Excel 中实测的排放变更与 PFBA 数值、湖水修复、零排放、动态极限、归趋因子重建、输入校验和未授权单元格不被修改。
HTTP 测试涵盖五种模式、批量部分失败、CSV/Excel/JSON/完整模型下载与同源限制。

原始模型来源：https://github.com/NovaMechanicsOpenSource/SimpleBox4Planet
提交：`297dfacb633afc8140760b754360b3ff5a7d83c6`。模型许可见 `SimpleBox4Planet/LICENSE`。
