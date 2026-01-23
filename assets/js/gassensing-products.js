/**
 * 气体传感器产品分页系统
 * 产品数据来自 products-data.js
 * 
 * 注意：此文件依赖 products-data.js 中的 GAS_SENSING_PRODUCTS 数组
 * 请确保在引入此文件前先引入 products-data.js
 */

// 分页配置
const ITEMS_PER_PAGE = 6;
let currentPage = 1;
let currentFilter = 'all';

// 初始化
document.addEventListener('DOMContentLoaded', function () {
    // 读取 URL 参数
    const urlParams = new URLSearchParams(window.location.search);
    const filterParam = urlParams.get('filter');
    if (filterParam) {
        currentFilter = filterParam;
    }
    initProductPagination();
});

function initProductPagination() {
    renderProducts();
    renderPagination();
    addFilterListeners();
}

function getFilteredProducts() {
    if (currentFilter === 'all') {
        return GAS_SENSING_PRODUCTS;
    }
    return GAS_SENSING_PRODUCTS.filter(p => p.category === currentFilter);
}

function renderProducts() {
    const products = getFilteredProducts();
    const totalPages = Math.ceil(products.length / ITEMS_PER_PAGE);

    // 确保当前页有效
    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    const pageProducts = products.slice(start, end);

    const container = document.querySelector('.vs-products-list');
    if (!container) return;

    // 淡出效果
    container.style.opacity = '0';
    container.style.transform = 'translateY(20px)';

    setTimeout(() => {
        container.innerHTML = pageProducts.map(product => `
            <li>
                <a href="${product.id}.html">
                    <div class="vs-product-img">
                        <img src="${product.image}" alt="${product.name}">
                    </div>
                    <div class="vs-product-info">
                        <h5>${product.name}</h5>
                        <p>${product.description}</p>
                        <span class="vs-product-more">查看详情</span>
                    </div>
                </a>
            </li>
        `).join('');

        // 淡入效果
        container.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        container.style.opacity = '1';
        container.style.transform = 'translateY(0)';
    }, 200);
}

function renderPagination() {
    const products = getFilteredProducts();
    const totalPages = Math.ceil(products.length / ITEMS_PER_PAGE);
    const totalItems = products.length;

    const container = document.querySelector('.vs-pagination');
    if (!container) return;

    let html = `<span>共${totalItems}个产品</span>`;

    // 上一页按钮
    if (currentPage > 1) {
        html += `<a href="#" data-page="${currentPage - 1}">«上一页</a>`;
    } else {
        html += `<span class="disabled">«上一页</span>`;
    }

    // 页码
    for (let i = 1; i <= totalPages; i++) {
        if (i === currentPage) {
            html += `<span class="current">${i}</span>`;
        } else {
            html += `<a href="#" data-page="${i}">${i}</a>`;
        }
    }

    // 下一页按钮
    if (currentPage < totalPages) {
        html += `<a href="#" data-page="${currentPage + 1}">下一页»</a>`;
    } else {
        html += `<span class="disabled">下一页»</span>`;
    }

    container.innerHTML = html;

    // 绑定分页事件
    container.querySelectorAll('a[data-page]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            currentPage = parseInt(this.dataset.page);
            renderProducts();
            renderPagination();
            scrollToProducts();
        });
    });
}

function addFilterListeners() {
    // 为分类导航添加筛选功能（可选扩展）
    const categoryNav = document.querySelector('.vs-category-nav ul');
    if (!categoryNav) return;

    // 筛选按钮配置
    const filters = [
        { key: 'all', label: '全部产品' },
        { key: 'iot', label: '物联网平台' },
        { key: 'sensor', label: '传感器' },
        { key: 'module', label: '检测模块' },
        { key: 'detector', label: '检测仪' },
        { key: 'alarm', label: '报警器' },
        { key: 'system', label: '监测系统' },
        { key: 'service', label: '定制服务' }
    ];

    // 生成筛选按钮HTML，根据currentFilter设置active
    const filterHTML = filters.map(f =>
        `<li><a href="#" data-filter="${f.key}" class="${currentFilter === f.key ? 'active' : ''}">${f.label}</a></li>`
    ).join('');

    categoryNav.innerHTML = filterHTML;

    categoryNav.querySelectorAll('a[data-filter]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();

            // 更新激活状态
            categoryNav.querySelectorAll('a').forEach(a => a.classList.remove('active'));
            this.classList.add('active');

            // 更新筛选
            currentFilter = this.dataset.filter;
            currentPage = 1;
            renderProducts();
            renderPagination();
        });
    });
}

function scrollToProducts() {
    const section = document.querySelector('.vs-products-section');
    if (section) {
        const top = section.getBoundingClientRect().top + window.pageYOffset - 100;
        window.scrollTo({ top: top, behavior: 'smooth' });
    }
}
