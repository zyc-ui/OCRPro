/* grid.js — 原生 DOM 虚拟滚动表格 · 列拖拽排序 · 无第三方依赖 */

// ── 列分类 ──────────────────────────────────────────────
const PRICE_COLS   = new Set(['Cost Price','High Price','Medium Price']);
const COMPANY_COLS = new Set(['SINWA SGP','Seven Seas','Wrist Far East',
                               'Anchor Marine','RMS Marine','Fuji Trading','Con Lash']);
const CODE_COLS    = new Set(['U8代码','IMPA代码','KERGER/IMATECH','NO']);
const WRAP_COLS    = new Set(['描述','详情','报价','备注1','备注2','客户描述']);
const FIXED_5_SET  = new Set(['Item NO.','商品代码','客户描述','数量','UOM']);

// ── 默认列宽 ─────────────────────────────────────────────
const DEFAULT_WIDTHS = {
  'Item NO.':65, '商品代码':130, '客户描述':280, '数量':65, 'UOM':65,
  'Brand Sort':90, 'NO':60,
  'U8代码':130, 'IMPA代码':110, 'KERGER/IMATECH':110,
  '描述':300, '详情':270, '报价':220, '备注1':200, '备注2':200,
  '库存量':75, 'Battery/Input':110, 'IP Rating':80,
  'Temp Class Gas':105, 'Surface Temp Dust':125, 'CERT':90,
  'Packing Dim':135, 'Packing Weight(KG)':125, 'HS Code':95,
  'COO':65, 'DATE':90, '单位':65,
  'Cost Price':95, 'High Price':95, 'Medium Price':95, 'L GROUP 3':90,
  'SINWA SGP':110, 'Seven Seas':110,
  'Wrist Far East':115, 'Anchor Marine':115, 'RMS Marine':110,
  'Fuji Trading':110, 'Con Lash':110,
};

const BUFFER = 20;

// ── 模块级引用 ────────────────────────────────────────────
let queryGridApi     = null;
let priceListGridApi = null;

// ── 价目表搜索状态 ────────────────────────────────────────
let _plData = [], _plCols = [], _matchIdx = [];


