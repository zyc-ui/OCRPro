# UMIHOSHI / Seastar — 项目说明书

> **用途**：供 Claude 新会话快速建立上下文，在最少读取文件的情况下定位修改点。  
> **最后更新**：2026-05

---

## 1. 项目背景与业务场景

### 1.1 这是什么

**Seastar（内部代号 UMIHOSHI）** 是一款面向船舶供应行业的**询价报价匹配工具**，运行于 Windows 桌面。

核心使用场景：
- 供应商（SeaStar 公司）收到客户的询价单（RFQ），需要快速从内部价目表（FullList）中找到对应产品，并把价格回填给客户。
- 价目表包含 3000+ 条船用物料，每条对应多家竞争公司的价格列（共 8 家公司）。

### 1.2 用户操作流程

```
选择公司 → 获取询价（OCR截图 或 粘贴SevenSeas链接）
        → 点击"查询价格"（本地TF-IDF匹配 或 向量检索）
        → 查看结果表格 → 手动修正 → 导出/保存
        → [SevenSeas专用] Finish 回填价格到 RFQ 页面
```

### 1.3 两种主要工作模式

| 公司 | 获取询价方式 | 匹配方式 | 专有功能 |
|------|------------|---------|---------|
| 非 SevenSeas（SINWA SGP、Anchor Marine 等）| OCR 截图 | 本地 TF-IDF | 复制表格、保存 .eml |
| SevenSeas | 粘贴 RFQ 链接（URL/HTML）| 本地 TF-IDF **或** 向量检索（Voyage+Qdrant）| Finish 回填价格、保存结果 CSV |

---

## 2. 技术架构一览

```
┌─────────────────────────────────────────┐
│          pywebview 桌面窗口              │
│  ┌──────────────────────────────────┐   │
│  │      前端（HTML + Alpine.js）     │   │
│  │  index.html / main.js / grid.js  │   │
│  └────────────┬─────────────────────┘   │
│               │ JS↔Python bridge        │
│  ┌────────────▼─────────────────────┐   │
│  │          api.py                   │   │
│  │  （唯一的 JS 调用入口层）          │   │
│  └──┬──────────┬──────────┬─────────┘   │
│     │          │          │              │
│  database.py  matcher.py  vector_matcher.py
│  ocr_engine.py Rfq_quotation_tool.py    │
│  DatabaseUpdate.py  config.py           │
│               │                         │
│          SQLite (database_data.db)      │
└─────────────────────────────────────────┘
```

**技术栈**：Python 3.11 + pywebview (Qt backend) + Alpine.js + 原生 DOM 虚拟滚动表格 + SQLite + Voyage AI + Qdrant

---

## 3. 文件职责速查表

### 3.1 根目录 Python 文件

#### `app.py` — 启动入口
- 创建 pywebview 窗口，注入 `API` 对象
- 配置日志（写入 `app.log`）
- 选择 Qt 后端（Windows），设置窗口尺寸
- **改这里**：窗口大小、标题、devtools 开关
- **不要改**：业务逻辑

---

#### `config.py` — 全局配置单一来源 ⭐ 改字段时必读
- `FL_DB_COLS`（列表，长度34）：SQLite 中 FullList 表的字段名，**顺序必须与数据库一致**
- `FL_DISPLAY`（列表，长度34）：前端展示用的列名，与 `FL_DB_COLS` 一一对应
- `PRICE_COL_START_IDX = 22`：价格列从第22列开始
- `COMPANY_COL_START_IDX = 26`：公司价格列从第26列开始
- `FL_COMPANY_DISPLAY_TO_IDX`：公司显示名 → FL_DISPLAY 索引的映射字典
- `COMPANY_OPTIONS`：前端下拉选项列表（"Other" + 各公司名）
- `FL_COL_WIDTHS`：前端表格列宽字典
- `get_db_path()`：返回 SQLite 路径（兼容打包/开发）
- **高风险**：列顺序错乱会导致整表数据错位

