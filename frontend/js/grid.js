/* grid.js — AG Grid 两个表格的初始化与数据更新 */

let queryGridApi     = null;
let priceListGridApi = null;

/* 列颜色分类 */
const PRICE_COLS   = new Set(['Cost Price','High Price','Medium Price']);
const COMPANY_COLS = new Set(['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                               'Anchor Marine','RMS Marine','Fuji Trading','Con Lash']);
const CODE_COLS    = new Set(['U8代码','IMPA代码','KERGER/IMATECH','NO']);
const WRAP_COLS    = new Set(['描述','详情','报价','备注1','备注2','客户描述']);

function cellClass(name) {
  const c = [];
  if (PRICE_COLS.has(name))   c.push('col-price');
  if (COMPANY_COLS.has(name)) c.push('col-company');
  if (CODE_COLS.has(name))    c.push('col-code');
  if (WRAP_COLS.has(name))    c.push('col-wrap');
  return c;
}
function headerClass(name) {
  if (PRICE_COLS.has(name))   return 'col-price-hdr';
  if (COMPANY_COLS.has(name)) return 'col-company-hdr';
  return '';
}

/* ───────── 查询结果表 ───────────────────────────────── */

function buildQueryColDefs(app) {
  const { flDisplay, colWidths, colVisibility, company } = app;

  const fixed = [
    { field: '_rn', headerName: '#', width: 42, minWidth: 42, maxWidth: 42,
      pinned: 'left', sortable: false, filter: false, resizable: false,
      cellClass: ['col-rownum','col-pin'],
      valueGetter: p => p.node.rowIndex + 1 },
    { field: 'Item NO.', headerName: 'Item NO.', width: 68, pinned: 'left',
      cellClass: 'col-pin' },
    { field: '商品代码',  headerName: '商品代码',  width: 140, pinned: 'left',
      cellClass: ['col-code','col-pin'] },
    { field: '客户描述',  headerName: '客户描述',  width: 260, pinned: 'left',
      cellClass: ['col-pin'], wrapText: false },
    { field: '数量', headerName: '数量', width: 65,  pinned: 'left', cellClass: 'col-pin' },
    { field: 'UOM',  headerName: 'UOM',  width: 58,  pinned: 'left', cellClass: 'col-pin' },
  ];

  const dynamic = [];

  /* 信息列 0-21（PRICE_COL_START_IDX = 22） */
  for (let i = 0; i < 22; i++) {
    const name = flDisplay[i];
    if (name === undefined) continue;
    if (!colVisibility[name]) continue;
    dynamic.push({
      field: name, headerName: name,
      width: colWidths[name] || 110, minWidth: 40,
      resizable: true,
      cellClass: cellClass(name),
      headerClass: headerClass(name),
      wrapText: WRAP_COLS.has(name),
    });
  }

  /* 价格列：公司列 or 通用 Cost/High/Medium */
  if (company && COMPANY_COLS.has(company)) {
    dynamic.push({
      field: company, headerName: company,
      width: colWidths[company] || 110, minWidth: 70,
      resizable: true,
      cellClass: ['col-company'],
      headerClass: 'col-company-hdr',
    });
  } else {
    ['Cost Price','High Price','Medium Price'].forEach(name => {
      if (colVisibility[name] === false) return;
      dynamic.push({
        field: name, headerName: name,
        width: colWidths[name] || 95, minWidth: 70,
        resizable: true,
        cellClass: ['col-price'],
        headerClass: 'col-price-hdr',
      });
    });
  }

  return [...fixed, ...dynamic];
}

function initQueryGrid(app) {
  const opts = {
    columnDefs: buildQueryColDefs(app),
    rowData: [],
    rowHeight: 34,
    headerHeight: 38,
    rowSelection: 'single',
    suppressRowClickSelection: false,
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
  // 初始化后触发一次 resize，确保 pywebview 下高度计算正确
  setTimeout(() => {
    window.dispatchEvent(new Event('resize'));
    if (queryGridApi) queryGridApi.sizeColumnsToFit();
  }, 200);
}

function normalizeGridRows(rows) {
  if (!Array.isArray(rows)) return [];
  return rows.map(row => ({ ...(row || {}) }));
}

function updateQueryGrid(rows) {
  console.log('[Grid] updateQueryGrid 调用, queryGridApi:', !!queryGridApi, '行数:', rows?.length);
  if (!queryGridApi) {
    console.error('[Grid] queryGridApi 为 null，表格未初始化');
    return false;
  }
  try {
    const normalizedRows = normalizeGridRows(rows);
    queryGridApi.setGridOption('rowData', normalizedRows);
    // 强制 AG Grid 重新计算视口尺寸（pywebview 嵌入式 Chromium 不会自动触发）
    requestAnimationFrame(() => {
      window.dispatchEvent(new Event('resize'));
      if (queryGridApi) {
        queryGridApi.refreshCells({ force: true });
        queryGridApi.redrawRows();
        queryGridApi.sizeColumnsToFit();
        if (normalizedRows.length) {
          queryGridApi.ensureIndexVisible(0, 'top');
        }
      }
    });
    console.log('[Grid] rowData 更新成功');
    return true;
  } catch (e) {
    console.error('[Grid] setGridOption 失败:', e);
    return false;
  }
}

/**
 * 先更新列定义，等 AG Grid 完成列重建（一个 rAF）后再设置 rowData。
 * 直接连续调用两次 setGridOption 会导致 rowData 在列尚未稳定时被丢弃。
 */
function refreshQueryCols(app) {
  if (!queryGridApi) return;
  // 第一步：更新列定义
  queryGridApi.setGridOption('columnDefs', buildQueryColDefs(app));
  // 第二步：等列稳定后设置行数据（requestAnimationFrame ≈ 16ms）
  requestAnimationFrame(() => {
    if (queryGridApi && app.queryResults && app.queryResults.length) {
      queryGridApi.setGridOption('rowData', normalizeGridRows(app.queryResults));
      queryGridApi.refreshCells({ force: true });
      queryGridApi.redrawRows();
      queryGridApi.ensureIndexVisible(0, 'top');
      console.log('[Grid] refreshQueryCols → rowData 已在 rAF 后更新，行数:', app.queryResults.length);
    }
  });
}

function syncQueryGrid(app, rows) {
  if (!queryGridApi) {
    console.error('[Grid] syncQueryGrid 失败: queryGridApi 尚未初始化');
    return false;
  }
  const normalizedRows = normalizeGridRows(rows);
  queryGridApi.setGridOption('columnDefs', buildQueryColDefs(app));
  requestAnimationFrame(() => {
    if (!queryGridApi) return;
    queryGridApi.setGridOption('rowData', normalizedRows);
    queryGridApi.refreshCells({ force: true });
    queryGridApi.redrawRows();
    window.dispatchEvent(new Event('resize'));
    queryGridApi.sizeColumnsToFit();
    if (normalizedRows.length) {
      queryGridApi.ensureIndexVisible(0, 'top');
    }
    console.log('[Grid] syncQueryGrid 完成，行数:', normalizedRows.length);
  });
  return true;
}

/* ───────── 价目表 ───────────────────────────────────── */

let _plData   = [];   /* 原始数组（供搜索使用） */
let _plCols   = [];
let _matchIdx = [];   /* 匹配行索引 */

function buildPriceListColDefs(cols, colWidths) {
  return cols.map(name => ({
    field: name, headerName: name,
    width: colWidths[name] || 110, minWidth: 40,
    resizable: true, sortable: true,
    pinned: (name === 'U8代码' || name === 'IMPA代码') ? 'left' : null,
    cellClass: cellClass(name),
    headerClass: headerClass(name),
    wrapText: WRAP_COLS.has(name),
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
    rowClassRules: {
      'row-matched': p  => _matchIdx.includes(p.rowIndex),
    },
    onRowDoubleClicked(p) {
      if (window.appState && window.appState.priceListCallback) {
        window.appState.priceListCallback(p.data);
        window.appState.priceListCallback = null;
      }
    },
  };
  priceListGridApi = agGrid.createGrid(document.getElementById('priceListGrid'), opts);
  app.priceListGridApi = priceListGridApi;
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
  priceListGridApi.setGridOption('rowData', _plData);
}

/* 权重搜索 */
const SCORE_W = { '描述': 3, '详情': 3, '报价': 3, '备注1': 2, '备注2': 2 };

function searchPriceList(keywords) {
  if (!priceListGridApi || !_plData.length) return 0;
  _matchIdx = [];
  if (!keywords.length) {
    priceListGridApi.redrawRows();
    return 0;
  }
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
