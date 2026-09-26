(function () {
  'use strict';

  if (typeof window === 'undefined' || typeof document === 'undefined') return;
  if (window.__yxSiteAnalyticsLoaded) return;
  window.__yxSiteAnalyticsLoaded = true;

  if ((window.location.pathname || '').startsWith('/admin')) return;

  var ENDPOINT = '/api/analytics/collect';
  var CONSENT_KEY = 'yx_cookie_consent';
  var CONSENT_REJECTED = 'rejected';
  var VISITOR_KEY = 'yx_analytics_vid';
  var SESSION_KEY = 'yx_analytics_sid';
  var SESSION_START_KEY = 'yx_analytics_session_start';
  var SESSION_TOUCH_KEY = 'yx_analytics_session_touch';
  var ATTRIBUTION_KEY = 'yx_site_attribution';
  var ATTRIBUTION_COOKIE = 'yx_site_attribution';
  var SESSION_TIMEOUT_MS = 30 * 60 * 1000;
  var ATTRIBUTION_TTL_MS = 7 * 24 * 60 * 60 * 1000;
  var FLUSH_DELAY_MS = 2000;
  var MAX_BATCH_SIZE = 20;
  var MAX_AUTO_EVENTS_PER_PAGE = 40;

  var queue = [];
  var flushTimer = null;
  var engagedTimer = null;
  var autoEventCount = 0;
  var didSendSessionEnd = false;
  var analyticsStarted = false;
  var analyticsDisabled = false;

  function nowMs() {
    return Date.now();
  }

  function getStorageItem(store, key) {
    try {
      return store.getItem(key) || '';
    } catch (_) {
      return '';
    }
  }

  function setStorageItem(store, key, value) {
    try {
      store.setItem(key, value);
    } catch (_) {
      // ignore storage failures
    }
  }

  function removeStorageItem(store, key) {
    try {
      store.removeItem(key);
    } catch (_) {
      // ignore storage failures
    }
  }

  function writeCookieValue(name, value, maxAgeSeconds) {
    try {
      document.cookie = String(name || '') + '=' + encodeURIComponent(String(value || '')) +
        '; path=/; max-age=' + String(maxAgeSeconds || 0) + '; samesite=lax';
    } catch (_) {
      // ignore cookie failures
    }
  }

  function readCookieValue(name) {
    var prefix = String(name || '') + '=';
    var cookies = document.cookie ? document.cookie.split('; ') : [];
    for (var i = 0; i < cookies.length; i++) {
      if (cookies[i].indexOf(prefix) === 0) {
        return decodeURIComponent(cookies[i].slice(prefix.length));
      }
    }
    return '';
  }

  function readConsentState() {
    var stored = getStorageItem(window.localStorage, CONSENT_KEY);
    if (stored) return String(stored).trim().toLowerCase();
    return String(readCookieValue(CONSENT_KEY) || '').trim().toLowerCase();
  }

  function clearAnalyticsStorage() {
    removeStorageItem(window.localStorage, VISITOR_KEY);
    removeStorageItem(window.localStorage, ATTRIBUTION_KEY);
    removeStorageItem(window.sessionStorage, SESSION_KEY);
    removeStorageItem(window.sessionStorage, SESSION_START_KEY);
    removeStorageItem(window.sessionStorage, SESSION_TOUCH_KEY);
    writeCookieValue(ATTRIBUTION_COOKIE, '', 0);
  }

  function disableAnalytics() {
    analyticsDisabled = true;
    queue = [];
    if (flushTimer) {
      window.clearTimeout(flushTimer);
      flushTimer = null;
    }
    if (engagedTimer) {
      window.clearTimeout(engagedTimer);
      engagedTimer = null;
    }
    didSendSessionEnd = true;
    clearAnalyticsStorage();
  }

  function startAnalytics() {
    if (analyticsStarted || analyticsDisabled) return;
    analyticsStarted = true;

    function makeId(prefix) {
      var base = '';
      if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        base = window.crypto.randomUUID().replace(/-/g, '');
      } else {
        base = Math.random().toString(36).slice(2) + String(nowMs());
      }
      return prefix + '_' + base.slice(0, 24);
    }

    function normalizePath(raw) {
      var text = String(raw || '').trim();
      if (!text) return '/';
      try {
        var u = new URL(text, window.location.origin);
        text = u.pathname || '/';
      } catch (_) {
        if (text.indexOf('?') >= 0) text = text.split('?')[0];
        if (text.indexOf('#') >= 0) text = text.split('#')[0];
      }
      if (!text.startsWith('/')) text = '/' + text.replace(/^\.?\//, '');
      return text.slice(0, 260);
    }

    function cleanUtmValue(raw) {
      return String(raw || '').trim().replace(/[^A-Za-z0-9._:-]+/g, '-').replace(/^[.:\-_]+|[.:\-_]+$/g, '').slice(0, 96);
    }

    function readUtm() {
      var params = new URLSearchParams(window.location.search || '');
      return {
        source: cleanUtmValue(params.get('utm_source')),
        medium: cleanUtmValue(params.get('utm_medium')),
        campaign: cleanUtmValue(params.get('utm_campaign')),
        content: cleanUtmValue(params.get('utm_content')),
        term: cleanUtmValue(params.get('utm_term')),
        id: cleanUtmValue(params.get('utm_id'))
      };
    }

    function hasUtm(utm) {
      return !!(utm && (utm.source || utm.medium || utm.campaign || utm.content || utm.term || utm.id));
    }

    function readStoredAttribution() {
      var raw = getStorageItem(window.localStorage, ATTRIBUTION_KEY);
      if (!raw) raw = readCookieValue(ATTRIBUTION_COOKIE);
      if (!raw) return { first: null, last: null };
      try {
        var parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return { first: null, last: null };
        var now = nowMs();
        ['first', 'last'].forEach(function (key) {
          var item = parsed[key];
          if (!item || typeof item !== 'object' || !item.utm) {
            parsed[key] = null;
            return;
          }
          var captured = Number(item.captured_at_ms || 0);
          if (!captured || now - captured > ATTRIBUTION_TTL_MS) parsed[key] = null;
        });
        return { first: parsed.first || null, last: parsed.last || null };
      } catch (_) {
        return { first: null, last: null };
      }
    }

    function writeStoredAttribution(value) {
      var payload = JSON.stringify(value || { first: null, last: null });
      setStorageItem(window.localStorage, ATTRIBUTION_KEY, payload);
      writeCookieValue(ATTRIBUTION_COOKIE, payload, Math.round(ATTRIBUTION_TTL_MS / 1000));
    }

    function makeAttributionTouch(utm) {
      return {
        utm: utm || {},
        promotion_mark: cleanUtmValue((utm && utm.id) || ''),
        landing_page: normalizePath(window.location.pathname + window.location.search),
        referrer: String(document.referrer || '').slice(0, 300),
        captured_at_ms: nowMs()
      };
    }

    function refreshAttributionFromUrl() {
      var stored = readStoredAttribution();
      var currentUtm = readUtm();
      if (hasUtm(currentUtm)) {
        var touch = makeAttributionTouch(currentUtm);
        if (!stored.first) stored.first = touch;
        stored.last = touch;
        writeStoredAttribution(stored);
      } else if (stored.first || stored.last) {
        writeStoredAttribution(stored);
      }
      return stored;
    }

    var currentAttribution = refreshAttributionFromUrl();

    function getCurrentAttribution() {
      currentAttribution = readStoredAttribution();
      return {
        first_touch: currentAttribution.first || null,
        last_touch: currentAttribution.last || null
      };
    }

    window.YXSiteAttribution = {
      get: getCurrentAttribution,
      getLastUtm: function () {
        var attr = getCurrentAttribution();
        return (attr.last_touch && attr.last_touch.utm) || {};
      }
    };

    function getVisitorId() {
      if (analyticsDisabled) return '';
      var visitorId = getStorageItem(window.localStorage, VISITOR_KEY);
      if (!visitorId) {
        visitorId = makeId('v');
        setStorageItem(window.localStorage, VISITOR_KEY, visitorId);
      }
      return visitorId;
    }

    function ensureSession() {
      if (analyticsDisabled) {
        return {
          sessionId: '',
          sessionStart: nowMs()
        };
      }
      var now = nowMs();
      var sessionId = getStorageItem(window.sessionStorage, SESSION_KEY);
      var sessionStart = Number(getStorageItem(window.sessionStorage, SESSION_START_KEY) || '0');
      var sessionTouch = Number(getStorageItem(window.sessionStorage, SESSION_TOUCH_KEY) || '0');

      var expired = !sessionId || !sessionStart || !sessionTouch || (now - sessionTouch > SESSION_TIMEOUT_MS);
      if (expired) {
        sessionId = makeId('s');
        sessionStart = now;
        setStorageItem(window.sessionStorage, SESSION_KEY, sessionId);
        setStorageItem(window.sessionStorage, SESSION_START_KEY, String(sessionStart));
      }
      setStorageItem(window.sessionStorage, SESSION_TOUCH_KEY, String(now));

      return {
        sessionId: sessionId,
        sessionStart: sessionStart
      };
    }

    function postEvents(events, useBeacon) {
      if (analyticsDisabled || !events || !events.length) return;
      var payload = JSON.stringify({ events: events.slice(0, MAX_BATCH_SIZE) });

      if (useBeacon && navigator.sendBeacon) {
        try {
          var blob = new Blob([payload], { type: 'application/json' });
          if (navigator.sendBeacon(ENDPOINT, blob)) return;
        } catch (_) {
          // fallback to fetch below
        }
      }

      fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true
      }).catch(function () {
        // drop on network failure
      });
    }

    function scheduleFlush() {
      if (analyticsDisabled || flushTimer) return;
      flushTimer = window.setTimeout(function () {
        flushTimer = null;
        flush(false);
      }, FLUSH_DELAY_MS);
    }

    function flush(useBeacon) {
      if (analyticsDisabled || !queue.length) return;
      var batch = queue.splice(0, MAX_BATCH_SIZE);
      postEvents(batch, !!useBeacon);
      if (queue.length) scheduleFlush();
    }

    function buildBaseEvent() {
      var sess = ensureSession();
      var attr = getCurrentAttribution();
      var lastTouch = attr.last_touch || {};
      var lastUtm = lastTouch.utm || {};
      var currentUtm = readUtm();
      var effectiveUtm = hasUtm(currentUtm) ? currentUtm : lastUtm;
      return {
        visitor_id: getVisitorId(),
        session_id: sess.sessionId,
        page_path: normalizePath(window.location.pathname),
        page_title: String(document.title || '').slice(0, 120),
        referrer: String(document.referrer || '').slice(0, 300),
        utm: effectiveUtm || {},
        promotion_mark: cleanUtmValue((effectiveUtm && effectiveUtm.id) || lastTouch.promotion_mark || '')
      };
    }

    function pushEvent(event) {
      if (analyticsDisabled) return;
      var item = Object.assign({}, buildBaseEvent(), event || {});
      if (!item.event_type) item.event_type = 'event';
      if (item.event_name) item.event_name = String(item.event_name).trim().toLowerCase().slice(0, 80);
      item.page_path = normalizePath(item.page_path || window.location.pathname);
      queue.push(item);
      if (queue.length >= MAX_BATCH_SIZE) {
        flush(false);
      } else {
        scheduleFlush();
      }
    }

    function pushAutoEvent(eventName, extra) {
      if (analyticsDisabled) return;
      if (autoEventCount >= MAX_AUTO_EVENTS_PER_PAGE) return;
      autoEventCount += 1;
      var payload = Object.assign({ event_type: 'event', event_name: eventName }, extra || {});
      pushEvent(payload);
    }

    function getAnalyticsTargetText(target) {
      if (!target) return '';
      var text = String(
        target.getAttribute('data-analytics-label') ||
        target.getAttribute('aria-label') ||
        target.getAttribute('title') ||
        target.textContent ||
        ''
      ).replace(/\s+/g, ' ').trim();
      return text.slice(0, 120);
    }

    function detectFormEventName(formEl) {
      var base = (
        String(formEl.id || '') +
        ' ' + String(formEl.name || '') +
        ' ' + String(formEl.action || '') +
        ' ' + String(formEl.className || '')
      ).toLowerCase();
      if (base.indexOf('job') >= 0 || base.indexOf('resume') >= 0) return 'job_apply';
      if (base.indexOf('contact') >= 0 || base.indexOf('message') >= 0 || base.indexOf('feedback') >= 0) return 'contact_submit';
      return 'form_submit';
    }

    function handleScrollDepth() {
      var fired = { 25: false, 50: false, 75: false, 100: false };
      var ticking = false;

      function measure() {
        if (analyticsDisabled) {
          ticking = false;
          return;
        }
        ticking = false;
        var doc = document.documentElement;
        var body = document.body;
        var scrollTop = window.pageYOffset || doc.scrollTop || body.scrollTop || 0;
        var viewport = window.innerHeight || doc.clientHeight || 0;
        var full = Math.max(
          body.scrollHeight || 0,
          doc.scrollHeight || 0,
          body.offsetHeight || 0,
          doc.offsetHeight || 0
        );
        var denom = Math.max(1, full - viewport);
        var depth = Math.min(100, Math.max(0, Math.round((scrollTop / denom) * 100)));

        [25, 50, 75, 100].forEach(function (mark) {
          if (!fired[mark] && depth >= mark) {
            fired[mark] = true;
            pushAutoEvent('scroll_depth', { scroll_depth: mark });
          }
        });
      }

      window.addEventListener('scroll', function () {
        if (analyticsDisabled) return;
        if (ticking) return;
        ticking = true;
        window.requestAnimationFrame(measure);
      }, { passive: true });
    }

    function sendSessionEnd() {
      if (analyticsDisabled || didSendSessionEnd) return;
      didSendSessionEnd = true;

      var sess = ensureSession();
      var duration = Math.max(1, Math.round((nowMs() - Number(sess.sessionStart || nowMs())) / 1000));
      var finalEvent = Object.assign({}, buildBaseEvent(), {
        event_type: 'session_end',
        event_name: 'session_end',
        session_duration_sec: duration
      });

      var pending = queue.splice(0, queue.length);
      pending.push(finalEvent);
      postEvents(pending, true);
    }

    // Baseline pageview
    pushEvent({ event_type: 'pageview', event_name: 'page_view' });

    // Basic engagement signal
    engagedTimer = window.setTimeout(function () {
      if (analyticsDisabled) return;
      pushAutoEvent('engaged_15s');
    }, 15000);

    document.addEventListener('click', function (evt) {
      if (analyticsDisabled) return;
      var target = evt.target && evt.target.closest
        ? evt.target.closest('[data-analytics-event], [data-analytics-conversion], a, button')
        : null;
      if (!target) return;

      var conversion = String(target.getAttribute('data-analytics-conversion') || '').trim();
      if (conversion) {
        pushAutoEvent('conversion_' + conversion.toLowerCase().replace(/[^a-z0-9_]+/g, '_'), {
          event_target_text: getAnalyticsTargetText(target),
          event_target_url: String(target.getAttribute('href') || '').trim().slice(0, 260)
        });
        return;
      }

      var customEvent = String(target.getAttribute('data-analytics-event') || '').trim();
      if (customEvent) {
        pushAutoEvent(customEvent.toLowerCase().replace(/[^a-z0-9_]+/g, '_'), {
          event_target_text: getAnalyticsTargetText(target),
          event_target_url: String(target.getAttribute('href') || '').trim().slice(0, 260)
        });
        return;
      }

      var tagName = String(target.tagName || '').toLowerCase();
      if (tagName === 'a') {
        var href = String(target.getAttribute('href') || '').trim();
        if (!href || href === '#') return;
        if (href.toLowerCase().startsWith('tel:')) {
          pushAutoEvent('phone_click', {
            event_target_text: getAnalyticsTargetText(target),
            event_target_url: href.slice(0, 260)
          });
          return;
        }
        if (href.toLowerCase().startsWith('mailto:')) {
          pushAutoEvent('email_click', {
            event_target_text: getAnalyticsTargetText(target),
            event_target_url: href.slice(0, 260)
          });
          return;
        }
        pushAutoEvent('click_link', {
          event_target_text: getAnalyticsTargetText(target),
          event_target_url: href.slice(0, 260)
        });
        return;
      }
      if (tagName === 'button') {
        pushAutoEvent('click_button', {
          event_target_text: getAnalyticsTargetText(target)
        });
      }
    }, true);

    document.addEventListener('submit', function (evt) {
      if (analyticsDisabled) return;
      var form = evt.target;
      if (!form || String(form.tagName || '').toLowerCase() !== 'form') return;
      try {
        var hidden = form.querySelector('input[name="attribution"]');
        if (!hidden) {
          hidden = document.createElement('input');
          hidden.type = 'hidden';
          hidden.name = 'attribution';
          form.appendChild(hidden);
        }
        hidden.value = JSON.stringify(getCurrentAttribution());
      } catch (_) {
        // ignore attribution field failures
      }
      pushAutoEvent(detectFormEventName(form));
    }, true);

    handleScrollDepth();

    document.addEventListener('visibilitychange', function () {
      if (analyticsDisabled) return;
      if (document.visibilityState === 'hidden') {
        flush(true);
      } else {
        ensureSession();
      }
    });

    window.addEventListener('pagehide', sendSessionEnd, { capture: true });
    window.addEventListener('beforeunload', sendSessionEnd, { capture: true });
  }

  window.addEventListener('yx-cookie-consent-accepted', startAnalytics);
  window.addEventListener('yx-cookie-consent-rejected', disableAnalytics);

  if (readConsentState() !== CONSENT_REJECTED) {
    startAnalytics();
  }
})();