---

#### `api.py` — 前后端桥接层 ⭐ 新增功能的主要入口
暴露给前端 JS 调用的所有方法，是业务流程的调度中心。

| 方法 | 功能 |
|------|------|
| `get_config()` | 返回公司列表、列宽、FL_DISPLAY、数据库状态 |
| `get_price_list(company)` | 读取完整价目表（根据公司选对应价格列） |
| `query_prices(items, company)` | 批量本地TF-IDF匹配，返回 {cols, rows} |
| `query_prices_vector(items, company)` | 批量向量检索匹配（SevenSeas专用），返回同格式 |
| `query_single(code, desc, qty, ...)` | 单条代码精确查询（编辑行后重查） |
| `parse_rfq(url)` | 解析 SevenSeas RFQ 页面，返回询价条目 |
| `fill_rfq_prices(url, prices)` | 把价格写入 RFQ HTML 并在浏览器打开 |
| `save_results_csv(cols, rows)` | 保存查询结果到 `Result/` 目录（CSV） |
| `start_ocr()` | 启动截图+OCR，结果通过 JS CustomEvent 回传 |
| `copy_html_to_clipboard(html)` | 把 HTML 表格写入 Windows 剪贴板 |
| `save_eml(html, plain)` | 保存 .eml 邮件文件 |
| `open_db_update()` | 打开文件选择器，导入 Excel 到数据库 |
| `global_search(keyword)` | 跨表关键词搜索（调试用） |

**关键设计原则**：
- `query_prices` 和 `query_prices_vector` 返回完全相同的 `{cols, rows}` 格式，前端无感切换
- 向量检索使用 `item["desc"]`（客户描述）作为输入，**不使用客户代码**
- 价格列格式统一为 `$数字`（两位小数）

---

#### `database.py` — 数据库访问层（DAL）
所有 SQLite 操作集中于此，其他模块禁止绕过直接访问数据库。

| 函数 | 功能 |
|------|------|
| `fetch_fulllist(company)` | 读取完整价目表，公司非空时只取该公司价格列，否则取 High/Medium |
| `check_fulllist_exists()` | 检查 FullList 表是否存在 |
| `query_product(code, ...)` | 按 IMPA → U8 → 模糊 的优先级查询单条 |
| `batch_query(items, company)` | 批量调用 query_product |
| `search_all_tables(keyword)` | 全库 LIKE 搜索（调试用） |
| `get_company_col_idx(company)` | 公司名 → FL_DISPLAY 索引 |

---

#### `matcher.py` — 本地 TF-IDF 三步描述匹配
- **Step 1**：从价目表"描述"列提取大类，TF-IDF 找最匹配大类，筛候选行
- **Step 2**：对候选行的"详情"列做参数词命中计数（命中越多越优先）
- **Step 3**：Step2 无结果时，用 TF-IDF 对"报价"列做兜底相似度匹配
- 入口：`find_best_matches(desc, db_rows, top_k, min_score)`
- 缓存：`clear_cache()` 在数据库更新后调用

---

#### `vector_matcher.py` — 向量检索引擎（Voyage AI + Qdrant）⭐ SevenSeas专用
**核心设计原则**：客户代码不可信，唯一检索依据是产品描述文本。

| 函数 | 说明 |
|------|------|
| `embed_query(text)` | 单条文本 → 1024维向量（Voyage AI voyage-large-2-instruct，input_type="query"）|
| `embed_batch(texts)` | 批量文本 → 向量列表（节省 API 调用次数） |
| `search_products(vector, top_k)` | 在 Qdrant 检索 Top-K 候选（collection: seastar_products） |
| `payload_to_fl_row(payload, score, company, ...)` | Qdrant payload → FL_DISPLAY 格式行字典 |
| `batch_match(items, company)` | 主入口：productItems 全量向量检索，返回 (cols, rows) |

