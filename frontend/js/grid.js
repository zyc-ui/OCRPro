/* grid.js — 原生 DOM 表格：虚拟滚动 + 列宽拖拽，无第三方依赖 */

// ── 常量 ──
const ROW_H  = 72;   // 固定行高 px（≈4行文字）
const BUFFER = 20;   // 虚拟滚动上下缓冲行数

// ── 列分类 ──
const PRICE_COLS   = new Set(['Cost Price','High Price','Medium Price']);
const COMPANY_COLS = new Set(['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                               'Anchor Marine','RMS Marine','Fuji Trading','Con Lash']);
const CODE_COLS    = new Set(['U8代码','IMPA代码','KERGER/IMATECH','NO']);
const WRAP_COLS    = new Set(['描述','详情','报价','备注1','备注2','客户描述']);
const FIXED_5_SET  = new Set(['Item NO.','商品代码','客户描述','数量','UOM']);

// ── 默认列宽（宽文本列加宽）──
const DEFAULT_WIDTHS = {
  '行号':50, 'Item NO.':65, '商品代码':130, '客户描述':280, '数量':65, 'UOM':65,
  'Brand Sort':90, 'NO':60,
  'U8代码':130, 'IMPA代码':110, 'KERGER/IMATECH':110,
  '描述':300, '详情':270, '报价':220, '备注1':200, '备注2':200,
  '库存量':75, 'Battery/Input':110, 'IP Rating':80,
  'Temp Class Gas':105, 'Surface Temp Dust':125, 'CERT':90,
  'Packing Dim':135, 'Packing Weight(KG)':125, 'HS Code':95,
  'COO':65, 'DATE':90, '单位':65,
  'Cost Price':95, 'High Price':95, 'Medium Price':95, 'L GROUP 3':90,
  'SINWA SGP':110, 'SSM 7SEA':110, 'Seven Seas':110,
  'Wrist Far East':115, 'Anchor Marine':115, 'RMS Marine':110,
  'Fuji Trading':110, 'Con Lash':110,
};

// ── 模块级 grid 引用 ──
let queryGridApi     = null;
let priceListGridApi = null;

// ── 价目表内部状态 ──
let _plData = [], _plCols = [], _matchIdx = [];

// ════════════════════════════════════════════════════
// createGrid — 核心工厂函数
// ════════════════════════════════════════════════════
function createGrid(containerId, { onRowSelected, onCellDoubleClicked, onRowDoubleClicked } = {}) {
  const el = document.getElementById(containerId);
  if (!el) { console.error('[Grid] 容器未找到:', containerId); return null; }
  el.innerHTML = '';

  // ── DOM 结构 ──
  const table    = document.createElement('table');
  table.className = 'sg-table';
  const colgroup = document.createElement('colgroup');
  const thead    = document.createElement('thead');
  thead.className = 'sg-thead';
  const tbody    = document.createElement('tbody');
  table.append(colgroup, thead, tbody);
  el.appendChild(table);

  // ── 内部状态 ──
  let _cols      = [];
  let _rows      = [];
  let _colWidths = {};   // col名 → px（含用户拖拽后的值）
  let _matchSet  = new Set();
  let _selIdx    = -1;

  // ── 列宽辅助 ──
  function getW(name) {
    return _colWidths[name] || DEFAULT_WIDTHS[name] || 110;
  }
  function totalW() {
    return _cols.reduce((s, c) => s + getW(c), 0);
  }

  // ── colgroup 全量同步 ──
  function applyColgroup() {
    colgroup.innerHTML = '';
    _cols.forEach(c => {
      const col = document.createElement('col');
      col.style.width = getW(c) + 'px';
      colgroup.appendChild(col);
    });
    table.style.width = totalW() + 'px';
  }

  // ── 单列宽度更新（拖拽时，不重渲染所有行）──
  function applyOneColWidth(ci, name) {
    const newW = getW(name);
    const colEls = colgroup.querySelectorAll('col');
    if (colEls[ci]) colEls[ci].style.width = newW + 'px';
    table.style.width = totalW() + 'px';
  }

  // ── 表头渲染（含 resize handle）──
  function renderHeader() {
    thead.innerHTML = '';
    if (!_cols.length) return;
    const tr = document.createElement('tr');
    _cols.forEach((col, ci) => {
      const th = document.createElement('th');
      th.className = 'sg-th' +
        (FIXED_5_SET.has(col)  ? ' col-fixed-hdr'   : '') +
        (PRICE_COLS.has(col)   ? ' col-price-hdr'   : '') +
        (COMPANY_COLS.has(col) ? ' col-company-hdr' : '');
      const w = getW(col);
      th.style.cssText = `width:${w}px;min-width:${w}px;position:relative;`;

      const span = document.createElement('span');
      span.className = 'sg-th-text';
      span.textContent = col;
      th.appendChild(span);

      // ── resize handle ──
      const handle = document.createElement('div');
      handle.className = 'sg-resize-handle';
      handle.addEventListener('mousedown', e => {
        e.preventDefault();
        e.stopPropagation();
        const startX = e.pageX;
        const startW = getW(col);
        document.body.style.cursor     = 'col-resize';
        document.body.style.userSelect = 'none';

        const onMove = ev => {
          const newW = Math.max(40, startW + ev.pageX - startX);
          _colWidths[col] = newW;
          th.style.width    = newW + 'px';
          th.style.minWidth = newW + 'px';
          applyOneColWidth(ci, col);
        };
        const onUp = () => {
          document.body.style.cursor     = '';
          document.body.style.userSelect = '';
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup',   onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup',   onUp);
      });
      th.appendChild(handle);
      tr.appendChild(th);
    });
    thead.appendChild(tr);
    applyColgroup();
  }

  // ── 虚拟滚动：只渲染可见区域的行 ──
  let _rafId = null;
  function scheduleRender() {
    if (_rafId) return;
    _rafId = requestAnimationFrame(() => {
      _rafId = null;
      renderVisible();
    });
  }

  function renderVisible() {
    if (!_cols.length) { tbody.innerHTML = ''; return; }

    const scrollTop = el.scrollTop;
    const viewH     = el.clientHeight || 500;
    const totalRows = _rows.length;

    if (totalRows === 0) { tbody.innerHTML = ''; return; }

    const start = Math.max(0, Math.floor(scrollTop / ROW_H) - BUFFER);
    const end   = Math.min(totalRows, Math.ceil((scrollTop + viewH) / ROW_H) + BUFFER);

    const frag = document.createDocumentFragment();

    // 上方占位
    if (start > 0) {
      const sp = document.createElement('tr');
      sp.className   = 'sg-spacer';
      sp.style.height = (start * ROW_H) + 'px';
      frag.appendChild(sp);
    }

    for (let i = start; i < end; i++) {
      frag.appendChild(buildRow(_rows[i], i));
    }

    // 下方占位
    const tail = totalRows - end;
    if (tail > 0) {
      const sp = document.createElement('tr');
      sp.className   = 'sg-spacer';
      sp.style.height = (tail * ROW_H) + 'px';
      frag.appendChild(sp);
    }

    tbody.innerHTML = '';
    tbody.appendChild(frag);
  }

  // ── 构建单行 ──
  function buildRow(row, i) {
    const tr = document.createElement('tr');
    tr.className    = rowCls(row, i);
    tr.style.height = ROW_H + 'px';
    tr.dataset.idx  = i;

    _cols.forEach(col => {
      const td = document.createElement('td');
      let cls = 'sg-td';
      if (FIXED_5_SET.has(col))       cls += ' col-fixed-5';
      else if (PRICE_COLS.has(col))   cls += ' col-price';
      else if (COMPANY_COLS.has(col)) cls += ' col-company';
      if (CODE_COLS.has(col))  cls += ' col-code';
      if (WRAP_COLS.has(col))  cls += ' col-wrap';
      td.className   = cls;
      td.textContent = row[col] != null ? String(row[col]) : '';
      tr.appendChild(td);
    });

    tr.addEventListener('click', () => {
      _selIdx = i;
      // 只刷新可见行的选中态，无需全量重渲
      tbody.querySelectorAll('tr[data-idx]').forEach(r => {
        const ri = +r.dataset.idx;
        if (!isNaN(ri) && _rows[ri]) r.className = rowCls(_rows[ri], ri);
      });
      onRowSelected?.({ rowIndex: i, data: row });
    });

    tr.addEventListener('dblclick', e => {
      const tdEl  = e.target.closest('td');
      const tdIdx = tdEl ? Array.from(tr.children).indexOf(tdEl) : -1;
      const colId = _cols[tdIdx] || '';
      onCellDoubleClicked?.({ rowIndex: i, data: row, colId });
      onRowDoubleClicked?.({ rowIndex: i, data: row });
    });

    return tr;
  }

  function rowCls(row, i) {
    let cls = 'sg-row ' + (i % 2 === 0 ? 'sg-row-even' : 'sg-row-odd');
    if (i === _selIdx)               cls += ' row-selected';
    if (_matchSet.has(i))            cls += ' row-matched';
    if (row?.['U8代码'] === '未找到') cls += ' row-not-found';
    return cls;
  }

  // 绑定滚动
  el.addEventListener('scroll', scheduleRender, { passive: true });

  // ── 公开 API ──
  return {
    setGridOption(key, value) {
      if (key === 'columnDefs') {
        _cols = value.map(d => d.field || d.headerName || '');
        // 仅在用户未手动拖拽过的列上应用外部默认宽度
        value.forEach(d => {
          if (d.width && d.field && _colWidths[d.field] == null) {
            _colWidths[d.field] = d.width;
          }
        });
        renderHeader();
        // 不立即 scheduleRender，等 rowData 设置后再渲染
      } else if (key === 'rowData') {
        _rows   = Array.isArray(value) ? value : [];
        _selIdx = -1;
        scheduleRender();
      }
      // 'rowHeight' 由虚拟滚动统一管理，忽略
    },

    setMatchIndices(indices) {
      _matchSet = new Set(indices);
      scheduleRender();
    },

    scrollToIndex(idx) {
      if (idx < 0 || idx >= _rows.length) return;
      const target = Math.max(0, idx * ROW_H - (el.clientHeight || 500) / 2);
      el.scrollTo({ top: target, behavior: 'smooth' });
    },

    ensureIndexVisible(idx) { this.scrollToIndex(idx); },
    redrawRows()            { scheduleRender(); },
    resetRowHeights()       { scheduleRender(); },
    sizeColumnsToFit()      { /* colgroup 控制宽度，无需操作 */ },
    getRows()               { return _rows; },
    getCols()               { return _cols;  },
  };
}


// ════════════════════════════════════════════════════
// 查询结果表
// ════════════════════════════════════════════════════

function initQueryGrid(app) {
  queryGridApi = createGrid('queryGrid', {
    onRowSelected({ rowIndex }) {
      if (window.appState) window.appState.selectedRowIdx = rowIndex;
    },
    onCellDoubleClicked({ rowIndex, data, colId }) {
      if (!window.appState) return;
      const editCols = new Set(['Item NO.', '商品代码', '客户描述', '数量', 'UOM']);
      if (editCols.has(colId)) {
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
 * 用 {cols, rows} 格式刷新查询结果表
 * cols      : string[]  列名数组
 * rows      : any[][]   二维数组（每行与 cols 对齐）
 * colWidths : object    列宽字典（来自 Python config）
 */
function updateQueryResultGrid(cols, rows, colWidths) {
  if (!queryGridApi) { console.error('[Grid] queryGridApi 未初始化'); return; }
  console.log('[Grid] updateQueryResultGrid:', cols.length, '列,', rows.length, '行');

  const rowData = rows.map(row => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = row[i] ?? ''; });
    return obj;
  });

  const colDefs = cols.map(name => ({
    field:      name,
    headerName: name,
    width: (colWidths && colWidths[name]) || DEFAULT_WIDTHS[name] || 110,
  }));

  queryGridApi.setGridOption('columnDefs', colDefs);
  requestAnimationFrame(() => {
    queryGridApi.setGridOption('rowData', rowData);
    console.log('[Grid] 查询结果写入完成，行数:', rowData.length);
  });
}

/** 直接用对象数组刷新（addBlankRow / removeSelectedRow 等）*/
function updateQueryGrid(rows) {
  if (!queryGridApi) return false;
  queryGridApi.setGridOption('rowData', Array.isArray(rows) ? rows : []);
  return true;
}


// ════════════════════════════════════════════════════
// 价目表
// ════════════════════════════════════════════════════

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

function updatePriceListGrid(cols, rows, colWidths) {
  if (!priceListGridApi) { console.error('[Grid] priceListGridApi 未初始化'); return; }

  _plCols = cols;
  _plData = rows.map(row => {
    const o = {};
    cols.forEach((c, i) => { o[c] = (row[i] ?? '') + ''; });
    return o;
  });

  const colDefs = cols.map(name => ({
    field:      name,
    headerName: name,
    width: (colWidths && colWidths[name]) || DEFAULT_WIDTHS[name] || 110,
  }));

  priceListGridApi.setGridOption('columnDefs', colDefs);
  requestAnimationFrame(() => {
    priceListGridApi.setGridOption('rowData', _plData);
    console.log('[Grid] 价目表写入完成，行数:', _plData.length);
  });
}


// ════════════════════════════════════════════════════
// 价目表搜索 / 定位 / 行高
// ════════════════════════════════════════════════════

const SCORE_W = { '描述':3, '详情':3, '报价':3, '备注1':2, '备注2':2 };

function searchPriceList(keywords) {
  if (!priceListGridApi || !_plData.length) return 0;
  _matchIdx = [];
  if (!keywords || !keywords.length) {
    priceListGridApi.setMatchIndices([]);
    return 0;
  }

  const reList = keywords.map(kw =>
    new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  );

  _plData.forEach((row, i) => {
    let score = 0;
    _plCols.forEach(col => {
      const cell = row[col] || '';
      if (!cell) return;
      const w = SCORE_W[col] || 1;
      reList.forEach(re => {
        re.lastIndex = 0;
        score += ((cell.match(re) || []).length) * w;
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

/** 行高调整：虚拟滚动使用固定行高，保留签名供 main.js 调用但不操作 DOM */
function setPriceListRowHeight(_lines) { /* no-op，虚拟滚动固定 ROW_H */ }

/** no-op（原生表格自动布局） */
function resizeGrid(_api) {}