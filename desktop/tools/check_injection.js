/**
 * 注入脚本的行为校验（零依赖，直接用 node 运行）。
 *
 * 注入脚本是外壳里最脆弱的一环：它要覆盖后台自己的标题写入、又要从后台渲染的
 * 未读徽标里读数字，一旦逻辑出错，表现是"托盘角标永远不动"这种静默失效。
 * 这里用一个最小 DOM 模拟把这套逻辑跑一遍，避免只能靠手工点界面来验证。
 *
 * 用法（项目根目录）：
 *     node desktop/tools/check_injection.js
 *
 * 作者：元芯传感技术团队
 */

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SCRIPT_PATH = path.join(__dirname, '..', 'src-tauri', 'src', 'scripts.rs');

/** 从 scripts.rs 里取出 BEHAVIOR_PATCH 的原始 JS。 */
function extractInjectedScript() {
    const source = fs.readFileSync(SCRIPT_PATH, 'utf8');
    const match = source.match(/const BEHAVIOR_PATCH: &str = r##"([\s\S]*?)"##;/);
    if (!match) {
        throw new Error('未能在 scripts.rs 中找到 BEHAVIOR_PATCH');
    }
    return match[1];
}

/** 构造一个刚好够用的 DOM 模拟。 */
function createSandbox() {
    class FakeDocument {}
    Object.defineProperty(FakeDocument.prototype, 'title', {
        configurable: true,
        get() { return this._title || ''; },
        set(value) { this._title = String(value); },
    });

    const elements = new Map();
    const intervals = [];

    const document = new FakeDocument();
    // HTML 解析器直接写 DOM，不走 JS setter——这是启动时标题的真实来源。
    document._title = '';
    document.getElementById = (id) => elements.get(id) || null;
    document.addEventListener = () => {};

    const sandbox = {
        window: { location: { assign() {} } },
        document,
        Document: FakeDocument,
        Object,
        String,
        Number,
        RegExp,
        Math,
        setTimeout,
        setInterval: (fn, ms) => { intervals.push({ fn, ms }); return intervals.length; },
        console,
    };
    sandbox.window.document = document;
    sandbox.window.setInterval = sandbox.setInterval;
    sandbox.globalThis = sandbox;

    return { sandbox, document, elements, intervals };
}

/** 模拟后台的 setMessagesUnreadIndicator 渲染出的徽标状态。 */
function setBadge(elements, count) {
    const hidden = count <= 0;
    elements.set('messageCenterUnreadBadge', {
        hasAttribute: (name) => name === 'hidden' && hidden,
        textContent: count > 99 ? '99+' : String(count),
    });
}

function setLoginVisible(elements, visible) {
    elements.set('loginPage', { style: { display: visible ? 'flex' : 'none' } });
}

let failures = 0;

function check(label, actual, expected) {
    const ok = actual === expected;
    if (!ok) {
        failures += 1;
    }
    console.log(`${ok ? '  ok  ' : '  FAIL'}  ${label}`);
    if (!ok) {
        console.log(`        期望: ${JSON.stringify(expected)}`);
        console.log(`        实际: ${JSON.stringify(actual)}`);
    }
}

function run() {
    const injected = extractInjectedScript();
    const { sandbox, document, elements, intervals } = createSandbox();

    setLoginVisible(elements, true);
    setBadge(elements, 0);

    vm.createContext(sandbox);
    vm.runInContext(injected, sandbox);

    // 注入脚本在 document-start 执行，此刻 <title> 还没解析出来。
    check('初始标题为空', document.title, '');

    // 解析器写入 <title>（不走 JS setter），随后后台 app.js 切视图时重写标题。
    document._title = '管理后台 - 元芯传感';
    document.title = '网站数据 - 管理后台';
    check('未读为 0 时不加前缀', document.title, '网站数据 - 管理后台');

    const tick = () => intervals.forEach(({ fn }) => fn());

    // 登录页可见时即使徽标有数字也不应显示角标。
    setBadge(elements, 5);
    tick();
    check('登录页可见时忽略徽标', document.title, '网站数据 - 管理后台');

    // 登录后：徽标出现 → 标题带上前缀。
    setLoginVisible(elements, false);
    tick();
    check('未读 5 条时标题带前缀', document.title, '(5) 网站数据 - 管理后台');

    // 后台切视图重写标题时，前缀必须保留（这是访问器覆盖的核心目的）。
    document.title = '留言系统 - 管理后台';
    check('后台重写标题后前缀仍在', document.title, '(5) 留言系统 - 管理后台');

    // 超过 99 条时后台渲染 99+，前缀要原样带上。
    setBadge(elements, 120);
    tick();
    check('未读 99+ 的前缀', document.title, '(99+) 留言系统 - 管理后台');

    // 未读清零 → 前缀消失，基准标题保持不变。
    setBadge(elements, 0);
    tick();
    check('未读清零后前缀消失', document.title, '留言系统 - 管理后台');

    // window.open 归一化：同窗口导航，且不返回窗口对象。
    let navigated = null;
    sandbox.window.location.assign = (url) => { navigated = url; };
    const opened = sandbox.window.open('/api/backup/download', '_blank', 'noopener');
    check('window.open 返回值', opened, null);
    check('window.open 改写为同窗口导航', navigated, '/api/backup/download');

    console.log('');
    console.log(failures === 0 ? '注入脚本行为校验全部通过。' : `${failures} 项校验失败。`);
    process.exitCode = failures === 0 ? 0 : 1;
}

run();
