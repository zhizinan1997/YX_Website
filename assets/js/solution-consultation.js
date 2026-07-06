(function (window, document) {
  'use strict';

  var PUBLIC_TURNSTILE_SCRIPT_SRC = '/assets/js/public-turnstile.js';
  var FORM_SELECTOR = '.contact-section .contact-form form, form[data-solution-consultation]';
  var turnstileScriptPromise = null;
  var formGuards = new WeakMap();

  function ensurePublicTurnstileScript() {
    if (window.createPublicTurnstileGuard) return Promise.resolve();
    if (turnstileScriptPromise) return turnstileScriptPromise;

    turnstileScriptPromise = new Promise(function (resolve, reject) {
      var existing = document.querySelector('script[src*="public-turnstile.js"]');
      if (existing) {
        if (window.createPublicTurnstileGuard) {
          resolve();
          return;
        }
        existing.addEventListener('load', function () { resolve(); }, { once: true });
        existing.addEventListener('error', function () { reject(new Error('Turnstile helper load failed')); }, { once: true });
        return;
      }

      var script = document.createElement('script');
      script.src = PUBLIC_TURNSTILE_SCRIPT_SRC;
      script.async = true;
      script.defer = true;
      script.dataset.solutionTurnstileLoader = '1';
      script.onload = function () { resolve(); };
      script.onerror = function () { reject(new Error('Turnstile helper load failed')); };
      document.head.appendChild(script);
    }).catch(function (error) {
      turnstileScriptPromise = null;
      throw error;
    });

    return turnstileScriptPromise;
  }

  function firstValue(elements) {
    for (var i = 0; i < elements.length; i += 1) {
      var value = String(elements[i] && elements[i].value || '').trim();
      if (value) return value;
    }
    return '';
  }

  function getNamed(form, names) {
    for (var i = 0; i < names.length; i += 1) {
      var el = form.elements[names[i]];
      if (el) return el;
    }
    return null;
  }

  function readFields(form) {
    var textInputs = Array.prototype.slice.call(form.querySelectorAll('input[type="text"], input:not([type])'));
    var nameEl = getNamed(form, ['txtUserName', 'name', 'user_name']) || textInputs[0] || null;
    var companyEl = getNamed(form, ['company', 'company_name']) || textInputs[1] || null;
    var emailEl = getNamed(form, ['txtUserEmail', 'email', 'user_email']) || form.querySelector('input[type="email"]');
    var phoneEl = getNamed(form, ['txtUserTel', 'phone', 'tel', 'mobile']) || form.querySelector('input[type="tel"]');
    var contentEl = getNamed(form, ['txtContent', 'content', 'message', 'requirement']) || form.querySelector('textarea');

    return {
      name: firstValue([nameEl]),
      company: firstValue([companyEl]),
      email: firstValue([emailEl]),
      phone: firstValue([phoneEl]),
      content: firstValue([contentEl])
    };
  }

  function ensureStatus(form) {
    var status = form.querySelector('.solution-consultation-status');
    if (status) return status;

    status = document.createElement('p');
    status.className = 'solution-consultation-status';
    status.setAttribute('role', 'status');
    status.style.cssText = 'margin:12px 0 0;font-size:14px;line-height:1.6;';
    var submitRow = form.querySelector('.form-submit');
    if (submitRow && submitRow.parentNode) {
      submitRow.parentNode.insertBefore(status, submitRow.nextSibling);
    } else {
      form.appendChild(status);
    }
    return status;
  }

  function setStatus(form, message, type) {
    var status = ensureStatus(form);
    status.textContent = message || '';
    status.style.color = type === 'success' ? '#15803d' : '#dc2626';
  }

  function getSubmitButton(form) {
    return form.querySelector('button[type="submit"], input[type="submit"]');
  }

  function setSubmitting(form, submitting) {
    var button = getSubmitButton(form);
    if (!button) return;
    if (submitting) {
      button.dataset.originalText = button.textContent || button.value || '';
      button.disabled = true;
      if (button.tagName === 'INPUT') {
        button.value = '提交中...';
      } else {
        button.textContent = '提交中...';
      }
    } else {
      button.disabled = false;
      var original = button.dataset.originalText || '';
      if (original) {
        if (button.tagName === 'INPUT') {
          button.value = original;
        } else {
          button.textContent = original;
        }
      }
    }
  }

  function buildFeedbackPayload(form, fields) {
    var pageTitle = String(document.title || '').trim();
    var sourceTitle = String(form.dataset.solutionTitle || pageTitle || '解决方案咨询').trim();
    var contentLines = [
      '来源页面：' + sourceTitle,
      '页面地址：' + (window.location.pathname + window.location.search)
    ];
    if (fields.company) contentLines.push('公司名称：' + fields.company);
    if (fields.content) contentLines.push('咨询需求：' + fields.content);

    var payload = new FormData();
    payload.set('txtUserName', fields.name || '解决方案访客');
    payload.set('txtUserTel', fields.phone);
    payload.set('txtUserEmail', fields.email || '');
    payload.set('txtTitle', '解决方案咨询 - ' + sourceTitle);
    payload.set('txtContent', contentLines.join('\n'));
    return payload;
  }

  async function getTurnstileGuard(form) {
    if (formGuards.has(form)) return formGuards.get(form);
    await ensurePublicTurnstileScript();
    if (!window.createPublicTurnstileGuard) return null;

    var submitRow = form.querySelector('.form-submit');
    var guard = window.createPublicTurnstileGuard({
      form: form,
      mountBefore: submitRow || null,
      onError: function (message) {
        if (message) setStatus(form, message, 'error');
      }
    });
    formGuards.set(form, guard);
    return guard;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    var form = event.currentTarget;
    if (!form || form.dataset.solutionSubmitting === '1') return;

    if (typeof form.reportValidity === 'function' && !form.reportValidity()) {
      return;
    }

    var fields = readFields(form);
    if (!fields.phone) {
      setStatus(form, '请填写联系电话。', 'error');
      return;
    }
    if (!fields.content) {
      setStatus(form, '请简要填写咨询需求。', 'error');
      return;
    }

    form.dataset.solutionSubmitting = '1';
    setSubmitting(form, true);
    setStatus(form, '', 'success');

    try {
      var payload = buildFeedbackPayload(form, fields);
      var guard = await getTurnstileGuard(form);
      if (guard) {
        await guard.decoratePayload(payload);
      }

      var response = await fetch('/api/feedback', {
        method: 'POST',
        body: payload
      });
      var data = await response.json().catch(function () { return {}; });
      if (!response.ok || !data.success) {
        throw new Error(data.message || '提交失败，请稍后重试。');
      }

      form.reset();
      if (guard) guard.reset();
      setStatus(form, data.message || '咨询已提交，我们会尽快联系您。', 'success');
    } catch (error) {
      setStatus(form, error && error.message ? error.message : '提交失败，请稍后重试。', 'error');
    } finally {
      delete form.dataset.solutionSubmitting;
      setSubmitting(form, false);
    }
  }

  function init() {
    var forms = Array.prototype.slice.call(document.querySelectorAll(FORM_SELECTOR));
    forms.forEach(function (form) {
      if (form.dataset.solutionConsultationBound === '1') return;
      form.dataset.solutionConsultationBound = '1';
      form.setAttribute('data-solution-consultation', '1');
      form.addEventListener('submit', handleSubmit);
      getTurnstileGuard(form)
        .then(function (guard) {
          if (guard) guard.ensureReady();
        })
        .catch(function () {
          // Submit-time validation will surface a user-facing message.
        });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window, document);
