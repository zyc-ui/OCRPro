/* grid.js — 原生 DOM 表格实现，无任何第三方依赖 */

// ── 模块级 API 引用（供 main.js 直接调用） ──
let queryGridApi     = null;
let priceListGridApi = null;

// ── 列分类 ──
const PRICE_COLS   = new Set(['Cost Price','High Price','Medium Price']);
const COMPANY_COLS = new Set(['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                               'Anchor Marine','RMS Marine','Fuji Trading','Con Lash']);
const CODE_COLS    = new Set(['U8代码','IMPA代码','KERGER/IMATECH','NO']);
const WRAP_COLS    = new Set(['描述','详情','报价','备注1','备注2','客户描述']);
const FIXED_COLS   = new Set(['Item NO.','商品代码','客户描述','数量','UOM']);

// ── 价目表内部状态 ──
let _plData   = [];
let _plCols   = [];
let _matchIdx = [];

// ═══════════════════════════════════════════════════════
// SimpleGrid：轻量原生表格封装
// ═══════════════════════════════════════════════════════

function createGrid(containerId, { onRowSelected, onCellDoubleClicked, onRowDoubleClicked } = {}) {
  const el = document.getElementById(containerId);
  if (!el) { console.error('[Grid] 容器未找到:', containerId); return null; }

  el.innerHTML = '';

  const table  = document.createElement('table');
  table.className = 'sg-table';
  const thead  = document.createElement('thead');
  thead.className = 'sg-thead';
  const tbody  = document.createElement('tbody');
  table.appendChild(thead);
  table.appendChild(tbody);
  el.appendChild(table);

  let _cols        = [];
  let _rows        = [];
  let _selectedIdx = -1;
  let _matchSet    = new Set();
  let _rowHeight   = null;   // px，null = auto

  // ── 表头渲染 ──────────────────────────────────────────
  function renderHeader() {
    thead.innerHTML = '';
    if (!_cols.length) return;
    const tr = document.createElement('tr');
    _cols.forEach(col => {
      const th = document.createElement('th');
      th.className = 'sg-th' +
        (PRICE_COLS.has(col)   ? ' col-price-hdr'   : '') +
        (COMPANY_COLS.has(col) ? ' col-company-hdr' : '');
      th.textContent = col;
      tr.appendChild(th);
    });
    thead.appendChild(tr);
  }

  // ── 行 CSS 类 ─────────────────────────────────────────
  function rowClass(row, i) {
    const base = ['sg-row', i % 2 === 0 ? 'sg-row-even' : 'sg-row-odd'];
    if (i === _selectedIdx) base.push('row-selected');
    if (_matchSet.has(i))   base.push('row-matched');
    const u8 = row['U8代码'];
    if (u8 === '未找到')    base.push('row-not-found');
    return base.join(' ');
  }

  // ── 数据行渲染 ────────────────────────────────────────
  function renderRows() {
    tbody.innerHTML = '';
    if (!_cols.length) return;

    _rows.forEach((row, i) => {
      const tr = document.createElement('tr');
      tr.className = rowClass(row, i);
      if (_rowHeight) tr.style.height = _rowHeight + 'px';

      _cols.forEach(col => {
        const td = document.createElement('td');
        const cls = ['sg-td'];
        if (PRICE_COLS.has(col))   cls.push('col-price');
        if (COMPANY_COLS.has(col)) cls.push('col-company');
        if (CODE_COLS.has(col))    cls.push('col-code');
        if (WRAP_COLS.has(col))    cls.push('col-wrap');
        td.className = cls.join(' ');
        td.textContent = row[col] !== undefined ? String(row[col]) : '';
        tr.appendChild(td);
      });

      // 单击选中
      tr.addEventListener('click', () => {
        _selectedIdx = i;
        tbody.querySelectorAll('tr').forEach((r, j) => {
          r.className = rowClass(_rows[j], j);
        });
        onRowSelected?.({ rowIndex: i, data: row });
      });

      // 双击
      tr.addEventListener('dblclick', e => {
        const tdEl  = e.target.closest('td');
        const tdIdx = tdEl ? Array.from(tr.children).indexOf(tdEl) : -1;
        const colId = _cols[tdIdx] || '';
        onCellDoubleClicked?.({ rowIndex: i, data: row, colId });
        onRowDoubleClicked?.({ rowIndex: i, data: row });
      });

      tbody.appendChild(tr);
    });
  }

  // ── 公开 API ──────────────────────────────────────────
  return {
    /** 兼容 AG Grid 的 setGridOption 接口 */
    setGridOption(key, value) {
      if (key === 'columnDefs') {
        _cols = value.map(d => d.field || d.headerName || '');
        renderHeader();
      } else if (key === 'rowData') {
        _rows = Array.isArray(value) ? value : [];
        renderRows();
      } else if (key === 'rowHeight') {
        _rowHeight = value;
        renderRows();
      }
    },

    setMatchIndices(indices) {
      _matchSet = new Set(indices);
      tbody.querySelectorAll('tr').forEach((r, j) => {
        if (_rows[j]) r.className = rowClass(_rows[j], j);
      });
    },

    scrollToIndex(idx) {
      const rows = tbody.querySelectorAll('tr');
      if (rows[idx]) rows[idx].scrollIntoView({ block: 'center', behavior: 'smooth' });
    },

    ensureIndexVisible(idx) { this.scrollToIndex(idx); },
    redrawRows()            { renderRows(); },
    resetRowHeights()       { renderRows(); },
    sizeColumnsToFit()      { /* 原生表格自动适应 */ },
    getRows()               { return _rows; },
    getCols()               { return _cols; },
  };
}


// ═══════════════════════════════════════════════════════
// 查询结果表
// ═══════════════════════════════════════════════════════

function initQueryGrid(app) {
  queryGridApi = createGrid('queryGrid', {
    onRowSelected({ rowIndex }) {
      if (window.appState) window.appState.selectedRowIdx = rowIndex;
    },
    onCellDoubleClicked({ rowIndex, data, colId }) {
      if (!window.appState) return;
      const editCols = ['Item NO.', '商品代码', '客户描述', '数量', 'UOM'];
      if (editCols.includes(colId)) {
        window.appState.openEditDialog(rowIndex, data);
      } else {
        window.appState.openPriceListForRow(rowIndex, data);
      }
    },
  });
  app.queryGridApi = queryGridApi;
  console.log('[Grid] queryGrid 初始化完成');
}

/**
 * 用 {cols, rows} 格式刷新查询结果表（与 updatePriceListGrid 同构）。
 * cols      : string[]   列名数组
 * rows      : any[][]    二维数组（每行与 cols 对齐）
 * colWidths : object     列宽字典
 */
function updateQueryResultGrid(cols, rows, colWidths) {
  if (!queryGridApi) { console.error('[Grid] queryGridApi 未初始化'); return; }

  console.log('[Grid] updateQueryResultGrid:', cols.length, '列,', rows.length, '行');

  // 二维数组 → 对象数组
  const rowData = rows.map(row => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = row[i] ?? ''; });
    return obj;
  });

  // 构建伪 columnDefs（只需 field 和 headerName）
  const colDefs = cols.map(name => ({ field: name, headerName: name, width: colWidths?.[name] || 110 }));

  queryGridApi.setGridOption('columnDefs', colDefs);
  // 等一帧再设数据，确保表头先渲染完
  requestAnimationFrame(() => {
    queryGridApi.setGridOption('rowData', rowData);
    console.log('[Grid] 查询结果已写入，行数:', rowData.length);
  });
}

