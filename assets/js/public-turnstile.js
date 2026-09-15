(function (window, document) {
  'use strict';

  var CONFIG_URL = '/api/turnstile/public';
  var turnstileConfigPromise = null;
  var turnstileScriptPromise = null;
  var aliyunScriptPromise = null;
  var styleInjected = false;

  function normalizeElement(target) {
    if (!target) return null;
    if (typeof target === 'string') return document.querySelector(target);
    return target.nodeType === 1 ? target : null;
  }

  function ensureStyles() {
    if (styleInjected) return;
    styleInjected = true;
    var style = document.createElement('style');
    style.setAttribute('data-public-turnstile-style', '1');
    style.textContent = [
      '.public-turnstile-wrap{margin:12px 0 8px;}',
      '.public-turnstile-wrap[hidden]{display:none !important;}',
      '.public-turnstile-error{margin-top:8px;font-size:12px;line-height:1.5;color:#dc2626;}'
    ].join('');
    document.head.appendChild(style);
  }

  var ALIYUN_CAPTCHA_SCRIPT_SRC = 'https://o.alicdn.com/captcha-frontend/aliyunCaptcha/AliyunCaptcha.js';
  var ALIYUN_CAPTCHA_SERVERS = ['captcha-esa-open.aliyuncs.com', 'captcha-esa-open-b.aliyuncs.com'];

  function fetchTurnstileConfig() {
    if (turnstileConfigPromise) return turnstileConfigPromise;
    turnstileConfigPromise = fetch(CONFIG_URL, { cache: 'no-store' })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        var provider = String(data && data.provider || 'cloudflare').toLowerCase();
        return {
          enabled: !!(data && data.enabled && (data.site_key || (provider === 'aliyun_esa' && data.esa_identity && data.esa_scene_id))),
          provider: provider === 'aliyun_esa' ? 'aliyun_esa' : 'cloudflare',
          site_key: data && data.site_key ? String(data.site_key) : '',
          esa_identity: data && data.esa_identity ? String(data.esa_identity) : '',
          esa_scene_id: data && data.esa_scene_id ? String(data.esa_scene_id) : '',
          esa_region: data && data.esa_region ? String(data.esa_region) : 'cn'
        };
      })
      .catch(function () {
        return { enabled: false, provider: 'cloudflare', site_key: '', esa_identity: '', esa_scene_id: '', esa_region: 'cn' };
      });
    return turnstileConfigPromise;
  }

  function ensureTurnstileScript() {
    if (window.turnstile) return Promise.resolve(window.turnstile);
    if (turnstileScriptPromise) return turnstileScriptPromise;

    turnstileScriptPromise = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-public-turnstile-script="1"]');
      if (existing) {
        existing.addEventListener('load', function () { resolve(window.turnstile); }, { once: true });
        existing.addEventListener('error', function () { reject(new Error('Turnstile script load failed')); }, { once: true });
        return;
      }

      var script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      script.defer = true;
      script.dataset.publicTurnstileScript = '1';
      script.onload = function () { resolve(window.turnstile); };
      script.onerror = function () { reject(new Error('Turnstile script load failed')); };
      document.head.appendChild(script);
    });

    return turnstileScriptPromise;
  }

  function ensureAliyunCaptchaScript() {
    if (window.initAliyunCaptcha) return Promise.resolve();
    if (aliyunScriptPromise) return aliyunScriptPromise;

    aliyunScriptPromise = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[data-public-aliyun-captcha="1"]');
      if (existing) {
        existing.addEventListener('load', function () { resolve(); }, { once: true });
        existing.addEventListener('error', function () { reject(new Error('Aliyun captcha script load failed')); }, { once: true });
        return;
      }

      var script = document.createElement('script');
      script.src = ALIYUN_CAPTCHA_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.dataset.publicAliyunCaptcha = '1';
      script.onload = function () { resolve(); };
      script.onerror = function () { reject(new Error('Aliyun captcha script load failed')); };
      document.head.appendChild(script);
    });

    return aliyunScriptPromise;
  }

  function createPublicTurnstileGuard(options) {
    var opts = options || {};
    var form = normalizeElement(opts.form);
    var mountBefore = normalizeElement(opts.mountBefore);
    var mountAfter = normalizeElement(opts.mountAfter);
    var mountTarget = normalizeElement(opts.mount);
    var token = '';
    var widgetId = null;
    var widgetRendered = false;
    var enabled = false;
    var provider = 'cloudflare';
    var aliyunInstance = null;
    var aliyunReady = false;
    var wrap = null;
    var widgetHost = null;
    var errorEl = null;
    var renderPromise = null;

    function notifyError(message) {
      var text = String(message || '').trim();
      if (errorEl) {
        errorEl.textContent = text;
        errorEl.style.display = text ? 'block' : 'none';
      }
      if (text && typeof opts.onError === 'function') {
        opts.onError(text);
      }
    }

    function clearLocalError() {
      if (errorEl) {
        errorEl.textContent = '';
        errorEl.style.display = 'none';
      }
    }

    function ensureMount() {
      if (wrap) return;
      ensureStyles();

      wrap = document.createElement('div');
      wrap.className = 'public-turnstile-wrap';
      wrap.hidden = true;

      widgetHost = document.createElement('div');
      widgetHost.className = 'public-turnstile-widget';

      errorEl = document.createElement('div');
      errorEl.className = 'public-turnstile-error';
      errorEl.style.display = 'none';

      wrap.appendChild(widgetHost);
      wrap.appendChild(errorEl);

      if (mountTarget) {
        mountTarget.appendChild(wrap);
        return;
      }
      if (mountBefore && mountBefore.parentNode) {
        mountBefore.parentNode.insertBefore(wrap, mountBefore);
        return;
      }
      if (mountAfter && mountAfter.parentNode) {
        if (mountAfter.nextSibling) {
          mountAfter.parentNode.insertBefore(wrap, mountAfter.nextSibling);
        } else {
          mountAfter.parentNode.appendChild(wrap);
        }
        return;
      }
      if (form) {
        form.appendChild(wrap);
      }
    }

    async function ensureReady() {
      if (renderPromise) return renderPromise;

      renderPromise = (async function () {
        try {
          var config = await fetchTurnstileConfig();
          provider = config.provider;
          enabled = !!config.enabled;
          ensureMount();

          if (!enabled) {
            if (wrap) wrap.hidden = true;
            clearLocalError();
            return false;
          }

          if (wrap) wrap.hidden = false;

          if (provider === 'aliyun_esa') {
            // ESA 验证码：阿里云 Captcha SDK，验签由 ESA 边缘规则完成。
            await ensureAliyunCaptchaScript();
            if (!window.initAliyunCaptcha) {
              notifyError('人机验证加载失败，请稍后重试');
              return false;
            }
            if (!aliyunReady) {
              if (!widgetHost.id) widgetHost.id = 'publicCaptchaHost_' + Math.random().toString(36).slice(2, 8);
              window.AliyunCaptchaConfig = {
                region: config.esa_region || 'cn',
                prefix: config.esa_identity
              };
              window.initAliyunCaptcha({
                SceneId: config.esa_scene_id,
                mode: 'embed',
                element: '#' + widgetHost.id,
                success: function (captchaVerifyParam) {
                  token = String(captchaVerifyParam || '');
                  clearLocalError();
                  if (typeof opts.onVerified === 'function') {
                    opts.onVerified(token);
                  }
                },
                fail: function () {
                  token = '';
                  notifyError('人机验证未通过，请重试');
                },
                getInstance: function (instance) {
                  aliyunInstance = instance;
                },
                server: ALIYUN_CAPTCHA_SERVERS
              });
              aliyunReady = true;
            }
            return true;
          }

          await ensureTurnstileScript();
          if (!window.turnstile) {
            notifyError('人机验证加载失败，请稍后重试');
            return false;
          }

          if (!widgetRendered) {
            widgetId = window.turnstile.render(widgetHost, {
              sitekey: config.site_key,
              callback: function (value) {
                token = String(value || '');
                clearLocalError();
                if (typeof opts.onVerified === 'function') {
                  opts.onVerified(token);
                }
              },
              'expired-callback': function () {
                token = '';
                notifyError('人机验证已过期，请重新验证');
              },
              'error-callback': function () {
                token = '';
                notifyError('人机验证加载失败，请稍后重试');
              }
            });
            widgetRendered = true;
          }

          return true;
        } catch (err) {
          notifyError('人机验证加载失败，请稍后重试');
          return false;
        }
      })().finally(function () {
        renderPromise = null;
      });

      return renderPromise;
    }

    async function decoratePayload(payload, fieldName) {
      await ensureReady();
      if (!enabled) return payload;
      if (!token) {
        notifyError('请先完成人机验证');
        throw new Error('请先完成人机验证');
      }

      clearLocalError();
      var key = fieldName || (provider === 'aliyun_esa' ? 'turnstileToken' : 'cf_turnstile_response');
      if (payload instanceof FormData) {
        payload.set(key, token);
        return payload;
      }
      if (payload && typeof payload === 'object') {
        payload[key] = token;
      }
      return payload;
    }

    function reset() {
      token = '';
      clearLocalError();
      if (provider === 'aliyun_esa') {
        if (aliyunInstance && typeof aliyunInstance.refresh === 'function') {
          try { aliyunInstance.refresh(); } catch (err) { /* noop */ }
        }
        return;
      }
      if (enabled && window.turnstile && widgetId !== null && widgetId !== undefined) {
        try {
          window.turnstile.reset(widgetId);
        } catch (err) {
          // noop
        }
      }
    }

    return {
      ensureReady: ensureReady,
      decoratePayload: decoratePayload,
      reset: reset,
      isEnabled: function () { return enabled; },
      getProvider: function () { return provider; }
    };
  }

  window.createPublicTurnstileGuard = createPublicTurnstileGuard;
})(window, document);
