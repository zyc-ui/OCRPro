/* main.js — Alpine.js App 组件 */

/* OCR 结果现在通过 CustomEvent 'ocr-result' 传递，由 body 上的 @ocr-result.window 接收 */

function App() {
  return {

    /* ── 配置（来自 Python） ─────────────────────────── */
    companyOptions: [],
    flDisplay:      [],
    colWidths:      {},

    /* ── UI 状态 ─────────────────────────────────────── */
    activeTab:    'query',
    lang:         'zh',
    isScanning:   false,
    isQuerying:   false,
    _ocrAppend:   false,

    /* ── 数据 ────────────────────────────────────────── */
    company:         '',
    companyColLabel: '',
    productItems:    [],
    queryResults:    [],
    codesText:       '未识别到商品代码',
    selectedRowIdx:  -1,

    /* ── 列显示 ──────────────────────────────────────── */
    colVisibility: {},
    infoColNames:  [],   /* FL_DISPLAY 0-21，供复选框渲染 */

    /* ── 价目表 ──────────────────────────────────────── */
    priceSearch:      '',
    priceStats:       '',
    rowLines:         3,
    _plLoadedFor:     null,
    _plGridInited:    false,   // 记录价目表 Grid 是否已初始化
    priceListCallback: null,

    /* ── 全局搜索 ─────────────────────────────────────── */
    globalKeyword: '',
    globalStats:   '在所有数据表中搜索关键词',

    /* ── 弹窗 ────────────────────────────────────────── */
    editDlg: {
      open: false, rowIndex: -1,
      item_no: '', code: '', desc: '', qty: '', unit: '',
    },
    exportDlg: { open: false },

    /* ── 标签页 ──────────────────────────────────────── */
    tabs: [
      { id: 'query',     label: '价格查询' },
      { id: 'pricelist', label: '价目表'   },
      { id: 'global',    label: '全局搜索' },
    ],

    /* ══════════════════════════════════════════════════
       初始化
    ══════════════════════════════════════════════════ */
    async init() {
      window.appState = this;
      await this._waitBridge();

      const cfg = await window.pywebview.api.get_config();
      this.companyOptions = cfg.company_options;
      this.flDisplay      = cfg.fl_display;
      this.colWidths      = cfg.col_widths;

      /* 列显示：信息列 0-24 */
      const names = {};
      cfg.fl_display.slice(0, 25).forEach(col => { names[col] = true; });
      this.colVisibility = names;
      this.infoColNames  = cfg.fl_display.slice(0, 22);

      if (!cfg.db_ok) {
        alert('⚠️ 数据库中缺少 FullList 表，请点击右上角 FullListUpdate 选择 Excel 文件导入数据');
      }

      // 查询 Grid 在可见的 query-panel 里初始化，没有问题
      initQueryGrid(this);

      // 价目表 Grid 延迟到用户第一次切换标签时初始化（避免在 display:none 元素上初始化失败）
      // initPriceListGrid 已移到 $watch 里

      /* 切换标签页时按需加载 */
      this.$watch('activeTab', async tab => {
        if (tab === 'pricelist') {
          // 延迟一个 tick，确保 Alpine 已将面板切换为可见（display != none）
          await this._nextTick();
          if (!this._plGridInited) {
            initPriceListGrid(this);
            this._plGridInited = true;
            // 等 Grid DOM 稳定后再加载数据
            await new Promise(r => setTimeout(r, 80));
          }
          await this._loadPriceList();
          resizeGrid(this.priceListGridApi);
        }
        if (tab === 'query') resizeGrid(this.queryGridApi);
      });
    },

    _waitBridge() {
      return new Promise(resolve => {
        if (window.pywebview?.api) { resolve(); return; }
        window.addEventListener('pywebviewready', resolve, { once: true });
      });
    },

    /** 等待下一个 microtask/macrotask，让 Alpine DOM 更新完成 */
    _nextTick() {
      return new Promise(r => setTimeout(r, 0));
    },

    /* ══════════════════════════════════════════════════
       标签页
    ══════════════════════════════════════════════════ */
    switchTab(id) { this.activeTab = id; },

    /* ══════════════════════════════════════════════════
       公司
    ══════════════════════════════════════════════════ */
    onCompanyChange() {
      const COMPANY_LIST = ['SINWA SGP','SSM 7SEA','Seven Seas','Wrist Far East',
                             'Anchor Marine','RMS Marine','Fuji Trading','Con Lash'];
      this.companyColLabel = COMPANY_LIST.includes(this.company)
        ? this.company : 'High / Medium Price';
      this._plLoadedFor = null;    // 公司变更：强制刷新价目表
      if (this.queryResults.length) refreshQueryCols(this);
    },

    /* ══════════════════════════════════════════════════
       OCR
    ══════════════════════════════════════════════════ */
    async startOCR(append) {
      this.isScanning = true;
      this._ocrAppend = append;
      const ok = await window.pywebview.api.start_ocr();
      if (!ok) {
        // Tesseract 未找到：立即重置按钮状态
        alert('❌ Tesseract 未找到，请检查 ocr_engine.py 中的路径配置');
        this.isScanning = false;
      }
      // ok=true 时：isScanning 将在收到 ocr-result 事件后重置（含取消情况）
    },

    _handleOCRResult(items) {
      console.log('[OCR] _handleOCRResult 收到', items?.length, '条', items);
      // 无论成功/取消/失败，都重置扫描状态
      this.isScanning = false;

      if (!items?.length) {
        // 取消或识别失败：不覆盖已有的 codesText
        if (!this.productItems.length) {
          this.codesText = '未识别到商品代码';
        }
        return;
      }
      const valid = items.filter(i => i.code);
      console.log('[OCR] 有效商品数:', valid.length);
      if (!valid.length) {
        this.codesText = '识别到结果但无商品代码，请重试';
        return;
      }
      this.productItems = this._ocrAppend
        ? [...this.productItems, ...valid]
        : valid;
      this.codesText = this.productItems
        .map(i => i.desc ? `${i.code}: ${i.desc}` : i.code)
        .join('  |  ');
      console.log('[OCR] productItems 已更新，数量:', this.productItems.length);
    },

    /* ══════════════════════════════════════════════════
       查询价格  ← 修复：先刷新列定义，再写入行数据
    ══════════════════════════════════════════════════ */
    async queryPrices() {
      if (!this.productItems.length) {
        alert('请先使用 OCR 识别商品代码');
        return;
      }
      if (!this.company) {
        alert('请先在左上角选择公司（选择 Other 则使用默认价格列）');
        return;
      }

      console.log('[Query] 开始查询，商品数:', this.productItems.length, '公司:', this.company);
      console.log('[Query] productItems[0]:', JSON.stringify(this.productItems[0]));

      this.isQuerying = true;
      try {
        // ── 1. 调用 Python API ────────────────────────────────────────
        const res = await window.pywebview.api.query_prices(
          this.productItems, this.company
        );

        // ── 2. 诊断返回值类型 ─────────────────────────────────────────
        console.log('[Query] 返回类型:', typeof res,
                    '是数组:', Array.isArray(res),
                    '长度:', Array.isArray(res) ? res.length : 'N/A');

        // pywebview 在 Python 抛出异常时会返回带 message/name 字段的普通对象
        if (res && typeof res === 'object' && !Array.isArray(res)) {
          const errMsg = res.message || res.error || JSON.stringify(res);
          console.error('[Query] Python 返回了错误对象:', errMsg);
          alert('查询出错（Python 异常）：\n' + errMsg
              + '\n\n请确认：\n1. 已通过 FullListUpdate 导入数据\n2. 数据库文件存在');
          return;
        }

        if (!Array.isArray(res) || res.length === 0) {
          console.warn('[Query] 返回空数组或非数组:', res);
          alert('查询完成但未返回数据。\n\n可能原因：\n'
              + '1. 数据库尚未导入（请点击 FullListUpdate）\n'
              + '2. 商品代码在数据库中不存在');
          return;
        }

        alert('[Query调试] 返回' + res.length + '条\n第一条keys: ' + Object.keys(res[0]).join(', ') + '\n商品代码: ' + res[0]['商品代码']);
        //console.log('[Query] 第一条结果 keys:', Object.keys(res[0]));DevTool

        // ── 3. 先刷新列定义（含当前公司价格列），再写入行数据 ─────────
        // AG Grid 重建列定义需要一个异步 tick，延迟后再设置 rowData
        this.queryResults = res;
        refreshQueryCols(this);             // 重建列（setColumnDefs + setRowData）
        await new Promise(r => setTimeout(r, 50));
        updateQueryGrid(this.queryResults); // 确保 rowData 在列稳定后再设置一次

        console.log('[Query] Grid 已更新，行数:', res.length);

      } catch (e) {
        console.error('[Query] JS 层捕获异常:', e);
        alert('查询出错: ' + String(e));
      } finally {
        this.isQuerying = false;
      }
    },

    /* ══════════════════════════════════════════════════
       列显示
    ══════════════════════════════════════════════════ */
    toggleCol(col, visible) {
      this.colVisibility[col] = visible;
      refreshQueryCols(this);
    },

    /* ══════════════════════════════════════════════════
       行管理
    ══════════════════════════════════════════════════ */
    addBlankRow() {
      const blank = { 'Item NO.': '', '商品代码': '双击选择',
                      '客户描述': '', '数量': '', 'UOM': '', '价格': '' };
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

    /* ══════════════════════════════════════════════════
       价目表
    ══════════════════════════════════════════════════ */
    async _loadPriceList() {
      const key = this.company || '';
      if (this._plLoadedFor === key) return;  // 缓存命中

      this.priceStats = '加载中…';
      try {
        const d = await window.pywebview.api.get_price_list(key);
        if (!d || !d.cols || !d.rows) {
          this.priceStats = '数据格式异常，请检查数据库';
          return;
        }
        updatePriceListGrid(d.cols, d.rows, this.colWidths);
        this._plLoadedFor = key;
        this.priceStats = d.rows.length > 0
          ? `共 ${d.rows.length} 条`
          : '暂无数据（请先通过 FullListUpdate 导入）';
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

    clearPriceSearch() {
      this.priceSearch = '';
      searchPriceList([]);
      this.priceStats = this._plLoadedFor !== null ? '' : '';
    },

    changeRowLines(delta) {
      this.rowLines = Math.max(1, Math.min(10, this.rowLines + delta));
      setPriceListRowHeight(this.rowLines);
    },

    /* 双击查询行 → 跳价目表 + 定位 */
    async openPriceListForRow(rowIdx, rowData) {
      this.selectedRowIdx = rowIdx;
      this.activeTab = 'pricelist';
      // _loadPriceList 由 $watch 触发，这里等待完成
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
        /* 无代码：直填 */
        const rebuilt = { ...old, ...sel,
          '商品代码': old['商品代码'],
          '客户描述': old['客户描述'],
          '数量':     old['数量'] };
        this.queryResults[rowIdx] = rebuilt;
        updateQueryGrid(this.queryResults);
        return;
      }
      try {
        const res = await window.pywebview.api.query_single(
          code, old['客户描述'], old['数量'], old['Item NO.'], old['UOM'], this.company
        );
        res['商品代码'] = old['商品代码'];
        res['客户描述'] = old['客户描述'];
        res['数量']     = old['数量'];
        this.queryResults[rowIdx] = res;
        updateQueryGrid(this.queryResults);
      } catch (e) { alert('重新查询失败: ' + e); }
    },

    /* ══════════════════════════════════════════════════
       编辑弹窗
    ══════════════════════════════════════════════════ */
    openEditDialog(idx, data) {
      this.editDlg = {
        open: true, rowIndex: idx,
        item_no: data['Item NO.'] || '',
        code:    data['商品代码']  || '',
        desc:    data['客户描述']  || '',
        qty:     data['数量']      || '',
        unit:    data['UOM']       || '',
      };
    },

    saveEdit() {
      const { rowIndex: i, item_no, code, desc, qty, unit } = this.editDlg;
      if (i < 0 || i >= this.queryResults.length) return;
      Object.assign(this.queryResults[i], {
        'Item NO.': item_no, '商品代码': code,
        '客户描述': desc, '数量': qty, 'UOM': unit,
      });
      updateQueryGrid(this.queryResults);
      this.editDlg.open = false;
    },

    async matchEdit() {
      const { rowIndex: i, item_no, code, desc, qty, unit } = this.editDlg;
      if (!code)          { alert('商品代码为空，无法查询'); return; }
      if (!this.company)  { alert('请先选择公司');           return; }
      this.editDlg.open = false;
      try {
        const res = await window.pywebview.api.query_single(
          code, desc, qty, item_no, unit, this.company
        );
        this.queryResults[i] = res;
        updateQueryGrid(this.queryResults);
      } catch (e) { alert('查询失败: ' + e); }
    },

    /* ══════════════════════════════════════════════════
       全局搜索
    ══════════════════════════════════════════════════ */
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
          t.innerHTML = `<thead><tr>${columns.map(c => `<th class="border border-slate-200 px-2 py-1 bg-slate-100 text-left font-medium whitespace-nowrap">${esc(c)}</th>`).join('')}</tr></thead>
            <tbody>${rows.map((row,ri) =>
              `<tr class="${ri%2?'bg-slate-50':'bg-white'}">${row.map(cell => {
                const s = esc(String(cell||''));
                return `<td class="border border-slate-200 px-2 py-1">${s.replace(re, m=>`<mark class="bg-yellow-200">${m}</mark>`)}</td>`;
              }).join('')}</tr>`
            ).join('')}</tbody>`;
          sec.appendChild(t);
          cont.appendChild(sec);
        });
        this.globalStats = `找到 ${total} 条，分布在 ${tables.length} 个表`;
      } catch (e) { this.globalStats = '搜索失败: ' + e; }
    },

    /* ══════════════════════════════════════════════════
       导出
    ══════════════════════════════════════════════════ */
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
        try {
          await navigator.clipboard.writeText(plain);
          alert('✅ 纯文本已复制');
        } catch { alert('剪贴板写入失败，请改用其他导出方式'); }
      }
    },

    _buildExportData() {
      const visCols = Object.entries(this.colVisibility)
        .filter(([,v]) => v).map(([k]) => k);
      const TH = 'border:1px solid #666;padding:6px 10px;background:#d0d7e3;font-weight:bold;font-family:Arial,sans-serif;font-size:13px;white-space:nowrap;';
      const TE = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#ffffff;';
      const TO = 'border:1px solid #999;padding:5px 10px;font-family:Arial,sans-serif;font-size:12px;background:#f0f4fa;';
      const headers = visCols.map(c => `<th style="${TH}">${c}</th>`).join('');
      const bodyHtml = this.queryResults.map((row, i) =>
        `<tr>${visCols.map(c => `<td style="${i%2?TO:TE}">${row[c]||''}</td>`).join('')}</tr>`
      ).join('\n');
      const html  = `<table style="border-collapse:collapse;border:2px solid #555;font-family:Arial,sans-serif;"><thead><tr>${headers}</tr></thead><tbody>${bodyHtml}</tbody></table>`;
      const sep   = '-'.repeat(80);
      const plain = [visCols.join(' | '), sep,
        ...this.queryResults.map(r => visCols.map(c => r[c]||'').join(' | '))
      ].join('\n');
      return { html, plain };
    },

    /* ══════════════════════════════════════════════════
       杂项
    ══════════════════════════════════════════════════ */
    clearAll() {
      this.productItems    = [];
      this.queryResults    = [];
      this.company         = '';
      this.companyColLabel = '';
      this.codesText       = '未识别到商品代码';
      this.selectedRowIdx  = -1;
      updateQueryGrid([]);
    },
    async openDBUpdate() { await window.pywebview.api.open_db_update(); },
    toggleLang()        { this.lang = this.lang === 'zh' ? 'en' : 'zh'; },
  };
}