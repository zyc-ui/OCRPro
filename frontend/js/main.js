/* main.js — Alpine.js App 组件 */

function App() {
  return {

    companyOptions: [],
    flDisplay:      [],
    colWidths:      {},

    activeTab:    'query',
    lang:         'zh',
    isScanning:   false,
    isQuerying:   false,
    _ocrAppend:   false,

    company:         '',
    companyColLabel: '',
    productItems:    [],
    queryResults:    [],   // 存对象数组，供导出用
    codesText:       '未识别到商品代码',
    selectedRowIdx:  -1,

    colVisibility: {},
    infoColNames:  [],

    priceSearch:      '',
    priceStats:       '',
    rowLines:         3,
    _plLoadedFor:     null,
    priceListGridApi: null,
    queryGridApi:     null,
    _plGridInited:    false,
    priceListCallback: null,

    globalKeyword: '',
    globalStats:   '在所有数据表中搜索关键词',

    editDlg: { open: false, rowIndex: -1, item_no: '', code: '', desc: '', qty: '', unit: '' },
    exportDlg: { open: false },

    tabs: [
      { id: 'query',     label: '价格查询' },
      { id: 'pricelist', label: '价目表'   },
      { id: 'global',    label: '全局搜索' },
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

      const names = {};
      cfg.fl_display.slice(0, 25).forEach(col => { names[col] = true; });
      this.colVisibility = names;
      this.infoColNames  = cfg.fl_display.slice(0, 22);

      if (!cfg.db_ok) {
        alert('⚠️ 数据库中缺少 FullList 表，请点击右上角 FullListUpdate 选择 Excel 文件导入数据');
      }

      // 查询 Grid：初始化（空列，等数据来了再建列）
      initQueryGrid(this);

      // 价目表 Grid：延迟到第一次切换时初始化
      this.$watch('activeTab', async tab => {
        if (tab === 'pricelist') {
            // 用 requestAnimationFrame 等浏览器完成布局，而非 0ms timeout
            await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));

            if (!this._plGridInited) {
              initPriceListGrid(this);
              this._plGridInited = true;
              // 再等一帧，让 AG Grid 完成内部初始化
              await new Promise(r => requestAnimationFrame(r));
            }
            await this._loadPriceList();

            // 用模块级变量而非 this.priceListGridApi
            resizeGrid(priceListGridApi);
        }
        if (tab === 'query') resizeGrid(queryGridApi);
      });
    },

    _waitBridge() {
      return new Promise(resolve => {
        if (window.pywebview?.api) { resolve(); return; }
        window.addEventListener('pywebviewready', resolve, { once: true });
      });
    },

    _nextTick() {
      return new Promise(r => setTimeout(r, 0));
    },

    /* ══════════════════════════════════════════════
       标签页 / 公司
    ══════════════════════════════════════════════ */
    switchTab(id) { this.activeTab = id; },

    onCompanyChange() {
      const COMPANY_LIST = ['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                             'Anchor Marine','RMS Marine','Fuji Trading','Con Lash'];
      this.companyColLabel = COMPANY_LIST.includes(this.company)
        ? this.company : 'High / Medium Price';
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
        alert('❌ Tesseract 未找到，请检查 ocr_engine.py 中的路径配置');
        this.isScanning = false;
      }
    },

    _handleOCRResult(items) {
      console.log('[OCR] 收到结果', items?.length, '条');
      this.isScanning = false;
      if (!items?.length) {
        if (!this.productItems.length) this.codesText = '未识别到商品代码';
        return;
      }
      const valid = items.filter(i => i.code);
      if (!valid.length) { this.codesText = '识别到结果但无商品代码，请重试'; return; }
      this.productItems = this._ocrAppend
        ? [...this.productItems, ...valid] : valid;
      this.codesText = this.productItems
        .map(i => i.desc ? `${i.code}: ${i.desc}` : i.code).join('  |  ');
    },

    /* ══════════════════════════════════════════════
       查询价格 ← 核心修复：完全仿照价目表加载方式
    ══════════════════════════════════════════════ */
    async queryPrices() {
      if (!this.productItems.length) { alert('请先使用 OCR 识别商品代码'); return; }
      if (!this.company)             { alert('请先在左上角选择公司'); return; }

      console.log('[Query] 开始查询，商品数:', this.productItems.length, '公司:', this.company);
      this.isQuerying = true;

      try {
        // 调用 Python，返回 {cols, rows} 与 get_price_list 完全相同的格式
        const d = await window.pywebview.api.query_prices(this.productItems, this.company);

        console.log('[Query] 返回:', d?.cols?.length, '列,', d?.rows?.length, '行');
        console.log('[Query] cols[0..4]:', d?.cols?.slice(0, 5));
        console.log('[Query] rows[0]:', d?.rows?.[0]);

        if (!d || !d.cols || !d.rows) {
          alert('查询返回数据格式异常，请查看控制台日志');
          return;
        }
        if (d.rows.length === 0) {
          alert('查询完成但未返回数据。\n可能原因：\n1. 数据库尚未导入（请点击 FullListUpdate）\n2. 商品代码在数据库中不存在');
          return;
        }

        // 保存对象数组供导出用
        this.queryResults = d.rows.map(row => {
          const obj = {};
          d.cols.forEach((c, i) => { obj[c] = row[i] || ''; });
          return obj;
        });

        // ★ 用与价目表完全相同的方式渲染
        updateQueryResultGrid(d.cols, d.rows, this.colWidths);

        console.log('[Query] 完成，行数:', d.rows.length);

      } catch (e) {
        console.error('[Query] 出错:', e);
        alert('查询出错: ' + String(e));
      } finally {
        this.isQuerying = false;
      }
    },

    /* ══════════════════════════════════════════════
       列显示（复选框）
    ══════════════════════════════════════════════ */
    toggleCol(col, visible) {
      this.colVisibility[col] = visible;
      // 重新查询后才生效，无需立即刷新
    },

    /* ══════════════════════════════════════════════
       行管理
    ══════════════════════════════════════════════ */
    addBlankRow() {
      const blank = { 'Item NO.': '', '商品代码': '双击选择', '客户描述': '', '数量': '', 'UOM': '' };
      this.flDisplay.forEach(n => { blank[n] = ''; });
      this.queryResults.push(blank);
      updateQueryGrid(this.queryResults);
    },

    removeSelectedRow() {
      if (this.selectedRowIdx < 0) { alert('请先单击选择要删除的行'); return; }
      if (!confirm('确定删除选中行？')) return;
      this.queryResults.splice(this.selectedRowIdx, 1);
      this.selectedRowIdx = -1;
      updateQueryGrid(this.queryResults);
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
        if (!d || !d.cols || !d.rows) { this.priceStats = '数据格式异常'; return; }
        updatePriceListGrid(d.cols, d.rows, this.colWidths);
        this._plLoadedFor = key;
        this.priceStats = d.rows.length > 0 ? `共 ${d.rows.length} 条` : '暂无数据';
      } catch (e) {
        console.error('[PriceList] 加载失败:', e);
        this.priceStats = '加载失败: ' + String(e);
      }
    },

    onPriceSearch() {
      const raw = this.priceSearch.trim();
      if (!raw) { this.clearPriceSearch(); return; }
      const kws = raw.split(/[,;\s，；]+/).map(k => k.trim().toUpperCase()).filter(Boolean);
      const n = searchPriceList(kws);
      this.priceStats = n ? `找到 ${n} 条匹配` : `未找到含 "${raw}" 的结果`;
    },

    clearPriceSearch() { this.priceSearch = ''; searchPriceList([]); this.priceStats = ''; },

    changeRowLines(delta) {
      this.rowLines = Math.max(1, Math.min(10, this.rowLines + delta));
      setPriceListRowHeight(this.rowLines);
    },

    async openPriceListForRow(rowIdx, rowData) {
      this.selectedRowIdx = rowIdx;
      this.activeTab = 'pricelist';
      await this._nextTick();
      await this._loadPriceList();
      this.priceListCallback = async selected => {
        await this._applyPriceListRow(rowIdx, rowData, selected);
        this.activeTab = 'query';
      };
      const kw = (rowData['U8代码'] || rowData['商品代码'] || '').replace('未找到','').trim();
      if (kw) setTimeout(() => locatePriceList(kw), 120);
    },

    async _applyPriceListRow(rowIdx, old, sel) {
      const u8   = (sel['U8代码']   || '').trim();
      const impa = (sel['IMPA代码'] || '').trim();
      const code = u8 || impa || old['商品代码'];
      if (!u8 && !impa) {
        const rebuilt = { ...old, ...sel, '商品代码': old['商品代码'], '客户描述': old['客户描述'], '数量': old['数量'] };
        this.queryResults[rowIdx] = rebuilt;
        updateQueryGrid(this.queryResults);
        return;
      }
      try {
        const res = await window.pywebview.api.query_single(
          code, old['客户描述'], old['数量'], old['Item NO.'], old['UOM'], this.company);
        res['商品代码'] = old['商品代码'];
        res['客户描述'] = old['客户描述'];
        res['数量']     = old['数量'];
        this.queryResults[rowIdx] = res;
        updateQueryGrid(this.queryResults);
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
      updateQueryGrid(this.queryResults);
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
        updateQueryGrid(this.queryResults);
      } catch (e) { alert('查询失败: ' + e); }
    },

    /* ══════════════════════════════════════════════
       全局搜索
    ══════════════════════════════════════════════ */
    async doGlobalSearch() {
      const kw = this.globalKeyword.trim();
      if (!kw) return;
      this.globalStats = '搜索中…';
      const cont = document.getElementById('globalResults');
      cont.innerHTML = '';
      try {
        const res = await window.pywebview.api.global_search(kw);
        const tables = Object.keys(res);
        if (!tables.length) { this.globalStats = `未找到含 "${kw}" 的结果`; return; }
        let total = 0;
        tables.forEach(tbl => {
          const { columns, rows } = res[tbl];
          total += rows.length;
          const sec = document.createElement('div');
          sec.className = 'mb-6';
          sec.innerHTML = `<p class="text-xs font-semibold text-slate-600 mb-1 px-1">${tbl} (${rows.length}条)</p>`;
          const t = document.createElement('table');
          t.className = 'w-full text-xs border-collapse';
          const re = new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
          const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
          t.innerHTML = `<thead><tr>${columns.map(c=>`<th class="border border-slate-200 px-2 py-1 bg-slate-100 text-left font-medium whitespace-nowrap">${esc(c)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((row,ri)=>`<tr class="${ri%2?'bg-slate-50':'bg-white'}">${row.map(cell=>{
              const s=esc(String(cell||''));
              return `<td class="border border-slate-200 px-2 py-1">${s.replace(re,m=>`<mark class="bg-yellow-200">${m}</mark>`)}</td>`;
            }).join('')}</tr>`).join('')}</tbody>`;
          sec.appendChild(t);
          cont.appendChild(sec);
        });
        this.globalStats = `找到 ${total} 条，分布在 ${tables.length} 个表`;
      } catch (e) { this.globalStats = '搜索失败: ' + e; }
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
      const visCols = Object.entries(this.colVisibility).filter(([,v])=>v).map(([k])=>k);
      const TH='border:1px solid #666;padding:6px 10px;background:#d0d7e3;font-weight:bold;font-family:Arial,sans-serif;font-size:13px;white-space:nowrap;';
      const TE='border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#ffffff;';
      const TO='border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#f0f4fa;';
      const headers = visCols.map(c=>`<th style="${TH}">${c}</th>`).join('');
      const bodyHtml = this.queryResults.map((row,i)=>`<tr>${visCols.map(c=>`<td style="${i%2?TO:TE}">${row[c]||''}</td>`).join('')}</tr>`).join('\n');
      const html = `<table style="border-collapse:collapse;border:2px solid #555;font-family:Arial,sans-serif;"><thead><tr>${headers}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
      const plain = [visCols.join(' | '), '-'.repeat(80), ...this.queryResults.map(r=>visCols.map(c=>r[c]||'').join(' | '))].join('\n');
      return { html, plain };
    },

    /* ══════════════════════════════════════════════
       杂项
    ══════════════════════════════════════════════ */
    clearAll() {
      this.productItems = []; this.queryResults = [];
      this.company = ''; this.companyColLabel = '';
      this.codesText = '未识别到商品代码'; this.selectedRowIdx = -1;
      if (queryGridApi) queryGridApi.setGridOption('rowData', []);
    },
    async openDBUpdate() { await window.pywebview.api.open_db_update(); },
    toggleLang()        { this.lang = this.lang === 'zh' ? 'en' : 'zh'; },
  };
}