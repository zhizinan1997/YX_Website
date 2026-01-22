/**
 * 气体传感器产品数据
 * 所有产品在一个页面，通过JS分页
 */

const GAS_SENSING_PRODUCTS = [
    // 物联网平台 - 放在首位作为重点推荐
    {
        id: 'mcs_iot_platform',
        name: 'MCS-IoT工业级气体监测物联网平台',
        image: '../../assets/images/iot2.png',
        description: '专为工业气体监测场景设计的物联网云平台，支持实时数据采集、可视化大屏、智能报警、设备管理和AI分析。一键部署，Docker容器化架构。',
        category: 'iot'
    },
    {
        id: 'ld_h2_detector',
        name: 'LD-H2型氢气检测仪',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png',
        description: 'LD-H2型氢气检测仪搭载高性能氢气传感器，具有响应速度快、动态校准范围广、测量误差小等特点；检测仪采用低功耗设计，续航时间长。',
        category: 'detector'
    },
    {
        id: 'mc_wd_wearable_alarm',
        name: 'MC-WD穿戴式氢气报警器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191119077851.png',
        description: 'MC-WD穿戴式氢气报警器是一款便携式氢气检测产品，更小巧、更轻便，可轻松穿戴在操作人员的衣帽之上。',
        category: 'alarm'
    },
    {
        id: 'mchp_vehicle_h2',
        name: 'MCHP-1.0型车载氢气传感模块',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101345141287.png',
        description: '通过钯合金薄膜表面对氢分子反应实现氢气浓度的测量，结合碳基传感芯片的高灵敏性，具备对氢气响应特异性强的特点。',
        category: 'module'
    },
    {
        id: 'mc_hla_fixed_alarm',
        name: 'MC-HLA-01固定式氢气报警器',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101343348440.png',
        description: 'MC-HLA-01固定式氢气报警器可检测管道中或受限空间以及大气环境中的氢气浓度，广泛应用于电池室、充电间等场景。',
        category: 'alarm'
    },
    {
        id: 'mchs_palladium_h2',
        name: 'MCHS-1.0型钯合金薄膜氢气传感器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191124239026.png',
        description: '采用钯合金薄膜技术的高性能氢气传感器，具有极高的选择性和灵敏度，适用于各种工业环境。',
        category: 'sensor'
    },
    {
        id: 'mchf_carbon_fet_h2',
        name: 'MCHF-1.0型碳基场效应型氢气传感器',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101351152977.png',
        description: '基于碳基场效应晶体管技术的新型氢气传感器，具有高灵敏度、低功耗、快速响应等特点。',
        category: 'sensor'
    },
    {
        id: 'mchc_catalytic_h2',
        name: 'MCHC-1.0型催化燃烧氢气传感器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191122589747.png',
        description: '采用催化燃烧原理的氢气传感器，适用于高浓度氢气检测场景，具有稳定性好、寿命长等优点。',
        category: 'sensor'
    },
    {
        id: 'mchm_h2_sensor',
        name: 'MCHM-1.0型氢气传感器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191120311735.png',
        description: '通用型氢气传感器，性能稳定，适用于多种工业和民用氢气检测场景。',
        category: 'sensor'
    },
    {
        id: 'mc_hfev_module',
        name: 'MC-HFEV-02多用途氢气检测模块',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101352116691.png',
        description: '多用途氢气检测模块，可集成到各种设备中，提供可靠的氢气浓度监测功能。',
        category: 'module'
    },
    {
        id: 'h2_detection_probe',
        name: '氢气检测探头',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101350333118.png',
        description: '高精度氢气检测探头，可配合各类检测仪表使用，实现精确的氢气浓度测量。',
        category: 'probe'
    },
    {
        id: 'mc_td_leak_detector',
        name: 'MC-TD-01 氮氢示踪检漏仪',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101346569735.png',
        description: 'MC-TD-01型氮氢示踪气体检漏仪，满足工业场景的快速检漏需求，采用氮氢混合气体为示踪气体。',
        category: 'detector'
    },
    {
        id: 'mcect_electrochemical_h2',
        name: 'MCECT-1.0型电化学氢气传感器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191136321756.png',
        description: '经典的定电位电解检测技术，以高性价比、低功耗及成熟的可靠性，成为便携式仪表的首选方案。',
        category: 'sensor'
    },
    {
        id: 'mctcx_thermal_h2',
        name: 'MCTCX-1.0型热导式氢气传感器',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202509191422318089.png',
        description: '基于MEMS微热板技术的全量程氢气测量专家，在宽温域与复杂工况下提供长达10年的稳定监测能力。',
        category: 'sensor'
    },
    {
        id: 'portable_gas_test_module',
        name: '便携式气体传感器测试模块',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202510200847356528.jpg',
        description: '便携式气体传感器测试模块，用于传感器性能测试和标定，操作简便。',
        category: 'module'
    },
    {
        id: 'smart_gas_mixing_system',
        name: '高精度智能配气系统',
        image: 'https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202502131553258888.jpg',
        description: '高精度智能配气系统，可精确配制各种浓度的标准气体，适用于传感器标定和科研实验。',
        category: 'system'
    },
    // 定制服务
    {
        id: '../customization/custom_gas_sensing_module',
        name: '定制气体传感模组',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101352513746.png',
        description: '针对客户应用需求，提供包含器件封装、驱动电路、信号变换模组等多项目的定制化服务与解决方案。',
        category: 'module'
    },
    {
        id: '../customization/custom_instrument_dev',
        name: '定制仪器仪表开发',
        image: 'http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101353274954.png',
        description: '提供气体检测仪表从设计、加工与测试，包括传感器芯片的封装与探测器的制造，仪器仪表结构的设计与开发等。',
        category: 'detector'
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
