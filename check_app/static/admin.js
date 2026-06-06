(function () {
  let editingTargetId = null;
  let cachedTargets = [];
  let turnstilePublicConfig = { enabled: false, site_key: '' };
  let turnstileToken = '';
  let turnstileWidgetId = null;
  let turnstileScriptPromise = null;
  const TURNSTILE_LOAD_TIMEOUT_MS = 15000;
  const ADMIN_PAGES = ['targets', 'runs', 'incidents'];
  const SIDEBAR_COLLAPSED_KEY = 'metachip-check-sidebar-collapsed';

  function $(id) {
    return document.getElementById(id);
  }

  async function api(url, options) {
    const res = await fetch(url, {
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      ...(options || {})
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) {
      throw new Error(data.message || `请求失败 (${res.status})`);
    }
    return data;
  }

  function fmt(value) {
    if (!value) return '-';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
  }

  function statusText(status) {
    return ({ ok: '正常', degraded: '资源异常', down: '不可访问', error: '异常', pending: '等待检测' })[status] || '未知状态';
  }

  function statusClass(status) {
    return ({ ok: 'ok', degraded: 'degraded', down: 'down', error: 'error', pending: 'pending' })[status] || 'pending';
  }

  function fmtLatency(value) {
    return value ? `${value} 毫秒` : '-';
  }

  function smtpSecurityText(data) {
    if (data.use_ssl) return 'SSL 加密';
    if (data.use_tls) return 'TLS 加密';
    return '未启用加密';
  }

  function smtpStatusText(status, configured) {
    if (!configured || status === 'missing') return '配置不完整';
    return ({ ok: '正常', error: '异常', unchecked: '未检测' })[status] || '未检测';
  }

  function smtpStatusClass(status, configured) {
    if (!configured || status === 'missing') return 'error';
    if (status === 'ok') return 'ok';
    if (status === 'error') return 'error';
    return 'pending';
  }

  function triggerText(trigger) {
    return ({ manual: '手动检测', schedule: '定时检测', retry: '异常复测', test: '测试检测' })[trigger] || '系统检测';
  }

  function getInitialAdminPage() {
    const page = window.location.hash.replace('#', '').trim();
    return ADMIN_PAGES.includes(page) ? page : 'targets';
  }

  function setActiveAdminPage(page, options) {
    const nextPage = ADMIN_PAGES.includes(page) ? page : 'targets';
    document.querySelectorAll('[data-admin-page-panel]').forEach((panel) => {
      panel.classList.toggle('is-active', panel.dataset.adminPagePanel === nextPage);
    });
    document.querySelectorAll('[data-admin-page]').forEach((link) => {
      const active = link.dataset.adminPage === nextPage;
      link.classList.toggle('is-active', active);
      if (active) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    });
    if (options && options.updateHash) {
      const nextHash = `#${nextPage}`;
      if (window.location.hash !== nextHash) {
        window.history.pushState(null, '', nextHash);
      }
    }
  }

  function updateSidebarToggle(collapsed) {
    const btn = $('sidebarToggleBtn');
    if (!btn) return;
    const label = collapsed ? '展开侧栏' : '收起侧栏';
    const text = btn.querySelector('.sidebar-toggle__text');
    const icon = btn.querySelector('.sidebar-toggle__icon');
    btn.setAttribute('aria-label', label);
    btn.setAttribute('title', label);
    btn.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
    if (text) text.textContent = collapsed ? '展开' : '收起';
    if (icon) icon.textContent = collapsed ? '>' : '<';
  }

  function setSidebarCollapsed(collapsed) {
    document.body.classList.toggle('sidebar-collapsed', Boolean(collapsed));
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? '1' : '0');
    } catch (_) {}
    updateSidebarToggle(Boolean(collapsed));
  }

  function initSidebarToggle() {
    let collapsed = false;
    try {
      collapsed = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1';
    } catch (_) {}
    setSidebarCollapsed(collapsed);
    const btn = $('sidebarToggleBtn');
    if (btn) {
      btn.addEventListener('click', () => {
        setSidebarCollapsed(!document.body.classList.contains('sidebar-collapsed'));
      });
    }
  }

  function initAdminNavigation() {
    setActiveAdminPage(getInitialAdminPage(), { updateHash: false });
    document.querySelectorAll('[data-admin-page]').forEach((link) => {
      link.addEventListener('click', (event) => {
        event.preventDefault();
        setActiveAdminPage(link.dataset.adminPage, { updateHash: true });
      });
    });
    window.addEventListener('hashchange', () => {
      setActiveAdminPage(getInitialAdminPage(), { updateHash: false });
    });
  }

  function formatSummary(value) {
    if (!value) return '-';
    return String(value)
      .replace(/\bHTTP\s*/g, '响应状态码 ')
      .replace(/\bms\b/g, '毫秒')
      .replace(/net::ERR_[A-Z_]+/g, '网络请求失败')
      .replace(/TypeError/g, '脚本错误')
      .replace(/Timeout|timeout/g, '超时')
      .replace(/request failed/gi, '请求失败')
      .replace(/failed/gi, '失败')
      .replace(/error/gi, '错误');
  }

  function turnstileRequired() {
    return Boolean(turnstilePublicConfig.enabled && turnstilePublicConfig.site_key);
  }

  function setLoginActionState(disabled) {
    $('sendCodeBtn').disabled = Boolean(disabled);
    $('verifyCodeBtn').disabled = Boolean(disabled);
  }

  function updateTurnstileActionState() {
    setLoginActionState(turnstileRequired() && !turnstileToken);
  }

  function setTurnstileError(message) {
    const el = $('loginTurnstileError');
    if (el) el.textContent = message || '';
  }

  function ensureTurnstileScriptLoaded() {
    if (window.turnstile) return Promise.resolve();
    if (turnstileScriptPromise) return turnstileScriptPromise;

    const loadPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector('script[data-turnstile="1"]');
      if (existing) {
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', () => reject(new Error('人机验证脚本加载失败')), { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.defer = true;
      script.dataset.turnstile = '1';
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('人机验证脚本加载失败'));
      document.head.appendChild(script);
    });

    const timeoutPromise = new Promise((_, reject) => {
      window.setTimeout(() => reject(new Error('人机验证脚本加载超时')), TURNSTILE_LOAD_TIMEOUT_MS);
    });

    turnstileScriptPromise = Promise.race([loadPromise, timeoutPromise]).catch((error) => {
      turnstileScriptPromise = null;
      throw error;
    });
    return turnstileScriptPromise;
  }

  function renderLoginTurnstile() {
    const target = $('loginTurnstileWidget');
    if (!target || !window.turnstile || !turnstileRequired()) return;
    target.innerHTML = '';
    turnstileWidgetId = window.turnstile.render('#loginTurnstileWidget', {
      sitekey: turnstilePublicConfig.site_key,
      theme: 'light',
      callback(token) {
        turnstileToken = String(token || '');
        setTurnstileError('');
        updateTurnstileActionState();
      },
      'expired-callback'() {
        turnstileToken = '';
        setTurnstileError('验证已过期，请重新验证');
        updateTurnstileActionState();
      },
      'error-callback'() {
        turnstileToken = '';
        setTurnstileError('人机验证异常，请刷新后重试');
        updateTurnstileActionState();
      }
    });
  }

  function resetLoginTurnstile(message) {
    turnstileToken = '';
    if (message !== undefined) setTurnstileError(message);
    if (window.turnstile && turnstileWidgetId !== null && turnstileWidgetId !== undefined) {
      try {
        window.turnstile.reset(turnstileWidgetId);
      } catch (_) {}
    }
    updateTurnstileActionState();
  }

  async function loadLoginSecurity() {
    const wrap = $('loginTurnstileWrap');
    const data = await api('/api/auth/turnstile/public');
    turnstilePublicConfig = {
      enabled: data.enabled === true,
      site_key: String(data.site_key || '').trim()
    };
    if (!turnstileRequired()) {
      turnstileToken = '';
      turnstileWidgetId = null;
      if (wrap) wrap.classList.add('hidden');
      setTurnstileError('');
      setLoginActionState(false);
      return;
    }
    if (wrap) wrap.classList.remove('hidden');
    setLoginActionState(true);
    try {
      await ensureTurnstileScriptLoaded();
      renderLoginTurnstile();
      resetLoginTurnstile('请先完成人机验证');
    } catch (_) {
      setTurnstileError('人机验证暂时无法加载，请稍后重试');
      setLoginActionState(true);
    }
  }

  function ensureTurnstileReady() {
    if (!turnstileRequired() || turnstileToken) return true;
    setTurnstileError('请先完成人机验证');
    updateTurnstileActionState();
    return false;
  }

  function withTurnstileToken(payload) {
    if (turnstileRequired()) {
      payload.turnstileToken = turnstileToken;
    }
    return payload;
  }

  function showLogin(message) {
    document.body.classList.remove('is-authenticated');
    document.body.classList.add('is-login');
    $('loginPanel').classList.remove('hidden');
    $('adminPanel').classList.add('hidden');
    if (message !== undefined) $('loginMessage').textContent = message;
    loadConfigStatus().catch(() => {});
    loadLoginSecurity().catch(() => {
      setTurnstileError('登录安全配置加载失败，请刷新后重试');
    });
  }

  function showAdmin(email) {
    document.body.classList.add('is-authenticated');
    document.body.classList.remove('is-login');
    $('loginPanel').classList.add('hidden');
    $('adminPanel').classList.remove('hidden');
    $('adminEmail').textContent = email || '-';
    setActiveAdminPage(getInitialAdminPage(), { updateHash: false });
  }

  async function checkSession() {
    const data = await api('/api/auth/session');
    if (data.logged_in) {
      showAdmin(data.email);
      await refreshAdmin();
    } else {
      showLogin('');
    }
  }

  async function loadConfigStatus() {
    const data = await api('/api/public/config-status');
    if (data.dev_login_enabled) {
      $('devLoginPanel').classList.remove('hidden');
    } else {
      $('devLoginPanel').classList.add('hidden');
    }
  }

  async function sendCode() {
    $('loginMessage').textContent = '';
    if (!ensureTurnstileReady()) return;
    const email = $('loginEmail').value.trim();
    await api('/api/auth/send-code', {
      method: 'POST',
      body: JSON.stringify(withTurnstileToken({ email }))
    });
    resetLoginTurnstile('');
    $('loginMessage').style.color = '#17935f';
    $('loginMessage').textContent = '验证码已发送，请查看邮箱。';
  }

  async function verifyCode() {
    $('loginMessage').textContent = '';
    if (!ensureTurnstileReady()) return;
    const email = $('loginEmail').value.trim();
    const code = $('loginCode').value.trim();
    const data = await api('/api/auth/verify-code', {
      method: 'POST',
      body: JSON.stringify(withTurnstileToken({ email, code }))
    });
    resetLoginTurnstile('');
    showAdmin(email);
    await refreshAdmin();
    return data;
  }

  async function devLogin() {
    const data = await api('/api/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({})
    });
    showAdmin(data.user && data.user.email);
    await refreshAdmin();
  }

  function renderTargets(targets) {
    cachedTargets = targets;
    $('adminTargets').classList.remove('loading-block');
    if (!targets.length) {
      $('adminTargets').innerHTML = '<div class="empty-block">尚未配置监测目标。</div>';
      return;
    }
    $('adminTargets').innerHTML = `
      <table>
        <thead>
          <tr><th>名称</th><th>网址</th><th>状态</th><th>间隔</th><th>最近检测</th><th>操作</th></tr>
        </thead>
        <tbody>
          ${targets.map((target) => `
            <tr>
              <td><div class="admin-target-name"><strong>${target.name}</strong><span class="muted">${target.enabled ? '已启用' : '已停用'}</span></div></td>
              <td><span class="admin-url-pill">${target.url}</span></td>
              <td><span class="admin-status admin-status--${statusClass(target.last_status)}">${statusText(target.last_status)}</span><span class="admin-latency">${fmtLatency(target.last_latency_ms)}</span></td>
              <td>${target.interval_seconds} 秒</td>
              <td>${fmt(target.last_checked_at)}</td>
              <td>
                <div class="table-actions">
                  <button class="mini-btn" data-action="check" data-id="${target.id}">检测</button>
                  <button class="mini-btn" data-action="edit" data-id="${target.id}">编辑</button>
                  <button class="mini-btn" data-action="delete" data-id="${target.id}">删除</button>
                </div>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function renderRuns(runs) {
    $('adminRuns').classList.remove('loading-block');
    if (!runs.length) {
      $('adminRuns').innerHTML = '<div class="empty-block">还没有检测记录。</div>';
      return;
    }
    $('adminRuns').innerHTML = `
      <table>
        <thead><tr><th>时间</th><th>目标</th><th>状态</th><th>响应延迟</th><th>资源失败</th><th>摘要</th></tr></thead>
        <tbody>
          ${runs.map((run) => `
            <tr>
              <td>${fmt(run.started_at)}</td>
              <td>${run.target_name}</td>
              <td><span class="admin-status admin-status--${statusClass(run.status)}">${statusText(run.status)}</span><span class="admin-latency">第 ${run.attempt} 次 / ${triggerText(run.trigger)}</span></td>
              <td>${fmtLatency(run.latency_ms)}</td>
              <td>${run.resource_failed}</td>
              <td>${formatSummary(run.error_summary)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function renderIncidents(incidents) {
    $('adminIncidents').classList.remove('loading-block');
    if (!incidents.length) {
      $('adminIncidents').innerHTML = '<div class="empty-block">还没有异常告警。</div>';
      return;
    }
    $('adminIncidents').innerHTML = `
      <table>
        <thead><tr><th>目标</th><th>状态</th><th>失败次数</th><th>打开时间</th><th>告警时间</th><th>摘要</th></tr></thead>
        <tbody>
          ${incidents.map((item) => `
            <tr>
              <td><div class="admin-target-name"><strong>${item.target_name}</strong><span class="admin-url-pill">${item.url}</span></div></td>
              <td><span class="admin-status admin-status--${item.status === 'resolved' ? 'ok' : 'down'}">${item.status === 'resolved' ? '已恢复' : '处理中'}</span></td>
              <td>${item.failure_count}</td>
              <td>${fmt(item.opened_at)}</td>
              <td>${fmt(item.alert_sent_at)}</td>
              <td>${formatSummary(item.last_error)}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  }

  function renderSmtpStatus(data) {
    const status = data.check_status || 'unchecked';
    const badgeClass = smtpStatusClass(status, data.configured);
    const badge = $('smtpStatusBadge');
    badge.className = `admin-status admin-status--${badgeClass}`;
    badge.textContent = smtpStatusText(status, data.configured);
    $('smtpSource').textContent = data.source || '-';
    $('smtpHost').textContent = data.host || '-';
    $('smtpPort').textContent = data.port || '-';
    $('smtpSecurity').textContent = smtpSecurityText(data);
    $('smtpUsername').textContent = data.username || '-';
    $('smtpFromEmail').textContent = data.from_email || '-';
    $('smtpFromName').textContent = data.from_name || '-';
    $('smtpPasswordConfigured').textContent = data.password_configured ? '已配置' : '未配置';
    $('smtpMessage').textContent = data.message || '已读取主站发信配置';
    $('smtpMessage').classList.toggle('is-ok', status === 'ok');
    $('smtpMessage').classList.toggle('is-error', !data.configured || status === 'error' || status === 'missing');
  }

  function updateAdminMetrics(targets, incidents) {
    const enabledTargets = targets.filter((target) => target.enabled);
    const okTargets = enabledTargets.filter((target) => target.last_status === 'ok');
    const latencies = enabledTargets
      .map((target) => Number(target.last_latency_ms || 0))
      .filter((value) => value > 0);
    const activeIncidents = incidents.filter((item) => item.status !== 'resolved');
    const avgLatency = latencies.length ? Math.round(latencies.reduce((sum, value) => sum + value, 0) / latencies.length) : null;
    $('adminMetricTargets').textContent = enabledTargets.length;
    $('adminMetricOk').textContent = okTargets.length;
    $('adminMetricLatency').textContent = avgLatency ? `${avgLatency} 毫秒` : '-';
    $('adminMetricIncidents').textContent = activeIncidents.length;
  }

  async function refreshAdmin() {
    const [targets, runs, incidents, smtp] = await Promise.all([
      api('/api/admin/targets'),
      api('/api/admin/runs'),
      api('/api/admin/incidents'),
      api('/api/admin/smtp')
    ]);
    const targetItems = targets.targets || [];
    const runItems = runs.runs || [];
    const incidentItems = incidents.incidents || [];
    updateAdminMetrics(targetItems, incidentItems);
    renderTargets(targetItems);
    renderRuns(runItems);
    renderIncidents(incidentItems);
    renderSmtpStatus(smtp);
  }

  async function checkSmtpService() {
    const btn = $('smtpCheckBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '正在检测';
    $('smtpMessage').textContent = '正在连接主站配置的 SMTP 服务...';
    $('smtpMessage').classList.remove('is-ok', 'is-error');
    try {
      const data = await api('/api/admin/smtp-check', { method: 'POST', body: '{}' });
      renderSmtpStatus(data);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  }

  function resetTargetForm() {
    editingTargetId = null;
    $('targetName').value = '';
    $('targetUrl').value = '';
    $('targetInterval').value = '3600';
    $('targetEnabled').checked = true;
  }

  function openTargetForm(target) {
    $('targetForm').classList.remove('hidden');
    if (target) {
      editingTargetId = target.id;
      $('targetName').value = target.name || '';
      $('targetUrl').value = target.url || '';
      $('targetInterval').value = target.interval_seconds || 3600;
      $('targetEnabled').checked = Boolean(target.enabled);
    } else {
      resetTargetForm();
    }
  }

  async function saveTarget() {
    const payload = {
      name: $('targetName').value.trim(),
      url: $('targetUrl').value.trim(),
      interval_seconds: Number($('targetInterval').value || 3600),
      timeout_ms: 25000,
      enabled: $('targetEnabled').checked
    };
    if (editingTargetId) {
      await api(`/api/admin/targets/${editingTargetId}`, { method: 'PUT', body: JSON.stringify(payload) });
    } else {
      await api('/api/admin/targets', { method: 'POST', body: JSON.stringify(payload) });
    }
    $('targetForm').classList.add('hidden');
    resetTargetForm();
    await refreshAdmin();
  }

  async function checkAllTargets() {
    const btn = $('checkAllBtn');
    const originalText = btn.textContent;
    btn.disabled = true;
    btn.textContent = '正在发起测试';
    try {
      const data = await api('/api/admin/check-all', { method: 'POST', body: '{}' });
      btn.textContent = data.skipped ? `已开始 ${data.accepted} 个，跳过 ${data.skipped} 个` : `已开始 ${data.accepted} 个`;
      window.setTimeout(refreshAdmin, 2500);
      window.setTimeout(refreshAdmin, 12000);
    } finally {
      window.setTimeout(() => {
        btn.disabled = false;
        btn.textContent = originalText;
      }, 1800);
    }
  }

  async function handleTargetAction(event) {
    const btn = event.target.closest('button[data-action]');
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const action = btn.dataset.action;
    if (action === 'check') {
      await api('/api/admin/check-now', { method: 'POST', body: JSON.stringify({ target_id: id }) });
      btn.textContent = '检测中';
      window.setTimeout(refreshAdmin, 2500);
    }
    if (action === 'edit') {
      const target = cachedTargets.find((item) => Number(item.id) === id);
      openTargetForm(target);
    }
    if (action === 'delete') {
      await api(`/api/admin/targets/${id}`, { method: 'DELETE', body: JSON.stringify({}) });
      await refreshAdmin();
    }
  }

  $('sendCodeBtn').addEventListener('click', () => sendCode().catch((error) => {
    resetLoginTurnstile('');
    $('loginMessage').style.color = '#c84658';
    $('loginMessage').textContent = error.message;
  }));
  $('verifyCodeBtn').addEventListener('click', () => verifyCode().catch((error) => {
    resetLoginTurnstile('');
    $('loginMessage').style.color = '#c84658';
    $('loginMessage').textContent = error.message;
  }));
  $('devLoginBtn').addEventListener('click', () => devLogin().catch((error) => {
    $('loginMessage').style.color = '#c84658';
    $('loginMessage').textContent = error.message;
  }));
  $('logoutBtn').addEventListener('click', () => api('/api/auth/logout', { method: 'POST', body: '{}' }).then(() => showLogin('')));
  $('checkAllBtn').addEventListener('click', () => checkAllTargets().catch((error) => alert(error.message)));
  $('smtpCheckBtn').addEventListener('click', () => checkSmtpService().catch((error) => {
    $('smtpMessage').textContent = error.message;
    $('smtpMessage').classList.add('is-error');
  }));
  $('addTargetBtn').addEventListener('click', () => openTargetForm(null));
  $('cancelTargetBtn').addEventListener('click', () => {
    $('targetForm').classList.add('hidden');
    resetTargetForm();
  });
  $('saveTargetBtn').addEventListener('click', () => saveTarget().catch((error) => alert(error.message)));
  $('adminTargets').addEventListener('click', (event) => handleTargetAction(event).catch((error) => alert(error.message)));

  initSidebarToggle();
  initAdminNavigation();
  checkSession().catch(() => showLogin(''));
})();