**外部服务配置**（硬编码在文件中，如需更换在此修改）：
- Voyage API Key：`pa-pLABwunI04lpfDGg6cyOxmKZ32xymGCah_byZM7hRro`
- Qdrant URL：`https://5aa93a5a-2e9f-40e3-abf9-2cd7e7bd2afb.us-east-1-1.aws.cloud.qdrant.io`
- Qdrant Collection：`seastar_products`
- 置信度阈值：`SCORE_HIGH=0.92`，`SCORE_MEDIUM=0.80`

**Payload 字段映射**（Qdrant 文档字段名 → 含义）：
```
description    → 产品描述
details / offer → 详情 / 报价
internal_code  → U8代码
impa_code      → IMPA代码
price_sinwa / price_seven_seas / price_wrist / price_anchor
price_rms / price_fuji / price_conlash → 各公司价格
high_price / medium_price → 高档/中档价
```

**限流处理**：Voyage 429 错误时指数退避重试（最多5次，初始等待60s）

---

#### `ocr_engine.py` — OCR 引擎
- 全屏选区 UI 在独立 daemon 线程（避免阻塞 pywebview 主线程）
- OCR 完成后通过 `window.evaluate_js()` 触发 `ocr-result` 自定义事件回传前端
- Tesseract 路径解析优先级：环境变量 → 打包内嵌 → PATH
- `perform_ocr(left, top, right, bottom)` 是纯函数，可独立测试

---

#### `Rfq_quotation_tool.py` — RFQ 页面解析器
- 支持 URL（在线）和本地 HTML 文件路径两种输入
- 目标列：SevenSeas Code / Item Description / Req Qty / UOM
- 识别逻辑：找包含 sevenseas/description/qty/uom 关键词的表格
- `parse_rfq_url(source)` → `{"cols": [...], "rows": [[...], ...]}`

---

#### `DatabaseUpdate.py` — Excel → SQLite 导入工具
- 读取 Excel 第一行作为字段名，表名固定为 `FullList`（不跟文件名走）
- 全量替换：先 DROP 再 CREATE 再批量 INSERT（500行一批）
- 字段处理：None 转空，列名特殊字符替换为 `_`
- 提供 tkinter 独立窗口（`open_update_window(parent)`）和函数接口两种调用方式

---

#### `category_router.py` — 已废弃，保留兼容性
- 原有硬编码规则已移至 `matcher.py` 动态处理
- 始终返回 `"GENERAL"` 和全量行，不做实际过滤

---

#### `databaseCheck.py` — 调试工具
- 打印数据库路径、大小、所有表的字段与行数
- 仅用于开发/排查，不影响运行

---

### 3.2 前端文件（`frontend/`）

#### `frontend/index.html` — 页面骨架与所有样式
- Alpine.js `x-data="App()"` 绑定到整个 body
- 包含所有 CSS（内联 `<style>`），不依赖外部 CSS 框架（除 Tailwind CDN）
- 所有弹窗（Modal）结构在此定义
- **关键 CSS 约定**：
  - `#init-overlay`：启动遮罩，Alpine 初始化完成后淡出消除，防止 FOUC 和白屏闪烁
  - `.top-bar`：`transform: translateZ(0)` + `isolation: isolate` — 禁止 backdrop-filter 引发的 repaint 闪烁
  - `#queryGrid, #priceListGrid`：`overflow-anchor: none` — 防止虚拟滚动底部抖动
  - `.modal-overlay`：backdrop-filter 预设静态值，只对 opacity/background 做动画，避免弹窗闪烁
  - `btn-save`：紫色渐变按钮，仅 SevenSeas 模式显示

---

#### `frontend/js/main.js` — 应用状态与业务逻辑（Alpine.js 组件）

