/* main.js — Alpine.js App 组件 */

const _ALWAYS_SHOW = new Set([
  'Item NO.','商品代码','客户描述','数量','UOM',
  'Cost Price','High Price','Medium Price',
  'SINWA SGP','Seven Seas','Wrist Far East',
  'Anchor Marine','RMS Marine','Fuji Trading','Con Lash',
]);

// 列名中→英翻译表（表头切换语言时使用）
const _COL_HEADERS_EN = {
  // 固定5列（客户信息）
  '商品代码':        'Item Code',
  '客户描述':        'Customer Desc',
  '数量':            'Qty',
  // 数据列
  'U8代码':          'U8 Code',
  'IMPA代码':        'IMPA Code',
  '描述':            'Description',
  '详情':            'Details',
  '报价':            'Offer',
  '备注1':           'Remark 1',
  '备注2':           'Remark 2',
  '库存量':          'Stock Qty',
  '单位':            'Unit',
};

// ══════════════════════════════════════════════════════════
// 翻译字典
// ══════════════════════════════════════════════════════════
const _I18N = {
  zh: {
    app_name:        'Seastar',
    company_label:   '公司',
    ocr_btn:         'OCR识别',
    scanning:        '识别中',
    append_ocr:      '追加识别',
    query_price:     '查询价格',
    querying:        '查询中…',
    copy_table:      '复制表格',
    clear:           '清空',
    row_height:      '行高',
    item_code_label: '商品代码',
    price_col_prefix:'价格列: ',
    tab_query:       '价格查询',
    tab_pricelist:   '价目表',
    show_cols:       '显示列:',
    add_row:         '＋ 行',
    del_row:         '－ 行',
    search_ph:       '关键词搜索（空格或逗号分隔）…',
    search_btn:      '搜索',
    clear_x:         '✕',
    keywords_btn:    '关键词',
    kw_filter_title: '选择关键词筛选',
    clear_all:       '清除全部',
    kw_selected:     '已选',
    kw_sep:          '个',
    edit_title:      '编辑商品信息',
    lbl_item_no:     'Item NO.',
    lbl_code:        '商品代码',
    lbl_desc:        '客户描述',
    lbl_qty:         '数量',
    lbl_uom:         'UOM',
    cancel:          '取消',
    save:            '保存',
    match_btn:       'Match 重新查询',
    export_title:    '选择导出方式',
    copy_html_btn:   '复制 HTML 表格',
    copy_html_sub:   '直接粘贴到 Outlook 邮件',
    save_eml_btn:    '保存 .eml 文件',
    save_eml_sub:    '双击可用邮件客户端打开',
    copy_text_btn:   '复制纯文本',
    no_item_code:    '未识别到商品代码',
    scan_no_code:    '识别到结果但无商品代码，请重试',
    no_items_alert:  '请先使用 OCR 识别商品代码',
    no_company:      '请先选择公司',
    query_fmt_err:   '查询返回格式异常',
    query_no_data:   '查询完成但无数据，请确认数据库已导入',
    query_err:       '查询出错: ',
    loading:         '加载中…',
    data_fmt_err:    '数据格式异常',
    load_fail:       '加载失败: ',
    matched:         '找到 {n} 条匹配',
    no_match:        '无匹配',
    total:           '共 {n} 条',
    select_row:      '请先单击选择要删除的行',
    confirm_del:     '确定删除选中行？',
    code_empty:      '商品代码为空，无法查询',
    requery_fail:    '查询失败: ',
    html_copied:     '✅ HTML 已复制，可在 Outlook 粘贴',
    copy_fail:       '复制失败: ',
    saved_ok:        '✅ 已保存: ',
    save_fail:       '保存失败: ',
    text_copied:     '✅ 纯文本已复制',
    clip_fail:       '剪贴板写入失败',
    db_missing:      '⚠️ 数据库中缺少 FullList 表，请点击右上角 FullListUpdate 导入数据',
    append_toast:    '已追加识别 {n} 个商品代码',
    placeholder_sel: '双击选择',
    lang_toggle:     'EN',
    fulllist_btn:    'FullListUpdate',
  },
  en: {
    app_name:        'Seastar',
    company_label:   'Company',
    ocr_btn:         'OCR Scan',
    scanning:        'Scanning',
    append_ocr:      'Append Scan',
    query_price:     'Query Price',
    querying:        'Querying…',
    copy_table:      'Copy Table',
    clear:           'Clear',
    row_height:      'Row H',
    item_code_label: 'Item Code',
    price_col_prefix:'Price Col: ',
    tab_query:       'Price Query',
    tab_pricelist:   'Price List',
    show_cols:       'Columns:',
    add_row:         '＋ Row',
    del_row:         '－ Row',
    search_ph:       'Search keywords (space or comma)…',
    search_btn:      'Search',
    clear_x:         '✕',
    keywords_btn:    'Keywords',
    kw_filter_title: 'Filter by keywords',
    clear_all:       'Clear All',
    kw_selected:     'Selected',
    kw_sep:          '',
    edit_title:      'Edit Item Info',
    lbl_item_no:     'Item NO.',
    lbl_code:        'Item Code',
    lbl_desc:        'Customer Desc',
    lbl_qty:         'Qty',
    lbl_uom:         'UOM',
    cancel:          'Cancel',
    save:            'Save',
    match_btn:       'Match & Re-query',
    export_title:    'Select Export Method',
    copy_html_btn:   'Copy HTML Table',
    copy_html_sub:   'Paste directly into Outlook',
    save_eml_btn:    'Save .eml File',
    save_eml_sub:    'Open with email client',
    copy_text_btn:   'Copy Plain Text',
    no_item_code:    'No item codes recognized',
    scan_no_code:    'Result found but no item code, please retry',
    no_items_alert:  'Please scan item codes with OCR first',
    no_company:      'Please select a company first',
    query_fmt_err:   'Query response format error',
    query_no_data:   'Query complete but no data. Please import the database.',
    query_err:       'Query error: ',
    loading:         'Loading…',
    data_fmt_err:    'Data format error',
    load_fail:       'Load failed: ',
    matched:         '{n} match(es) found',
    no_match:        'No matches',
    total:           '{n} items',
    select_row:      'Please click to select a row first',
    confirm_del:     'Delete selected row?',
    code_empty:      'Item code is empty, cannot query',
    requery_fail:    'Query failed: ',
    html_copied:     '✅ HTML copied, paste into Outlook',
    copy_fail:       'Copy failed: ',
    saved_ok:        '✅ Saved: ',
    save_fail:       'Save failed: ',
    text_copied:     '✅ Plain text copied',
    clip_fail:       'Clipboard write failed',
    db_missing:      '⚠️ FullList table not found. Please import data via FullListUpdate.',
    append_toast:    '{n} item code(s) appended',
    placeholder_sel: 'Dbl-click to select',
    lang_toggle:     '中',
    fulllist_btn:    'FullListUpdate',
  },
};

