/* grid.js — AG Grid 两个表格的初始化与数据更新 */

let queryGridApi     = null;
let priceListGridApi = null;

/* 列颜色分类 */
const PRICE_COLS   = new Set(['Cost Price','High Price','Medium Price']);
const COMPANY_COLS = new Set(['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                               'Anchor Marine','RMS Marine','Fuji Trading','Con Lash']);
const CODE_COLS    = new Set(['U8代码','IMPA代码','KERGER/IMATECH','NO']);
const WRAP_COLS    = new Set(['描述','详情','报价','备注1','备注2','客户描述']);
const FIXED_COLS   = new Set(['Item NO.','商品代码','客户描述','数量','UOM']);

function cellClass(name) {
  const c = [];
  if (PRICE_COLS.has(name))   c.push('col-price');
  if (COMPANY_COLS.has(name)) c.push('col-company');
  if (CODE_COLS.has(name))    c.push('col-code');
  if (FIXED_COLS.has(name))   c.push('col-pin');
  return c;
}
function headerClass(name) {
  if (PRICE_COLS.has(name))   return 'col-price-hdr';
  if (COMPANY_COLS.has(name)) return 'col-company-hdr';
  return '';
}

/* ══════════════════════════════════════════════════
   查询结果表
   initQueryGrid：初始化（列为空，等数据来了再建）
   updateQueryResultGrid：完全仿照 updatePriceListGrid
══════════════════════════════════════════════════ */

function initQueryGrid(app) {
  const opts = {
    columnDefs: [],
    rowData: [],
    rowHeight: 34,
    headerHeight: 38,
    rowSelection: 'single',
    animateRows: false,
    suppressContextMenu: true,
    defaultColDef: { sortable: true, filter: false, resizable: true },
    rowClassRules: {
      'row-not-found': p => {
        const u8 = p.data && p.data['U8代码'];
        return !u8 || u8 === '未找到';
      },
    },
    onRowSelected(p) {
      if (p.node.isSelected() && window.appState) {
        window.appState.selectedRowIdx = p.rowIndex;
      }
    },
    onCellDoubleClicked(p) {
      if (!window.appState) return;
      const editCols = ['Item NO.','商品代码','客户描述','数量','UOM'];
      if (editCols.includes(p.column.getColId())) {
        window.appState.openEditDialog(p.rowIndex, p.data);
      } else {
        window.appState.openPriceListForRow(p.rowIndex, p.data);
      }
    },
  };
  queryGridApi = agGrid.createGrid(document.getElementById('queryGrid'), opts);
  app.queryGridApi = queryGridApi;
}

/**
 * 用与 updatePriceListGrid 完全相同的方式渲染查询结果。
 * cols  : 列名数组（Python 返回的 {cols, rows}.cols）
 * rows  : 二维数组（Python 返回的 {cols, rows}.rows）
 * colWidths : 列宽字典
 */
function updateQueryResultGrid(cols, rows, colWidths) {
  if (!queryGridApi) {
    console.error('[Grid] queryGridApi 未初始化');
    return;
  }

  console.log('[Grid] updateQueryResultGrid: cols =', cols.length, ' rows =', rows.length);

  // ── 1. 把二维数组转成对象数组（与 updatePriceListGrid 一致） ──────────────
  const rowData = rows.map(row => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = (row[i] ?? ''); });
    return obj;
  });

  // ── 2. 构建列定义（固定列 pinned left，其余按分类着色） ────────────────────
  const colDefs = cols.map(name => ({
    field:       name,
    headerName:  name,
    width:       colWidths[name] || (FIXED_COLS.has(name) ? 130 : 110),
    minWidth:    40,
    resizable:   true,
    pinned:      FIXED_COLS.has(name) ? 'left' : null,
    cellClass:   cellClass(name),
    headerClass: headerClass(name),
    wrapText:    WRAP_COLS.has(name),
  }));

  // ── 3. 先设列定义，用 rAF 等一帧后再设行数据（与价目表完全相同的时序） ────
  queryGridApi.setGridOption('columnDefs', colDefs);
  requestAnimationFrame(() => {
    queryGridApi.setGridOption('rowData', rowData);
    console.log('[Grid] rowData 已写入，行数:', rowData.length);
  });
}

/* 保留旧函数名供其他地方调用（内部转发给新函数） */
function updateQueryGrid(rows) {
  if (!queryGridApi) return false;
  queryGridApi.setGridOption('rowData', rows);
  return true;
}