**关键状态字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `company` | string | 当前选择的公司名 |
| `productItems` | Array | 询价条目列表，每项 `{item_no, code, desc, qty, unit}` |
| `queryResults` | Array | 查询结果列表，每项为列名→值的字典 |
| `vectorMode` | bool | 是否启用向量检索（仅 SevenSeas） |
| `isVectorQuerying` | bool | 向量检索进行中标志 |
| `_rfqUrl` | string | 当前解析的 RFQ 链接（Finish 功能需要） |
| `_rfqHeaderMap` | object | 列名翻译映射（SevenSeas 模式下替换中文列头） |
| `_lastQueryAllCols` | Array | 最后一次查询的完整列名列表 |
| `vectorConfirmDlg.open` | bool | 关闭向量检索确认弹窗 |

**关键方法**：

| 方法 | 触发时机 | 说明 |
|------|---------|------|
| `init()` | 页面加载 | 获取配置、初始化表格、注册 watcher、移除启动遮罩 |
| `onVectorToggle()` | 点击向量检索 Toggle | OFF→ON：直接调向量查询；ON→OFF：弹确认弹窗 |
| `_runVectorQuery()` | 向量检索核心 | 调 `query_prices_vector`，全量替换 queryResults |
| `queryPrices()` | 本地查询 | 调 `query_prices`，全量替换 queryResults |
| `submitPasteLink()` | 确认粘贴链接 | 解析 RFQ → 更新 productItems → 按当前模式查询 |
| `saveResults()` | 点击保存结果 | 调 `save_results_csv`，保存到 Result 文件夹 |
| `finishRFQ()` | 点击 Finish | 提取价格列 → 调 `fill_rfq_prices` 回填到网页 |
| `_dismissOverlay()` | init 末尾 | 淡出启动遮罩 |

**i18n**：`_I18N.zh` / `_I18N.en` 两份翻译字典，`t(key)` / `tf(key, {n})` 取值。

---

#### `frontend/js/grid.js` — 虚拟滚动表格引擎

**核心机制**：
- 纯原生 DOM，无第三方依赖
- 虚拟滚动：只渲染可视区域 ±BUFFER(20) 行，上下用 spacer `<tr>` 补足高度
- `overflow-anchor: none` + `_lastSt` 状态缓存：防止 scrollTop 未变时重复渲染（消除底部抖动）
- `tbody.replaceChildren(frag)`：原子性 DOM 替换，减少 reflow 次数
- 列拖拽排序：mousedown → ghost 跟随 → mouseup 重建列序

**两个表格实例**：
- `queryGridApi`：价格查询结果表（`#queryGrid`）
- `priceListGridApi`：价目表（`#priceListGrid`）

**关键 API**（供 main.js 调用）：

| 函数 | 说明 |
|------|------|
| `createGrid(containerId, callbacks)` | 工厂函数，返回 gridApi 对象 |
| `updateQueryResultGrid(cols, rows, colWidths, visCols)` | 全量更新查询结果表 |
| `updateQueryGrid(rows, visCols)` | 仅更新行数据（列不变） |
| `updatePriceListGrid(cols, rows, colWidths)` | 全量更新价目表 |
| `searchPriceList(keywords)` | 高亮匹配行，返回匹配数 |
| `locatePriceList(keyword)` | 精确定位并滚动到目标行 |
| `nextPriceMatch() / prevPriceMatch()` | 上下翻页浏览匹配行 |

---

### 3.3 数据与资源文件

| 文件 | 说明 |
|------|------|
| `database_data.db` | SQLite 数据库，含 `FullList` 表（3000+ 行 × 34列） |
| `Result/` | CSV 保存目录（程序自动创建，不纳入版本控制） |
| `app.log` | 运行日志，每次启动追加 |
| `images/app_icon.ico` | Windows 应用图标 |
| `images/seastarEngineLogo.png` | 品牌 Logo |
| `UMIHOSHI.spec` | PyInstaller 打包配置 |
| `build.bat` | Windows 一键打包脚本 |

---

## 4. 数据库结构

### FullList 表（核心价目表）

**列索引速查**（共34列，索引0-33）：

