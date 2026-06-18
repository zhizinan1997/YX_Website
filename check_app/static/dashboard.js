(function () {
  const statusLabel = {
    ok: '正常',
    degraded: '资源异常',
    down: '不可访问',
    error: '异常',
    pending: '等待检测'
  };

  function fmtTime(value) {
    if (!value) return '-';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
  }

  function fmtLatency(value) {
    return value ? `${value} 毫秒` : '-';
  }

  function localDateKey(date) {
    return [
      date.getFullYear(),
      String(date.getMonth() + 1).padStart(2, '0'),
      String(date.getDate()).padStart(2, '0')
    ].join('-');
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

  function statusClass(status) {
    if (status === 'ok') return 'status-ok';
    if (status === 'degraded') return 'status-degraded';
    if (status === 'down' || status === 'error') return 'status-down';
    return 'pending';
  }

  function renderTimeline(points, referenceTime) {
    const scale = '<div class="timeline-scale"><span class="tick-0">0时</span><span class="tick-6">6时</span><span class="tick-12">12时</span><span class="tick-18">18时</span><span class="tick-24">24时</span></div>';
    if (!points || !points.length) {
      return '<div class="timeline-wrap">' + scale + '<div class="timeline">' + Array.from({ length: 24 }, () => '<span></span>').join('') + '</div></div>';
    }
    const buckets = Array.from({ length: 24 }, () => null);
    const referenceDate = referenceTime ? new Date(referenceTime) : new Date();
    const dayKey = Number.isNaN(referenceDate.getTime()) ? localDateKey(new Date()) : localDateKey(referenceDate);
    points.forEach((point) => {
      const date = new Date(point.t);
      const t = date.getTime();
      if (Number.isNaN(t) || localDateKey(date) !== dayKey) return;
      const idx = date.getHours();
      const current = buckets[idx];
      if (!current || new Date(current.t).getTime() < t) {
        buckets[idx] = point;
      }
    });
    return '<div class="timeline-wrap">' + scale + '<div class="timeline">' + buckets.map((point) => {
      const cls = point ? statusClass(point.status) : '';
      const title = point ? `${fmtTime(point.t)} ${statusLabel[point.status] || '未知状态'} ${fmtLatency(point.latency_ms)}` : '本小时暂无检测数据';
      return `<span class="${cls}" title="${title}"></span>`;
    }).join('') + '</div></div>';
  }

  function renderTargets(targets, referenceTime) {
    const el = document.getElementById('targetList');
    if (!targets.length) {
      el.innerHTML = '<div class="empty-block">尚未配置监测目标。</div>';
      return;
    }
    el.innerHTML = targets.map((target, index) => {
      const status = target.last_status || 'pending';
      const statusModifier = status === 'ok' ? 'ok' : status === 'degraded' ? 'degraded' : status === 'pending' ? 'pending' : 'down';
      return `
        <article class="target-card target-card--${statusModifier}" style="animation-delay:${index * 0.06}s">
          <div class="target-card__head">
            <div>
              <div class="target-title"><i class="bi bi-globe2 target-icon"></i><span class="status-dot status-dot--${statusModifier}"></span>${target.name}</div>
              <div class="target-url">${target.url}</div>
            </div>
            <span class="status-pill ${statusClass(status)}">${statusLabel[status] || '未知状态'}</span>
          </div>
          ${renderTimeline(target.points || [], referenceTime)}
          <div class="target-meta">
            <span>最近检测：<strong>${fmtTime(target.last_checked_at)}</strong></span>
            <span>响应延迟：<strong>${fmtLatency(target.last_latency_ms)}</strong></span>
            <span>24小时正常率：<strong>${target.uptime_percent === null ? '-' : `${target.uptime_percent}%`}</strong></span>
            ${target.last_error ? `<span>摘要：<strong>${formatSummary(target.last_error)}</strong></span>` : ''}
          </div>
        </article>
      `;
    }).join('');
  }

  function renderIncidents(incidents) {
    const el = document.getElementById('incidentList');
    if (!incidents.length) {
      el.innerHTML = '<div class="empty-block">最近没有异常记录。</div>';
      return;
    }
    el.innerHTML = incidents.map((item) => `
      <div class="incident-item ${item.status === 'resolved' ? 'resolved' : ''}">
        <div>
          <strong>${item.status === 'resolved'
            ? '<i class="bi bi-check-circle incident-icon incident-icon--resolved"></i>'
            : '<i class="bi bi-exclamation-triangle incident-icon incident-icon--down"></i>'}${item.target_name}</strong>
          <div class="target-url">${item.url}</div>
          <div class="muted">${formatSummary(item.last_error)}</div>
        </div>
        <div>
          <span class="status-pill ${item.status === 'resolved' ? 'status-ok' : 'status-down'}">${item.status === 'resolved' ? '已恢复' : '处理中'}</span>
          <div class="muted">${fmtTime(item.opened_at)}</div>
        </div>
      </div>
    `).join('');
  }

  async function loadStatus() {
    const res = await fetch('/api/public/status?window=24', { credentials: 'same-origin' });
    const data = await res.json();
    const summary = data.summary || {};
    document.getElementById('metricTargets').textContent = summary.target_count ?? '-';
    document.getElementById('metricOk').textContent = summary.ok_count ?? '-';
    document.getElementById('metricLatency').textContent = summary.avg_latency_ms ? `${summary.avg_latency_ms} 毫秒` : '-';
    document.getElementById('metricIncidents').textContent = summary.active_incidents ?? '-';
    document.getElementById('lastUpdated').textContent = `更新于 ${fmtTime(data.generated_at)}`;

    const overall = document.getElementById('overallStatus');
    let status = 'ok';
    let text = '运行正常';
    if ((summary.down_count || 0) > 0) {
      status = 'down';
      text = '存在不可访问页面';
    } else if ((summary.degraded_count || 0) > 0 || (summary.active_incidents || 0) > 0) {
      status = 'degraded';
      text = '存在资源异常';
    }
    overall.innerHTML = `<span class="status-dot status-dot--${status}"></span><strong>${text}</strong><small>最近 24 小时，${summary.target_count || 0} 个监测目标</small>`;
    renderTargets(data.targets || [], data.generated_at);
    renderIncidents(data.incidents || []);
  }

  loadStatus().catch((error) => {
    document.getElementById('targetList').innerHTML = '<div class="empty-block">监测数据加载失败，请稍后重试。</div>';
  });
  window.setInterval(loadStatus, 60000);
})();