function refreshQueryCols(app) {
  /* 新方案中列定义由 updateQueryResultGrid 负责，此函数保持为空即可 */
}

/* ══════════════════════════════════════════════════
   价目表（保持不变）
══════════════════════════════════════════════════ */

let _plData   = [];
let _plCols   = [];
let _matchIdx = [];

function buildPriceListColDefs(cols, colWidths) {
  return cols.map(name => ({
    field:       name,
    headerName:  name,
    width:       colWidths[name] || 110,
    minWidth:    40,
    resizable:   true,
    sortable:    true,
    pinned:      (name === 'U8代码' || name === 'IMPA代码') ? 'left' : null,
    cellClass:   cellClass(name),
    headerClass: headerClass(name),
    wrapText:    WRAP_COLS.has(name),
  }));
}

function initPriceListGrid(app) {
  const opts = {
    columnDefs: [],
    rowData: [],
    rowHeight: 34,
    headerHeight: 38,
    rowBuffer: 30,
    rowSelection: 'single',
    suppressContextMenu: true,
    animateRows: false,
    defaultColDef: { sortable: true, filter: true, resizable: true },

    // ← 新增：Grid 就绪时自适应列宽
    onGridReady(params) {
      params.api.sizeColumnsToFit();
    },

    rowClassRules: {
      'row-matched': p => _matchIdx.includes(p.rowIndex),
    },
    onRowDoubleClicked(p) {
      if (window.appState && window.appState.priceListCallback) {
        window.appState.priceListCallback(p.data);
        window.appState.priceListCallback = null;
      }
    },
  };
  priceListGridApi = agGrid.createGrid(document.getElementById('priceListGrid'), opts);
  app.priceListGridApi = priceListGridApi;  // 现在 app 里声明了此属性，Alpine 能响应
}

function updatePriceListGrid(cols, rows, colWidths) {
  if (!priceListGridApi) return;
  _plCols = cols;
  _plData = rows.map(row => {
    const o = {};
    cols.forEach((c, i) => { o[c] = (row[i] ?? '') + ''; });
    return o;
  });
  priceListGridApi.setGridOption('columnDefs', buildPriceListColDefs(cols, colWidths));
  requestAnimationFrame(() => {
    priceListGridApi.setGridOption('rowData', _plData);
    // 数据写入后强制重算列宽（修复高度为0时初始化的后遗症）
    requestAnimationFrame(() => {
      priceListGridApi.sizeColumnsToFit();
    });
  });
}

/* ── 搜索 ────────────────────────────────────────── */
const SCORE_W = { '描述': 3, '详情': 3, '报价': 3, '备注1': 2, '备注2': 2 };

function searchPriceList(keywords) {
  if (!priceListGridApi || !_plData.length) return 0;
  _matchIdx = [];
  if (!keywords.length) { priceListGridApi.redrawRows(); return 0; }
  _plData.forEach((row, i) => {
    let score = 0;
    _plCols.forEach(col => {
      const cell = (row[col] || '').toUpperCase();
      if (!cell) return;
      const w = SCORE_W[col] || 1;
      keywords.forEach(kw => { score += (cell.match(new RegExp(kw, 'g')) || []).length * w; });
    });
    if (score > 0) _matchIdx.push(i);
  });
  priceListGridApi.redrawRows();
  if (_matchIdx.length) priceListGridApi.ensureIndexVisible(_matchIdx[0], 'top');
  return _matchIdx.length;
}

function locatePriceList(keyword) {
  if (!priceListGridApi || !_plData.length || !keyword) return;
  const kw = keyword.toUpperCase();
  const idx = _plData.findIndex(row =>
    Object.values(row).some(v => v && v.toString().toUpperCase().includes(kw))
  );
  if (idx >= 0) {
    _matchIdx = [idx];
    priceListGridApi.redrawRows();
    priceListGridApi.ensureIndexVisible(idx, 'middle');
  }
}

function setPriceListRowHeight(lines) {
  if (!priceListGridApi) return;
  priceListGridApi.setGridOption('rowHeight', Math.max(28, 18 * lines + 6));
  priceListGridApi.resetRowHeights();
}

function resizeGrid(api) {
  if (api) setTimeout(() => api.sizeColumnsToFit(), 50);
}