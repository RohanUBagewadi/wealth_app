/* The UI keeps financial values in the browser and does not send analytics. */
(() => {
  'use strict';
  const $ = (s, root=document) => root.querySelector(s);
  const $$ = (s, root=document) => [...root.querySelectorAll(s)];
  const state = { page:'dashboard', data:null, transactionOffset:0, transactionLimit:25, review:null, report:null, restore:null };
  const palettes = [
    ['#8877e8','#f0edff'],['#49ae91','#e7f7f0'],['#e69363','#fff0e6'],['#6693db','#eaf1ff'],
    ['#d97088','#fff0f3'],['#7a9c62','#eff6e9'],['#c582c8','#faeffa'],['#50aeb7','#e7f7f8']
  ];
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const icon = name => {const aliases={sparkles:'sparkle','plus-circle':'plus'};return `<svg class="icon" aria-hidden="true"><use href="#i-${esc(aliases[name]||name)}"/></svg>`;};
  const currencyExponent = code => (state.data?.currencies || []).find(x=>x.code===code)?.exponent ?? 2;
  function money(minor, currency) {
    const exp=currencyExponent(currency), n=BigInt(minor||0), neg=n<0n, abs=neg?-n:n, base=10n**BigInt(exp);
    const whole=(abs/base).toString().replace(/\B(?=(\d{3})+(?!\d))/g,',');
    const frac=exp?'.'+(abs%base).toString().padStart(exp,'0'):'';
    let symbol=currency+' ';
    try { symbol=new Intl.NumberFormat(undefined,{style:'currency',currency,minimumFractionDigits:0,maximumFractionDigits:0}).formatToParts(0).find(p=>p.type==='currency')?.value || symbol; } catch (_) {}
    return `${neg?'-':''}${symbol}${whole}${frac}`;
  }
  function dateLabel(value, opts={month:'short',day:'numeric',year:undefined}) {
    if(!value)return '—';
    const [y,m,d]=value.slice(0,10).split('-').map(Number);
    return new Intl.DateTimeFormat(undefined,{...opts,timeZone:'UTC'}).format(new Date(Date.UTC(y,m-1,d)));
  }
  function monthStart(d=new Date()){return new Date(Date.UTC(d.getFullYear(),d.getMonth(),1)).toISOString().slice(0,10)}
  function monthEnd(d=new Date()){return new Date(Date.UTC(d.getFullYear(),d.getMonth()+1,0)).toISOString().slice(0,10)}
  function currentRange() {
    const mode=$('#dashboardRange')?.value||'month', now=new Date();
    if(mode==='year')return [`${now.getFullYear()}-01-01`,now.toISOString().slice(0,10)];
    if(mode==='last-month'){const d=new Date(now.getFullYear(),now.getMonth()-1,1);return [monthStart(d),monthEnd(d)];}
    return [monthStart(now),now.toISOString().slice(0,10)];
  }
  async function api(path, opts={}) {
    const headers={...(opts.body?{'Content-Type':'application/json'}:{}),...(opts.headers||{})};
    let res;
    try { res=await fetch(path,{...opts,headers,cache:'no-store'}); }
    catch (_) { throw new Error('The local app server is unavailable. Your existing data has not been changed.'); }
    if(!res.ok){let body={};try{body=await res.json()}catch(_){}throw new Error(body.error||'The request could not be completed.');}
    if(opts.raw)return res;
    const type=res.headers.get('content-type')||'';
    return type.includes('application/json')?res.json():res.text();
  }
  const json=(method,body)=>({method,body:JSON.stringify(body)});
  function toast(message, kind='') {
    const node=document.createElement('div');node.className=`toast ${kind}`;node.textContent=message;
    $('#toastRegion').append(node);window.setTimeout(()=>node.remove(),4300);
  }
  function fail(error){toast(error?.message||'Something went wrong. Try again.','error');}
  function empty(title, text, glyph='sparkle') {
    return `<div class="empty-state"><span class="empty-icon">${icon(glyph)}</span><strong>${esc(title)}</strong><p>${esc(text)}</p></div>`;
  }
  function selected(name, value){return String(name??'')===String(value??'')?' selected':'';}
  function walletOptions(value='', includeArchived=false) {
    const wallets=(state.data?.wallets||[]).filter(w=>includeArchived||!w.archived_at);
    return `<option value="">Choose wallet</option>`+wallets.map(w=>`<option value="${esc(w.id)}"${selected(w.id,value)}>${esc(w.name)} · ${esc(w.currency)}</option>`).join('');
  }
  function categoryOptions(value='', kind='expense') {
    const cats=(state.data?.categories||[]).filter(c=>!c.archived_at&&(c.kind===kind||c.kind==='both'));
    return `<option value="">Uncategorized</option>`+cats.map(c=>`<option value="${esc(c.id)}"${selected(c.id,value)}>${esc(c.name)}</option>`).join('');
  }
  function updateCount(){const n=state.data?.transactions?.total||0;$('#transactionCount').textContent=n>99?'99+':String(n);}
  function setPage(page) {
    if(!$('#view-'+page))page='dashboard';
    state.page=page;location.hash=page;
    $$('[data-view]').forEach(el=>el.classList.toggle('hidden',el.dataset.view!==page));
    $$('[data-page]').forEach(el=>el.classList.toggle('active',el.dataset.page===page));
    const title={dashboard:'Dashboard',transactions:'Transactions',wallets:'Wallets',budgets:'Budgets',reports:'Reports',categories:'Categories',import:'Import & export',settings:'Settings'}[page]||'Dashboard';
    $('#crumbCurrent').textContent=title;document.title=`${title} · Wealth`;
    if(page==='transactions')loadTransactions();
    if(page==='reports')loadReports();
    if(page==='wallets')renderWallets();
    if(page==='budgets')renderBudgets();
    if(page==='categories')renderCategories();
    if(page==='settings')renderSettings();
    window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});
  }
  function renderSelects(){
    const walletFilter=$('#filterWallet'), catFilter=$('#filterCategory'), pdfWallet=$('#pdfWallet'), currency=$('#displayCurrency');
    const oldWallet=walletFilter.value,oldCat=catFilter.value,oldPdf=pdfWallet.value;
    walletFilter.innerHTML='<option value="">All wallets</option>'+(state.data.wallets||[]).filter(w=>!w.archived_at).map(w=>`<option value="${esc(w.id)}">${esc(w.name)}</option>`).join('');walletFilter.value=oldWallet;
    catFilter.innerHTML='<option value="">All categories</option>'+(state.data.categories||[]).filter(c=>!c.archived_at).map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('');catFilter.value=oldCat;
    pdfWallet.innerHTML=walletOptions(oldPdf);pdfWallet.addEventListener('change',()=>{const w=state.data.wallets.find(x=>x.id===pdfWallet.value);if(w)$('#pdfCurrency').value=w.currency;});
    currency.innerHTML=(state.data.currencies||[]).map(c=>`<option value="${esc(c.code)}">${esc(c.code)}</option>`).join('');
    currency.value=localStorage.getItem('wealth.displayCurrency')||'EUR';
  }
  function renderDashboard(){
    const [from,to]=currentRange(), d=state.data.dashboard;
    $('#todayLabel').textContent=new Intl.DateTimeFormat(undefined,{weekday:'long',month:'long',day:'numeric'}).format(new Date()).toUpperCase();
    const summaries=d.summary||[];
    if(!summaries.length){
      const curr=localStorage.getItem('wealth.displayCurrency')||'EUR';
      $('#summaryCards').innerHTML=metric('Total balance',money((d.wallets||[]).filter(w=>w.currency===curr).reduce((a,w)=>a+Number(w.balance_minor),0),curr),'i-wallet','lav')+metric('Income',money(0,curr),'i-arrow-down','mint')+metric('Expenses',money(0,curr),'i-arrow-up','peach')+metric('Net cash flow',money(0,curr),'i-chart','blue');
    } else {
      const balanceGroups={};(d.wallets||[]).forEach(w=>balanceGroups[w.currency]=(balanceGroups[w.currency]||0)+Number(w.balance_minor));
      const balanceText=Object.entries(balanceGroups).map(([c,v])=>money(v,c)).join(' · ')||'—';
      const income=summaries.map(x=>money(x.income_minor,x.currency)).join(' · '),expense=summaries.map(x=>money(x.expense_minor,x.currency)).join(' · '),net=summaries.map(x=>money(x.net_minor,x.currency)).join(' · ');
      $('#summaryCards').innerHTML=metric('Total balance',balanceText,'i-wallet','lav')+metric('Income',income||'—','i-arrow-down','mint',`Since ${dateLabel(from,{month:'short',day:'numeric'})}`)+metric('Expenses',expense||'—','i-arrow-up','peach',`Through ${dateLabel(to,{month:'short',day:'numeric'})}`)+metric('Net cash flow',net||'—','i-chart','blue');
    }
    renderCashflow(d,from,to);renderBudgetMini(d.budgets||[]);renderWalletMini(d.wallets||[]);renderRecent(d.recent||[]);
  }
  function metric(label,value,glyph,tone,caption='Compared with the selected period'){
    const styles={lav:['#7d6ee7','#f0edff'],mint:['#43aa8a','#e6f7f0'],peach:['#e58e62','#fff0e7'],blue:['#5f91dc','#eaf1ff']}[tone];
    return `<article class="metric-card" style="--metric-color:${styles[0]};--metric-soft:${styles[1]};--metric-blob:${styles[1]}"><div class="metric-top"><span class="metric-label">${esc(label)}</span><span class="metric-icon">${icon(glyph.replace(/^i-/,''))}</span></div><div class="metric-value" title="${esc(value)}">${esc(value)}</div><div class="metric-caption">${esc(caption)}</div></article>`;
  }
  function renderCashflow(d,from,to){
    const rows=(d.summary||[]);const chart=$('#cashflowChart');
    if(!rows.length){chart.innerHTML=empty('Your first chapter starts here','Add a wallet and a transaction to see your cash flow.','chart');return;}
    chart.innerHTML=`<div class="cashflow-list">${rows.map(r=>{const max=Math.max(1,Number(r.income_minor),Number(r.expense_minor));return `<section class="cashflow-currency"><div class="cashflow-currency-head"><strong>${esc(r.currency)}</strong><small>${esc(dateLabel(from,{month:'short',day:'numeric'}))} – ${esc(dateLabel(to,{month:'short',day:'numeric'}))}</small></div><div class="cashflow-row"><span>Income</span><div class="cashflow-track"><i class="income" style="width:${Math.max(0,Number(r.income_minor)*100/max)}%"></i></div><strong>${esc(money(r.income_minor,r.currency))}</strong></div><div class="cashflow-row"><span>Expenses</span><div class="cashflow-track"><i class="expense" style="width:${Math.max(0,Number(r.expense_minor)*100/max)}%"></i></div><strong>${esc(money(r.expense_minor,r.currency))}</strong></div></section>`;}).join('')}</div>`;
  }
  function renderBudgetMini(budgets){
    const root=$('#dashboardBudgets');if(!budgets.length){root.innerHTML=empty('No budgets yet','Create one to give your plans a little shape.','chart');return;}
    root.innerHTML=budgets.map((b,i)=>`<div class="budget-row"><span class="budget-icon" style="--cat-color:${palettes[i%palettes.length][0]};--cat-soft:${palettes[i%palettes.length][1]}">${icon('chart')}</span><div class="budget-row-main"><strong>${esc(b.name)}</strong><small>${esc(b.scope==='overall'?'Overall':b.category_name||b.wallet_name||'Budget')}</small><div class="progress-track"><div class="progress-fill ${b.progress_percent>=90?'warning':''}" style="width:${Math.max(0,Math.min(100,b.progress_percent))}%"></div></div></div><span class="budget-value">${esc(money(b.spent_minor,b.currency))}<br><small>of ${esc(money(b.amount_minor,b.currency))}</small></span></div>`).join('');
  }
  function renderWalletMini(wallets){
    const root=$('#dashboardWallets');if(!wallets.length){root.innerHTML=empty('No wallets yet','Create a wallet to start your private ledger.','wallet');return;}
    root.innerHTML=wallets.slice(0,4).map((w,i)=>`<div class="wallet-mini-row"><span class="wallet-color" style="--wallet-color:${palettes[i%8][0]};--wallet-soft:${palettes[i%8][1]}">${icon(w.type==='cash'?'wallet':w.type==='credit'?'card':'wallet')}</span><span class="wallet-name-block"><strong>${esc(w.name)}</strong><small>${esc(w.type)} · ${esc(w.currency)}</small></span><span class="wallet-amount">${esc(money(w.balance_minor,w.currency))}</span></div>`).join('');
  }
  function txDescription(t){
    if(t.type==='transfer'){
      const opposite=t.transfer_side==='out'?t.destination_wallet_id:t.source_wallet_id;
      const other=(state.data.wallets||[]).find(w=>w.id===opposite);
      return t.transfer_side==='out'?`Transfer to ${other?.name||'another wallet'}`:`Transfer from ${other?.name||'another wallet'}`;
    }
    return t.description||t.payee||t.category_name||'Transaction';
  }
  function txGlyph(t){if(t.type==='income')return 'arrow-down';if(t.type==='transfer')return 'repeat';return 'bag';}
  function renderRecent(rows){
    const root=$('#recentTransactions');if(!rows.length){root.innerHTML=empty('Nothing here just yet','Your recent activity will appear here after your first entry.','list');return;}
    root.innerHTML=rows.slice(0,6).map(t=>`<div class="recent-row"><span class="recent-mark" style="--cat-color:${t.type==='income'?'#42a788':t.type==='transfer'?'#796fe0':'#dc7b87'};--cat-soft:${t.type==='income'?'#e7f6ef':t.type==='transfer'?'#efedff':'#fff0f2'}">${icon(txGlyph(t))}</span><span class="recent-label"><strong>${esc(txDescription(t))}</strong><small>${esc(t.wallet_name)} · ${dateLabel(t.transaction_date)}</small></span><span class="recent-amount ${t.type==='income'?'amount-income':t.type==='transfer'?'amount-transfer':'amount-expense'}">${t.type==='expense'?'−':t.type==='income'?'+':t.transfer_side==='out'?'−':'+'}${esc(money(t.amount_minor,t.currency))}</span></div>`).join('');
  }
  async function refresh(){
    try{state.data=await api('/api/bootstrap');updateCount();renderSelects();renderDashboard();if(state.page==='wallets')renderWallets();if(state.page==='budgets')renderBudgets();if(state.page==='categories')renderCategories();}
    catch(e){showFatal(e.message);}
  }
  function showFatal(message){$('#view-dashboard').innerHTML=`<div class="page-heading"><div><p class="eyebrow">LOCAL WORKSPACE</p><h1>Wealth is starting up</h1><p class="page-subtitle">${esc(message)}</p></div></div><article class="surface" style="padding:24px"><p>Keep this app on its local address, <strong>http://127.0.0.1:8000</strong>. Your financial records are not sent to a remote service.</p><button class="button button-primary" onclick="location.reload()">Try again</button></article>`;}
  function renderWallets(){
    if(!state.data)return;const all=state.data.wallets||[],active=all.filter(w=>!w.archived_at),archived=all.filter(w=>w.archived_at),root=$('#walletGrid');
    if(!active.length)root.innerHTML=empty('A wallet for every kind of money','Add a cash, checking, savings, credit, or other wallet.','wallet');
    else root.innerHTML=active.map((w,i)=>`<article class="surface wallet-card"><div class="wallet-card-top"><span class="wallet-color" style="--wallet-color:${palettes[i%8][0]};--wallet-soft:${palettes[i%8][1]}">${icon(w.type==='checking'?'wallet':w.type==='credit'?'card':'wallet')}</span><button class="icon-button small wallet-actions" data-action="edit-wallet" data-id="${esc(w.id)}" aria-label="Edit wallet">${icon('more')}</button></div><h3 title="${esc(w.name)}">${esc(w.name)}</h3><span class="wallet-type">${esc(w.type)} · ${esc(w.currency)}</span><div class="wallet-balance">${esc(money(w.balance_minor,w.currency))}</div><div class="wallet-balance-label">Current balance</div><div class="wallet-card-bottom"><span>Opening ${dateLabel(w.opening_date)}</span><button class="text-button" data-action="wallet-transactions" data-id="${esc(w.id)}">Activity ${icon('chevron')}</button></div></article>`).join('');
    const groups={};active.forEach(w=>groups[w.currency]=(groups[w.currency]||0)+Number(w.balance_minor));
    $('#walletCurrencyTotals').innerHTML=Object.keys(groups).length?Object.entries(groups).map(([c,v])=>`<span class="currency-total"><strong>${esc(money(v,c))}</strong><small>${esc(c)} · ${active.filter(w=>w.currency===c).length} wallet${active.filter(w=>w.currency===c).length===1?'':'s'}</small></span>`).join(''):empty('Nothing to total','Create a wallet to see balances grouped by currency.','wallet');
    $('#archivedWallets').innerHTML=archived.length?`<h2>Archived wallets</h2><div class="wallet-grid">${archived.map(w=>`<article class="surface wallet-card"><div class="wallet-card-top"><span class="wallet-color">${icon('wallet')}</span><button class="button button-secondary" data-action="unarchive-wallet" data-id="${esc(w.id)}">Restore</button></div><h3>${esc(w.name)}</h3><span class="wallet-type">Archived · ${esc(w.currency)}</span><div class="wallet-balance">${esc(money(w.balance_minor,w.currency))}</div></article>`).join('')}</div>`:'';
  }
  function renderBudgets(){
    if(!state.data)return;const budgets=state.data.budgets||[];
    const totalByCurrency={};budgets.forEach(b=>{const x=totalByCurrency[b.currency]||{amount:0,spent:0};x.amount+=Number(b.amount_minor);x.spent+=Number(b.spent_minor);totalByCurrency[b.currency]=x;});
    $('#budgetSummary').innerHTML=Object.keys(totalByCurrency).length?Object.entries(totalByCurrency).map(([c,x])=>`<article class="surface budget-summary-card"><small>PLANNED · ${esc(c)}</small><strong>${esc(money(x.amount,c))}</strong><small>${esc(money(x.spent,c))} spent across budgets</small></article>`).join(''):'';
    const root=$('#budgetGrid');if(!budgets.length){root.innerHTML=`<article class="surface">${empty('No budgets set up','Choose a period and spending scope to start planning.','chart')}</article>`;return;}
    root.innerHTML=budgets.map((b,i)=>`<article class="surface budget-detail-card"><div class="budget-row"><span class="budget-icon" style="--cat-color:${palettes[i%8][0]};--cat-soft:${palettes[i%8][1]}">${icon(b.scope==='category'?'tag':'chart')}</span><div class="budget-row-main"><strong>${esc(b.name)}</strong><small>${esc(b.scope==='overall'?'Overall':b.category_name||b.wallet_name||b.scope)}</small></div><button class="icon-button small" data-action="archive-budget" data-id="${esc(b.id)}" aria-label="Archive budget">${icon('more')}</button></div><div class="progress-track"><div class="progress-fill ${b.progress_percent>=90?'warning':''}" style="width:${Math.max(0,Math.min(100,b.progress_percent))}%"></div></div><div class="budget-row-main" style="margin-top:8px"><strong>${esc(money(b.spent_minor,b.currency))} <span class="muted-inline">spent</span></strong></div><div class="budget-meta"><div><small>Remaining</small><strong>${esc(money(b.remaining_minor,b.currency))}</strong></div><div><small>Limit</small><strong>${esc(money(b.amount_minor,b.currency))}</strong></div><div><small>Period</small><strong>${dateLabel(b.start_date,{month:'short',day:'numeric'})} – ${dateLabel(b.end_date,{month:'short',day:'numeric'})}</strong></div></div></article>`).join('');
  }
  function renderCategories(){
    if(!state.data)return;const cats=(state.data.categories||[]).filter(c=>!c.archived_at);const root=$('#categoryGroups');
    root.innerHTML=['expense','income'].map(kind=>{const rows=cats.filter(c=>c.kind===kind||c.kind==='both');return `<article class="surface category-group"><div class="section-heading"><div><p class="eyebrow">${kind==='expense'?'MONEY OUT':'MONEY IN'}</p><h2>${kind==='expense'?'Expense categories':'Income categories'}</h2></div><span class="state-chip muted">${rows.length}</span></div><div class="category-list">${rows.map((c,i)=>{const parent=(state.data.categories||[]).find(p=>p.id===c.parent_id);return `<div class="category-manage-row"><span class="category-icon" style="--cat-color:${esc(c.color||palettes[i%8][0])};--cat-soft:${esc(c.color||palettes[i%8][0])}20">${icon(c.icon||'circle')}</span><span><strong>${c.parent_id?'↳ ':''}${esc(c.name)}</strong><small>${parent?`Under ${esc(parent.name)} · `:''}${c.is_system?'Default':'Custom'}</small></span><button class="icon-button small" data-action="edit-category" data-id="${esc(c.id)}" aria-label="Edit category">${icon('more')}</button></div>`;}).join('')||empty('No categories yet','Create one to organize your activity.','tag')}</div></article>`;}).join('');
  }
  async function loadTransactions(){
    if(!state.data)return;const params=new URLSearchParams({limit:String(state.transactionLimit),offset:String(state.transactionOffset)});
    const search=$('#transactionSearch').value||$('#globalSearch').value;
    if(search)params.set('q',search);if($('#filterWallet').value)params.set('wallet_id',$('#filterWallet').value);if($('#filterType').value)params.set('type',$('#filterType').value);if($('#filterCategory').value)params.set('category_id',$('#filterCategory').value);
    try{const result=await api('/api/transactions?'+params);state.data.transactions=result;updateCount();renderTransactionRows(result);}catch(e){fail(e);}
  }
  function renderTransactionRows(result){
    const root=$('#transactionRows');if(!result.items.length){root.innerHTML=`<tr><td colspan="6">${empty('No transactions found','Try another filter or add your first transaction.','list')}</td></tr>`;}
    else root.innerHTML=result.items.map(t=>`<tr><td><span class="transaction-cell"><span class="recent-mark">${icon(txGlyph(t))}</span><span><strong>${esc(txDescription(t))}</strong><small>${esc(t.type==='transfer'?'Transfer':t.payee||t.category_name||t.type)}</small></span></span></td><td>${esc(t.wallet_name)}</td><td><span class="category-pill"><i style="--cat-color:${esc((state.data.categories.find(c=>c.id===t.category_id)||{}).color||'#9389e9')}"></i>${esc(t.category_name|| (t.type==='transfer'?'Transfer':'Uncategorized'))}</span></td><td>${dateLabel(t.transaction_date,{month:'short',day:'numeric',year:'numeric'})}</td><td class="align-right ${t.type==='income'?'amount-income':t.type==='transfer'?'amount-transfer':'amount-expense'}">${t.type==='expense'?'−':t.type==='income'?'+':t.transfer_side==='out'?'−':'+'}${esc(money(t.amount_minor,t.currency))}</td><td><button class="icon-button small" data-action="edit-transaction" data-id="${esc(t.id)}" aria-label="Edit transaction">${icon('more')}</button></td></tr>`).join('');
    const start=result.total?result.offset+1:0,end=Math.min(result.offset+result.limit,result.total);$('#transactionSummary').textContent=`Showing ${start}–${end} of ${result.total}`;$('#pageLabel').textContent=`${Math.floor(result.offset/result.limit)+1}`;$('#pagePrev').disabled=result.offset===0;$('#pageNext').disabled=end>=result.total;
  }
  async function loadReports(){
    const from=$('#reportFrom'),to=$('#reportTo');if(!from.value)from.value=monthStart();if(!to.value)to.value=new Date().toISOString().slice(0,10);
    try{const r=await api('/api/reports?'+new URLSearchParams({from:from.value,to:to.value}));state.report=r;renderReports(r);}catch(e){fail(e);}
  }
  function renderReports(r){
    const totals={};r.monthly.forEach(m=>{const t=totals[m.currency]||{income:0,expense:0};t.income+=Number(m.income_minor);t.expense+=Number(m.expense_minor);totals[m.currency]=t;});
    $('#reportSummary').innerHTML=Object.keys(totals).length?Object.entries(totals).map(([c,v])=>metric(`Income · ${c}`,money(v.income,c),'arrow-down','mint')+metric(`Expenses · ${c}`,money(v.expense,c),'arrow-up','peach')+metric(`Net · ${c}`,money(v.income-v.expense,c),'chart','lav')).join(''):metric('Income','—','arrow-down','mint')+metric('Expenses','—','arrow-up','peach')+metric('Net','—','chart','lav');
    const cats=r.categories;const max=Math.max(1,...cats.map(x=>Number(x.amount_minor)));$('#categoryReport').innerHTML=cats.length?cats.map((x,i)=>`<div class="bar-row"><span class="bar-row-label">${esc(x.name)}</span><span class="bar-track"><i class="bar-fill" style="display:block;width:${Number(x.amount_minor)*100/max}%;background:${palettes[i%8][0]}"></i></span><strong class="bar-value">${esc(money(x.amount_minor,x.currency))}</strong></div>`).join(''):empty('No spending to chart','Expense categories will appear here after you add activity.','pie');
    const months=r.monthly;$('#monthlyReport').innerHTML=months.length?months.map(m=>`<div class="monthly-row"><strong>${esc(m.month)}</strong><span class="monthly-track"><i style="width:${Math.max(3,Math.min(100,Number(m.income_minor)*100/Math.max(1,Number(m.income_minor),Number(m.expense_minor))))}%"></i></span><span class="monthly-track expense"><i style="width:${Math.max(3,Math.min(100,Number(m.expense_minor)*100/Math.max(1,Number(m.income_minor),Number(m.expense_minor))))}%"></i></span></div><div class="monthly-amounts"><small>${esc(m.currency)} · income ${esc(money(m.income_minor,m.currency))}</small><small>expense ${esc(money(m.expense_minor,m.currency))}</small></div>`).join(''):empty('A little time makes a trend','Monthly cash flow appears when there is activity in the selected period.','chart');
    const w=r.wallets.filter(x=>Number(x.expense_minor)>0),mx=Math.max(1,...w.map(x=>Number(x.expense_minor)));$('#walletReport').innerHTML=w.length?w.map((x,i)=>`<div class="bar-row"><span class="bar-row-label">${esc(x.name)}</span><span class="bar-track"><i class="bar-fill" style="display:block;width:${Number(x.expense_minor)*100/mx}%;background:${palettes[i%8][0]}"></i></span><strong class="bar-value">${esc(money(x.expense_minor,x.currency))}</strong></div>`).join(''):empty('No wallet spending yet','Wallet spending is grouped by each wallet currency.','wallet');
  }
  function renderSettings(){
    const prefs=JSON.parse(localStorage.getItem('wealth.preferences')||'{}');$('#displayCurrency').value=prefs.currency||localStorage.getItem('wealth.displayCurrency')||'EUR';$('#themeSelect').value=prefs.theme||'light';$('#weekStart').value=prefs.weekStart||'monday';
  }
  function modal(title,subtitle,fields,submitLabel='Save',wide=false){
    $('#modalRoot').innerHTML=`<div class="modal-backdrop" data-backdrop><section class="modal ${wide?'wide':''}" role="dialog" aria-modal="true" aria-labelledby="modalTitle"><div class="modal-head"><div><p class="eyebrow">PRIVATE LEDGER</p><h2 id="modalTitle">${esc(title)}</h2>${subtitle?`<p>${esc(subtitle)}</p>`:''}</div><button type="button" class="modal-close" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><form class="modal-form" id="activeForm">${fields}<div class="modal-actions"><button class="button button-quiet" type="button" data-action="close-modal">Cancel</button><button class="button button-primary" type="submit">${esc(submitLabel)}</button></div></form></section></div>`;
    const first=$('input,select,textarea,button', $('#activeForm'));if(first)first.focus();
  }
  function field(label,name,value='',type='text',extra=''){
    const id='f_'+name;
    if(type==='select')return `<div class="field ${extra.includes('full')?'full':''}"><label for="${id}">${esc(label)}</label><select id="${id}" name="${esc(name)}" ${extra.replace('full','')}>${value}</select></div>`;
    if(type==='textarea')return `<div class="field full"><label for="${id}">${esc(label)}</label><textarea id="${id}" name="${esc(name)}" maxlength="1000">${esc(value)}</textarea></div>`;
    if(type==='checkbox')return `<label class="toggle-field"><input type="checkbox" name="${esc(name)}" ${value?'checked':''}>${esc(label)}</label>`;
    return `<div class="field ${extra.includes('full')?'full':''}"><label for="${id}">${esc(label)}</label><input id="${id}" name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" ${type==='number'?'min="0.01" step="0.01"':''} ${extra.replace('full','')}></div>`;
  }
  function formData(form){const fd=new FormData(form),out={};for(const [k,v] of fd.entries())out[k]=v;for(const el of $$('input[type=checkbox]',form))out[el.name]=el.checked;return out;}
  function openTransaction(record=null){
    const t=record||{},type=t.type==='income'?'income':'expense';
    if(t.type==='transfer'){openTransferEditor(t);return;}
    const wallet=t.wallet_id||state.data.wallets.find(w=>!w.archived_at)?.id||'';
    const currencies=state.data.wallets.filter(w=>!w.archived_at).map(w=>w.currency).filter((x,i,a)=>a.indexOf(x)===i);
    const fields=`${field('Type','type',`<option value="expense"${selected(type,'expense')}>Expense</option><option value="income"${selected(type,'income')}>Income</option>`,'select')}${field('Wallet','wallet_id',walletOptions(wallet),'select','required')}${field('Amount','amount',t.amount_minor!=null?major(t.amount_minor,t.currency):'','number','inputmode="decimal" required')}${field('Date','transaction_date',t.transaction_date||new Date().toISOString().slice(0,10),'date','required')}${field('Category','category_id',categoryOptions(t.category_id,type),'select')}${field('Payee','payee',t.payee||'','text','maxlength="120"')}${field('Description','description',t.description||'','text','full maxlength="180"')}${field('Notes','notes',t.notes||'','textarea')}`;
    modal(record?'Edit transaction':'Add transaction','Enter one item at a time. Transfers use a separate atomic flow.',fields,record?'Save changes':'Save transaction');
    $('#activeForm').dataset.kind=record?'transaction-edit':'transaction-create';$('#activeForm').dataset.id=record?.id||'';
    if(record)$('#activeForm .modal-actions').insertAdjacentHTML('afterbegin',`<button type="button" class="button button-danger" style="margin-right:auto" data-action="request-delete" data-id="${esc(record.id)}">Delete</button>`);
    $('#f_type').addEventListener('change',e=>{$('#f_category_id').innerHTML=categoryOptions('',e.target.value);});
    $('#f_wallet_id').addEventListener('change',e=>{const w=state.data.wallets.find(x=>x.id===e.target.value);$('#f_amount').placeholder=w?`Amount in ${w.currency}`:'';});
    if(!record){const footer=$('#activeForm .modal-actions');footer.insertAdjacentHTML('afterbegin','<button type="button" class="button button-secondary" data-action="add-transfer">Transfer</button>');}
  }
  function major(minor,currency){const exp=currencyExponent(currency),n=BigInt(minor),base=10n**BigInt(exp),abs=n<0n?-n:n;return exp?`${n<0n?'-':''}${abs/base}.${(abs%base).toString().padStart(exp,'0')}`:`${n}`;}
  function openTransfer(){
    const wallets=state.data.wallets.filter(w=>!w.archived_at);const first=wallets[0]?.id||'',second=wallets.find(w=>w.id!==first)?.id||'';
    const fields=`${field('From wallet','source_wallet_id',walletOptions(first),'select','required')}${field('To wallet','destination_wallet_id',walletOptions(second),'select','required')}${field('Amount','amount','','number','required inputmode="decimal"')}${field('Date','transaction_date',new Date().toISOString().slice(0,10),'date','required')}${field('Note','note','','text','full maxlength="180"')}`;
    modal('Move between wallets','The paired ledger entries are saved together. Transfers are excluded from income and expense totals.',fields,'Save transfer');$('#activeForm').dataset.kind='transfer-create';
  }
  function openTransferEditor(t){
    const fields=`${field('From wallet','source_wallet_id',walletOptions(t.source_wallet_id),'select','required')}${field('To wallet','destination_wallet_id',walletOptions(t.destination_wallet_id),'select','required')}${field('Amount','amount',major(t.amount_minor,t.currency),'number','required')}${field('Date','transaction_date',t.transaction_date,'date','required')}${field('Note','note',t.note||'','text','full maxlength="180"')}`;
    modal('Edit transfer','Both ledger entries update atomically.',fields,'Save transfer');$('#activeForm').dataset.kind='transfer-edit';$('#activeForm').dataset.id=t.transfer_id;
  }
  function openWallet(wallet=null){
    const w=wallet||{};const types=['cash','checking','savings','credit','other'];const currencies=state.data.currencies.map(c=>c.code);
    const fields=`${field('Wallet name','name',w.name||'','text','required maxlength="80"')}${field('Type','type',types.map(x=>`<option value="${x}"${selected(w.type||'cash',x)}>${x[0].toUpperCase()+x.slice(1)}</option>`).join(''),'select')}${field('Currency','currency',currencies.map(x=>`<option value="${x}"${selected(w.currency||'EUR',x)}>${x}</option>`).join(''),'select')}${field('Opening balance','opening_balance',w.opening_balance_minor!=null?major(w.opening_balance_minor,w.currency):'0','number','required inputmode="decimal"')}${field('Opening date','opening_date',w.opening_date||new Date().toISOString().slice(0,10),'date','required')}${w.id?field('Archived','archived',Boolean(w.archived_at),'checkbox'):''}`;
    modal(w.id?'Edit wallet':'Create wallet','Balances are derived from opening balance and ledger activity.',fields,w.id?'Save changes':'Create wallet');$('#activeForm').dataset.kind=w.id?'wallet-edit':'wallet-create';$('#activeForm').dataset.id=w.id||'';
    $('#f_currency').addEventListener('change',()=>{$('#f_opening_balance').step=currencyExponent($('#f_currency').value)===0?'1':'0.01';});
  }
  function openCategory(cat=null){
    const c=cat||{};const kinds=['expense','income','both'];const icons=['home','utensils','train','bag','heart','bolt','briefcase','plane','circle','sparkle','tag','wallet'];const parents=(state.data.categories||[]).filter(x=>!x.archived_at&&!x.parent_id&&x.id!==c.id);
    const parentOptions=`<option value="">No parent</option>${parents.map(x=>`<option value="${esc(x.id)}"${selected(c.parent_id||'',x.id)}>${esc(x.name)}</option>`).join('')}`;
    const fields=`${field('Name','name',c.name||'','text','required maxlength="60"')}${field('Applies to','kind',kinds.map(x=>`<option value="${x}"${selected(c.kind||'expense',x)}>${x==='both'?'Both income & expense':x}</option>`).join(''),'select')}${field('Parent category','parent_id',parentOptions,'select')}${field('Icon','icon',icons.map(x=>`<option value="${x}"${selected(c.icon||'circle',x)}>${x}</option>`).join(''),'select')}${field('Color','color',c.color||'#8877e8','color')}${c.id?field('Archived','archived',Boolean(c.archived_at),'checkbox'):''}`;
    modal(c.id?'Edit category':'New category','Archived categories stay attached to older transactions.',fields,c.id?'Save changes':'Create category');$('#activeForm').dataset.kind=c.id?'category-edit':'category-create';$('#activeForm').dataset.id=c.id||'';
  }
  function openBudget(){
    const fields=`${field('Budget name','name','','text','required maxlength="80"')}${field('Period','period','<option value="monthly">Calendar month</option><option value="custom">Custom dates</option>','select')}${field('Amount','amount','','number','required inputmode="decimal"')}${field('Currency','currency',state.data.currencies.map(c=>`<option value="${c.code}"${selected(c.code,localStorage.getItem('wealth.displayCurrency')||'EUR')}>${c.code}</option>`).join(''),'select')}${field('Scope','scope','<option value="overall">Overall</option><option value="category">Category</option><option value="wallet">Wallet</option>','select')}${field('Category','category_id',categoryOptions('', 'expense'),'select')}${field('Wallet','wallet_id',walletOptions(),'select')}${field('Start date','start_date',monthStart(),'date','required')}${field('End date','end_date',monthEnd(),'date','required')}<p class="field-hint full">Budgets cover the selected date range. Rollover is not supported.</p>`;
    modal('Create a budget','Counts expenses by transaction date; transfers are not spending.',fields,'Create budget');$('#activeForm').dataset.kind='budget-create';
    $('#f_scope').addEventListener('change',e=>{$('#f_category_id').closest('.field').classList.toggle('hidden',e.target.value!=='category');$('#f_wallet_id').closest('.field').classList.toggle('hidden',e.target.value!=='wallet');});
    const updateMonthlyEnd=()=>{if($('#f_period').value==='monthly'&&$('#f_start_date').value)$('#f_end_date').value=monthEnd(new Date($('#f_start_date').value+'T00:00:00'));};
    $('#f_period').addEventListener('change',updateMonthlyEnd);$('#f_start_date').addEventListener('change',updateMonthlyEnd);
  }
  function openDeleteConfirm(tx){
    const transfer=tx.type==='transfer';const id=transfer?tx.transfer_id:tx.id;
    $('#modalRoot').innerHTML=`<div class="modal-backdrop"><section class="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirmTitle"><div class="modal-head"><div><p class="eyebrow">PLEASE CONFIRM</p><h2 id="confirmTitle">${transfer?'Remove this transfer?':'Delete this transaction?'}</h2></div><button class="modal-close" data-action="close-modal" aria-label="Close dialog">${icon('close')}</button></div><p class="dialog-message">${transfer?'Both linked transfer entries will be removed together.':'This entry will be hidden from totals and lists. The action can’t be undone in this version.'}</p><div class="modal-actions"><button class="button button-quiet" data-action="close-modal">Cancel</button><button class="button button-danger" data-action="confirm-delete" data-kind="${transfer?'transfer':'transaction'}" data-id="${esc(id)}">${transfer?'Remove transfer':'Delete transaction'}</button></div></section></div>`;
  }
  function openBackupCreate(){
    const fields=`${field('Backup passphrase','passphrase','','password','required minlength="12" maxlength="1024" autocomplete="new-password"')}${field('Confirm passphrase','confirm','','password','required minlength="12" maxlength="1024" autocomplete="new-password"')}<div class="field full"><span class="field-hint">The passphrase is never stored. If you lose it, the backup cannot be recovered.</span></div>`;
    modal('Create encrypted backup','A private archive you can save anywhere, including pCloud.',fields,'Encrypt & download');$('#activeForm').dataset.kind='backup-create';
  }
  function openRestorePassphrase(){
    const fields=`<div class="field full"><label>Selected encrypted file</label><input value="${esc(state.restore?.fileName||'Backup file')}" readonly></div>${field('Passphrase','passphrase','','password','required autocomplete="current-password"')}`;
    modal('Unlock backup','We’ll validate it and show a preview before any records are changed.',fields,'Preview restore');$('#activeForm').dataset.kind='backup-preview';
  }
  async function onSubmit(form){
    const kind=form.dataset.kind,data=formData(form),id=form.dataset.id;
    const idem=form.dataset.idempotencyKey||(form.dataset.idempotencyKey=(crypto.randomUUID?crypto.randomUUID():`${Date.now()}-${Math.random().toString(36).slice(2)}`));
    const savePost=(path,body)=>api(path,{...json('POST',body),headers:{'Idempotency-Key':idem}});
    try{
      if(kind==='transaction-create')await savePost('/api/transactions',data);
      if(kind==='transaction-edit')await api('/api/transactions/'+encodeURIComponent(id),json('PATCH',data));
      if(kind==='transfer-create')await savePost('/api/transfers',data);
      if(kind==='transfer-edit')await api('/api/transfers/'+encodeURIComponent(id),json('PATCH',data));
      if(kind==='wallet-create')await api('/api/wallets',json('POST',data));
      if(kind==='wallet-edit')await api('/api/wallets/'+encodeURIComponent(id),json('PATCH',{...data,archived:Boolean(data.archived)}));
      if(kind==='category-create')await api('/api/categories',json('POST',data));
      if(kind==='category-edit')await api('/api/categories/'+encodeURIComponent(id),json('PATCH',{...data,archived:Boolean(data.archived)}));
      if(kind==='budget-create')await api('/api/budgets',json('POST',data));
      if(kind==='backup-create'){
        if(data.passphrase!==data.confirm)throw new Error('The passphrases do not match.');
        const response=await api('/api/backup/create',{...json('POST',{passphrase:data.passphrase}),raw:true});
        const blob=await response.blob();downloadBlob(blob,'wealth-app-backup.wbackup');toast('Encrypted backup created. Keep the passphrase somewhere safe.','success');closeModal();return;
      }
      if(kind==='backup-preview'){
        if(!state.restore?.content)throw new Error('Choose a backup file first.');
        const result=await api('/api/backup/preview',json('POST',{content_base64:state.restore.content,passphrase:data.passphrase}));
        state.restore.preview=result.preview;state.restore.payload=result.payload;state.restore.passphrase=data.passphrase;closeModal();renderRestorePreview();return;
      }
      closeModal();await refresh();if(state.page==='transactions')await loadTransactions();toast(kind?.includes('edit')?'Changes saved.':'Saved on this device.','success');
    }catch(e){showFormError(form,e.message);}
  }
  function showFormError(form,message){let node=$('.form-error',form);if(!node){node=document.createElement('div');node.className='form-error';form.prepend(node);}node.textContent=message;}
  function closeModal(){ $('#modalRoot').innerHTML=''; }
  function downloadBlob(blob,name){const a=document.createElement('a');const url=URL.createObjectURL(blob);a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  function renderImportReview(review){
    state.review=review;const root=$('#importReview'),rows=review.rows||[];
    root.innerHTML=`<article class="surface review-panel"><div class="review-top"><div><p class="eyebrow">STAGED · NOT SAVED</p><h2>Review ${rows.length} candidate row${rows.length===1?'':'s'}</h2><p>${review.accepted_count} ready · ${review.review_count} need your attention. Nothing is saved until you confirm.</p></div><button class="icon-button" data-action="cancel-import" aria-label="Cancel import">${icon('close')}</button></div><div class="review-scroll"><table class="review-table"><thead><tr><th>INCLUDE</th><th>DATE</th><th>TYPE</th><th>AMOUNT</th><th>WALLET</th><th>CATEGORY</th><th>DESCRIPTION</th><th>NOTES</th><th>REVIEW</th></tr></thead><tbody>${rows.map(r=>`<tr data-row-id="${esc(r.id)}"><td><input type="checkbox" data-col="accepted" ${r.accepted?'checked':''} aria-label="Include row ${r.row_number}"></td><td><input data-col="transaction_date" type="date" value="${esc(r.transaction_date||'')}"></td><td><select data-col="type"><option value="expense"${selected(r.type,'expense')}>Expense</option><option value="income"${selected(r.type,'income')}>Income</option></select></td><td><input data-col="amount" inputmode="decimal" value="${r.amount_minor!=null?esc(major(r.amount_minor,r.currency)):''}" aria-label="Amount"></td><td><select data-col="wallet_id">${walletOptions(r.wallet_id)}</select></td><td><select data-col="category_id">${categoryOptions(r.category_id,r.type)}</select></td><td><input data-col="description" maxlength="180" value="${esc(r.description||'')}" aria-label="Description"></td><td><input data-col="notes" maxlength="500" value="${esc(r.notes||'')}" aria-label="Notes"></td><td><span class="review-warn">${esc((r.warnings||[]).join(' · ')||'Ready')}</span></td></tr>`).join('')}</tbody></table></div><div class="review-actions"><span class="field-hint" style="margin-right:auto">Possible duplicates are flagged; verify before including.</span><button class="button button-quiet" data-action="cancel-import">Discard</button><button class="button button-primary" data-action="commit-import">Save selected rows</button></div></article>`;
  }
  function gatherReviewRows(){
    return $$('#importReview tbody tr').map(row=>{
      const val=name=>row.querySelector(`[data-col="${name}"]`);
      const w=state.data.wallets.find(x=>x.id===val('wallet_id').value);
      let minor=null;try{if(val('amount').value)minor=toMinorClient(val('amount').value,w?.currency||'EUR')}catch(_){ }
      return {id:row.dataset.rowId,accepted:val('accepted').checked,transaction_date:val('transaction_date').value,type:val('type').value,
        amount_minor:minor,currency:w?.currency||'EUR',wallet_id:val('wallet_id').value,category_id:val('category_id').value||null,description:val('description').value,notes:val('notes').value};
    });
  }
  function toMinorClient(value,currency){const exp=currencyExponent(currency),s=String(value).trim();if(!/^\d+(?:\.\d+)?$/.test(s))throw new Error('Invalid amount');const [whole,frac='']=s.split('.');if(frac.length>exp)throw new Error('Precision');return Number(BigInt(whole)*10n**BigInt(exp)+BigInt((frac+'0'.repeat(exp)).slice(0,exp)||'0'));}
  function renderRestorePreview(){
    const p=state.restore?.preview;if(!p)return;const root=$('#importReview');
    const rows=Object.entries(p.counts).map(([table,count])=>`<div class="setting-row"><span><strong>${esc(table.replace(/_/g,' '))}</strong></span><span>${count} records · ${p.conflicts[table]} matching IDs already on this device</span></div>`).join('');
    root.innerHTML=`<article class="surface review-panel"><div class="review-top"><div><p class="eyebrow">RESTORE PREVIEW · NOT APPLIED</p><h2>Review backup contents</h2><p>Choose merge to add records with new IDs. Existing IDs are kept. Replacement clears current records and requires an additional typed confirmation.</p></div></div>${rows}<div class="review-actions"><button class="button button-quiet" data-action="clear-restore">Cancel</button><button class="button button-secondary" data-action="restore-merge">Merge new records</button><button class="button button-danger" data-action="restore-replace">Replace my data…</button></div></article>`;
  }
  async function restore(mode){
    if(!state.restore) return;let confirmation;
    if(mode==='replace'){confirmation=prompt('This replaces all current local records. Type REPLACE MY DATA to continue.');if(confirmation!=='REPLACE MY DATA')return;}
    try{const result=await api('/api/backup/restore',json('POST',{content_base64:state.restore.content,passphrase:state.restore.passphrase,mode,confirmation}));state.restore=null;$('#importReview').innerHTML='';await refresh();toast(`${result.inserted.transactions} transactions restored. Review complete.`,'success');}
    catch(e){fail(e);}
  }
  async function exportCsv(){
    const q=new URLSearchParams();if($('#exportFrom').value)q.set('from',$('#exportFrom').value);if($('#exportTo').value)q.set('to',$('#exportTo').value);
    try{const res=await api('/api/transactions/export.csv?'+q,{raw:true});downloadBlob(await res.blob(),'wealth-app-transactions.csv');toast('CSV exported. Store the file somewhere private.','success');}catch(e){fail(e);}
  }
  async function onClick(e){
    const go=e.target.closest('[data-go]');if(go){setPage(go.dataset.go);return;}
    const nav=e.target.closest('[data-page]');if(nav){e.preventDefault();setPage(nav.dataset.page);return;}
    const action=e.target.closest('[data-action]');if(!action)return;
    const id=action.dataset.id, kind=action.dataset.action;
    if(kind==='close-modal'){closeModal();return;}
    if(kind==='add-transaction'){openTransaction();return;}
    if(kind==='add-transfer'){openTransfer();return;}
    if(kind==='add-wallet'){openWallet();return;}
    if(kind==='add-category'){openCategory();return;}
    if(kind==='add-budget'){openBudget();return;}
    if(kind==='privacy-info'){setPage('settings');return;}
    if(kind==='dashboard-more'){toast('Choose a date range from the control above.');return;}
    if(kind==='clear-filters'){$('#transactionSearch').value='';$('#globalSearch').value='';$('#filterWallet').value='';$('#filterType').value='';$('#filterCategory').value='';state.transactionOffset=0;loadTransactions();return;}
    if(kind==='edit-wallet'){const w=state.data.wallets.find(x=>x.id===id);if(w)openWallet(w);return;}
    if(kind==='unarchive-wallet'){const w=state.data.wallets.find(x=>x.id===id);if(w){try{await api('/api/wallets/'+encodeURIComponent(id),json('PATCH',{name:w.name,type:w.type,currency:w.currency,opening_balance:major(w.opening_balance_minor,w.currency),opening_date:w.opening_date,archived:false}));await refresh();}catch(err){fail(err);}}return;}
    if(kind==='wallet-transactions'){$('#filterWallet').value=id;setPage('transactions');return;}
    if(kind==='edit-category'){const c=state.data.categories.find(x=>x.id===id);if(c)openCategory(c);return;}
    if(kind==='archive-budget'){const b=state.data.budgets.find(x=>x.id===id);if(b){if(confirm('Archive this budget? Its history will remain.')){try{await api('/api/budgets/'+encodeURIComponent(id),json('PATCH',{name:b.name,archived:true}));await refresh();toast('Budget archived.','success');}catch(err){fail(err);}}}return;}
    if(kind==='edit-transaction'){
      const current=state.data.transactions.items?.find(x=>x.id===id);let t=current;
      if(!t){try{const data=await api('/api/transactions?limit=200');t=data.items.find(x=>x.id===id);}catch(err){fail(err);return;}}
      if(t)openTransaction(t);return;
    }
    if(kind==='request-delete'){
      let t=state.data.transactions.items?.find(x=>x.id===id);
      if(!t){try{const page=await api('/api/transactions?limit=200');t=page.items.find(x=>x.id===id);}catch(err){fail(err);return;}}
      if(t)openDeleteConfirm(t);return;
    }
    if(kind==='confirm-delete'){
      try{await api(`/api/${action.dataset.kind==='transfer'?'transfers':'transactions'}/${encodeURIComponent(id)}`,{method:'DELETE'});closeModal();await refresh();if(state.page==='transactions')await loadTransactions();toast('Entry removed from your ledger.','success');}catch(err){fail(err);}return;
    }
    if(kind==='cancel-import'){
      const batch=state.review?.batch_id;if(batch){try{await api(`/api/imports/${encodeURIComponent(batch)}/cancel`,json('POST',{}));}catch(err){fail(err);}}
      state.review=null;$('#importReview').innerHTML='';return;
    }
    if(kind==='commit-import'){
      if(!state.review)return;try{const rows=gatherReviewRows();const result=await api(`/api/imports/${encodeURIComponent(state.review.batch_id)}/commit`,json('POST',{rows}));state.review=null;$('#importReview').innerHTML='';await refresh();toast(`${result.accepted_count} rows saved.`,`success`);}catch(err){fail(err);}return;
    }
    if(kind==='backup-create'){openBackupCreate();return;}
    if(kind==='clear-restore'){state.restore=null;$('#importReview').innerHTML='';return;}
    if(kind==='restore-merge'){restore('merge');return;}
    if(kind==='restore-replace'){restore('replace');return;}
    if(kind==='export-csv'){exportCsv();return;}
    if(kind==='save-preferences'){
      const prefs={currency:$('#displayCurrency').value,theme:$('#themeSelect').value,weekStart:$('#weekStart').value};localStorage.setItem('wealth.preferences',JSON.stringify(prefs));localStorage.setItem('wealth.displayCurrency',prefs.currency);document.body.dataset.theme=prefs.theme==='system'?'system':prefs.theme;toast('Preferences saved on this device.','success');return;
    }
  }
  async function onFile(e){
    const file=e.target.files?.[0];if(!file)return;e.target.value='';
    try{
      if(e.target.id==='csvFile'){
        if(file.size>2*1024*1024)throw new Error('CSV file is too large. Limit is 2 MB.');
        const content=await file.text();const result=await api('/api/imports/csv/preview',json('POST',{file_name:file.name,content}));renderImportReview(result);toast('Import preview ready. No rows have been saved.');
      } else if(e.target.id==='pdfFile'){
        if(file.size>8*1024*1024)throw new Error('PDF file is too large. Limit is 8 MB.');
        const wallet=$('#pdfWallet').value;if(!wallet)throw new Error('Choose a destination wallet first.');
        const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
        const result=await api('/api/imports/pdf/preview',json('POST',{file_name:file.name,content_base64:btoa(binary),wallet_id:wallet,currency:$('#pdfCurrency').value.toUpperCase()}));renderImportReview(result);toast('PDF candidates extracted locally. Review every row before saving.');
      } else if(e.target.id==='backupFile'){
        if(file.size>12*1024*1024)throw new Error('Backup file is too large. Limit is 12 MB.');
        const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));
        state.restore={fileName:file.name,content:btoa(binary)};openRestorePassphrase();
      }
    }catch(err){fail(err);}
  }
  let searchTimer;
  function bind(){
    document.addEventListener('click',e=>{onClick(e).catch(fail);if(e.target.matches('[data-backdrop]'))closeModal();});
    document.addEventListener('submit',e=>{if(e.target.id==='activeForm'){e.preventDefault();onSubmit(e.target);}});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&$('#modalRoot').innerHTML)closeModal();if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='k'){e.preventDefault();$('#globalSearch').focus();}});
    ['transactionSearch','filterWallet','filterType','filterCategory'].forEach(id=>$('#'+id).addEventListener(id==='transactionSearch'?'input':'change',()=>{state.transactionOffset=0;clearTimeout(searchTimer);searchTimer=setTimeout(loadTransactions,180);}));
    $('#globalSearch').addEventListener('input',()=>{if(state.page!=='transactions')setPage('transactions');$('#transactionSearch').value=$('#globalSearch').value;clearTimeout(searchTimer);searchTimer=setTimeout(loadTransactions,180);});
    $('#dashboardRange').addEventListener('change',()=>{if(state.data){const [from,to]=currentRange();api('/api/reports?'+new URLSearchParams({from,to})).then(()=>refresh()).catch(fail);}});
    $('#pagePrev').addEventListener('click',()=>{state.transactionOffset=Math.max(0,state.transactionOffset-state.transactionLimit);loadTransactions();});
    $('#pageNext').addEventListener('click',()=>{state.transactionOffset+=state.transactionLimit;loadTransactions();});
    $('#refreshReport').addEventListener('click',loadReports);
    ['csvFile','pdfFile','backupFile'].forEach(id=>$('#'+id).addEventListener('change',onFile));
  }
  function boot(){
    const prefs=JSON.parse(localStorage.getItem('wealth.preferences')||'{}');document.body.dataset.theme=prefs.theme||'light';
    if('serviceWorker' in navigator)navigator.serviceWorker.register('/service-worker.js').catch(()=>{});
    bind();setPage(location.hash.slice(1)||'dashboard');refresh();
    window.addEventListener('hashchange',()=>{const page=location.hash.slice(1);if(page&&page!==state.page)setPage(page);});
    window.addEventListener('online',()=>toast('Connection to the local app restored.','success'));
  }
  boot();
})();
