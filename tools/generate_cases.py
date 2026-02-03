import os

# Base directory for generated cases
OUTPUT_DIR = '/Users/zhizinan/Desktop/YX_Website/pages/gassensing/cases'
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

# HTML Template
TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">

<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - 应用案例 - 元芯传感</title>
    <link rel="stylesheet" href="../../../assets/css/vaisala-style.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        .vs-case-hero {{
            background: linear-gradient(rgba(0, 0, 0, 0.6), rgba(0, 0, 0, 0.7)), url('{image_bg}');
            background-size: cover;
            background-position: center;
            padding: 140px 0 80px;
            color: white;
            text-align: center;
        }}

        .vs-case-hero h1 {{
            font-size: 42px;
            font-weight: 700;
            margin-bottom: 20px;
        }}

        .vs-case-detail-section {{
            padding: 80px 0;
            background: #fff;
        }}

        .vs-case-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 60px;
        }}
        
        @media (max-width: 992px) {{
            .vs-case-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        .vs-content-block {{
            margin-bottom: 40px;
        }}

        .vs-content-block h2 {{
            font-size: 24px;
            color: var(--color-primary);
            border-left: 4px solid var(--color-accent-blue);
            padding-left: 16px;
            margin-bottom: 20px;
        }}
        
        .vs-content-block p {{
            font-size: 16px;
            line-height: 1.8;
            color: #444;
            margin-bottom: 15px;
        }}

        .vs-sidebar-box {{
            background: #f8fafc;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            border: 1px solid #eee;
        }}

        .vs-sidebar-box h3 {{
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 1px solid #ddd;
        }}

        .vs-info-list li {{
            margin-bottom: 15px;
            display: flex;
            align-items: flex-start;
            font-size: 14px;
        }}

        .vs-info-list i {{
            color: var(--color-primary);
            margin-right: 10px;
            margin-top: 4px;
        }}
        
        .vs-product-card-mini {{
            background: white;
            padding: 15px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            display: flex;
            align-items: center;
            margin-top: 15px;
        }}
        
        .vs-product-card-mini img {{
            width: 60px;
            height: 60px;
            object-fit: contain;
            margin-right: 15px;
        }}
    </style>
     <!-- Site Search -->
    <link rel="stylesheet" href="../../../assets/css/search.css">
</head>

<body>

    <header class="vs-header">
        <div class="vs-container vs-header__inner">
            <div style="display: flex; align-items: center;">
                <a href="../../../index.html" class="vs-logo">
                    <img src="../../../assets/images/logo.png" alt="Metachip Logo"
                        style="filter: brightness(0) invert(1);">
                    METACHIP
                </a>
            </div>

            <nav class="vs-nav">
                <ul class="vs-nav__list">
                    <li class="vs-nav__item">
                        <a href="../../../pages/gassensing/all-products.html" class="vs-nav__link">产品</a>
                    </li>
                    <li class="vs-nav__item vs-nav__item--has-mega">
                        <a href="../../../pages/gassensing/index.html" class="vs-nav__link">解决方案</a>
                    </li>
                    <li class="vs-nav__item"><a href="../../../pages/news/news.html" class="vs-nav__link">洞察与资讯</a></li>
                    <li class="vs-nav__item"><a href="../../../pages/about/about.html" class="vs-nav__link">公司简介</a></li>
                    <li class="vs-nav__item"><a href="../../../pages/contact/contact.html" class="vs-nav__link">联系我们</a>
                    </li>
                </ul>
            </nav>
            
             <div style="display: flex; gap: 24px; color: white; align-items: center;">
                <a href="#" class="vs-search-trigger" title="搜索 (Ctrl+K)"><i class="fas fa-search"></i></a>
                <a href="#" style="font-size: 14px; font-weight: 500;">CN / EN</a>
            </div>
        </div>
    </header>

    <main>
        <!-- Case Hero -->
        <section class="vs-case-hero">
            <div class="vs-container">
                <div style="margin-bottom: 20px; font-size: 14px; opacity: 0.8;">
                     <a href="../../../index.html" style="color:white;text-decoration:none;">首页</a> / 
                     <a href="../../gassensing/index.html" style="color:white;text-decoration:none;">解决方案</a> / 
                     <a href="../service-cases.html" style="color:white;text-decoration:none;">应用案例</a>
                </div>
                <h1>{title}</h1>
                <p style="font-size: 20px; max-width: 800px; margin: 0 auto;">{subtitle}</p>
            </div>
        </section>

        <section class="vs-case-detail-section">
            <div class="vs-container">
                <div class="vs-case-grid">
                    <!-- Main Content -->
                    <div class="vs-case-main">
                        <div class="vs-content-block">
                            <h2>案例背景</h2>
                            <p>{background}</p>
                        </div>
                        
                        <div class="vs-content-block">
                            <h2>核心需求与难点</h2>
                            <p>{requirements}</p>
                            <p>{challenges}</p>
                        </div>

                        <div class="vs-content-block">
                            <h2>元芯解决方案</h2>
                            <p>{solution}</p>
                            <img src="{image_detail}" alt="Solution Diagram" style="width: 100%; border-radius: 8px; margin: 20px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                        </div>
                        
                        <div class="vs-content-block">
                            <h2>达成效果</h2>
                            <p>{results}</p>
                        </div>
                        
                        <div class="vs-content-block">
                            <h2>专家点评</h2>
                            <div style="background: #f0f7ff; padding: 20px; border-radius: 8px; border-left: 4px solid var(--color-primary);">
                                <p style="margin:0; font-style: italic;">“{expert_comment}”</p>
                            </div>
                        </div>
                    </div>

                    <!-- Sidebar -->
                    <div class="vs-case-sidebar">
                        <div class="vs-sidebar-box">
                            <h3>项目概况</h3>
                            <ul class="vs-info-list" style="list-style: none; padding: 0;">
                                <li><i class="fas fa-map-marker-alt"></i> <strong>地点：</strong> {location}</li>
                                <li><i class="fas fa-industry"></i> <strong>行业：</strong> {industry}</li>
                                <li><i class="fas fa-calendar-alt"></i> <strong>时间：</strong> {date}</li>
                            </ul>
                        </div>

                        <div class="vs-sidebar-box">
                            <h3>应用产品</h3>
                            <div class="vs-product-card-mini">
                                <img src="{product_image}" alt="Product" style="background:#eee;">
                                <div>
                                    <h4 style="font-size: 14px; margin:0 0 5px 0;">{product_name}</h4>
                                    <a href="{product_link}" style="font-size: 12px; color: var(--color-primary);">查看产品详情</a>
                                </div>
                            </div>
                        </div>

                        <div class="vs-sidebar-box" style="text-align: center;">
                            <h3>需要类似方案？</h3>
                            <p style="font-size: 14px; margin-bottom: 20px;">我们的工程师随时为您提供专业解答。</p>
                            <a href="../../../pages/contact/contact.html" class="vs-btn vs-btn--primary" style="display: block;">联系我们</a>
                        </div>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <footer class="vs-footer">
        <div class="vs-container">
            <div class="vs-footer__bottom">
                <span>© 2024 湖南元芯传感科技有限责任公司. All rights reserved.</span>
            </div>
        </div>
    </footer>
    
    <!-- 全站搜索 -->
    <script src="../../../assets/js/search.js"></script>
</body>
</html>
"""

# Case Data
CASES = [
    {
        "filename": "case-1-truck.html",
        "title": "氢能重卡氢气检测",
        "subtitle": "保障天山脚下的绿色运输安全",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051020053200.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051020053200.png",
        "background": "随着“双碳”战略的推进，新疆地区利用丰富的可再生能源大力发展氢能重卡运输。然而，重卡在长途高负荷运行中，氢气管路接口易受震动影响而松动，存在泄漏风险。",
        "requirements": "客户需要一套便携、高灵敏度的检测设备，能够在日常巡检中快速发现微小的氢气泄漏点。",
        "challenges": "户外作业环境恶劣，风沙大、温差大，且车辆结构复杂，检测空间狭小。",
        "solution": "元芯传感提供的高灵敏度手持氢气检测仪，采用微纳加工MEMS芯片技术，具备极快的响应速度（T90 < 2s）和极高的灵敏度（ppm级）。设备设计坚固耐用，具备IP65防护等级，完全适应恶劣的户外环境。其柔性探头设计，能够轻松深入发动机舱内部狭窄区域进行检测。",
        "results": "该方案成功应用于车队的日常维护中，帮助技术人员提前发现了多处微小泄漏隐患，有效避免了安全事故的发生，保障了氢能重卡在天山脚下的安全驰骋。",
        "expert_comment": "便携式检测设备的高可靠性和易用性是保障氢能交通工具运营安全的第一道防线。",
        "location": "新疆 | 天山",
        "industry": "交通运输",
        "date": "2023年",
        "product_name": "手持氢气检测仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    },
    {
        "filename": "case-2-car-leak.html",
        "title": "氢燃料电池车氢气泄漏检测",
        "subtitle": "为城市氢能公交保驾护航",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051022163386.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051022163386.png",
        "background": "重庆某氢能公交运营公司，拥有一批氢燃料电池公交车。为确保乘客安全和车辆稳定运行，需要建立严格的车辆出入库检测机制。",
        "requirements": "需要对车辆储氢瓶阀门、管路接头及燃料电池电堆进行快速、准确的定点检漏。",
        "challenges": "公交场站环境嘈杂，干扰气体多（如尾气），要求检测设备具有极强的抗干扰能力。",
        "solution": "元芯传感手持氢气检测仪内置高性能气体传感器芯片，对氢气具有高度选择性，不受甲烷、一氧化碳等其他气体干扰。结合泵吸式采样，能够迅速捕捉泄漏信号并发出声光报警。",
        "results": "实施该检测方案后，公交公司的车辆故障检出率提升了30%，检修效率提高了50%，有力保障了市民的绿色出行。",
        "expert_comment": "在高干扰环境下实现精准检漏，体现了国产高端气体传感器技术的突破。",
        "location": "重庆",
        "industry": "公共交通",
        "date": "2023年",
        "product_name": "手持氢气检测仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    },
    {
        "filename": "case-3-sensor-line.html",
        "title": "国内首条片式印刷半导体传感器产线",
        "subtitle": "传感器产线EPC整体解决方案",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051024340419.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051024340419.png",
        "background": "随着物联网市场的爆发，对高性能、低成本传感器的需求激增。客户计划建设一条先进的片式印刷半导体传感器生产线。",
        "requirements": "需要一站式的EPC（设计、采购、施工）服务，包括工艺设计、设备选型、系统集成及调试。",
        "challenges": "工艺流程复杂，涉及微纳加工技术，且对环境洁净度、温湿度控制要求极高。",
        "solution": "元芯传感凭借在微纳加工领域的深厚积累，为客户提供了从厂房规划到工艺落地的全套解决方案。我们定制了高精度的印刷设备和烧结设备，集成了先进的在线检测系统，确保产品的一致性和良率。",
        "results": "产线一次性试产成功，各项指标达到国际先进水平，大大缩短了客户的产品上市周期，填补了国内技术空白。",
        "expert_comment": "这条产线的建成，标志着我国在高端传感器制造领域迈出了重要一步。",
        "location": "湖南 | 湘潭",
        "industry": "智能制造",
        "date": "2024年",
        "product_name": "传感器产线EPC"
    },
    {
        "filename": "case-4-pipeline-safety.html",
        "title": "输氢管道维护人员安全监测",
        "subtitle": "全天候守护能源动脉守护者",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051033217885.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051033217885.png",
        "background": "长距离输氢管道是“西氢东送”的大动脉。沿线巡检维护人员面临着高压氢气泄漏带来的窒息和爆炸风险。",
        "requirements": "必须为每位巡检人员配备轻便、可靠的个人防护装备，实时监测环境氢气浓度。",
        "challenges": "野外作业时间长，对设备续航能力要求高；且需具备跌落报警等人员状态监测功能。",
        "solution": "元芯传感穿戴式氢气报警器，采用低功耗设计，单次充电可连续工作48小时以上。设备体积小巧，佩戴舒适，集成蓝牙/LORA通讯模块，可将数据实时上传至监控中心，实现人员位置与安全状态的双重监控。",
        "results": "该设备已成为巡检队伍的标配，多次在微量泄漏初期发出预警，成功避免了人员伤亡事故。",
        "expert_comment": "以人为本的安全理念，通过物联网技术得到了完美落地。",
        "location": "管道沿线",
        "industry": "能源输送",
        "date": "2024年",
        "product_name": "穿戴式氢气报警器"
    },
    {
        "filename": "case-5-chemical-plant.html",
        "title": "化工场所氢气泄漏监测",
        "subtitle": "构建化工厂区的安全防线",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051036122090.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051036122090.png",
        "background": "某大型化工园区内，氢气作为重要的原料气和副产气，广泛存在于各个生产环节。一旦发生泄漏，后果不堪设想。",
        "requirements": "需建立覆盖全厂区的氢气泄漏在线监测系统，实现24小时不间断监控和联动报警。",
        "challenges": "厂区面积大，监测点位多，布线困难；且环境存在腐蚀性气体，对传感器寿命是极大考验。",
        "solution": "元芯传感部署了数百台固定式氢气报警器，利用防腐蚀涂层技术增强传感器耐用性。系统采用无线MESH组网技术，解决了布线难题，并与厂区DCS系统无缝对接，一旦报警自动触发排风和切断阀。",
        "results": "系统运行以来，不仅满足了安监部门的严格要求，更将企业的安全管理水平提升到了智能化新高度。",
        "expert_comment": "工业互联网+安全生产，是化工行业未来发展的必由之路。",
        "location": "江苏",
        "industry": "化工与新材料",
        "date": "2023年",
        "product_name": "固定式氢气报警器"
    },
     {
        "filename": "case-6-train.html",
        "title": "氢能源市域列车氢气检测",
        "subtitle": "保障轨道交通的绿色动力",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051036521468.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051036521468.png",
        "background": "全球首列氢能源市域列车投入试运行，标志着轨道交通迈入氢能时代。车辆检修基地的安全保障变得尤为重要。",
        "requirements": "对列车顶部的储氢系统和底部的燃料电池系统进行定期、全面的泄漏检测。",
        "challenges": "检测部位分散，高空作业难度大，要求检测设备轻便且具备远距离采样能力。",
        "solution": "我们提供了配备伸缩采样杆的手持氢气检测仪，检修人员无需登高即可完成车顶管路的检测。设备操作简单，读数直观，大大降低了作业强度和风险。",
        "results": "该方案已纳入列车标准检修规程，为氢能列车的安全运营提供了坚实的技术支撑。",
        "expert_comment": "针对特定应用场景的定制化解决方案，极大提升了运维效率。",
        "location": "四川 | 成都",
        "industry": "轨道交通",
        "date": "2024年",
        "product_name": "手持氢气检测仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    },
     {
        "filename": "case-7-humidity-box.html",
        "title": "恒温恒湿箱漏点检测",
        "subtitle": "精密仪器的气密性守护者",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051037326913.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051037326913.png",
        "background": "恒温恒湿箱是环境试验的关键设备，其箱体密封性能直接影响温湿度控制的精度和均匀性。",
        "requirements": "传统的肥皂泡检漏法效率低、易污染，客户急需一种非接触、高灵敏度的检漏方法。",
        "challenges": "泄漏点通常极为细微（针孔级），且位置隐蔽，难以通过肉眼发现。",
        "solution": "元芯传感引入氮氢示踪检漏技术，利用氢气分子极小的特性（穿透力强）和氮氢示踪检漏仪的超高灵敏度，快速定位微小泄漏点。该方法无毒无害，清洁环保。",
        "results": "检漏效率提高了10倍以上，且能发现传统方法无法检测的微漏，显著提升了环境试验箱的产品质量。",
        "expert_comment": "示踪气体检漏技术在精密制造领域的应用前景广阔。",
        "location": "广东 | 东莞",
        "industry": "仪器仪表",
        "date": "2023年",
        "product_name": "氮氢示踪检漏仪"
    },
    {
        "filename": "case-8-h2-generator.html",
        "title": "制氢机氢气泄漏检测",
        "subtitle": "家用与医疗制氢设备的安全卫士",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051038477044.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051038477044.png",
        "background": "随着氢医学的发展，家用吸氢机和富氢水机逐渐普及。作为消费电子类产品，其安全性是用户关注的焦点。",
        "requirements": "生产线上需要对每一台制氢机进行全检，确保出厂产品零泄漏。",
        "challenges": "生产节拍快，要求检测设备响应迅速、复位快，且不能对产品造成二次污染。",
        "solution": "元芯传感为生产线定制了快速检漏工装，配套高精度手持检测仪。通过优化气路设计，实现了秒级响应和快速清洗归零，完美适配流水线作业节奏。",
        "results": "帮助客户建立了严格的质量控制体系，大大降低了售后返修率，提升了品牌口碑。",
        "expert_comment": "消费级氢能产品的安全标准，正在通过先进的检测手段逐步建立。",
        "location": "上海",
        "industry": "医疗健康",
        "date": "2024年",
        "product_name": "手持氢气检测仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    },
    {
        "filename": "case-9-lab-safety.html",
        "title": "氢燃料电池科研实验室人员安全监测",
        "subtitle": "高校实验室的安全屏障",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051040294898.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051040294898.png",
        "background": "高校和研究院所的燃料电池实验室，经常涉及高压氢气和各种催化剂实验，实验条件复杂多变。",
        "requirements": "不仅要监测环境氢气浓度，还要保障每一位实验人员的个人安全，防止因操作失误导致的局部泄漏伤害。",
        "challenges": "实验室空间封闭，人员流动性大，这就要求安全监测既要全面覆盖又要重点跟踪。",
        "solution": "采用“固定监测+移动防护”的组合方案。在关键设备旁安装固定式报警器，同时要求实验人员佩戴便携式报警器。两者形成互补，构建了全方位的安全防护网。",
        "results": "彻底消除了实验室的安全盲区，让科研人员能够全身心投入创新研究，无后顾之忧。",
        "expert_comment": "安全是科研的前提，多重防护机制值得推广。",
        "location": "北京",
        "industry": "科研教育",
        "date": "2023年",
        "product_name": "穿戴式氢气报警器"
    },
    {
        "filename": "case-10-liquid-h2.html",
        "title": "液氢储罐区工作人员安全监测",
        "subtitle": "超低温环境下的可靠感知",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051041110661.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051041110661.png",
        "background": "液氢的大规模应用是未来的趋势，但液氢泄漏后会迅速气化并吸收大量热量，并在低温下积聚，特性与常温氢气不同。",
        "requirements": "监测设备需在低温环境下保持正常工作，且能灵敏探测低温氢气。",
        "challenges": "极低温度（-253℃附近的泄漏源）会导致常规电子元器件失效或漂移。",
        "solution": "元芯传感针对液氢场景，对报警器进行了宽温域补偿和防冻设计。特殊的传感器封装结构有效防止了水汽结冰堵塞进气孔，确保了在液氢储罐区巡检时的可靠性。",
        "results": "成功解决了液氢环境下监测难的问题，为民用液氢产业的发展积累了宝贵的安全管理经验。",
        "expert_comment": "攻克极端环境下的传感难题，展现了深厚的技术底蕴。",
        "location": "内蒙古",
        "industry": "能源化工",
        "date": "2024年",
        "product_name": "穿戴式氢气报警器"
    },
    {
        "filename": "case-11-mining-truck.html",
        "title": "氢能矿卡氢气泄漏检测",
        "subtitle": "助力绿色矿山建设",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051058555575.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051058555575.png",
        "background": "露天矿山正在积极推广氢能矿卡以替代柴油车，减少碳排放。矿区路况颠簸，粉尘极大。",
        "requirements": "车载泄漏检测系统必须具备抗震、防尘、防泥水的特性，且需与车辆控制系统联动。",
        "challenges": "强烈的机械振动和高浓度的煤粉尘容易导致传统传感器误报或失效。",
        "solution": "元芯传感的车载氢泄漏模组，内部填充减震胶，接口采用车规级防水插件。特殊的透气膜设计，只透气不透水和粉尘。模组通过CAN总线与车辆VCU通信，实现毫秒级联动切断。",
        "results": "该模组已在前装市场大批量应用，在万吨级氢能矿卡的示范运营中表现优异，零误报，零故障。",
        "expert_comment": "车规级的设计标准，完美适配了最严苛的商用车应用场景。",
        "location": "内蒙古 | 鄂尔多斯",
        "industry": "矿山机械",
        "date": "2023年",
        "product_name": "手持氢气检测仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    },
    {
        "filename": "case-12-gas-system.html",
        "title": "高校科研实验室配气系统",
        "subtitle": "精准调控，赋能基础研究",
        "image_bg": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051059472632.png",
        "image_detail": "https://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202506051059472632.png",
        "background": "传感器研发和催化剂评价实验中，需要精确配置不同浓度、不同湿度的混合气体。",
        "requirements": "能够动态调节氢气、氧气、氮气及VOCs气体的配比，精度优于±1%。",
        "challenges": "微小流量控制难，且需保证气体混合的均匀性和稳定性。",
        "solution": "元芯传感自主研发的动态配气系统，采用高精度质量流量控制器（MFC）和独特的混气室设计。系统内置智能算法，可根据实验需求自动生成梯度浓度曲线，并实时记录数据。",
        "results": "极大提高了实验效率和数据的重复性，成为多个国家重点实验室的得力助手。",
        "expert_comment": "工欲善其事，必先利其器。高精度的配气系统是气体研究的基石。",
        "location": "湖北 | 武汉",
        "industry": "科研仪器",
        "date": "2023年",
        "product_name": "动态配气系统"
    },
    {
        "filename": "case-13-diesel-engine.html",
        "title": "柴油发动机真空检漏",
        "subtitle": "高效定位发动机气密性隐患",
        "image_bg": "../../../assets/images/cases/weifang/4.png",
        "image_detail": "../../../assets/images/cases/weifang/3.png",
        "background": "柴油发动机作为工业动力核心，其气密性直接影响燃烧效率和动力输出。传统的水检或气压衰减法难以定位微小泄漏点，且效率低下。",
        "requirements": "客户需要对发动机整机及零部件进行高精度的真空检漏，要求能精确定位到针孔级泄漏点。",
        "challenges": "发动机结构复杂，铸造件表面粗糙，密封腔体多，且生产节拍紧凑。",
        "solution": "采用元芯传感氮氢示踪检漏系统。向发动机内部充入低压氮氢混合气，利用氢气分子强穿透性，配合高灵敏度手持检漏仪在外部扫描，快速捕捉泄漏信号。该方案对微小泄漏具有极高的响应速度。",
        "results": "检漏灵敏度提升至10^-7 mbar·l/s量级，单台检测时间大幅缩短，帮助客户显著提升了产品良率，确保了发动机在严苛环境下的可靠运行。",
        "expert_comment": "示踪气体检漏技术彻底解决了复杂铸件微漏难查的行业痛点。",
        "location": "山东 | 潍坊",
        "industry": "机械制造",
        "date": "2024年",
        "product_name": "氮氢示踪检漏仪",
        "product_link": "../ld_h2_detector.html",
        "product_image": "http://wstx.web.vleader.net.cn/9D939A2595A6407F93967928E013299E/202501101344323886.png"
    }
]

def generate_files():
    for case in CASES:
        file_path = os.path.join(OUTPUT_DIR, case['filename'])
        
        # Calculate relative path depth adjustment (not needed for absolute links in this simplified template, 
        # but kept mentally consistent: file is at pages/gassensing/cases/, so root is ../../../)
        
        html_content = TEMPLATE.format(
            title=case['title'],
            subtitle=case['subtitle'],
            image_bg=case['image_bg'],
            image_detail=case['image_detail'],
            background=case['background'],
            requirements=case['requirements'],
            challenges=case['challenges'],
            solution=case['solution'],
            results=case['results'],
            expert_comment=case['expert_comment'],
            location=case['location'],
            industry=case['industry'],
            date=case['date'],
            product_name=case['product_name'],
            product_link=case.get('product_link', '../../gassensing/all-products.html'),
            product_image=case.get('product_image', '../../../assets/images/product_placeholder.png')
        )
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"Generated: {case['filename']}")

if __name__ == '__main__':
    generate_files()
