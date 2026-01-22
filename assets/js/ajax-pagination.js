/**
 * AJAX Pagination System
 * 实现无刷新翻页功能
 */

(function () {
    'use strict';

    // 初始化
    document.addEventListener('DOMContentLoaded', function () {
        initAjaxPagination();
    });

    function initAjaxPagination() {
        const pagination = document.querySelector('.vs-pagination');
        if (!pagination) return;

        // 为分页链接绑定事件
        bindPaginationEvents();

        // 更新浏览器历史记录支持
        window.addEventListener('popstate', function (e) {
            if (e.state && e.state.page) {
                loadPage(e.state.url, false);
            }
        });

        // 保存初始状态
        history.replaceState({ page: getCurrentPage(), url: location.href }, '', location.href);
    }

    function bindPaginationEvents() {
        const pagination = document.querySelector('.vs-pagination');
        if (!pagination) return;

        // 移除旧事件监听（使用事件委托）
        pagination.removeEventListener('click', handlePaginationClick);
        pagination.addEventListener('click', handlePaginationClick);
    }

    function handlePaginationClick(e) {
        const link = e.target.closest('a');
        if (!link) return;

        e.preventDefault();

        const url = link.href;
        if (!url) return;

        loadPage(url, true);
    }

    async function loadPage(url, pushState = true) {
        const productsContainer = document.querySelector('.vs-products-list');
        const pagination = document.querySelector('.vs-pagination');

        if (!productsContainer || !pagination) return;

        // 显示加载状态
        showLoading(productsContainer);

        try {
            const response = await fetch(url);
            if (!response.ok) throw new Error('Network response was not ok');

            const html = await response.text();

            // 解析返回的 HTML
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            // 获取新的产品列表和分页
            const newProducts = doc.querySelector('.vs-products-list');
            const newPagination = doc.querySelector('.vs-pagination');

            if (newProducts && newPagination) {
                // 淡出动画
                productsContainer.style.opacity = '0';
                productsContainer.style.transform = 'translateY(20px)';

                await sleep(200);

                // 替换内容
                productsContainer.innerHTML = newProducts.innerHTML;
                pagination.innerHTML = newPagination.innerHTML;

                // 淡入动画
                productsContainer.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
                productsContainer.style.opacity = '1';
                productsContainer.style.transform = 'translateY(0)';

                // 重新绑定事件
                bindPaginationEvents();

                // 更新浏览器历史
                if (pushState) {
                    const pageNum = getPageFromUrl(url);
                    history.pushState({ page: pageNum, url: url }, '', url);
                }

                // 滚动到产品区域顶部
                scrollToProducts();
            }
        } catch (error) {
            console.error('Error loading page:', error);
            // 出错时直接跳转
            window.location.href = url;
        }

        hideLoading(productsContainer);
    }

    function showLoading(container) {
        // 创建加载遮罩
        let overlay = document.querySelector('.vs-loading-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.className = 'vs-loading-overlay';
            overlay.innerHTML = `
                <div class="vs-loading-spinner">
                    <div class="spinner-ring"></div>
                    <span>加载中...</span>
                </div>
            `;

            // 添加样式
            const style = document.createElement('style');
            style.textContent = `
                .vs-loading-overlay {
                    position: fixed;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(255, 255, 255, 0.8);
                    backdrop-filter: blur(4px);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 9999;
                    opacity: 0;
                    transition: opacity 0.3s ease;
                    pointer-events: none;
                }
                .vs-loading-overlay.active {
                    opacity: 1;
                    pointer-events: auto;
                }
                .vs-loading-spinner {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 16px;
                    color: var(--color-primary, #00338d);
                    font-weight: 600;
                }
                .spinner-ring {
                    width: 48px;
                    height: 48px;
                    border: 4px solid rgba(0, 51, 141, 0.1);
                    border-top-color: var(--color-primary, #00338d);
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    to { transform: rotate(360deg); }
                }
            `;
            document.head.appendChild(style);
            document.body.appendChild(overlay);
        }

        // 触发重排后添加 active 类以启动动画
        requestAnimationFrame(() => {
            overlay.classList.add('active');
        });
    }

    function hideLoading() {
        const overlay = document.querySelector('.vs-loading-overlay');
        if (overlay) {
            overlay.classList.remove('active');
        }
    }

    function scrollToProducts() {
        const productsSection = document.querySelector('.vs-products-section');
        if (productsSection) {
            const headerHeight = 100; // 考虑固定头部的高度
            const top = productsSection.getBoundingClientRect().top + window.pageYOffset - headerHeight;

            window.scrollTo({
                top: top,
                behavior: 'smooth'
            });
        }
    }

    function getCurrentPage() {
        const pagination = document.querySelector('.vs-pagination .current');
        return pagination ? parseInt(pagination.textContent) : 1;
    }

    function getPageFromUrl(url) {
        const match = url.match(/page[_-]?(\d+)/i);
        return match ? parseInt(match[1]) : 1;
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // 暴露全局方法（可选）
    window.AjaxPagination = {
        loadPage: loadPage,
        refresh: bindPaginationEvents
    };

})();