// ══════════════════════════════════════════════════════════
// createGrid — 核心工厂
// ══════════════════════════════════════════════════════════
function createGrid(containerId, { onRowSelected, onCellDoubleClicked, onRowDoubleClicked } = {}) {
  const el = document.getElementById(containerId);
  if (!el) { console.error('[Grid] 容器未找到:', containerId); return null; }
  el.innerHTML = '';

  const table    = document.createElement('table');
  table.className = 'sg-table';
  const colgroup = document.createElement('colgroup');
  const thead    = document.createElement('thead');
  thead.className = 'sg-thead';
  const tbody    = document.createElement('tbody');
  table.append(colgroup, thead, tbody);
  el.appendChild(table);

  let _cols        = [];
  let _rows        = [];
  let _colWidths   = {};
  let _matchSet    = new Set();
  let _selIdx      = -1;
  let _rowH        = 72;
  let _headerNames = {};   // col key → display label（语言切换时更新）

  // ── 列拖拽状态（每实例独立，pointer-events 实现）──
  let _dragSrcIdx  = null;
  let _dragOverIdx = null;
  let _dragGhost   = null;

  const getW  = n  => _colWidths[n] || DEFAULT_WIDTHS[n] || 110;
  const total = () => _cols.reduce((s, c) => s + getW(c), 0);

  function syncColgroup() {
    colgroup.innerHTML = '';
    _cols.forEach(c => {
      const col = document.createElement('col');
      col.style.width = getW(c) + 'px';
      colgroup.appendChild(col);
    });
    table.style.width = total() + 'px';
  }

  function patchColWidth(ci, name) {
    const w = getW(name);
    const cols = colgroup.querySelectorAll('col');
    if (cols[ci]) cols[ci].style.width = w + 'px';
    table.style.width = total() + 'px';
  }

  // ── 表头（列宽 handle + pointer 拖拽排序）──
  function renderHeader() {
    thead.innerHTML = '';
    if (!_cols.length) return;
    const tr = document.createElement('tr');

    _cols.forEach((col, ci) => {
      const th = document.createElement('th');
      th.className = 'sg-th'
        + (FIXED_5_SET.has(col)  ? ' col-fixed-hdr'   : '')
        + (PRICE_COLS.has(col)   ? ' col-price-hdr'   : '')
        + (COMPANY_COLS.has(col) ? ' col-company-hdr' : '');
      const w = getW(col);
      th.style.cssText = `width:${w}px;min-width:${w}px;position:relative;`;

      const span = document.createElement('span');
      span.className   = 'sg-th-text';
      span.textContent = _headerNames[col] || col;
      th.appendChild(span);

      // ── 列宽调整 handle（右边缘 resize）──
      const resizeHandle = document.createElement('div');
      resizeHandle.className = 'sg-resize-handle';
      resizeHandle.addEventListener('mousedown', e => {
        e.preventDefault();
        e.stopPropagation();
        const sx = e.pageX, sw = getW(col);
        document.body.style.cursor     = 'col-resize';
        document.body.style.userSelect = 'none';
        const onMove = ev => {
          const nw = Math.max(40, sw + ev.pageX - sx);
          _colWidths[col] = nw;
          th.style.width = th.style.minWidth = nw + 'px';
          patchColWidth(ci, col);
        };
        const onUp = () => {
          document.body.style.cursor = document.body.style.userSelect = '';
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup',   onUp);
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup',   onUp);
      });
      th.appendChild(resizeHandle);

      // ── 列排序：pointer events（可见 ghost + 兄弟列滑动）──
      th.addEventListener('mousedown', e => {
        if (e.target.classList.contains('sg-resize-handle')) return;
        if (e.button !== 0) return;
        e.preventDefault();

        _dragSrcIdx  = ci;
        _dragOverIdx = ci;

        const thRect = th.getBoundingClientRect();
        const thW    = thRect.width;

        // 创建 ghost：克隆 th，悬浮跟随光标
        const ghost = th.cloneNode(true);
        ghost.querySelector('.sg-resize-handle')?.remove();
        ghost.style.cssText = [
          'position:fixed', 'pointer-events:none', 'z-index:99999',
          `left:${thRect.left}px`, `top:${thRect.top}px`,
          `width:${thW}px`, `height:${thRect.height}px`,
          'margin:0', 'border-radius:6px',
          'box-shadow:0 8px 20px rgba(0,0,0,.22)',
          'opacity:0.95', 'cursor:grabbing',
          'transition:transform 0.12s cubic-bezier(0.34,1.56,0.64,1),box-shadow 0.12s ease',
        ].join(';');
        document.body.appendChild(ghost);
        _dragGhost = ghost;

        // 动画：卡起来
        requestAnimationFrame(() => {
          ghost.style.transform  = 'rotate(-2deg) scale(1.07)';
          ghost.style.boxShadow  = '0 20px 48px rgba(0,0,0,.38)';
        });

        // 源列淡出
        th.classList.add('sg-th-drag-source');
        // 给所有 th 加平滑 transform transition
        const allThs = Array.from(thead.querySelectorAll('th.sg-th'));
        allThs.forEach(t => { t.style.transition = 'transform 0.18s cubic-bezier(0.4,0,0.2,1)'; });

        document.body.style.cursor     = 'grabbing';
        document.body.style.userSelect = 'none';

        const onMove = ev => {
          // ghost 跟随光标水平移动，垂直固定在表头
          ghost.style.left = (ev.clientX - thW / 2) + 'px';

          // 临时隐藏 ghost，找光标下真实元素
          ghost.style.visibility = 'hidden';
          const under = document.elementFromPoint(ev.clientX, ev.clientY);
          ghost.style.visibility = '';

          const underTh = under?.closest('th.sg-th');
          const newOver = underTh ? allThs.indexOf(underTh) : _dragOverIdx;
          if (newOver < 0 || newOver === _dragOverIdx) return;
          _dragOverIdx = newOver;

          // 计算每列应该位移多少：在 src 和 target 之间的列反向退开
          const srcW = thW;
          allThs.forEach((t, idx) => {
            if (idx === ci) return; // 源列本身不位移（只淡出）
            let shift = 0;
            if (ci < newOver && idx > ci && idx <= newOver) shift = -srcW; // 向右拖：中间列左移
            if (ci > newOver && idx >= newOver && idx < ci)  shift =  srcW; // 向左拖：中间列右移
            t.style.transform = shift ? `translateX(${shift}px)` : '';
          });
        };

        const onUp = () => {
          document.removeEventListener('mousemove', onMove);
          document.removeEventListener('mouseup',   onUp);

          ghost.remove();
          _dragGhost = null;

          th.classList.remove('sg-th-drag-source');
          allThs.forEach(t => { t.style.transform = ''; t.style.transition = ''; });
          document.body.style.cursor = document.body.style.userSelect = '';

          if (_dragOverIdx !== null && _dragOverIdx !== _dragSrcIdx) {
            const [moved] = _cols.splice(_dragSrcIdx, 1);
            _cols.splice(_dragOverIdx, 0, moved);
            renderHeader();
            scheduleRender();
          }
          _dragSrcIdx = _dragOverIdx = null;
        };

        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup',   onUp);
      });

      tr.appendChild(th);
    });

    thead.appendChild(tr);
    syncColgroup();
  }

  // ── 虚拟滚动 ──
  let _rafId = null;
  const scheduleRender = () => {
    if (_rafId) return;
    _rafId = requestAnimationFrame(() => { _rafId = null; renderVisible(); });
  };

  function renderVisible() {
    if (!_cols.length || !_rows.length) { tbody.innerHTML = ''; return; }
    const st = el.scrollTop, vh = el.clientHeight || 500;
    const start = Math.max(0, Math.floor(st / _rowH) - BUFFER);
    const end   = Math.min(_rows.length, Math.ceil((st + vh) / _rowH) + BUFFER);
    const frag  = document.createDocumentFragment();

    if (start > 0) {
      const sp = document.createElement('tr');
      sp.className = 'sg-spacer';
      sp.style.height = (start * _rowH) + 'px';
      frag.appendChild(sp);
    }
    for (let i = start; i < end; i++) frag.appendChild(buildRow(_rows[i], i));
    const tail = _rows.length - end;
    if (tail > 0) {
      const sp = document.createElement('tr');
      sp.className = 'sg-spacer';
      sp.style.height = (tail * _rowH) + 'px';
      frag.appendChild(sp);
    }
    tbody.innerHTML = '';
    tbody.appendChild(frag);
  }

  function buildRow(row, i) {
    const tr = document.createElement('tr');
    tr.className  = rowCls(row, i);
    tr.style.height = _rowH + 'px';
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
      tbody.querySelectorAll('tr[data-idx]').forEach(r => {
        const ri = +r.dataset.idx;
        if (!isNaN(ri) && _rows[ri]) r.className = rowCls(_rows[ri], ri);
      });
      onRowSelected?.({ rowIndex: i, data: row });
    });

    tr.addEventListener('dblclick', e => {
      const tdEl  = e.target.closest('td');
      const tdIdx = tdEl ? Array.from(tr.children).indexOf(tdEl) : -1;
      onCellDoubleClicked?.({ rowIndex: i, data: row, colId: _cols[tdIdx] || '' });
      onRowDoubleClicked?.({ rowIndex: i, data: row });
    });
    return tr;
  }

  function rowCls(row, i) {
    let c = 'sg-row ' + (i % 2 === 0 ? 'sg-row-even' : 'sg-row-odd');
    if (i === _selIdx)               c += ' row-selected';
    if (_matchSet.has(i))            c += ' row-matched';
    if (row?.['U8代码'] === '未找到') c += ' row-not-found';
    return c;
  }

  el.addEventListener('scroll', scheduleRender, { passive: true });

  return {
    setGridOption(key, value) {
      if (key === 'columnDefs') {
        _cols = value.map(d => d.field || d.headerName || '');
        value.forEach(d => {
          if (d.width && d.field && _colWidths[d.field] == null)
            _colWidths[d.field] = d.width;
        });
        renderHeader();
      } else if (key === 'rowData') {
        _rows = Array.isArray(value) ? value : [];
        _selIdx = -1;
        scheduleRender();
      }
    },
    setRowHeight(px) {
      _rowH = Math.max(24, Math.min(300, +px));
      scheduleRender();
    },
    setMatchIndices(indices) {
      _matchSet = new Set(indices);
      scheduleRender();
    },
    scrollToIndex(idx) {
      if (idx < 0 || idx >= _rows.length) return;
      el.scrollTo({ top: Math.max(0, idx * _rowH - (el.clientHeight || 500) / 2), behavior: 'smooth' });
    },
    ensureIndexVisible(idx) { this.scrollToIndex(idx); },
    redrawRows()            { scheduleRender(); },
    sizeColumnsToFit()      { /* no-op */ },
    getRows()               { return _rows; },
    getCols()               { return _cols;  },
    /** 更新表头显示文字（不改变内部 key）, map: {colKey: displayLabel} */
    setHeaderNames(map) {
      _headerNames = map || {};
      const ths = thead.querySelectorAll('th.sg-th .sg-th-text');
      _cols.forEach((col, ci) => {
        if (ths[ci]) ths[ci].textContent = _headerNames[col] || col;
      });
    },
  };
}


