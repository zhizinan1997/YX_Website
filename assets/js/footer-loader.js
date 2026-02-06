(function () {
  var ROOT_ID = 'mc-footer-root';
  var CSS_ID = 'mc-footer-component-css';
  var CHATBOT_SCRIPT_SRC = '/assets/js/chatbot.js';

  function ensureStylesheet() {
    if (document.getElementById(CSS_ID)) return;
    var link = document.createElement('link');
    link.id = CSS_ID;
    link.rel = 'stylesheet';
    link.href = '/assets/css/footer-component.css';
    document.head.appendChild(link);
  }

  function ensureChatbotScript() {
    var exists = Array.prototype.some.call(document.getElementsByTagName('script'), function (s) {
      var src = s.getAttribute('src') || '';
      return src.indexOf('chatbot.js') !== -1;
    });
    if (exists) return;
    var script = document.createElement('script');
    script.src = CHATBOT_SCRIPT_SRC;
    script.defer = true;
    document.body.appendChild(script);
  }

  function bindFooterInteractions(root) {
    if (!root) return;
    var trigger = root.querySelector('.vs-wechat-trigger');
    if (!trigger) return;

    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      trigger.classList.toggle('is-open');
    });

    document.addEventListener('click', function (e) {
      if (!trigger.contains(e.target)) {
        trigger.classList.remove('is-open');
      }
    });
  }

  function boot() {
    ensureChatbotScript();

    var root = document.getElementById(ROOT_ID);
    if (!root) return;

    ensureStylesheet();
    fetch('/assets/partials/footer-main.html', { cache: 'no-cache' })
      .then(function (res) {
        if (!res.ok) throw new Error('footer partial load failed');
        return res.text();
      })
      .then(function (html) {
        root.innerHTML = html;
        bindFooterInteractions(root);
      })
      .catch(function (err) {
        console.error('[footer-loader]', err);
      });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
