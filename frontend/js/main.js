/* main.js — Alpine.js App 组件 */

// 价格 / 公司列（切换复选框时永远保留，不被隐藏）
const _ALWAYS_SHOW = new Set([
  'Item NO.','商品代码','客户描述','数量','UOM',
  'Cost Price','High Price','Medium Price',
  'SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
  'Anchor Marine','RMS Marine','Fuji Trading','Con Lash',
]);

function App() {
  return {
    // ── 配置 ──
    companyOptions: [],
    flDisplay:      [],
    colWidths:      {},

    // ── 状态 ──
    activeTab:    'query',
    lang:         'zh',
    isScanning:   false,
    isQuerying:   false,
    _ocrAppend:   false,

    company:         '',
    companyColLabel: '',
    productItems:    [],
    queryResults:    [],
    codesText:       '未识别到商品代码',
    selectedRowIdx:  -1,

    colVisibility:    {},
    infoColNames:     [],
    _lastQueryAllCols: [],   // 记录最近一次查询的全量列（用于复选框重建）

    priceSearch:      '',
    priceStats:       '',
    rowHeight:        72,    // 当前行高 px（两张表共用）
    _plLoadedFor:     null,
    _plGridInited:    false,
    priceListCallback: null,

    // ── 价目表关键词选择器 ──
    plKeywords:   [],        // 可选关键词列表
    plKwSel:      [],        // 已选关键词
    plKwOpen:     false,     // 下拉面板是否打开

    editDlg:  { open:false, rowIndex:-1, item_no:'', code:'', desc:'', qty:'', unit:'' },
    exportDlg: { open:false },

    tabs: [
      { id: 'query',     label: '价格查询' },
      { id: 'pricelist', label: '价目表'   },
    ],

    /* ══════════════════════════════════════════════
       初始化
    ══════════════════════════════════════════════ */
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

      if (!cfg.db_ok) {
        alert('⚠️ 数据库中缺少 FullList 表，请点击右上角 FullListUpdate 导入数据');
      }

      // 初始化查询表格
      initQueryGrid(this);

      // 监听标签切换 → 初始化价目表
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

    /* ══════════════════════════════════════════════
       标签页
    ══════════════════════════════════════════════ */
    switchTab(id) { this.activeTab = id; },

    onCompanyChange() {
      const LIST = ['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                    'Anchor Marine','RMS Marine','Fuji Trading','Con Lash'];
      this.companyColLabel = LIST.includes(this.company) ? this.company : 'High / Medium Price';
      this._plLoadedFor = null;
    },

    /* ══════════════════════════════════════════════
       OCR
    ══════════════════════════════════════════════ */
    async startOCR(append) {
      this.isScanning = true;
      this._ocrAppend = append;
      const ok = await window.pywebview.api.start_ocr();
      if (!ok) {
        alert('❌ Tesseract 未找到');
        this.isScanning = false;
      }
    },

    _handleOCRResult(items) {
      this.isScanning = false;
      if (!items?.length) {
        if (!this.productItems.length) this.codesText = '未识别到商品代码';
        return;
      }
      const valid = items.filter(i => i.code);
      if (!valid.length) { this.codesText = '识别到结果但无商品代码，请重试'; return; }
      this.productItems = this._ocrAppend ? [...this.productItems, ...valid] : valid;
      this.codesText = this.productItems
        .map(i => i.desc ? `${i.code}: ${i.desc}` : i.code).join('  |  ');
    },

    /* ══════════════════════════════════════════════
       查询价格
    ══════════════════════════════════════════════ */
    async queryPrices() {
      if (!this.productItems.length) { alert('请先使用 OCR 识别商品代码'); return; }
      if (!this.company)             { alert('请先选择公司'); return; }
      this.isQuerying = true;
      try {
        const d = await window.pywebview.api.query_prices(this.productItems, this.company);
        if (!d?.cols?.length || !d?.rows) { alert('查询返回格式异常'); return; }
        if (!d.rows.length) { alert('查询完成但无数据，请确认数据库已导入'); return; }

        // 存全量列（复选框过滤用）
        this._lastQueryAllCols = d.cols;

        // 存对象数组（导出用）
        this.queryResults = d.rows.map(row => {
          const obj = {};
          d.cols.forEach((c, i) => { obj[c] = row[i] || ''; });
          return obj;
        });

        // 应用当前复选框可见性，再渲染
        const visCols = this._visibleQueryCols(d.cols);
        updateQueryResultGrid(d.cols, d.rows, this.colWidths, visCols);

        // 同步行高
        if (queryGridApi) queryGridApi.setRowHeight(this.rowHeight);

      } catch (e) {
        console.error('[Query] 出错:', e);
        alert('查询出错: ' + String(e));
      } finally {
        this.isQuerying = false;
      }
    },

    /* ══════════════════════════════════════════════
       列显示切换（复选框）
    ══════════════════════════════════════════════ */
    toggleCol(col, visible) {
      this.colVisibility[col] = visible;
      if (!this.queryResults.length || !this._lastQueryAllCols.length) return;

      const visCols = this._visibleQueryCols(this._lastQueryAllCols);
      const colDefs = visCols.map(name => ({
        field: name, headerName: name,
        width: (this.colWidths[name]) || 110,
      }));

      if (queryGridApi) {
        queryGridApi.setGridOption('columnDefs', colDefs);
        requestAnimationFrame(() => queryGridApi.setGridOption('rowData', this.queryResults));
      }
    },

    /** 从全量列中过滤出当前应显示的列 */
    _visibleQueryCols(allCols) {
      return allCols.filter(c => {
        if (_ALWAYS_SHOW.has(c)) return true;
        return this.colVisibility[c] !== false;
      });
    },

    /* ══════════════════════════════════════════════
       行管理
    ══════════════════════════════════════════════ */
    addBlankRow() {
      const blank = { 'Item NO.':'', '商品代码':'双击选择', '客户描述':'', '数量':'', 'UOM':'' };
      this.flDisplay.forEach(n => { blank[n] = ''; });
      this.queryResults.push(blank);
      const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
        ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {}));
      updateQueryGrid(this.queryResults, visCols);
    },

    removeSelectedRow() {
      if (this.selectedRowIdx < 0) { alert('请先单击选择要删除的行'); return; }
      if (!confirm('确定删除选中行？')) return;
      this.queryResults.splice(this.selectedRowIdx, 1);
      this.selectedRowIdx = -1;
      const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
        ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {}));
      updateQueryGrid(this.queryResults, visCols);
    },

    /* ══════════════════════════════════════════════
       行高控制（双表同步）
    ══════════════════════════════════════════════ */
    onRowHeightChange(px) {
      this.rowHeight = +px;
      if (queryGridApi)     queryGridApi.setRowHeight(this.rowHeight);
      if (priceListGridApi) priceListGridApi.setRowHeight(this.rowHeight);
    },

    /* ══════════════════════════════════════════════
       价目表
    ══════════════════════════════════════════════ */
    async _loadPriceList() {
      const key = this.company || '';
      if (this._plLoadedFor === key) return;
      this.priceStats = '加载中…';
      try {
        const d = await window.pywebview.api.get_price_list(key);
        if (!d?.cols?.length) { this.priceStats = '数据格式异常'; return; }
        updatePriceListGrid(d.cols, d.rows, this.colWidths);
        if (priceListGridApi) priceListGridApi.setRowHeight(this.rowHeight);
        this._plLoadedFor = key;
        this.priceStats = d.rows.length ? `共 ${d.rows.length} 条` : '暂无数据';
      } catch (e) {
        console.error('[PriceList] 加载失败:', e);
        this.priceStats = '加载失败: ' + String(e);
      }
    },

    /* ── 价目表搜索（合并搜索栏 + 选中关键词）── */
    onPriceSearch() {
      this._doSearch();
    },
    clearPriceSearch() {
      this.priceSearch = '';
      this._doSearch();
    },
    _doSearch() {
      const raw = this.priceSearch.trim();
      const barKws = raw
        ? raw.split(/[,;\s，；]+/).map(k => k.trim().toUpperCase()).filter(Boolean)
        : [];
      const kwKws = this.plKwSel.map(k => k.toUpperCase());
      const all   = [...new Set([...barKws, ...kwKws])];
      const n = searchPriceList(all);
      this.priceStats = n ? `找到 ${n} 条匹配` : (all.length ? '无匹配' : (this._plLoadedFor != null ? `共 ${_plData.length} 条` : ''));
    },

    /* ── 关键词下拉 ── */
    togglePlKw(kw) {
      if (this.plKwSel.includes(kw)) {
        this.plKwSel = this.plKwSel.filter(k => k !== kw);
      } else {
        this.plKwSel = [...this.plKwSel, kw];
      }
      this._doSearch();
    },
    clearPlKw() {
      this.plKwSel = [];
      this._doSearch();
    },
    isKwSelected(kw) { return this.plKwSel.includes(kw); },

    /* ══════════════════════════════════════════════
       从查询表双击 → 价目表
    ══════════════════════════════════════════════ */
    async openPriceListForRow(rowIdx, rowData) {
      this.selectedRowIdx = rowIdx;

      // 提取关键词（商品代码 + 客户描述）
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
      this.plKwSel  = [];
      this.plKwOpen = false;
      this.priceSearch = '';

      this.activeTab = 'pricelist';
      await new Promise(r => requestAnimationFrame(r));
      await this._loadPriceList();

      this.priceListCallback = async selected => {
        await this._applyPriceListRow(rowIdx, rowData, selected);
        this.activeTab = 'query';
      };

      const kw = (rowData['U8代码'] || rowData['商品代码'] || '').replace('未找到', '').trim();
      if (kw) setTimeout(() => locatePriceList(kw), 150);
    },

    async _applyPriceListRow(rowIdx, old, sel) {
      const u8   = (sel['U8代码']   || '').trim();
      const impa = (sel['IMPA代码'] || '').trim();
      const code = u8 || impa || old['商品代码'];
      if (!u8 && !impa) {
        const rebuilt = { ...old, ...sel, '商品代码': old['商品代码'], '客户描述': old['客户描述'], '数量': old['数量'] };
        this.queryResults[rowIdx] = rebuilt;
        const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
          ? this._lastQueryAllCols : Object.keys(rebuilt));
        updateQueryGrid(this.queryResults, visCols);
        return;
      }
      try {
        const res = await window.pywebview.api.query_single(
          code, old['客户描述'], old['数量'], old['Item NO.'], old['UOM'], this.company);
        res['商品代码'] = old['商品代码'];
        res['客户描述'] = old['客户描述'];
        res['数量']     = old['数量'];
        this.queryResults[rowIdx] = res;
        const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
          ? this._lastQueryAllCols : Object.keys(res));
        updateQueryGrid(this.queryResults, visCols);
      } catch (e) { alert('重新查询失败: ' + e); }
    },

    /* ══════════════════════════════════════════════
       编辑弹窗
    ══════════════════════════════════════════════ */
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
      const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
        ? this._lastQueryAllCols : Object.keys(this.queryResults[0] || {}));
      updateQueryGrid(this.queryResults, visCols);
      this.editDlg.open = false;
    },
    async matchEdit() {
      const { rowIndex: i, item_no, code, desc, qty, unit } = this.editDlg;
      if (!code)         { alert('商品代码为空，无法查询'); return; }
      if (!this.company) { alert('请先选择公司'); return; }
      this.editDlg.open = false;
      try {
        const res = await window.pywebview.api.query_single(code, desc, qty, item_no, unit, this.company);
        this.queryResults[i] = res;
        const visCols = this._visibleQueryCols(this._lastQueryAllCols.length
          ? this._lastQueryAllCols : Object.keys(res));
        updateQueryGrid(this.queryResults, visCols);
      } catch (e) { alert('查询失败: ' + e); }
    },

    /* ══════════════════════════════════════════════
       导出
    ══════════════════════════════════════════════ */
    openExportDialog() { this.exportDlg.open = true; },
    async doExport(type) {
      this.exportDlg.open = false;
      const { html, plain } = this._buildExportData();
      if (type === 'html') {
        const r = await window.pywebview.api.copy_html_to_clipboard(html);
        alert(r.ok ? '✅ HTML 已复制，可在 Outlook 粘贴' : '复制失败: ' + r.error);
      } else if (type === 'eml') {
        const r = await window.pywebview.api.save_eml(html, plain);
        if (r.ok) alert(`✅ 已保存: ${r.path}`);
        else if (r.error !== 'cancelled') alert('保存失败: ' + r.error);
      } else {
        try { await navigator.clipboard.writeText(plain); alert('✅ 纯文本已复制'); }
        catch { alert('剪贴板写入失败'); }
      }
    },
    _buildExportData() {
      const visCols = Object.entries(this.colVisibility).filter(([, v]) => v).map(([k]) => k);
      const TH = 'border:1px solid #666;padding:6px 10px;background:#d0d7e3;font-weight:bold;font-family:Arial,sans-serif;font-size:13px;white-space:nowrap;';
      const TE = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#ffffff;';
      const TO = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#f0f4fa;';
      const headers = visCols.map(c => `<th style="${TH}">${c}</th>`).join('');
      const body = this.queryResults.map((row, i) =>
        `<tr>${visCols.map(c => `<td style="${i % 2 ? TO : TE}">${row[c] || ''}</td>`).join('')}</tr>`
      ).join('\n');
      const html = `<table style="border-collapse:collapse;border:2px solid #555;font-family:Arial,sans-serif;"><thead><tr>${headers}</tr></thead><tbody>${body}</tbody></table>`;
      const plain = [visCols.join(' | '), '-'.repeat(80),
        ...this.queryResults.map(r => visCols.map(c => r[c] || '').join(' | '))].join('\n');
      return { html, plain };
    },

    /* ══════════════════════════════════════════════
       杂项
    ══════════════════════════════════════════════ */
    clearAll() {
      this.productItems = []; this.queryResults = [];
      this.company = ''; this.companyColLabel = '';
      this.codesText = '未识别到商品代码'; this.selectedRowIdx = -1;
      this._lastQueryAllCols = [];
      if (queryGridApi) queryGridApi.setGridOption('rowData', []);
    },
    async openDBUpdate() { await window.pywebview.api.open_db_update(); },
    toggleLang() { this.lang = this.lang === 'zh' ? 'en' : 'zh'; },
  };
}