function App() {
  return {
    // ── 配置 ──
    companyOptions: [],
    flDisplay:      [],
    colWidths:      {},

    // ── 状态 ──
    lang:         'zh',
    activeTab:    'query',
    isScanning:   false,
    isQuerying:   false,
    _ocrAppend:   false,

    company:         '',
    companyColLabel: '',
    productItems:    [],
    queryResults:    [],
    codesText:       '未识别到商品代码',
    selectedRowIdx:  -1,

    colVisibility:     {},
    infoColNames:      [],
    _lastQueryAllCols: [],

    priceSearch:      '',
    priceStats:       '',
    rowHeight:        72,
    _plLoadedFor:     null,
    _plGridInited:    false,
    priceListCallback: null,

    plKeywords:  [],
    plKwSel:     [],
    plKwOpen:    false,

    // ── Toast ──
    toast: { show: false, msg: '', _timer: null },

    editDlg:   { open:false, rowIndex:-1, item_no:'', code:'', desc:'', qty:'', unit:'' },
    exportDlg: { open:false },

    tabs: [
      { id: 'query',     label: '价格查询' },
      { id: 'pricelist', label: '价目表'   },
    ],

    // ══════════════════════════════════════════════
    // 翻译函数
    // ══════════════════════════════════════════════
    t(key) {
      return (_I18N[this.lang] || _I18N.zh)[key] ?? key;
    },
    tf(key, vars = {}) {
      let s = this.t(key);
      Object.entries(vars).forEach(([k, v]) => { s = s.replace(`{${k}}`, v); });
      return s;
    },

    // ══════════════════════════════════════════════
    // Toast
    // ══════════════════════════════════════════════
    showToast(msg, ms = 3000) {
      this.toast.msg  = msg;
      this.toast.show = true;
      clearTimeout(this.toast._timer);
      this.toast._timer = setTimeout(() => { this.toast.show = false; }, ms);
    },

    // ══════════════════════════════════════════════
    // 初始化
    // ══════════════════════════════════════════════
    async init() {
      window.appState = this;
      await this._waitBridge();

      const cfg = await window.pywebview.api.get_config();
      this.companyOptions = cfg.company_options;
      this.flDisplay      = cfg.fl_display;
      this.colWidths      = cfg.col_widths;

      const vis = {};
      cfg.fl_display.slice(0, 25).forEach(col => { vis[col] = true; });
      this.colVisibility = vis;
      this.infoColNames  = cfg.fl_display.slice(0, 22);

      if (!cfg.db_ok) alert(this.t('db_missing'));

      initQueryGrid(this);

      // 语言切换时同步动态文本
      this.$watch('lang', () => {
        this.tabs[0].label = this.t('tab_query');
        this.tabs[1].label = this.t('tab_pricelist');
        // 若 codesText 是默认提示，同步翻译
        const defaults = ['未识别到商品代码', 'No item codes recognized'];
        if (defaults.includes(this.codesText)) this.codesText = this.t('no_item_code');
        // 刷新表格列标题
        this.refreshGridHeaders();
      });

      this.$watch('activeTab', async tab => {
        if (tab === 'pricelist') {
          await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
          if (!this._plGridInited) {
            initPriceListGrid(this);
            this._plGridInited = true;
            await new Promise(r => requestAnimationFrame(r));
          }
          await this._loadPriceList();
        }
      });
    },

    _waitBridge() {
      return new Promise(resolve => {
        if (window.pywebview?.api) { resolve(); return; }
        window.addEventListener('pywebviewready', resolve, { once: true });
      });
    },

    // ══════════════════════════════════════════════
    // 语言切换
    // ══════════════════════════════════════════════
    toggleLang() {
      this.lang = this.lang === 'zh' ? 'en' : 'zh';
    },

    // ══════════════════════════════════════════════
    // 列标题语言刷新
    // ══════════════════════════════════════════════
    refreshGridHeaders() {
      const map = this.lang === 'en' ? _COL_HEADERS_EN : {};
      if (queryGridApi)     queryGridApi.setHeaderNames(map);
      if (priceListGridApi) priceListGridApi.setHeaderNames(map);
    },

    /** 返回列的当前语言显示名（供复选框标签使用）*/
    colLabel(col) {
      return this.lang === 'en' ? (_COL_HEADERS_EN[col] || col) : col;
    },

    // ══════════════════════════════════════════════
    // 标签页
    // ══════════════════════════════════════════════
    switchTab(id) { this.activeTab = id; },

    onCompanyChange() {
      const LIST = ['SINWA SGP','Seven Seas','Wrist Far East',
                    'Anchor Marine','RMS Marine','Fuji Trading','Con Lash'];
      this.companyColLabel = LIST.includes(this.company) ? this.company : 'High / Medium Price';
      this._plLoadedFor = null;
    },

    // ══════════════════════════════════════════════
    // OCR
    // ══════════════════════════════════════════════
    async startOCR(append) {
      this.isScanning = true;
      this._ocrAppend = append;
      const ok = await window.pywebview.api.start_ocr();
      if (!ok) {
        alert('❌ Tesseract not found');
        this.isScanning = false;
      }
    },

    _handleOCRResult(items) {
      this.isScanning = false;
      if (!items?.length) {
        if (!this.productItems.length) this.codesText = this.t('no_item_code');
        return;
      }
      const valid = items.filter(i => i.code);
      if (!valid.length) { this.codesText = this.t('scan_no_code'); return; }

      if (this._ocrAppend) {
        // ── 追加模式：直接加到查询表格末尾 + Toast ──
        this.productItems = [...this.productItems, ...valid];

        // 使用已有列结构，或退回到基础5列
        const baseCols = this._lastQueryAllCols.length
          ? this._lastQueryAllCols
          : ['Item NO.', '商品代码', '客户描述', '数量', 'UOM'];

        const newRows = valid.map(item => {
          const row = {};
          baseCols.forEach(c => { row[c] = ''; });
          row['Item NO.']  = item.item_no || '';
          row['商品代码']  = item.code    || '';
          row['客户描述']  = item.desc    || '';
          row['数量']      = item.qty     || '';
          row['UOM']       = item.unit    || '';
          return row;
        });

        this.queryResults = [...this.queryResults, ...newRows];

        const visCols = this._lastQueryAllCols.length
          ? this._visibleQueryCols(this._lastQueryAllCols)
          : baseCols;

        updateQueryGrid(this.queryResults, visCols);
        if (queryGridApi) queryGridApi.setRowHeight(this.rowHeight);

        // 3 秒 Toast
        this.showToast(this.tf('append_toast', { n: valid.length }));

        this.codesText = this.productItems
          .map(i => i.desc ? `${i.code}: ${i.desc}` : i.code).join('  |  ');
      } else {
        // ── 普通识别模式 ──
        this.productItems = valid;
        this.codesText = this.productItems
          .map(i => i.desc ? `${i.code}: ${i.desc}` : i.code).join('  |  ');
      }
    },

    // ══════════════════════════════════════════════
    // 查询价格
    // ══════════════════════════════════════════════
    async queryPrices() {
      if (!this.productItems.length) { alert(this.t('no_items_alert')); return; }
      if (!this.company)             { alert(this.t('no_company'));      return; }
      this.isQuerying = true;
      try {
        const d = await window.pywebview.api.query_prices(this.productItems, this.company);
        if (!d?.cols?.length || !d?.rows) { alert(this.t('query_fmt_err')); return; }
        if (!d.rows.length)               { alert(this.t('query_no_data')); return; }

        this._lastQueryAllCols = d.cols;
        this.queryResults = d.rows.map(row => {
          const obj = {};
          d.cols.forEach((c, i) => { obj[c] = row[i] || ''; });
          return obj;
        });

        const visCols = this._visibleQueryCols(d.cols);
        updateQueryResultGrid(d.cols, d.rows, this.colWidths, visCols);
        if (queryGridApi) queryGridApi.setRowHeight(this.rowHeight);
      } catch (e) {
        console.error('[Query] 出错:', e);
        alert(this.t('query_err') + String(e));
      } finally {
        this.isQuerying = false;
      }
    },

    // ══════════════════════════════════════════════
    // 列显示切换（复选框）
    // ══════════════════════════════════════════════
    toggleCol(col, visible) {
      this.colVisibility[col] = visible;
      if (!this.queryResults.length || !this._lastQueryAllCols.length) return;
      const visCols = this._visibleQueryCols(this._lastQueryAllCols);
      if (queryGridApi) {
        queryGridApi.setGridOption('columnDefs', visCols.map(name => ({
          field: name, headerName: name,
          width: (this.colWidths[name]) || 110,
        })));
        requestAnimationFrame(() => queryGridApi.setGridOption('rowData', this.queryResults));
      }
    },

    _visibleQueryCols(allCols) {
      return allCols.filter(c => {
        if (_ALWAYS_SHOW.has(c)) return true;
        return this.colVisibility[c] !== false;
      });
    },

    // ══════════════════════════════════════════════
    // 行管理
    // ══════════════════════════════════════════════
    addBlankRow() {
      const blank = { 'Item NO.':'', '商品代码': this.t('placeholder_sel'), '客户描述':'', '数量':'', 'UOM':'' };
      this.flDisplay.forEach(n => { blank[n] = ''; });
      // 有选中行则插在其下方，否则追加到末尾
      const insertAt = this.selectedRowIdx >= 0
        ? this.selectedRowIdx + 1
        : this.queryResults.length;
      this.queryResults.splice(insertAt, 0, blank);
      const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
        ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {}));
      updateQueryGrid(this.queryResults, visCols);
      if (queryGridApi) queryGridApi.setRowHeight(this.rowHeight);
    },

    removeSelectedRow() {
      if (this.selectedRowIdx < 0) { alert(this.t('select_row')); return; }
      if (!confirm(this.t('confirm_del'))) return;
      this.queryResults.splice(this.selectedRowIdx, 1);
      this.selectedRowIdx = -1;
      const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
        ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {}));
      updateQueryGrid(this.queryResults, visCols);
    },

    // ══════════════════════════════════════════════
    // 行高
    // ══════════════════════════════════════════════
    onRowHeightChange(px) {
      this.rowHeight = +px;
      if (queryGridApi)     queryGridApi.setRowHeight(this.rowHeight);
      if (priceListGridApi) priceListGridApi.setRowHeight(this.rowHeight);
    },

    // ══════════════════════════════════════════════
    // 价目表
    // ══════════════════════════════════════════════
    async _loadPriceList() {
      const key = this.company || '';
      if (this._plLoadedFor === key) return;
      this.priceStats = this.t('loading');
      try {
        const d = await window.pywebview.api.get_price_list(key);
        if (!d?.cols?.length) { this.priceStats = this.t('data_fmt_err'); return; }
        updatePriceListGrid(d.cols, d.rows, this.colWidths);
        if (priceListGridApi) priceListGridApi.setRowHeight(this.rowHeight);
        this._plLoadedFor = key;
        this.priceStats = d.rows.length ? this.tf('total', { n: d.rows.length }) : '';
      } catch (e) {
        console.error('[PriceList] 加载失败:', e);
        this.priceStats = this.t('load_fail') + String(e);
      }
    },

    onPriceSearch() { this._doSearch(); },
    clearPriceSearch() { this.priceSearch = ''; this._doSearch(); },
    _doSearch() {
      const raw = this.priceSearch.trim();
      const barKws = raw
        ? raw.split(/[,;\s，；]+/).map(k => k.trim().toUpperCase()).filter(Boolean)
        : [];
      const kwKws = this.plKwSel.map(k => k.toUpperCase());
      const all   = [...new Set([...barKws, ...kwKws])];
      const n     = searchPriceList(all);
      if (n)             this.priceStats = this.tf('matched', { n });
      else if (all.length) this.priceStats = this.t('no_match');
      else if (this._plLoadedFor != null) this.priceStats = this.tf('total', { n: _plData.length });
      else               this.priceStats = '';
    },

    togglePlKw(kw) {
      if (this.plKwSel.includes(kw)) this.plKwSel = this.plKwSel.filter(k => k !== kw);
      else                           this.plKwSel = [...this.plKwSel, kw];
      this._doSearch();
    },
    clearPlKw() { this.plKwSel = []; this._doSearch(); },
    isKwSelected(kw) { return this.plKwSel.includes(kw); },

    // ══════════════════════════════════════════════
    // 查询表双击 → 价目表
    // ══════════════════════════════════════════════
    async openPriceListForRow(rowIdx, rowData) {
      this.selectedRowIdx = rowIdx;
      const src = `${rowData['商品代码'] || ''} ${rowData['客户描述'] || ''}`;
      const seen = new Set();
      this.plKeywords = [];
      src.split(/[\s,，;；]+/).forEach(w => {
        w = w.trim();
        if (w.length > 1 && !seen.has(w.toUpperCase())) {
          seen.add(w.toUpperCase());
          this.plKeywords.push(w);
        }
      });
      this.plKwSel = []; this.plKwOpen = false; this.priceSearch = '';
      this.activeTab = 'pricelist';
      await new Promise(r => requestAnimationFrame(r));
      await this._loadPriceList();
      this.priceListCallback = async sel => {
        await this._applyPriceListRow(rowIdx, rowData, sel);
        this.activeTab = 'query';
      };
      const kw = (rowData['U8代码'] || rowData['商品代码'] || '').replace('未找到','').trim();
      if (kw) setTimeout(() => locatePriceList(kw), 150);
    },

    async _applyPriceListRow(rowIdx, old, sel) {
      const u8   = (sel['U8代码']   || '').trim();
      const impa = (sel['IMPA代码'] || '').trim();
      const code = u8 || impa || old['商品代码'];
      if (!u8 && !impa) {
        const rebuilt = { ...old, ...sel, '商品代码': old['商品代码'], '客户描述': old['客户描述'], '数量': old['数量'] };
        this.queryResults[rowIdx] = rebuilt;
        updateQueryGrid(this.queryResults, this._visibleQueryCols(
          this._lastQueryAllCols.length ? this._lastQueryAllCols : Object.keys(rebuilt)));
        return;
      }
      try {
        const res = await window.pywebview.api.query_single(
          code, old['客户描述'], old['数量'], old['Item NO.'], old['UOM'], this.company);
        res['商品代码'] = old['商品代码'];
        res['客户描述'] = old['客户描述'];
        res['数量']     = old['数量'];
        this.queryResults[rowIdx] = res;
        updateQueryGrid(this.queryResults, this._visibleQueryCols(
          this._lastQueryAllCols.length ? this._lastQueryAllCols : Object.keys(res)));
      } catch (e) { alert(this.t('requery_fail') + e); }
    },

    // ══════════════════════════════════════════════
    // 编辑弹窗
    // ══════════════════════════════════════════════
    openEditDialog(idx, data) {
      this.editDlg = {
        open: true, rowIndex: idx,
        item_no: data['Item NO.'] || '', code: data['商品代码'] || '',
        desc: data['客户描述'] || '', qty: data['数量'] || '', unit: data['UOM'] || '',
      };
    },
    saveEdit() {
      const { rowIndex: i, item_no, code, desc, qty, unit } = this.editDlg;
      if (i < 0 || i >= this.queryResults.length) return;
      Object.assign(this.queryResults[i], { 'Item NO.': item_no, '商品代码': code, '客户描述': desc, '数量': qty, 'UOM': unit });
      updateQueryGrid(this.queryResults, this._visibleQueryCols(
        this._lastQueryAllCols.length ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {})));
      this.editDlg.open = false;
    },
    async matchEdit() {
      const { rowIndex: i, item_no, code, desc, qty, unit } = this.editDlg;
      if (!code)         { alert(this.t('code_empty')); return; }
      if (!this.company) { alert(this.t('no_company')); return; }
      this.editDlg.open = false;
      try {
        const res = await window.pywebview.api.query_single(code, desc, qty, item_no, unit, this.company);
        this.queryResults[i] = res;
        updateQueryGrid(this.queryResults, this._visibleQueryCols(
          this._lastQueryAllCols.length ? this._lastQueryAllCols : Object.keys(res)));
      } catch (e) { alert(this.t('requery_fail') + e); }
    },

    // ══════════════════════════════════════════════
    // 导出
    // ══════════════════════════════════════════════
    openExportDialog() { this.exportDlg.open = true; },
    async doExport(type) {
      this.exportDlg.open = false;
      const { html, plain } = this._buildExportData();
      if (type === 'html') {
        const r = await window.pywebview.api.copy_html_to_clipboard(html);
        alert(r.ok ? this.t('html_copied') : this.t('copy_fail') + r.error);
      } else if (type === 'eml') {
        const r = await window.pywebview.api.save_eml(html, plain);
        if (r.ok) alert(this.t('saved_ok') + r.path);
        else if (r.error !== 'cancelled') alert(this.t('save_fail') + r.error);
      } else {
        try { await navigator.clipboard.writeText(plain); alert(this.t('text_copied')); }
        catch { alert(this.t('clip_fail')); }
      }
    },
    _buildExportData() {
      const visCols = Object.entries(this.colVisibility).filter(([,v]) => v).map(([k]) => k);
      const TH = 'border:1px solid #666;padding:6px 10px;background:#d0d7e3;font-weight:bold;font-family:Arial,sans-serif;font-size:13px;white-space:nowrap;';
      const TE = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#ffffff;';
      const TO = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#f0f4fa;';
      const headers = visCols.map(c => `<th style="${TH}">${c}</th>`).join('');
      const body    = this.queryResults.map((row, i) =>
        `<tr>${visCols.map(c => `<td style="${i%2?TO:TE}">${row[c]||''}</td>`).join('')}</tr>`
      ).join('\n');
      const html  = `<table style="border-collapse:collapse;border:2px solid #555;font-family:Arial,sans-serif;"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;
      const plain = [visCols.join(' | '), '-'.repeat(80),
        ...this.queryResults.map(r => visCols.map(c => r[c]||'').join(' | '))].join('\n');
      return { html, plain };
    },

    // ══════════════════════════════════════════════
    // 杂项
    // ══════════════════════════════════════════════
    clearAll() {
      this.productItems = []; this.queryResults = [];
      this.company = ''; this.companyColLabel = '';
      this.codesText = this.t('no_item_code');
      this.selectedRowIdx = -1; this._lastQueryAllCols = [];
      if (queryGridApi) queryGridApi.setGridOption('rowData', []);
    },
    async openDBUpdate() { await window.pywebview.api.open_db_update(); },
  };
}