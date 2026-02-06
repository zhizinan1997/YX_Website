/**
 * 气体传感器产品分页系统
 * 
 * 产品数据从 /api/products 自动获取
 * 服务器会自动扫描 pages/gassensing/ 目录下的产品HTML文件
 * 
 * ✅ 完全自动化：添加新产品HTML文件后，刷新页面即可显示
 */

// 产品数据（从API加载）
let GAS_SENSING_PRODUCTS = [];
let INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];

// 分页配置
const ITEMS_PER_PAGE = 6;
let currentPage = 1;
let currentFilter = 'all';

// 初始化
document.addEventListener('DOMContentLoaded', async function () {
    // 从API加载产品数据
    await loadProductsFromAPI();
    await loadIndustryFiltersFromAPI();

    // 读取 URL 参数
    const urlParams = new URLSearchParams(window.location.search);
    const filterParam = urlParams.get('filter');
    if (filterParam) {
        currentFilter = filterParam;
    }
    initProductPagination();
});

async function loadProductsFromAPI() {
    try {
        // 使用带设置的 API 以获取多分类信息
        const response = await fetch('/api/products/with-settings');
        const data = await response.json();

        if (data.products && data.products.length > 0) {
            GAS_SENSING_PRODUCTS = data.products;
            console.log(`Loaded ${data.count} products from API`);
        } else {
            console.warn('No products found from API');
        }
    } catch (error) {
        console.error('Failed to load products from API:', error);
        // 降级处理
        if (typeof window.GAS_SENSING_PRODUCTS_BACKUP !== 'undefined') {
            GAS_SENSING_PRODUCTS = window.GAS_SENSING_PRODUCTS_BACKUP;
        }
    }
}

async function loadIndustryFiltersFromAPI() {
    try {
        const response = await fetch('/api/products/industry-filters');
        const data = await response.json();
        const categories = Array.isArray(data.categories) ? data.categories : [];

        INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];
        categories.forEach(item => {
            if (!item || !item.key || !item.name) return;
            INDUSTRY_FILTERS.push({ key: item.key, label: item.name });
        });
    } catch (error) {
        console.error('Failed to load industry filters:', error);
        INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];
    }
}

function initProductPagination() {
    if (GAS_SENSING_PRODUCTS.length === 0) {
        const container = document.querySelector('.vs-products-list');
        if (container) {
            container.innerHTML = '<li style="text-align:center;padding:40px;color:#666;">暂无产品数据</li>';
        }
        return;
    }

    // 若 URL 参数里的分类不存在，回退为“全部产品”
    const filterKeys = new Set(INDUSTRY_FILTERS.map(f => f.key));
    if (!filterKeys.has(currentFilter)) {
        currentFilter = 'all';
    }

    renderFilterNav();
    renderProducts();
    renderPagination();
}

function getFilteredProducts() {
    if (currentFilter === 'all') {
        return GAS_SENSING_PRODUCTS;
    }
    // 按“领域分类”筛选
    return GAS_SENSING_PRODUCTS.filter(p => {
        const categories = p.industryCategories || [];
        return categories.includes(currentFilter);
    });
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
                        <img src="${product.cardImage || product.image}" alt="${product.cardTitle || product.name}">
                    </div>
                    <div class="vs-product-info">
                        <h5>${product.cardTitle || product.name}</h5>
                        <p>${product.cardSummary || product.description || ''}</p>
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

function renderFilterNav() {
    // 为分类导航添加筛选功能（可选扩展）
    const categoryNav = document.querySelector('.vs-category-nav ul');
    if (!categoryNav) return;

    // 生成筛选按钮HTML，根据currentFilter设置active
    const filterHTML = INDUSTRY_FILTERS.map(f =>
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