/** 直接用对象数组刷新（供 addBlankRow / removeSelectedRow 等调用） */
function updateQueryGrid(rows) {
  if (!queryGridApi) return false;
  queryGridApi.setGridOption('rowData', Array.isArray(rows) ? rows : []);
  return true;
}


// ═══════════════════════════════════════════════════════
// 价目表
// ═══════════════════════════════════════════════════════

function initPriceListGrid(app) {
  priceListGridApi = createGrid('priceListGrid', {
    onRowDoubleClicked({ data }) {
      if (window.appState?.priceListCallback) {
        window.appState.priceListCallback(data);
        window.appState.priceListCallback = null;
      }
    },
  });
  app.priceListGridApi = priceListGridApi;
  console.log('[Grid] priceListGrid 初始化完成');
}

function _buildPriceColDefs(cols, colWidths) {
  return cols.map(name => ({ field: name, headerName: name, width: colWidths?.[name] || 110 }));
}

function updatePriceListGrid(cols, rows, colWidths) {
  if (!priceListGridApi) { console.error('[Grid] priceListGridApi 未初始化'); return; }

  _plCols = cols;
  _plData = rows.map(row => {
    const o = {};
    cols.forEach((c, i) => { o[c] = (row[i] ?? '') + ''; });
    return o;
  });

  priceListGridApi.setGridOption('columnDefs', _buildPriceColDefs(cols, colWidths));
  requestAnimationFrame(() => {
    priceListGridApi.setGridOption('rowData', _plData);
    console.log('[Grid] 价目表写入完成，行数:', _plData.length);
  });
}


// ═══════════════════════════════════════════════════════
// 价目表搜索 / 定位 / 行高
// ═══════════════════════════════════════════════════════

const SCORE_W = { '描述': 3, '详情': 3, '报价': 3, '备注1': 2, '备注2': 2 };

function searchPriceList(keywords) {
  if (!priceListGridApi || !_plData.length) return 0;
  _matchIdx = [];
  if (!keywords.length) {
    priceListGridApi.setMatchIndices([]);
    return 0;
  }

  _plData.forEach((row, i) => {
    let score = 0;
    _plCols.forEach(col => {
      const cell = (row[col] || '').toUpperCase();
      if (!cell) return;
      const w = SCORE_W[col] || 1;
      keywords.forEach(kw => {
        score += (cell.match(new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g')) || []).length * w;
      });
    });
    if (score > 0) _matchIdx.push(i);
  });

  priceListGridApi.setMatchIndices(_matchIdx);
  if (_matchIdx.length) priceListGridApi.scrollToIndex(_matchIdx[0]);
  return _matchIdx.length;
}

function locatePriceList(keyword) {
  if (!priceListGridApi || !_plData.length || !keyword) return;
  const kw  = keyword.toUpperCase();
  const idx = _plData.findIndex(row =>
    Object.values(row).some(v => v && v.toString().toUpperCase().includes(kw))
  );
  if (idx >= 0) {
    priceListGridApi.setMatchIndices([idx]);
    priceListGridApi.scrollToIndex(idx);
  }
}

function setPriceListRowHeight(lines) {
  if (!priceListGridApi) return;
  const px = Math.max(28, 18 * lines + 6);
  priceListGridApi.setGridOption('rowHeight', px);
}

/** 兼容旧调用，现在是 no-op（原生表格自动布局） */
function resizeGrid(api) { /* no-op */ }