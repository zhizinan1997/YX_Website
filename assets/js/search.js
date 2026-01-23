/**
 * 全站搜索功能 - Premium Version
 * Site-wide Search Functionality
 */

(function() {
  'use strict';

  // 搜索配置
  const SEARCH_CONFIG = {
    apiUrl: '/api/search',
    debounceDelay: 300,
    minQueryLength: 2,
    maxResults: 20
  };

  // 热门搜索关键词
  const POPULAR_KEYWORDS = [
    '氢气传感器',
    '生物传感器',
    '气体检测',
    '车载氢气',
    '环境监测',
    '储能安全'
  ];

  let searchModal = null;
  let searchInput = null;
  let searchWrapper = null;
  let searchResults = null; // .vs-search-results
  let searchBody = null;    // .vs-search-body (scroller)
  let searchClear = null;
  let searchOverlay = null;
  let debounceTimer = null;

  /**
   * 初始化搜索功能
   */
  function init() {
    createSearchModal();
    bindEvents();
  }

  /**
   * 创建搜索模态框
   */
  function createSearchModal() {
    // 创建遮罩
    searchOverlay = document.createElement('div');
    searchOverlay.className = 'vs-search-overlay';
    document.body.appendChild(searchOverlay);

    // 创建搜索模态框结构
    searchModal = document.createElement('div');
    searchModal.className = 'vs-search-modal';
    
    const html = `
      <div class="vs-search-wrapper">
        <!-- 头部搜索栏 -->
        <div class="vs-search-header">
          <i class="fas fa-search vs-search-icon"></i>
          <input type="text" class="vs-search-input" placeholder="搜索产品、解决方案、文档..." autocomplete="off" />
          <button class="vs-search-clear" aria-label="清除"><i class="fas fa-times"></i></button>
          <button class="vs-search-close-btn">关闭</button>
        </div>

        <!-- 内容滚动区 -->
        <div class="vs-search-body">
          <div class="vs-search-results"></div>
        </div>

        <!-- 底部状态栏 -->
        <div class="vs-search-footer">
          <div>Metachip 智能搜索</div>
        </div>
      </div>
    `;

    searchModal.innerHTML = html;
    document.body.appendChild(searchModal);

    // 获取元素引用
    searchWrapper = searchModal.querySelector('.vs-search-wrapper');
    searchInput = searchModal.querySelector('.vs-search-input');
    searchBody = searchModal.querySelector('.vs-search-body');
    searchResults = searchModal.querySelector('.vs-search-results');
    searchClear = searchModal.querySelector('.vs-search-clear');
    
    // 初始化显示热门搜索
    showHints();
  }

  /**
   * 绑定事件
   */
  function bindEvents() {
    // 触发器绑定
    document.addEventListener('click', function(e) {
      const trigger = e.target.closest('.vs-search-trigger, [href="#"][class*="fa-search"]');
      if (trigger) {
        e.preventDefault();
        openSearch();
      }
    });

    // 关闭按钮
    const closeBtn = searchModal.querySelector('.vs-search-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', closeSearch);
    
    // 遮罩点击关闭
    searchOverlay.addEventListener('click', closeSearch);

    // 清除按钮
    searchClear.addEventListener('click', function() {
      searchInput.value = '';
      searchClear.classList.remove('visible');
      showHints();
      searchInput.focus();
    });

    // 输入事件
    searchInput.addEventListener('input', function() {
      const query = this.value.trim();
      
      searchClear.classList.toggle('visible', query.length > 0);
      
      clearTimeout(debounceTimer);
      
      if (query.length === 0) {
        showHints();
        return;
      }
      
      debounceTimer = setTimeout(function() {
        if (query.length >= SEARCH_CONFIG.minQueryLength) {
          performSearch(query);
        }
      }, SEARCH_CONFIG.debounceDelay);
    });

    // 键盘导航
    searchInput.addEventListener('keydown', handleKeyNavigation);

    // 结果点击代理
    searchResults.addEventListener('click', function(e) {
      // 检查点击的是否是结果项
      const item = e.target.closest('.vs-search-result-item');
      if (item) {
        // item本身是<a>标签，浏览器会处理跳转，我们只需关闭搜索
        // setTimeout 让跳转先发生（如果不是SPA路由）
        setTimeout(closeSearch, 100);
      }
      
      // 检查点击的是否是标签
      const tag = e.target.closest('.vs-tag-btn');
      if (tag) {
        const keyword = tag.dataset.keyword;
        searchInput.value = keyword;
        searchClear.classList.add('visible');
        performSearch(keyword);
      }
    });

    // 全局快捷键
    document.addEventListener('keydown', function(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchModal.classList.contains('active') ? closeSearch() : openSearch();
      }
      if (e.key === 'Escape' && searchModal.classList.contains('active')) {
        closeSearch();
      }
    });
  }

  /**
   * 打开搜索
   */
  function openSearch() {
    searchOverlay.classList.add('active');
    searchModal.classList.add('active');
    document.body.style.overflow = 'hidden'; // 防止背景滚动
    searchInput.value = '';
    showHints();
    setTimeout(() => searchInput.focus(), 100);
  }

  /**
   * 关闭搜索
   */
  function closeSearch() {
    searchOverlay.classList.remove('active');
    searchModal.classList.remove('active');
    document.body.style.overflow = '';
    setTimeout(() => {
      // 等待动画结束清理
      if (!searchModal.classList.contains('active')) {
        searchInput.value = '';
        showHints();
      }
    }, 300);
  }

  /**
   * 显示热门/空状态
   */
  function showHints() {
    searchResults.innerHTML = `
      <div class="vs-state-container">
        <div class="vs-state-icon"><i class="fab fa-hotjar"></i></div>
        <div class="vs-state-title">热门搜索</div>
        <div class="vs-tags-cloud">
          ${POPULAR_KEYWORDS.map(k => `<button class="vs-tag-btn" data-keyword="${k}">${k}</button>`).join('')}
        </div>
      </div>
    `;
  }

  /**
   * 执行搜索
   */
  function performSearch(query) {
    searchResults.innerHTML = `
      <div class="vs-state-container">
        <div class="spinner"></div>
      </div>
    `;

    fetch(`${SEARCH_CONFIG.apiUrl}?q=${encodeURIComponent(query)}&limit=${SEARCH_CONFIG.maxResults}`)
      .then(res => res.json())
      .then(data => {
        renderResults(data.results, query);
      })
      .catch(err => {
        searchResults.innerHTML = `
          <div class="vs-state-container">
            <div class="vs-state-icon"><i class="fas fa-exclamation-triangle"></i></div>
            <div class="vs-state-title">搜索服务暂时不可用</div>
            <div class="vs-state-desc">请检查网络连接或稍后再试</div>
          </div>
        `;
      });
  }

  /**
   * 渲染结果
   */
  function renderResults(results, query) {
    if (!results || results.length === 0) {
      searchResults.innerHTML = `
        <div class="vs-state-container">
          <div class="vs-state-icon"><i class="fas fa-search"></i></div>
          <div class="vs-state-title">未找到相关结果</div>
          <div class="vs-state-desc">尝试更换关键词，或缩短搜索词</div>
        </div>
      `;
      return;
    }

    const highlight = (text) => {
      if (!text) return '';
      const reg = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
      return text.replace(reg, '<mark>$1</mark>');
    };

    let html = `<div class="vs-search-group-title">找到 ${results.length} 个结果</div>`;
    
    html += results.map((item, idx) => `
      <a href="${item.url}" class="vs-search-result-item" data-index="${idx}">
        <div class="g-icon">
          <i class="fas fa-file-alt"></i>
        </div>
        <div class="g-content">
          <div class="g-title">${highlight(item.title)}</div>
          <div class="g-snippet">${highlight(item.snippet)}</div>
          <!-- <div class="g-meta">
             <span class="g-tag">页面</span>
             <span>${item.url}</span>
           </div> -->
        </div>
      </a>
    `).join('');

    searchResults.innerHTML = html;
  }

  /**
   * 键盘导航逻辑
   */
  function handleKeyNavigation(e) {
    const items = searchResults.querySelectorAll('.vs-search-result-item');
    if (items.length === 0) return;

    let current = -1;
    items.forEach((el, idx) => {
      if (el.classList.contains('focused')) current = idx;
    });

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = current < items.length - 1 ? current + 1 : 0;
      updateFocus(items, next);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = current > 0 ? current - 1 : items.length - 1;
      updateFocus(items, prev);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (current >= 0) {
         items[current].click();
      } else {
         // 如果没有选中项，默认回车打开第一个
         items[0].click();
      }
    }
  }

  function updateFocus(items, index) {
    items.forEach(el => el.classList.remove('focused'));
    const target = items[index];
    target.classList.add('focused');
    target.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  // 启动
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // 暴露 API
  window.VsSearch = { open: openSearch, close: closeSearch };

})();