```
0   Brand_Sort         品牌排序
1   NO_                产品编号
2   SEASTAR_U8_CODE    U8内部代码  ← 查询常用
3   IMPA               国际船用品编码 ← 查询常用
4   KERGER_IMATECH     KERGER/IMATECH代码
5   DESCRIPTION        产品描述（大类名称）← matcher.py Step1 依据
6   DETAILS            技术详情（参数）← matcher.py Step2 依据
7   OFFER              报价说明 ← matcher.py Step3 依据
8   REMARK1            备注1
9   REMARK2            备注2
10  Quantity           库存量
11-15  电气参数、认证等
16-20  包装、HS编码、产地、日期
21  UNIT               单位
--- 以下为价格列（PRICE_COL_START_IDX=22）---
22  Cost_Price         成本价
23  High_Price         高档零售价 ← 公司为 Other 时显示
24  Medium_Price       中档零售价 ← 公司为 Other 时显示
25  L_GROUP_3          L组价格
--- 以下为公司专属价格列（COMPANY_COL_START_IDX=26）---
26  SINWA_SINGAPORE    SINWA SGP
27  SSM_7SEA           SSM 7SEA（已从下拉移除但列保留）
28  Seven_Seas_...     Seven Seas ← 向量检索默认公司
29  Wrist_Far_East     Wrist Far East
30  Anchor_Marine      Anchor Marine
31  RMS_Marine         RMS Marine
32  Fuji_Trading       Fuji Trading
33  Con_Lash           Con Lash
```

**查询优先级**：IMPA精确 → U8精确 → IMPA模糊 OR U8模糊（LIKE）

---

## 5. 向量检索完整流程

```
用户粘贴 RFQ 链接
        ↓
parse_rfq() 解析出 productItems
  每项：{ item_no, code(SevenSeas Code), desc(Item Description), qty, unit }
        ↓
点击向量检索 Toggle（ON）
        ↓
_runVectorQuery() → api.query_prices_vector(productItems, "Seven Seas")
        ↓
vector_matcher.batch_match(items, company)
  1. 提取所有 items[i]["desc"]（Item Description，客户描述）
  2. embed_batch(descs) → Voyage AI → 向量列表
  3. 对每条向量 search_products() → Qdrant Top-1
  4. payload_to_fl_row() → 格式化为 FL_DISPLAY 结构
  5. 返回 (cols, rows) — 格式与本地查询完全一致
        ↓
前端 updateQueryResultGrid() 全量重新渲染表格
```

**关闭向量检索时**：弹确认框 → 用户选"是" → vectorMode=false → 调 queryPrices()（本地重查）

---

## 6. 按改动目标快速定位

### 想改"价格匹配逻辑"
1. `matcher.py` — 调整 TF-IDF 阈值、分步策略
2. `vector_matcher.py` — 调整 Qdrant 检索参数、payload 映射
3. `api.py` 的 `_match_one()` — 调整描述匹配与代码精确匹配的优先级

### 想改"数据库字段/公司列"
1. `config.py` — **先改这里**，确保 FL_DB_COLS 与 FL_DISPLAY 对应
2. `database.py` — 确认 SQL 查询字段
3. `vector_matcher.py` — 更新 `_COMPANY_PRICE_FIELD` 字典

### 想改"前端UI/按钮布局"
1. `frontend/index.html` — 结构和样式
2. `frontend/js/main.js` — 按钮行为、状态管理
3. 若涉及新的后端 API：`api.py` 中新增方法

### 想改"表格显示/滚动性能"
1. `frontend/js/grid.js` — 虚拟滚动逻辑、行渲染、列拖拽
2. `frontend/index.html` — 表格相关 CSS（`overflow-anchor`、`.sg-*` 类）

### 想改"RFQ 解析规则"
1. `Rfq_quotation_tool.py` — HTML 表格识别逻辑
2. `api.py` 的 `parse_rfq()` — 接口联动

### 想改"导入 Excel 到数据库"
1. `DatabaseUpdate.py` — 读取规则、字段处理
2. `config.py` — 确认列名映射是否需要同步更新

