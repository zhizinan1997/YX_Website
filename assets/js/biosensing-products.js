/**
 * 生物传感器产品数据
 * 所有产品在一个页面，通过JS分页
 */

const BIOSENSING_PRODUCTS = [
    {
        id: 'mc_bw_bio_workstation',
        name: 'MC-BW-01 生物传感工作站',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501141610379601.jpg',
        description: 'MC-BW-01生物传感工作站具备皮安级的电流测量精度，专为微弱电流信号的便捷测量而设计，同时支持多通道并行测试。',
        category: 'instrument'
    },
    {
        id: 'ion_detector',
        name: '离子检测仪',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501141553278669.png',
        description: '离子检测仪是一种便携、快速、精准的测试设备，采用离子选择性电极技术，能够在现场进行实时分析。',
        category: 'instrument'
    },
    {
        id: 'portable_bio_detector',
        name: '便携式手持生物检测仪',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501141535249134.png',
        description: '便携式手持生物测试仪，具备纳安级的电流测量精度，专为微弱电流信号的便捷测量而设计，体积小巧，携带方便。',
        category: 'instrument'
    },
    {
        id: 'carbon_bio_package_chip',
        name: '碳基生物封装芯片',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101346080807.png',
        description: 'MCB-P系列碳基生物封装芯片采用碳基场效应晶体管传感原理，具有高均一、微型化、高灵敏、稳定性好的特点。',
        category: 'chip'
    },
    {
        id: 'blood_potassium_chip',
        name: '便携式血钾检测芯片',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501141545220675.bmp',
        description: '便携式血钾检测芯片，采用离子敏感场效应晶体管检测方法，在体外诊断行业为国内首创。',
        category: 'chip'
    },
    {
        id: 'chlorine_detection_chip',
        name: '余氯检测芯片',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501141602163019.png',
        description: '余氯检测芯片是采用微纳加工工艺，结合电化学检测原理设计制造的一款针对水质检测方向的芯片。',
        category: 'chip'
    },
    {
        id: 'carbon_bio_platform',
        name: '碳基生物传感平台',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101345491479.png',
        description: '采用碳基场效应晶体管传感原理构建通用型生物传感平台，具有高均一、微型化、高灵敏、低噪声的特点。',
        category: 'platform'
    },
    {
        id: 'custom_bio_sensor_chip',
        name: '定制化生物传感芯片',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101352242634.png',
        description: '采用碳基场效应晶体管传感原理，具有高均一、微型化、高灵敏、稳定性好的特点，可定制化生产。',
        category: 'chip'
    },
    {
        id: 'respiratory_virus_chip',
        name: '急性呼吸道病毒检测芯片',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202510200917507059.png',
        description: '基于碳基场效应晶体管传感技术的急性呼吸道病毒快速检测芯片，可实现多种病毒的高灵敏度检测。',
        category: 'chip'
    },
    {
        id: 'igzo_device',
        name: 'IGZO器件',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202510200908335899.png',
        description: 'IGZO（铟镓锌氧化物）薄膜晶体管器件，具有高迁移率、低漏电流、高透明度等优异特性。',
        category: 'device'
    },
    // 定制服务
    {
        id: '../customization/custom_gas_sensing_module',
        name: '定制气体传感模组',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101352513746.png',
        description: '针对客户应用需求，提供包含器件封装、驱动电路、信号变换模组等多项目的定制化服务与解决方案。',
        category: 'instrument'
    },
    {
        id: '../customization/custom_instrument_dev',
        name: '定制仪器仪表开发',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101353274954.png',
        description: '提供气体检测仪表从设计、加工与测试，包括传感器芯片的封装与探测器的制造，仪器仪表结构的设计与开发等。',
        category: 'instrument'
    },
    {
        id: '../customization/micronano_fabrication',
        name: '微纳加工服务',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101352373523.png',
        description: '提供从设计到加工到测试的全链条定制化服务，包括贵金属沉积、介质生长及完整的微纳工艺。',
        category: 'service'
    }
];

// 分页配置
const ITEMS_PER_PAGE = 6;
let currentPage = 1;
let currentFilter = 'all';

// 初始化
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
                        <span class="vs-product-more">查看详情</span>
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

    let html = `<span>共${totalItems}个产品</span>`;

    if (currentPage > 1) {
        html += `<a href="#" data-page="${currentPage - 1}">«上一页</a>`;
    } else {
        html += `<span class="disabled">«上一页</span>`;
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
        html += `<span class="disabled">下一页»</span>`;
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
        <li><a href="#" data-filter="all" class="active">全部产品</a></li>
        <li><a href="#" data-filter="instrument">检测仪器</a></li>
        <li><a href="#" data-filter="chip">生物芯片</a></li>
        <li><a href="#" data-filter="platform">传感平台</a></li>
        <li><a href="#" data-filter="device">器件</a></li>
        <li><a href="#" data-filter="service">定制服务</a></li>
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