// ══════════════════════════════════════════════════════════
// 查询结果表
// ══════════════════════════════════════════════════════════
function initQueryGrid(app) {
  queryGridApi = createGrid('queryGrid', {
    onRowSelected({ rowIndex }) {
      if (window.appState) window.appState.selectedRowIdx = rowIndex;
    },
    onCellDoubleClicked({ rowIndex, data, colId }) {
      if (!window.appState) return;
      const editCols = new Set(['Item NO.', '商品代码', '客户描述', '数量', 'UOM']);
      if (editCols.has(colId)) window.appState.openEditDialog(rowIndex, data);
      else                      window.appState.openPriceListForRow(rowIndex, data);
    },
  });
  app.queryGridApi = queryGridApi;
  console.log('[Grid] queryGrid 初始化');
}

function updateQueryResultGrid(cols, rows, colWidths, visibleColsOverride) {
  if (!queryGridApi) { console.error('[Grid] queryGridApi 未初始化'); return; }
  const visCols = visibleColsOverride || cols;
  const rowData = rows.map(row => {
    const obj = {};
    cols.forEach((c, i) => { obj[c] = row[i] ?? ''; });
    return obj;
  });
  const colDefs = visCols.map(name => ({
    field: name, headerName: name,
    width: (colWidths && colWidths[name]) || DEFAULT_WIDTHS[name] || 110,
  }));
  queryGridApi.setGridOption('columnDefs', colDefs);
  requestAnimationFrame(() => queryGridApi.setGridOption('rowData', rowData));
}