### 想改"打包/部署"
1. `UMIHOSHI.spec` — PyInstaller 配置（资源文件、隐藏导入）
2. `build.bat` — 构建脚本

### 想改"向量检索服务配置"
1. `vector_matcher.py` 顶部常量区 — API Key、Qdrant URL、Collection 名

---

## 7. 已知约定与注意事项

### 7.1 列顺序一致性（最高风险点）
`config.py` 中 `FL_DB_COLS` 和 `FL_DISPLAY` 的顺序**必须与 SQLite 实际列顺序完全一致**。任何新增列都要在两个列表的相同位置同时添加，并更新相关索引常量（`PRICE_COL_START_IDX`、`COMPANY_COL_START_IDX`）。

### 7.2 价格格式统一
所有从数据库取出的价格在显示层统一格式化为 `$数字.两位小数`。`database.py` 的 `query_product()` 在 `PRICE_COL_START_IDX` 之后的列自动加 `$` 前缀。

### 7.3 SevenSeas 模式的特殊行为
- 顶栏按钮组完全不同（`<template x-if>` 控制，非 `x-show`）：避免隐藏元素的 reflow
- `_rfqHeaderMap` 激活时，表格列头显示英文（SevenSeas Code / Item Description / Req Qty）
- 切换公司到非 SevenSeas 时，`_rfqHeaderMap` 和 `_rfqUrl` 自动清空

### 7.4 向量检索的全量替换语义
`_runVectorQuery()` 调用后，**所有行**都会被重新匹配，不保留旧结果。productItems 中每条的 `desc` 字段是向量化输入，`code` 字段仅保留在输出列中作为客户原始代码展示，不参与检索。

### 7.5 启动遮罩机制
`index.html` 中 `#init-overlay` 是一个固定定位的白色遮罩层，覆盖 pywebview 启动时 Qt 渲染引擎预热导致的白屏闪烁和 Alpine.js 初始化前的 HTML 裸露（FOUC）。`main.js` 的 `init()` 末尾调用 `_dismissOverlay()` 触发淡出动画后移除该元素。

### 7.6 滚动抖动修复原理
表格容器设置 `overflow-anchor: none` + `grid.js` 中 `tbody.style.overflowAnchor = 'none'`，禁止浏览器在子元素高度变化时自动补偿滚动位置。渲染节流通过 `_lastSt` 记录上次 scrollTop，滚动量为0时跳过重渲染。

### 7.7 Modal 弹窗不使用 backdrop-filter 动画
所有弹窗的 `backdrop-filter` 值预设为静态值（不在 `transition` 中包含它），避免 Chromium 在动画 blur 变化时触发整层重绘，解决弹窗打开/关闭时的页面闪烁问题。

---

## 8. 依赖安装清单

```bash
# 核心运行
pip install pywebview PySide6 openpyxl

# OCR（需另外安装 Tesseract）
pip install pytesseract pillow

# RFQ 解析
pip install requests beautifulsoup4 lxml tabulate

# 向量检索（SevenSeas 功能）
pip install qdrant-client requests

# 导出（Windows）
pip install pywin32

# 打包
pip install pyinstaller
```

---

## 9. 版本历史摘要（供 Claude 参考变更脉络）

| 功能 | 说明 |
|------|------|
| 基础版 | 本地 TF-IDF 匹配 + OCR + SQLite 价目表 |
| RFQ 集成 | SevenSeas 粘贴链接解析 + Finish 回填 |
| 向量检索 | Voyage AI + Qdrant，SevenSeas 专用 Toggle，关闭时确认弹窗 |
| 稳定性修复 | 启动遮罩、表格抖动（overflow-anchor）、顶栏闪烁（isolation）、Modal 闪烁（静态 backdrop-filter）|
| 保存结果 | Seven Seas 模式下 CSV 保存至 Result/ 目录 |

---

*本文档由 Claude 根据源代码自动生成，如修改了模块职责或新增文件，请同步更新此文档。*
