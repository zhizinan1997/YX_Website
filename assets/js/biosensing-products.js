/**
 * 生物传感产品分页系统
 *
 * 产品数据与领域分类从后台 API 获取：
 * - /api/bio-products/with-settings
 * - /api/bio-products/industry-filters
 */

let BIOSENSING_PRODUCTS = [];
let INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];

const ITEMS_PER_PAGE = 6;
let currentPage = 1;
let currentFilter = 'all';

function isVisibleBiosensingProduct(product) {
    if (!product || product.hidden) return false;
    const id = String(product.id || '').trim();
    if (!id) return false;
    return id.startsWith('../biosensing/');
}

function buildProductHref(product) {
    const id = String(product?.id || '').trim();
    if (!id) return '#';
    if (id.startsWith('../')) return `${id}.html`;
    return `${id}.html`;
}

document.addEventListener('DOMContentLoaded', async function () {
    await loadProductsFromAPI();
    await loadIndustryFiltersFromAPI();

    const urlParams = new URLSearchParams(window.location.search);
    const filterParam = (urlParams.get('filter') || '').trim();
    if (filterParam) {
        currentFilter = filterParam;
    }

    initProductPagination();
});

async function loadProductsFromAPI() {
    try {
        const response = await fetch('/api/bio-products/with-settings');
        const data = await response.json();
        const rows = Array.isArray(data.products) ? data.products : [];
        BIOSENSING_PRODUCTS = rows.filter(isVisibleBiosensingProduct);
    } catch (error) {
        console.error('Failed to load biosensing products:', error);
        BIOSENSING_PRODUCTS = [];
    }
}

async function loadIndustryFiltersFromAPI() {
    try {
        const response = await fetch('/api/bio-products/industry-filters');
        const data = await response.json();
        const categories = Array.isArray(data.categories) ? data.categories : [];

        INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];
        categories.forEach(item => {
            if (!item || !item.key || !item.name) return;
            INDUSTRY_FILTERS.push({ key: item.key, label: item.name });
        });
    } catch (error) {
        console.error('Failed to load biosensing industry filters:', error);
        INDUSTRY_FILTERS = [{ key: 'all', label: '全部产品' }];
    }
}

function initProductPagination() {
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
        return BIOSENSING_PRODUCTS;
    }
    return BIOSENSING_PRODUCTS.filter(product => {
        const categories = Array.isArray(product.industryCategories) ? product.industryCategories : [];
        return categories.includes(currentFilter);
    });
}

function renderProducts() {
    const products = getFilteredProducts();
    const totalPages = Math.ceil(products.length / ITEMS_PER_PAGE);
    const container = document.querySelector('.vs-products-list');
    if (!container) return;

    if (products.length === 0) {
        container.innerHTML = '<li style="text-align:center;padding:40px;color:#666;">当前分类暂无可展示产品</li>';
        return;
    }

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    const pageProducts = products.slice(start, end);

    container.style.opacity = '0';
    container.style.transform = 'translateY(20px)';

    setTimeout(() => {
        container.innerHTML = pageProducts.map(product => `
            <li>
                <a href="${buildProductHref(product)}">
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

        container.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        container.style.opacity = '1';
        container.style.transform = 'translateY(0)';
    }, 160);
}

function renderPagination() {
    const products = getFilteredProducts();
    const totalPages = Math.ceil(products.length / ITEMS_PER_PAGE);
    const totalItems = products.length;

    const container = document.querySelector('.vs-pagination');
    if (!container) return;
    if (totalItems === 0) {
        container.innerHTML = '<span>共0个产品</span>';
        return;
    }

    let html = `<span>共${totalItems}个产品</span>`;

    if (currentPage > 1) {
        html += `<a href="#" data-page="${currentPage - 1}">«上一页</a>`;
    } else {
        html += '<span class="disabled">«上一页</span>';
    }

    for (let i = 1; i <= totalPages; i++) {
        if (i === currentPage) {
            html += `<span class="current">${i}</span>`;
        } else {
            html += `<a href="#" data-page="${i}">${i}</a>`;
        }
    }

    if (currentPage < totalPages) {
        html += `<a href="#" data-page="${currentPage + 1}">下一页»</a>`;
    } else {
        html += '<span class="disabled">下一页»</span>';
    }

    container.innerHTML = html;
    container.querySelectorAll('a[data-page]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            currentPage = parseInt(this.dataset.page, 10) || 1;
            renderProducts();
            renderPagination();
            scrollToProducts();
        });
    });
}

function renderFilterNav() {
    const categoryNav = document.querySelector('.vs-category-nav ul');
    if (!categoryNav) return;

    categoryNav.innerHTML = INDUSTRY_FILTERS.map(item => `
        <li>
            <a href="#" data-filter="${item.key}" class="${currentFilter === item.key ? 'active' : ''}">
                ${item.label}
            </a>
        </li>
    `).join('');

    categoryNav.querySelectorAll('a[data-filter]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            currentFilter = this.dataset.filter || 'all';
            currentPage = 1;
            updateFilterInUrl(currentFilter);
            renderFilterNav();
            renderProducts();
            renderPagination();
        });
    });
}

function updateFilterInUrl(filterKey) {
    const url = new URL(window.location.href);
    if (!filterKey || filterKey === 'all') {
        url.searchParams.delete('filter');
    } else {
        url.searchParams.set('filter', filterKey);
    }
    window.history.replaceState({}, '', url.toString());
}

function scrollToProducts() {
    const section = document.querySelector('.vs-products-section');
    if (section) {
        const top = section.getBoundingClientRect().top + window.pageYOffset - 100;
        window.scrollTo({ top, behavior: 'smooth' });
    }
}