function updateQueryGrid(rows, visibleCols) {
  if (!queryGridApi) return false;
  if (visibleCols) {
    queryGridApi.setGridOption('columnDefs', visibleCols.map(name => ({
      field: name, headerName: name,
      width: DEFAULT_WIDTHS[name] || 110,
    })));
  }
  queryGridApi.setGridOption('rowData', Array.isArray(rows) ? rows : []);
  return true;
}


// ══════════════════════════════════════════════════════════
// 价目表
// ══════════════════════════════════════════════════════════
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
  console.log('[Grid] priceListGrid 初始化');
}

function updatePriceListGrid(cols, rows, colWidths) {
  if (!priceListGridApi) { console.error('[Grid] priceListGridApi 未初始化'); return; }
  _plCols = cols;
  _plData = rows.map(row => {
    const o = {};
    cols.forEach((c, i) => { o[c] = (row[i] ?? '') + ''; });
    return o;
  });
  priceListGridApi.setGridOption('columnDefs', cols.map(name => ({
    field: name, headerName: name,
    width: (colWidths && colWidths[name]) || DEFAULT_WIDTHS[name] || 110,
  })));
  requestAnimationFrame(() => {
    priceListGridApi.setGridOption('rowData', _plData);
    console.log('[Grid] 价目表写入完成:', _plData.length, '行');
  });
}


// ══════════════════════════════════════════════════════════
// 价目表搜索 / 定位
// ══════════════════════════════════════════════════════════
const SCORE_W = { '描述':3, '详情':3, '报价':3, '备注1':2, '备注2':2 };

function searchPriceList(keywords) {
  if (!priceListGridApi || !_plData.length) return 0;
  _matchIdx = [];
  if (!keywords || !keywords.length) { priceListGridApi.setMatchIndices([]); return 0; }
  const reList = keywords.map(kw =>
    new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi'));
  _plData.forEach((row, i) => {
    let score = 0;
    _plCols.forEach(col => {
      const cell = row[col] || '';
      if (!cell) return;
      const w = SCORE_W[col] || 1;
      reList.forEach(re => { re.lastIndex = 0; score += ((cell.match(re) || []).length) * w; });
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
    Object.values(row).some(v => v && v.toString().toUpperCase().includes(kw)));
  if (idx >= 0) { priceListGridApi.setMatchIndices([idx]); priceListGridApi.scrollToIndex(idx); }
}

function setPriceListRowHeight(px) {
  if (priceListGridApi) priceListGridApi.setRowHeight(px);
}

function resizeGrid(_api) { /* no-op */ }