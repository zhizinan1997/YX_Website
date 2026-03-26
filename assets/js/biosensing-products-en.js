/**
 * Biosensing Product Data (English)
 */

const BIOSENSING_PRODUCTS = [
    {
        id: 'mc_bw_bio_workstation',
        name: 'MC-BW-01 Biosensing Workstation',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/71239bd525e4.jpg',
        description: 'The MC-BW-01 biosensing workstation features pico-ampere level current measurement precision, designed for convenient measurement of weak current signals, supporting multi-channel parallel testing.',
        category: 'instrument'
    },
    {
        id: 'ion_detector',
        name: 'Ion Detector',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/e7c2ff731b1c.png',
        description: 'The Ion Detector is a portable, fast, and precise testing device utilizing ion-selective electrode technology for real-time field analysis.',
        category: 'instrument'
    },
    {
        id: 'portable_bio_detector',
        name: 'Portable Handheld Bio-Detector',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/889872f2cdab.png',
        description: 'A portable handheld bio-tester with nano-ampere level current measurement precision, designed for convenient measurement of weak current signals. Compact and easy to carry.',
        category: 'instrument'
    },
    {
        id: 'carbon_bio_package_chip',
        name: 'Carbon-Based Bio-Packaging Chip',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/5ae73ef90181.png',
        description: 'The MCB-P series carbon-based bio-packaging chips use carbon-based FET sensing principles, featuring high uniformity, miniaturization, high sensitivity, and excellent stability.',
        category: 'chip'
    },
    {
        id: 'blood_potassium_chip',
        name: 'Portable Blood Potassium Detection Chip',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/c7c3bf65312d.bmp',
        description: 'Portable blood potassium detection chip utilizing ion-sensitive field-effect transistor detection methodology, a domestic first in the IVD industry.',
        category: 'chip'
    },
    {
        id: 'chlorine_detection_chip',
        name: 'Residual Chlorine Detection Chip',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/e44b0c29e5b8.png',
        description: 'The residual chlorine detection chip is designed and manufactured using micro-nano fabrication processes combined with electrochemical detection principles for water quality testing.',
        category: 'chip'
    },
    {
        id: 'carbon_bio_platform',
        name: 'Carbon-Based Biosensing Platform',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/8496a8cc6608.png',
        description: 'A universal biosensing platform built on carbon-based field-effect transistor principles, featuring high uniformity, miniaturization, high sensitivity, and low noise.',
        category: 'platform'
    },
    {
        id: 'custom_bio_sensor_chip',
        name: 'Customized Biosensing Chip',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/5ae73ef90181.png',
        description: 'Utilizing carbon-based FET sensing principles, featuring high uniformity, miniaturization, and high sensitivity. Available for customized production.',
        category: 'chip'
    },
    {
        id: 'respiratory_virus_chip',
        name: 'Acute Respiratory Virus Detection Chip',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/ac96ed29d345.png',
        description: 'Rapid detection chip for acute respiratory viruses based on carbon-based FET technology, enabling high-sensitivity detection of various viruses.',
        category: 'chip'
    },
    {
        id: 'igzo_device',
        name: 'IGZO Device',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/a68f7093c2a5.png',
        description: 'IGZO (Indium Gallium Zinc Oxide) thin-film transistor devices, featuring high mobility, low leakage current, and high transparency.',
        category: 'device'
    },
    {
        id: '../customization/micronano_fabrication',
        name: 'Micro-nano Fabrication Service',
        image: '/cdn_assets/images/external-cache/wstx.web.vleader.net.cn/693d8dddb7ee.png',
        description: 'Providing full-chain customized services from design to fabrication to testing, including noble metal deposition, dielectric growth, and complete micro-nano processes.',
        category: 'service'
    }
];

// Pagination Configuration
const ITEMS_PER_PAGE = 6;
let currentPage = 1;
let currentFilter = 'all';

// Initialization
document.addEventListener('DOMContentLoaded', function () {
    initProductPagination();
});

function initProductPagination() {
    renderProducts();
    renderPagination();
    addFilterListeners();
}

function getFilteredProducts() {
    if (currentFilter === 'all') {
        return BIOSENSING_PRODUCTS;
    }
    return BIOSENSING_PRODUCTS.filter(p => p.category === currentFilter);
}

function renderProducts() {
    const products = getFilteredProducts();
    const totalPages = Math.ceil(products.length / ITEMS_PER_PAGE);

    if (currentPage > totalPages) currentPage = totalPages;
    if (currentPage < 1) currentPage = 1;

    const start = (currentPage - 1) * ITEMS_PER_PAGE;
    const end = start + ITEMS_PER_PAGE;
    const pageProducts = products.slice(start, end);

    const container = document.querySelector('.vs-products-list');
    if (!container) return;

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
                        <span class="vs-product-more">Details</span>
                    </div>
                </a>
            </li>
        `).join('');

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

    let html = `<span>Total ${totalItems} products</span>`;

    if (currentPage > 1) {
        html += `<a href="#" data-page="${currentPage - 1}">« Prev</a>`;
    } else {
        html += `<span class="disabled">« Prev</span>`;
    }

    for (let i = 1; i <= totalPages; i++) {
        if (i === currentPage) {
            html += `<span class="current">${i}</span>`;
        } else {
            html += `<a href="#" data-page="${i}">${i}</a>`;
        }
    }

    if (currentPage < totalPages) {
        html += `<a href="#" data-page="${currentPage + 1}">Next »</a>`;
    } else {
        html += `<span class="disabled">Next »</span>`;
    }

    container.innerHTML = html;

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
    const categoryNav = document.querySelector('.vs-category-nav ul');
    if (!categoryNav) return;

    const filterHTML = `
        <li><a href="#" data-filter="all" class="active">All Products</a></li>
        <li><a href="#" data-filter="instrument">Instruments</a></li>
        <li><a href="#" data-filter="chip">Bio-Chips</a></li>
        <li><a href="#" data-filter="platform">Sensing Platforms</a></li>
        <li><a href="#" data-filter="device">Devices</a></li>
        <li><a href="#" data-filter="service">Custom Services</a></li>
    `;

    categoryNav.innerHTML = filterHTML;

    categoryNav.querySelectorAll('a[data-filter]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();

            categoryNav.querySelectorAll('a').forEach(a => a.classList.remove('active'));
            this.classList.add('active');

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
