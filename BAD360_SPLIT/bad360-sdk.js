/**
 * BAD360.ai — Frontend SDK v4.1
 * Auth + AI + API helpers shared across all suite pages.
 *
 * Included via <script src="bad360-sdk.js"></script> in every page.
 * Works when served by FastAPI (same-origin) OR opened locally
 * (falls back to http://localhost:8000).
 */
(function () {
  'use strict';

  // ── Auto-detect API base ─────────────────────────────────────────────
  const API = window.location.protocol === 'file:'
    ? 'http://localhost:8000'
    : '';

  const LS = {
    TOKEN : 'bad360_token',
    USER  : 'bad360_user',
    STORE : 'bad360_store',   // generic localStorage data store
  };

  // ── Storage helpers ──────────────────────────────────────────────────
  function getToken()  { return localStorage.getItem(LS.TOKEN); }
  function getUser()   { try { return JSON.parse(localStorage.getItem(LS.USER)); } catch { return null; } }

  function storeGet(key, def = null) {
    try {
      const s = JSON.parse(localStorage.getItem(LS.STORE) || '{}');
      return key in s ? s[key] : def;
    } catch { return def; }
  }
  function storeSet(key, val) {
    try {
      const s = JSON.parse(localStorage.getItem(LS.STORE) || '{}');
      s[key] = val;
      localStorage.setItem(LS.STORE, JSON.stringify(s));
    } catch {}
  }

  // ── Auth fetch — always sends JWT ────────────────────────────────────
  async function authFetch(path, opts = {}) {
    const token = getToken();
    opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    if (token) opts.headers['Authorization'] = 'Bearer ' + token;
    return fetch(API + path, opts);
  }

  // ── Login ────────────────────────────────────────────────────────────
  async function login(email, password) {
    const r = await fetch(API + '/api/auth/demo-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!r.ok) {
      const e = await r.json().catch(() => ({}));
      throw new Error(e.detail || 'Credenziali non valide');
    }
    const d = await r.json();
    localStorage.setItem(LS.TOKEN, d.access_token);
    localStorage.setItem(LS.USER, JSON.stringify(d.user));
    return d;
  }

  // ── Logout ───────────────────────────────────────────────────────────
  function logout() {
    localStorage.removeItem(LS.TOKEN);
    localStorage.removeItem(LS.USER);
    window.location.href = 'login.html';
  }

  // ── AI query ─────────────────────────────────────────────────────────
  /**
   * Call the BAD360 AI Advisor.
   * @param {string} query
   * @param {string} module  general|haccp|scm|beverage|esg
   * @param {string} context optional extra context
   * @returns {Promise<string>}  answer text
   */
  async function aiQuery(query, module = 'general', context = '') {
    try {
      const r = await authFetch('/api/ai/query', {
        method: 'POST',
        body: JSON.stringify({ query, module, context }),
      });
      if (!r.ok) throw new Error('API error ' + r.status);
      const d = await r.json();
      return d.answer || d.raw || '';
    } catch (e) {
      return `[AI non raggiungibile — avvia il server: ${e.message}]`;
    }
  }

  // ── Health check ─────────────────────────────────────────────────────
  async function checkHealth() {
    try {
      const r = await fetch(API + '/api/health', { signal: AbortSignal.timeout(3000) });
      if (!r.ok) return { ok: false };
      return await r.json();
    } catch { return { ok: false }; }
  }

  // ── Toast (registers global showToast if page doesn't already have one) ──
  function _ensureToast() {
    if (typeof window.showToast === 'function') return;
    let el = document.getElementById('toast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'toast';
      el.style.cssText = 'position:fixed;bottom:24px;right:24px;background:var(--bg2,#1a1408);border:1px solid rgba(201,168,76,.3);color:var(--g,#C9A84C);padding:11px 18px;border-radius:10px;font-size:13px;font-weight:600;z-index:9999;opacity:0;transform:translateY(8px);transition:all .3s;pointer-events:none';
      document.body.appendChild(el);
    }
    window.showToast = function(msg, type) {
      el.textContent = msg;
      el.style.borderColor = type === 'err' ? 'rgba(201,74,74,.4)' : 'rgba(201,168,76,.3)';
      el.style.color       = type === 'err' ? 'var(--red,#c94a4a)' : 'var(--g,#C9A84C)';
      el.style.opacity = '1'; el.style.transform = 'translateY(0)';
      clearTimeout(el._t);
      el._t = setTimeout(() => { el.style.opacity='0'; el.style.transform='translateY(8px)'; }, 3800);
    };
  }

  // ── AI inline widget ─────────────────────────────────────────────────
  /**
   * Inject a floating AI assistant button on any page.
   * @param {string} defaultModule  haccp|scm|beverage|general
   * @param {string} defaultContext Extra context sent with every query
   */
  function mountAIWidget(defaultModule = 'general', defaultContext = '') {
    if (document.getElementById('b360-ai-widget')) return;

    const widget = document.createElement('div');
    widget.id = 'b360-ai-widget';
    widget.innerHTML = `
      <button id="b360-ai-fab" title="AI Advisor BAD360" style="
        position:fixed;bottom:24px;left:24px;z-index:8000;
        width:48px;height:48px;border-radius:50%;
        background:linear-gradient(135deg,#6B4F0A,#C9A84C);
        border:none;cursor:pointer;font-size:20px;
        box-shadow:0 4px 20px rgba(201,168,76,.4);
        transition:transform .2s;display:flex;align-items:center;justify-content:center;color:#06060A;font-weight:700">🤖</button>

      <div id="b360-ai-panel" style="
        display:none;position:fixed;bottom:84px;left:24px;z-index:8000;
        width:340px;max-width:calc(100vw - 48px);
        background:var(--bg2,#0D0B08);border:1px solid rgba(201,168,76,.25);
        border-radius:14px;box-shadow:0 16px 48px rgba(0,0,0,.6);
        overflow:hidden;font-family:'DM Sans',sans-serif;">
        <div style="padding:12px 16px;border-bottom:1px solid rgba(201,168,76,.15);display:flex;align-items:center;gap:8px">
          <span style="font-size:16px">🤖</span>
          <div style="flex:1">
            <div style="font-weight:700;font-size:13px;color:var(--g,#C9A84C)">AI Advisor BAD360</div>
            <div style="font-size:10px;color:var(--txt3,#4a3a1a);font-family:'DM Mono',monospace">${defaultModule.toUpperCase()} · claude-sonnet</div>
          </div>
          <button onclick="document.getElementById('b360-ai-panel').style.display='none'" style="background:none;border:none;cursor:pointer;color:var(--txt3,#4a3a1a);font-size:18px;line-height:1">×</button>
        </div>
        <div id="b360-ai-msgs" style="height:260px;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:10px;"></div>
        <div style="padding:10px 12px;border-top:1px solid rgba(201,168,76,.1);display:flex;gap:8px;">
          <input id="b360-ai-input" placeholder="Chiedi all'AI advisor…"
            style="flex:1;background:rgba(255,255,255,.04);border:1px solid rgba(201,168,76,.15);border-radius:8px;padding:8px 12px;color:var(--txt,#F8F4EE);font-size:12.5px;outline:none;font-family:inherit"
            onkeydown="if(event.key==='Enter')window._b360AISend()">
          <button onclick="window._b360AISend()" style="background:linear-gradient(135deg,#6B4F0A,#C9A84C);border:none;border-radius:8px;width:36px;height:36px;cursor:pointer;font-size:16px;color:#06060A;display:flex;align-items:center;justify-content:center">→</button>
        </div>
      </div>`;
    document.body.appendChild(widget);

    document.getElementById('b360-ai-fab').onclick = function() {
      const p = document.getElementById('b360-ai-panel');
      const open = p.style.display !== 'none';
      p.style.display = open ? 'none' : 'flex';
      p.style.flexDirection = 'column';
      if (!open) document.getElementById('b360-ai-input').focus();
    };

    window._b360AISend = async function() {
      const inp = document.getElementById('b360-ai-input');
      const msgs = document.getElementById('b360-ai-msgs');
      const q = inp.value.trim();
      if (!q) return;
      inp.value = '';

      const addMsg = (text, isUser) => {
        const m = document.createElement('div');
        m.style.cssText = `max-width:90%;padding:8px 12px;border-radius:10px;font-size:12.5px;line-height:1.55;word-break:break-word;${
          isUser
            ? 'align-self:flex-end;background:linear-gradient(135deg,#6B4F0A,#C9A84C);color:#06060A;border-radius:10px 10px 0 10px;'
            : 'align-self:flex-start;background:rgba(255,255,255,.05);color:var(--txt,#F8F4EE);border:1px solid rgba(201,168,76,.1);border-radius:10px 10px 10px 0;'}`;
        m.innerHTML = isUser ? text : text.replace(/\n/g,'<br>');
        msgs.appendChild(m);
        msgs.scrollTop = msgs.scrollHeight;
        return m;
      };

      addMsg(q, true);
      const thinking = addMsg('…', false);
      thinking.style.animation = 'pulse 1s infinite';

      const answer = await aiQuery(q, defaultModule,
        defaultContext || `Hotel: ${document.title || 'BAD360.ai'}`);
      thinking.remove();
      addMsg(answer, false);
    };
  }

  // ── Topbar user pill ─────────────────────────────────────────────────
  function _injectUserPill(user) {
    const tbr = document.querySelector('.b360-tb-r');
    if (!tbr || tbr.querySelector('.b360-user-pill')) return;

    const ROLES = { bar_manager:'Bar Mgr', general_manager:'GM', owner:'Owner', platform_admin:'Admin' };
    const pill = document.createElement('div');
    pill.className = 'b360-user-pill';
    pill.style.cssText = 'display:flex;align-items:center;gap:5px;cursor:pointer;background:rgba(201,168,76,.08);border:1px solid rgba(201,168,76,.18);border-radius:99px;padding:3px 10px 3px 6px;font-size:11.5px;color:var(--g);font-weight:600;user-select:none';
    pill.title = 'Clicca per uscire · ' + user.email;
    pill.innerHTML = `<span style="width:22px;height:22px;border-radius:50%;background:rgba(201,168,76,.2);display:flex;align-items:center;justify-content:center;font-size:11px">👤</span>
      <span>${user.name || user.email.split('@')[0]}</span>
      <span style="color:var(--txt3,#4a3a1a);font-family:'DM Mono',monospace;font-size:9.5px">${ROLES[user.role] || user.role}</span>`;
    pill.onclick = () => {
      if (confirm('Uscire da BAD360.ai?\n\n' + (user.name || user.email))) logout();
    };
    tbr.insertBefore(pill, tbr.firstChild);
    // Account (tutti) + Impostazioni Sito (solo admin)
    tbr.insertBefore(_tbBtn('⚙', 'Il mio account', openAccount), tbr.firstChild);
    if (isAdmin()) tbr.insertBefore(_tbBtn('🛠', 'Impostazioni Sito (admin)', openSiteSettings), tbr.firstChild);
  }

  // ── Online/offline indicator ─────────────────────────────────────────
  function _injectApiStatus(health) {
    const pill = document.querySelector('.b360-tb-pill');
    if (!pill) return;
    if (health.ok !== false) {
      pill.style.borderColor = 'rgba(106,171,118,.3)';
      pill.title = 'API online · ' + (health.version || '');
    } else {
      pill.style.borderColor = 'rgba(212,128,58,.3)';
      pill.style.color = 'var(--orange,#d4803a)';
      pill.title = 'API offline — dati locali';
    }
  }

  // ── CSV helper ───────────────────────────────────────────────────────
  /**
   * Download any array-of-objects as a CSV file.
   * @param {object[]} rows
   * @param {string[]} cols  column keys
   * @param {string}   filename
   */
  function downloadCSV(rows, cols, filename) {
    const esc = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const lines = [cols.join(','), ...rows.map(r => cols.map(c => esc(r[c])).join(','))];
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ── Init on DOMContentLoaded ─────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    _ensureToast();

    const user = getUser();
    if (user) _injectUserPill(user);

    // Background health check — updates v4.1 pill colour
    checkHealth().then(_injectApiStatus);

    // Validate token silently
    const token = getToken();
    if (token) {
      authFetch('/api/auth/me').then(r => r.json()).then(d => {
        if (d.authenticated === false) {
          // expired — clear but don't disrupt the page
          localStorage.removeItem(LS.TOKEN);
          localStorage.removeItem(LS.USER);
        }
      }).catch(() => {});
    }
  });

  // ── Universal Modal ──────────────────────────────────────────────────
  /**
   * Show a simple modal dialog with optional form fields.
   * @param {object} opts  { title, body, fields, onConfirm, confirmLabel }
   *   fields: [{id, label, type, placeholder, value}]
   *   onConfirm: function(values) called with {id: value} map
   */
  function modal(opts) {
    // Remove any existing modal
    const existing = document.getElementById('b360-sdk-modal');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'b360-sdk-modal';
    overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:90000;display:flex;align-items:center;justify-content:center;padding:20px;backdrop-filter:blur(8px)';
    overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };

    const s = document.documentElement.getAttribute('data-theme') === 'light';
    const bg  = s ? '#ffffff' : '#0D0B08';
    const border = 'rgba(201,168,76,.22)';
    const txt = s ? '#1a1408' : '#F8F4EE';
    const txt2 = s ? '#6b5a2a' : '#8a7a5a';

    const fieldsHTML = (opts.fields || []).map(f => `
      <div style="margin-bottom:12px">
        <label style="display:block;font-family:'DM Mono',monospace;font-size:9px;letter-spacing:1.5px;text-transform:uppercase;color:${txt2};margin-bottom:5px">${f.label}</label>
        ${f.type === 'select'
          ? `<select id="b360m-${f.id}" style="width:100%;background:rgba(201,168,76,.05);border:1.5px solid rgba(201,168,76,.15);border-radius:8px;padding:9px 13px;color:${txt};font-family:inherit;font-size:13px;outline:none">${(f.options||[]).map(o=>`<option value="${o}">${o}</option>`).join('')}</select>`
          : f.type === 'textarea'
          ? `<textarea id="b360m-${f.id}" rows="3" placeholder="${f.placeholder||''}" style="width:100%;background:rgba(201,168,76,.05);border:1.5px solid rgba(201,168,76,.15);border-radius:8px;padding:9px 13px;color:${txt};font-family:inherit;font-size:13px;resize:vertical;outline:none">${f.value||''}</textarea>`
          : `<input id="b360m-${f.id}" type="${f.type||'text'}" placeholder="${f.placeholder||''}" value="${f.value||''}" style="width:100%;background:rgba(201,168,76,.05);border:1.5px solid rgba(201,168,76,.15);border-radius:8px;padding:9px 13px;color:${txt};font-family:inherit;font-size:13px;outline:none">`
        }
      </div>`).join('');

    const bodyHTML = opts.body || '';
    const confirmLabel = opts.confirmLabel || '✓ Salva';

    overlay.innerHTML = `
      <div style="background:${bg};border:1px solid ${border};border-radius:16px;padding:28px;max-width:480px;width:100%;max-height:85vh;overflow-y:auto;box-shadow:0 24px 64px rgba(0,0,0,.7);position:relative">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:20px">
          <div style="font-family:'Syne',sans-serif;font-size:17px;font-weight:700;color:${txt}">${opts.title||''}</div>
          <button onclick="document.getElementById('b360-sdk-modal').remove()" style="background:rgba(201,168,76,.08);border:1px solid rgba(201,168,76,.15);border-radius:7px;width:30px;height:30px;cursor:pointer;color:${txt2};font-size:18px;line-height:1;display:flex;align-items:center;justify-content:center">×</button>
        </div>
        ${bodyHTML}
        ${fieldsHTML}
        ${opts.fields ? `<div id="b360m-err" style="display:none;color:#c94a4a;font-size:12px;margin-bottom:10px"></div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;padding-top:14px;border-top:1px solid rgba(201,168,76,.1)">
          <button onclick="document.getElementById('b360-sdk-modal').remove()" style="background:transparent;border:1px solid rgba(201,168,76,.15);border-radius:8px;padding:8px 18px;color:${txt2};cursor:pointer;font-family:inherit;font-size:13px">Annulla</button>
          <button id="b360m-confirm" style="background:linear-gradient(135deg,#6B4F0A,#C9A84C);border:none;border-radius:8px;padding:8px 22px;color:#06060A;font-weight:700;cursor:pointer;font-family:inherit;font-size:13px">${confirmLabel}</button>
        </div>` : ''}
      </div>`;

    document.body.appendChild(overlay);

    // Wire confirm button
    if (opts.fields && opts.onConfirm) {
      document.getElementById('b360m-confirm').onclick = () => {
        const values = {};
        opts.fields.forEach(f => {
          const el = document.getElementById('b360m-' + f.id);
          if (el) values[f.id] = el.value;
        });
        const result = opts.onConfirm(values);
        if (result !== false) overlay.remove();
      };
    }

    // Close on Escape
    const onKey = e => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); } };
    document.addEventListener('keydown', onKey);
  }

  // ── Print / report helper ────────────────────────────────────────────
  function printPage(title, contentHTML) {
    const w = window.open('', '_blank', 'width=900,height=700');
    if (!w) { window.print(); return; }
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    w.document.write(`<!DOCTYPE html><html><head>
      <meta charset="UTF-8">
      <title>${title}</title>
      <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400&display=swap" rel="stylesheet">
      <style>
        *{box-sizing:border-box;margin:0;padding:0}
        body{font-family:'DM Sans',sans-serif;font-size:13px;color:#111;background:#fff;padding:32px}
        h1{font-family:'Syne',sans-serif;font-size:22px;font-weight:800;margin-bottom:4px}
        h2{font-family:'Syne',sans-serif;font-size:16px;font-weight:700;margin:20px 0 8px}
        table{width:100%;border-collapse:collapse;font-size:12px;margin-bottom:16px}
        th{background:#f5f0e8;padding:8px 12px;text-align:left;font-family:'DM Mono',monospace;font-size:9px;letter-spacing:1px;text-transform:uppercase;border-bottom:2px solid #C9A84C}
        td{padding:8px 12px;border-bottom:1px solid #e5dcc8}
        .gold{color:#8B6914} .header{border-bottom:2px solid #C9A84C;padding-bottom:12px;margin-bottom:20px}
        .sub{color:#6b5a2a;font-size:11px;margin-top:4px}
        .badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;font-family:'DM Mono',monospace}
        .badge-ok{background:#e8f5e8;color:#2d7a2d} .badge-warn{background:#fef3e2;color:#9a6c00} .badge-err{background:#fce8e8;color:#c94a4a}
        @media print{body{padding:16px}}
      </style></head><body>
      <div class="header">
        <div style="font-family:'DM Mono',monospace;font-size:10px;color:#8B6914;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px">BAD360.ai · Hotel Baia Sardinia</div>
        <h1>${title}</h1>
        <div class="sub">Generato il ${new Date().toLocaleString('it-IT')} · BAD360.ai v4.1</div>
      </div>
      ${contentHTML}
      <script>window.onload=()=>window.print()<\/script>
    </body></html>`);
    w.document.close();
  }

  // ══ SaaS: Account utente + Impostazioni Sito (admin) ═════════════════
  const ADMIN_ROLES = ['owner', 'platform_admin', 'admin', 'developer'];
  function isAdmin() { const u = getUser(); return !!(u && ADMIN_ROLES.includes(u.role)); }
  function _v(id) { const e = document.getElementById(id); return e ? e.value.trim() : ''; }
  function _toast(m, t) { if (window.showToast) window.showToast(m, t); }

  async function openAccount() {
    modal({ title: '👤 Il mio account', body: '<div id="b360-acct" style="font-size:13px">Caricamento…</div>' });
    try {
      const r = await authFetch('/api/account/profile'); const d = await r.json();
      const el = document.getElementById('b360-acct'); if (!el) return;
      if (!d.ok) { el.innerHTML = '<div style="color:#c94a4a">' + (d.error || 'Errore') + '</div>'; return; }
      const u = d.user || {}, us = d.usage || {}, unl = us.unlimited, used = us.used || 0, lim = us.limit || 0;
      const pct = unl ? 6 : Math.min(100, lim ? Math.round(used / lim * 100) : 0);
      const planLbl = u.is_admin ? 'Amministratore' : (d.plan === 'active' ? 'Abbonato' : d.plan === 'free' ? 'Licenza gratuita' : d.plan === 'expired' ? 'Scaduto' : 'Prova gratuita');
      const showUp = !u.is_admin && d.plan !== 'active' && d.plan !== 'free';
      el.innerHTML = `<div style="line-height:1.7">
        <div><b>${u.name || ''}</b> · ${u.email || ''}</div>
        <div style="margin:6px 0"><span style="background:rgba(201,168,76,.15);color:#8B6914;padding:2px 10px;border-radius:99px;font-size:11px;font-weight:700">${planLbl}</span></div>
        <div style="margin-top:14px;display:flex;justify-content:space-between;font-size:12px"><span>Operazioni AI (${us.period || ''})</span><b>${unl ? 'illimitate' : (used + ' / ' + lim)}</b></div>
        <div style="height:8px;background:rgba(201,168,76,.12);border-radius:99px;overflow:hidden;margin:5px 0"><div style="height:100%;width:${pct}%;background:${pct >= 90 ? '#c94a4a' : pct >= 70 ? '#d4803a' : '#6aab76'}"></div></div>
        <label style="display:flex;align-items:center;gap:8px;margin-top:14px;font-size:12.5px;cursor:pointer"><input type="checkbox" id="b360-notif" ${d.preferences && d.preferences.email_notifications ? 'checked' : ''}> Ricevi notifiche via email</label>
        <div style="margin-top:14px;display:flex;gap:8px">
          <button onclick="B360.saveAccountPrefs()" style="background:linear-gradient(135deg,#6B4F0A,#C9A84C);border:none;border-radius:8px;padding:8px 16px;color:#06060A;font-weight:700;cursor:pointer">Salva preferenze</button>
          ${showUp ? '<button onclick="B360.startUpgrade()" style="background:transparent;border:1px solid rgba(201,168,76,.3);border-radius:8px;padding:8px 16px;color:#8B6914;font-weight:700;cursor:pointer">⭐ Abbonati</button>' : ''}
        </div></div>`;
    } catch (e) { const el = document.getElementById('b360-acct'); if (el) el.innerHTML = 'Backend non raggiungibile.'; }
  }
  async function saveAccountPrefs() {
    const cb = document.getElementById('b360-notif');
    try { await authFetch('/api/account/preferences', { method: 'POST', body: JSON.stringify({ email_notifications: cb && cb.checked }) }); _toast('Preferenze salvate', 'ok'); }
    catch (e) { _toast('Errore', 'err'); }
  }
  async function startUpgrade() {
    try {
      const r = await fetch(API + '/api/billing/config'); const d = await r.json();
      if (d && d.enabled) {
        const rr = await authFetch('/api/billing/checkout', { method: 'POST', body: JSON.stringify({ plan: 'pro' }) });
        const dd = await rr.json();
        if (dd.ok && dd.url) { location.href = dd.url; return; }
        if (dd.error) { alert(dd.error); return; }
      }
    } catch (e) {}
    _toast('Pagamenti non ancora attivi — configurali dal pannello admin', 'warn');
  }

  function _cfgInp(id, val, ph, type) {
    return `<input id="${id}" type="${type || 'text'}" value="${(val || '').toString().replace(/"/g, '&quot;')}" placeholder="${ph || ''}" style="width:100%;background:rgba(201,168,76,.05);border:1.5px solid rgba(201,168,76,.15);border-radius:8px;padding:8px 11px;color:inherit;font-size:12.5px;outline:none;margin:3px 0">`;
  }
  async function openSiteSettings() {
    modal({ title: '⚙ Impostazioni Sito', body: '<div id="b360-cfg" style="font-size:12.5px">Caricamento…</div>' });
    await renderSiteSettings();
  }
  async function renderSiteSettings() {
    const el = document.getElementById('b360-cfg'); if (!el) return;
    let S = {};
    try { const r = await authFetch('/api/admin/settings'); const d = await r.json(); if (!d.ok) { el.innerHTML = '<div style="color:#c94a4a">' + (d.error || 'Non autorizzato') + '</div>'; return; } S = d.settings || {}; }
    catch (e) { el.innerHTML = 'Backend non raggiungibile.'; return; }
    const origin = location.origin;
    const pill = on => `<span style="font-size:9px;font-weight:700;padding:2px 7px;border-radius:99px;background:${on ? 'rgba(106,171,118,.15)' : 'rgba(201,80,80,.12)'};color:${on ? '#3a8a4a' : '#c94a4a'}">${on ? 'OK' : 'DA IMPOSTARE'}</span>`;
    const box = inner => `<div style="border:1px solid rgba(201,168,76,.15);border-radius:10px;padding:12px;margin-bottom:12px">${inner}</div>`;
    el.innerHTML =
      box(`<b>🔑 API Anthropic</b> ${pill(S.anthropic_api_key_configured)}${_cfgInp('cfg-api', '', 'sk-ant-… (vuoto = non cambiare)', 'password')}<button onclick="B360.cfgSave('api')" class="b360cb">Salva</button>`)
      + box(`<b>📧 SMTP</b> ${pill(S.smtp_configured)}${_cfgInp('cfg-smtp-host', S.smtp_host, 'smtp.gmail.com')}${_cfgInp('cfg-smtp-port', S.smtp_port || '587', '587')}${_cfgInp('cfg-smtp-user', S.smtp_user, 'tua@email.it')}${_cfgInp('cfg-smtp-pass', '', 'password (vuoto=invariata)', 'password')}${_cfgInp('cfg-smtp-from', S.smtp_from, 'BAD360 <tua@email.it>')}<button onclick="B360.cfgSave('smtp')" class="b360cb">Salva</button> <button onclick="B360.cfgSmtpTest()" class="b360cb2">Test email</button>`)
      + box(`<b>💳 Pagamenti Stripe</b> ${pill(S.payments_live)} ${S.stripe_lib ? '' : '<span style="color:#c94a4a;font-size:10px">(modulo in deploy)</span>'}
        <label style="display:flex;align-items:center;gap:6px;margin:6px 0"><input type="checkbox" id="cfg-pay-on" ${S.payments_enabled ? 'checked' : ''}> Attiva pagamenti</label>
        <select id="cfg-mode" style="width:100%;background:rgba(201,168,76,.05);border:1.5px solid rgba(201,168,76,.15);border-radius:8px;padding:8px;color:inherit;font-size:12.5px;margin:3px 0">${['sandbox', 'live'].map(m => `<option value="${m}" ${S.stripe_mode === m ? 'selected' : ''}>${m}</option>`).join('')}</select>
        ${_cfgInp('cfg-pubs', S.stripe_pub_sandbox, 'pk_test_…')}${_cfgInp('cfg-secs', '', 'sk_test_… (vuoto=invariata)', 'password')}${_cfgInp('cfg-publ', S.stripe_pub_live, 'pk_live_…')}${_cfgInp('cfg-secl', '', 'sk_live_… (vuoto=invariata)', 'password')}${_cfgInp('cfg-pbase', S.stripe_price_base, 'price_… Base')}${_cfgInp('cfg-ppro', S.stripe_price_pro, 'price_… Pro')}${_cfgInp('cfg-wh', '', 'whsec_… (vuoto=invariata)', 'password')}
        <div style="font-size:10px;color:#8a7a5a;margin:4px 0">Webhook: <code>${origin}/api/billing/webhook</code></div><button onclick="B360.cfgSave('pay')" class="b360cb">Salva</button>`)
      + box(`<b>🌐 APP_URL</b>${_cfgInp('cfg-appurl', S.app_url, 'https://app.bad360.ai')}<button onclick="B360.cfgSave('gen')" class="b360cb">Salva</button>`)
      + `<style>.b360cb{background:linear-gradient(135deg,#6B4F0A,#C9A84C);border:none;border-radius:7px;padding:7px 14px;color:#06060A;font-weight:700;cursor:pointer;font-size:12px;margin-top:6px}.b360cb2{background:transparent;border:1px solid rgba(201,168,76,.3);border-radius:7px;padding:7px 12px;color:#8B6914;font-weight:600;cursor:pointer;font-size:12px;margin-top:6px}</style>`;
  }
  async function cfgSave(section) {
    let s = {};
    if (section === 'api') { const k = _v('cfg-api'); if (!k) { _toast('Inserisci una chiave', 'warn'); return; } s.ANTHROPIC_API_KEY = k; }
    else if (section === 'smtp') { s = { SMTP_HOST: _v('cfg-smtp-host'), SMTP_PORT: _v('cfg-smtp-port'), SMTP_USER: _v('cfg-smtp-user'), SMTP_FROM: _v('cfg-smtp-from') }; const p = _v('cfg-smtp-pass'); if (p) s.SMTP_PASS = p; }
    else if (section === 'pay') { s = { PAYMENTS_ENABLED: document.getElementById('cfg-pay-on').checked ? '1' : '0', STRIPE_MODE: _v('cfg-mode'), STRIPE_PUB_SANDBOX: _v('cfg-pubs'), STRIPE_PUB_LIVE: _v('cfg-publ'), STRIPE_PRICE_BASE: _v('cfg-pbase'), STRIPE_PRICE_PRO: _v('cfg-ppro') }; const ss = _v('cfg-secs'); if (ss) s.STRIPE_SECRET_SANDBOX = ss; const sl = _v('cfg-secl'); if (sl) s.STRIPE_SECRET_LIVE = sl; const wh = _v('cfg-wh'); if (wh) s.STRIPE_WEBHOOK_SECRET = wh; }
    else { s = { APP_URL: _v('cfg-appurl') }; }
    try { const r = await authFetch('/api/admin/settings', { method: 'POST', body: JSON.stringify({ settings: s }) }); const d = await r.json(); if (d.ok) { _toast('Salvato', 'ok'); renderSiteSettings(); } else _toast(d.error || 'Errore', 'err'); }
    catch (e) { _toast('Errore di rete', 'err'); }
  }
  async function cfgSmtpTest() {
    try { const r = await authFetch('/api/admin/smtp/test', { method: 'POST', body: JSON.stringify({}) }); const d = await r.json(); _toast(d.ok ? 'Email di test inviata' : (d.error || 'Errore'), d.ok ? 'ok' : 'err'); }
    catch (e) { _toast('Errore', 'err'); }
  }

  function _tbBtn(label, title, onclick) {
    const b = document.createElement('div');
    b.style.cssText = 'display:flex;align-items:center;justify-content:center;width:30px;height:30px;border-radius:8px;cursor:pointer;background:rgba(201,168,76,.08);border:1px solid rgba(201,168,76,.18);color:var(--g,#C9A84C);font-size:14px;user-select:none';
    b.textContent = label; b.title = title; b.onclick = onclick; return b;
  }

  // ── Public API ───────────────────────────────────────────────────────
  window.B360 = {
    API,
    login,
    logout,
    getToken,
    getUser,
    authFetch,
    aiQuery,
    checkHealth,
    downloadCSV,
    storeGet,
    storeSet,
    mountAIWidget,
    modal,
    printPage,
    openAccount,
    openSiteSettings,
    saveAccountPrefs,
    startUpgrade,
    cfgSave,
    cfgSmtpTest,
  };

})();
