/**
 * 元芯传感 - AI智能客服
 * 支持上下文对话和知识库检索
 */

(function () {
    'use strict';

    // Guard against duplicate script injection from page templates and loader scripts.
    if (window.__METACHIP_CHATBOT_INITIALIZED__) {
        return;
    }
    window.__METACHIP_CHATBOT_INITIALIZED__ = true;

    const CHATBOT_MIN_WIDTH = 360;
    const CHATBOT_DESKTOP_DEFAULT_WIDTH = 460;
    const CHATBOT_MOBILE_BREAKPOINT = 480;
    const AGENT_STATUS_MIN_VISIBLE_MS = 1000;
    const TYPEWRITER_DELAY_MS = 18;
    const CHATBOT_REQUEST_TIMEOUT_MS = 90000;
    const RECOMMENDATIONS_REVEAL_DELAY_MS = 520;
    const PUBLIC_TURNSTILE_SCRIPT_SRC = '/assets/js/public-turnstile.js';

    // 会话ID（每次页面加载时生成新的）
    let sessionId = generateSessionId();

    // 对话历史（不持久化，关闭/刷新即清除）
    let conversationHistory = [];

    // DOM Elements
    let chatbotTrigger, chatbotWindow, messagesContainer, inputField, sendButton, suggestionTrack, resizeHandle, turnstileMount;
    let hideWindowTimer = null;
    let lastTouchToggleAt = 0;
    let ignoreOutsideClickUntil = 0;
    let isResizing = false;
    let resizeStartX = 0;
    let resizeStartWidth = 0;
    let chatbotCustomWidth = null;
    let publicTurnstileScriptPromise = null;
    let chatbotTurnstileGuard = null;
    let pendingTurnstileToken = '';
    let pendingTurnstileRetry = null;
    let retryingAfterTurnstile = false;

    // 输入区预设问题（滚动展示，可一键发送）
    const PRESET_QUESTIONS = [
        '介绍一下元芯传感',
        '氢气传感器有哪些产品',
        '你们有哪些行业解决方案',
        '怎么选择适合的检测方案',
        '支持哪些定制化服务',
        '如何获取产品报价',
        '售后和技术支持怎么联系',
        '可以提供测试样机吗'
    ];

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initChatbot);
    } else {
        initChatbot();
    }

    function initChatbot() {
        // Prevent running in iframes (e.g. particle effects)
        if (window.self !== window.top) return;

        loadStyles().then(() => {
            createChatbotUI();
            renderPresetQuestions();
            bindEvents();
        });
        // 不再加载历史记录
    }

    function loadStyles() {
        return new Promise((resolve) => {
            if (document.querySelector('link[href*="chatbot.css"]')) {
                resolve();
                return;
            }

            // Attempt to find the script tag to resolve path
            const scripts = document.getElementsByTagName('script');
            let scriptPath = '';
            for (let i = 0; i < scripts.length; i++) {
                if (scripts[i].src && scripts[i].src.includes('chatbot.js')) {
                    scriptPath = scripts[i].src;
                    break;
                }
            }

            let cssPath;
            if (scriptPath) {
                // resolve ../css/chatbot.css relative to js/chatbot.js
                // scriptPath is like .../assets/js/chatbot.js
                // we want .../assets/css/chatbot.css
                cssPath = scriptPath.replace('/js/', '/css/').replace('.js', '.css');
            } else {
                // Fallback for default structure
                cssPath = '/assets/css/chatbot.css';
            }

            const link = document.createElement('link');
            link.rel = 'stylesheet';
            link.href = cssPath;
            link.onload = resolve;
            link.onerror = resolve; // Continue even if error
            document.head.appendChild(link);
        });
    }

    function generateSessionId() {
        return 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    function createChatbotUI() {
        // Create floating trigger widget (bottom-right minimized bar)
        const triggerHTML = `
            <button class="chatbot-trigger" id="chatbotTrigger" aria-label="打开智能客服">
                <i class="fas fa-comment-dots chatbot-trigger__icon"></i>
                <span class="chatbot-trigger__text">有问题？与元芯 AI 沟通</span>
            </button>
        `;

        // Create chat window
        const windowHTML = `
            <div class="chatbot-window" id="chatbotWindow" style="display: none;">
                <div class="chatbot-resize-handle" id="chatbotResizeHandle" aria-hidden="true">
                    <span class="chatbot-resize-grip"></span>
                </div>
                <div class="chatbot-header">
                    <div class="chatbot-avatar">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="chatbot-info">
                        <h4>元芯智能助手</h4>
                        <span>在线服务中</span>
                    </div>
                    <div class="chatbot-header-actions">
                        <button class="chatbot-window-btn chatbot-minimize" id="chatbotMinimize" aria-label="最小化">
                            <i class="fas fa-minus"></i>
                        </button>
                        <button class="chatbot-window-btn chatbot-close" id="chatbotClose" aria-label="关闭">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                <div class="chatbot-messages" id="chatbotMessages">
                    <div class="chat-welcome">
                        <h4>👋 您好！我是元芯智能助手</h4>
                        <p>有关产品、技术或合作的问题，我都可以帮您解答。</p>
                        <div class="quick-actions">
                            <button class="quick-action-btn" data-question="介绍一下元芯传感">公司介绍</button>
                            <button class="quick-action-btn" data-question="氢气传感器有哪些产品">氢气传感器</button>
                            <button class="quick-action-btn" data-question="如何联系你们">联系方式</button>
                        </div>
                    </div>
                </div>
                <div class="chatbot-input-area">
                    <div class="chatbot-suggestion-ticker" aria-label="可点击发送的预设问题">
                        <div class="chatbot-suggestion-track" id="chatbotSuggestionTrack"></div>
                    </div>
                    <div class="chatbot-turnstile" id="chatbotTurnstile" hidden></div>
                    <div class="chatbot-input-row">
                        <textarea class="chatbot-input" id="chatbotInput" placeholder="输入您的问题..." rows="1"></textarea>
                        <button class="chatbot-send" id="chatbotSend" aria-label="发送">
                            <i class="fas fa-paper-plane"></i>
                        </button>
                    </div>
                    <div class="chatbot-disclaimer">AI 的回答可能会犯错</div>
                </div>
            </div>
        `;

        // Append trigger and window
        document.body.insertAdjacentHTML('beforeend', triggerHTML);
        document.body.insertAdjacentHTML('beforeend', windowHTML);

        // Get DOM references
        chatbotTrigger = document.getElementById('chatbotTrigger');
        chatbotWindow = document.getElementById('chatbotWindow');
        messagesContainer = document.getElementById('chatbotMessages');
        inputField = document.getElementById('chatbotInput');
        sendButton = document.getElementById('chatbotSend');
        suggestionTrack = document.getElementById('chatbotSuggestionTrack');
        resizeHandle = document.getElementById('chatbotResizeHandle');
        turnstileMount = document.getElementById('chatbotTurnstile');
    }

    function renderPresetQuestions() {
        if (!suggestionTrack) return;

        const buildGroup = (hidden) => {
            const group = document.createElement('div');
            group.className = 'chatbot-suggestion-group';
            if (hidden) group.setAttribute('aria-hidden', 'true');

            PRESET_QUESTIONS.forEach((question) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'chatbot-suggestion-pill';
                btn.setAttribute('data-question', question);
                btn.setAttribute('title', question);
                btn.textContent = question;
                group.appendChild(btn);
            });

            return group;
        };

        suggestionTrack.innerHTML = '';
        suggestionTrack.appendChild(buildGroup(false));
        suggestionTrack.appendChild(buildGroup(true));
    }

    /* Trigger is always placed as a fixed element on document.body.
       No nav-bar integration needed. */

    function bindEvents() {
        // Toggle chat window
        chatbotTrigger.addEventListener('touchend', (e) => {
            if (!e.cancelable) return;
            e.preventDefault();
            e.stopPropagation();
            lastTouchToggleAt = Date.now();
            ignoreOutsideClickUntil = Date.now() + 500;
            toggleChatWindow();
        }, { passive: false });

        chatbotTrigger.addEventListener('click', (e) => {
            // iOS/Android may emit synthetic click after touchend.
            if (Date.now() - lastTouchToggleAt < 700) {
                e.preventDefault();
                e.stopPropagation();
                return;
            }
            ignoreOutsideClickUntil = Date.now() + 300;
            toggleChatWindow();
        });
        document.getElementById('chatbotMinimize').addEventListener('click', minimizeChatWindow);
        document.getElementById('chatbotClose').addEventListener('click', closeChatWindow);
        chatbotWindow.addEventListener('wheel', handleChatWindowWheel, { passive: false });
        window.addEventListener('resize', positionChatWindow);
        if (resizeHandle) {
            resizeHandle.addEventListener('pointerdown', startResizeChatWindow);
        }
        window.addEventListener('pointermove', handleResizeChatWindow);
        window.addEventListener('pointerup', stopResizeChatWindow);
        window.addEventListener('pointercancel', stopResizeChatWindow);

        // Send message
        sendButton.addEventListener('click', sendMessage);
        inputField.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        // Auto-resize textarea
        inputField.addEventListener('input', autoResizeTextarea);

        // Quick action buttons
        document.addEventListener('click', (e) => {
            const target = e.target instanceof Element ? e.target : null;
            if (!target) return;

            const suggestionBtn = target.closest('.chatbot-suggestion-pill');
            if (suggestionBtn) {
                const question = suggestionBtn.getAttribute('data-question');
                if (question) {
                    inputField.value = question;
                    sendMessage();
                }
                return;
            }

            const quickActionBtn = target.closest('.quick-action-btn');
            if (quickActionBtn) {
                const question = quickActionBtn.getAttribute('data-question');
                if (question) {
                    inputField.value = question;
                    sendMessage();
                }
            }
        });

        // Close on outside click
        document.addEventListener('click', (e) => {
            if (!chatbotWindow.classList.contains('open')) return;
            if (Date.now() < ignoreOutsideClickUntil) return;

            const eventPath = typeof e.composedPath === 'function' ? e.composedPath() : null;
            const clickedInsideChatbot = Array.isArray(eventPath)
                ? eventPath.includes(chatbotWindow) || eventPath.includes(chatbotTrigger)
                : (chatbotWindow.contains(e.target) || chatbotTrigger.contains(e.target));

            if (!clickedInsideChatbot) {
                minimizeChatWindow();
            }
        });
    }

    function toggleChatWindow() {
        if (chatbotWindow.classList.contains('open')) {
            minimizeChatWindow();
        } else {
            openChatWindow();
        }
    }

    function openChatWindow() {
        if (hideWindowTimer) {
            clearTimeout(hideWindowTimer);
            hideWindowTimer = null;
        }
        syncChatbotWidthForViewport();
        chatbotWindow.style.display = 'flex';
        positionChatWindow();
        // Force reflow
        chatbotWindow.offsetHeight;
        chatbotWindow.classList.add('open');
        chatbotTrigger.classList.add('active');
        inputField.focus();
    }

    function minimizeChatWindow() {
        chatbotWindow.classList.remove('open');
        chatbotTrigger.classList.remove('active');
        if (hideWindowTimer) {
            clearTimeout(hideWindowTimer);
            hideWindowTimer = null;
        }

        // Wait for transition (300ms) then hide
        hideWindowTimer = setTimeout(() => {
            chatbotWindow.style.display = 'none';
            hideWindowTimer = null;
        }, 300);
    }

    function closeChatWindow() {
        minimizeChatWindow();
    }

    function handleChatWindowWheel(e) {
        if (!chatbotWindow || !chatbotWindow.classList.contains('open')) return;
        if (!messagesContainer) return;

        // Only intercept scroll when mouse is inside the chatbot window
        const rect = chatbotWindow.getBoundingClientRect();
        const isInsideChatbot = 
            e.clientX >= rect.left && 
            e.clientX <= rect.right && 
            e.clientY >= rect.top && 
            e.clientY <= rect.bottom;

        if (isInsideChatbot) {
            messagesContainer.scrollTop += e.deltaY;
            e.preventDefault();
        }
    }

    function positionChatWindow() {
        if (!chatbotWindow || !chatbotTrigger) return;
        syncChatbotWidthForViewport();

        const triggerRect = chatbotTrigger.getBoundingClientRect();
        const gap = window.innerWidth <= 480 ? 12 : 14;
        const viewportPadding = window.innerWidth <= 480 ? 10 : 16;
        const right = isMobileViewport()
            ? viewportPadding
            : Math.max(viewportPadding, window.innerWidth - triggerRect.right);
        const bottom = Math.max(viewportPadding, window.innerHeight - triggerRect.top + gap);
        const availableHeight = Math.max(320, triggerRect.top - gap - viewportPadding);

        chatbotWindow.style.left = 'auto';
        chatbotWindow.style.top = 'auto';
        chatbotWindow.style.right = `${right}px`;
        chatbotWindow.style.bottom = `${bottom}px`;
        chatbotWindow.style.maxHeight = `${availableHeight}px`;
    }

    function isMobileViewport() {
        return window.innerWidth <= CHATBOT_MOBILE_BREAKPOINT;
    }

    function getChatbotMaxWidth() {
        const viewportAllowance = Math.max(320, window.innerWidth - 32);
        return Math.max(CHATBOT_MIN_WIDTH, viewportAllowance);
    }

    function syncChatbotWidthForViewport() {
        if (!chatbotWindow) return;

        if (isMobileViewport()) {
            chatbotWindow.style.width = '';
            chatbotWindow.style.maxWidth = '';
            return;
        }

        const width = Math.min(
            getChatbotMaxWidth(),
            Math.max(CHATBOT_MIN_WIDTH, Number(chatbotCustomWidth) || CHATBOT_DESKTOP_DEFAULT_WIDTH)
        );
        chatbotWindow.style.width = `${width}px`;
        chatbotWindow.style.maxWidth = 'calc(100vw - 32px)';
    }

    function startResizeChatWindow(e) {
        if (!chatbotWindow || isMobileViewport()) return;
        if (typeof e.button === 'number' && e.button !== 0) return;

        e.preventDefault();
        isResizing = true;
        resizeStartX = e.clientX;
        resizeStartWidth = chatbotWindow.getBoundingClientRect().width;
        chatbotWindow.classList.add('chatbot-window-resizing');
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
        if (resizeHandle && typeof resizeHandle.setPointerCapture === 'function') {
            try {
                resizeHandle.setPointerCapture(e.pointerId);
            } catch (_err) {
                // Ignore pointer capture failures.
            }
        }
    }

    function handleResizeChatWindow(e) {
        if (!isResizing || !chatbotWindow) return;

        const deltaX = resizeStartX - e.clientX;
        const nextWidth = Math.min(
            getChatbotMaxWidth(),
            Math.max(CHATBOT_MIN_WIDTH, resizeStartWidth + deltaX)
        );
        chatbotCustomWidth = nextWidth;
        chatbotWindow.style.width = `${nextWidth}px`;
        chatbotWindow.style.maxWidth = 'calc(100vw - 32px)';
        positionChatWindow();
    }

    function stopResizeChatWindow(e) {
        if (!isResizing) return;
        isResizing = false;
        chatbotWindow.classList.remove('chatbot-window-resizing');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (resizeHandle && typeof resizeHandle.releasePointerCapture === 'function' && e && typeof e.pointerId === 'number') {
            try {
                resizeHandle.releasePointerCapture(e.pointerId);
            } catch (_err) {
                // Ignore pointer capture failures.
            }
        }
    }

    function clearChatHistory() {
        conversationHistory = [];
        // 重置消息区域为欢迎界面
        messagesContainer.innerHTML = `
            <div class="chat-welcome">
                <h4>👋 您好！我是元芯智能助手</h4>
                <p>有关产品、技术或合作的问题，我都可以帮您解答。</p>
                <div class="quick-actions">
                    <button class="quick-action-btn" data-question="介绍一下元芯传感">公司介绍</button>
                    <button class="quick-action-btn" data-question="氢气传感器有哪些产品">氢气传感器</button>
                    <button class="quick-action-btn" data-question="如何联系你们">联系方式</button>
                </div>
            </div>
        `;
        // 生成新的会话ID
        sessionId = generateSessionId();
    }

    function autoResizeTextarea() {
        inputField.style.height = 'auto';
        inputField.style.height = Math.min(inputField.scrollHeight, 100) + 'px';
    }

    // 不再需要持久化历史记录

    async function sendMessage() {
        const message = inputField.value.trim();
        if (!message) return;

        // Clear input
        inputField.value = '';
        inputField.style.height = 'auto';

        // Remove welcome message if present
        const welcome = messagesContainer.querySelector('.chat-welcome');
        if (welcome) welcome.remove();

        // Append user message
        appendMessage('user', message);
        conversationHistory.push({ role: 'user', content: message });

        // Show agent status indicator
        const typingEl = showAgentStatusIndicator();

        // Disable input while processing
        setInputEnabled(false);

        const turnstileTokenForRequest = pendingTurnstileToken;
        pendingTurnstileToken = '';
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), CHATBOT_REQUEST_TIMEOUT_MS);

        try {
            const response = await fetch('/api/chatbot/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId,
                    page_url: window.location.pathname + window.location.search,
                    page_title: document.title || '',
                    turnstileToken: turnstileTokenForRequest,
                    history: conversationHistory.slice(-10) // Send last 10 messages for context
                }),
                signal: controller.signal
            });

            if (!response.ok && await handleChatbotTurnstileResponse(response.clone(), message, typingEl)) {
                return;
            }

            if (!response.ok) {
                removeTypingIndicator(typingEl);
                appendError(await getResponseErrorMessage(response));
                return;
            }

            if (turnstileTokenForRequest) {
                hideChatbotTurnstile();
            }

            // Check if it's a streaming response
            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('text/event-stream')) {
                // Handle streaming response
                await handleStreamingResponse(response, typingEl);
            } else {
                // Handle regular JSON response
                const data = await response.json();
                if (data.success) {
                    const replyText = data.response || '';
                    const recommendations = data.recommendations || [];
                    const botEl = prepareThinkingMessageForAnswer(typingEl, data.status_updates || [])
                        || appendMessage('bot', '', true);
                    if (Array.isArray(data.status_updates) && data.status_updates.length) {
                        compactAgentStatusPanel(botEl, data.status_updates);
                    }
                    await renderMessageWithTypewriter(botEl, replyText);
                    await revealMessageRecommendations(botEl, recommendations);
                    conversationHistory.push({ role: 'assistant', content: replyText });
                } else {
                    removeTypingIndicator(typingEl);
                    appendError(data.message || '抱歉，出现了一些问题。');
                }
            }
        } catch (error) {
            removeTypingIndicator(typingEl);
            console.error('Chat error:', error);
            if (error && error.name === 'AbortError') {
                appendError('请求超时，请稍后重试。');
            } else {
                appendError('网络连接失败，请稍后重试。');
            }
        } finally {
            clearTimeout(timeoutId);
            setInputEnabled(true);
            inputField.focus();
        }
    }

    function retractPendingUserMessage(message) {
        const lastHistory = conversationHistory[conversationHistory.length - 1];
        if (lastHistory && lastHistory.role === 'user' && lastHistory.content === message) {
            conversationHistory.pop();
        }
        const userMessages = messagesContainer.querySelectorAll('.chat-message.user');
        const lastUserMessage = userMessages[userMessages.length - 1];
        if (lastUserMessage) {
            lastUserMessage.remove();
        }
    }

    function ensurePublicTurnstileScript() {
        if (window.createPublicTurnstileGuard) return Promise.resolve();
        if (publicTurnstileScriptPromise) return publicTurnstileScriptPromise;

        publicTurnstileScriptPromise = new Promise((resolve, reject) => {
            const existing = document.querySelector('script[data-chatbot-turnstile-loader="1"],script[src*="public-turnstile.js"]');
            if (existing) {
                if (window.createPublicTurnstileGuard) {
                    resolve();
                    return;
                }
                existing.addEventListener('load', () => resolve(), { once: true });
                existing.addEventListener('error', () => reject(new Error('Turnstile helper load failed')), { once: true });
                return;
            }

            const script = document.createElement('script');
            script.src = PUBLIC_TURNSTILE_SCRIPT_SRC;
            script.async = true;
            script.defer = true;
            script.dataset.chatbotTurnstileLoader = '1';
            script.onload = () => resolve();
            script.onerror = () => reject(new Error('Turnstile helper load failed'));
            document.head.appendChild(script);
        }).catch((error) => {
            publicTurnstileScriptPromise = null;
            throw error;
        });

        return publicTurnstileScriptPromise;
    }

    async function ensureChatbotTurnstileGuard() {
        if (chatbotTurnstileGuard) return chatbotTurnstileGuard;
        if (!turnstileMount) throw new Error('Turnstile mount missing');

        await ensurePublicTurnstileScript();
        if (!window.createPublicTurnstileGuard) {
            throw new Error('Turnstile helper unavailable');
        }

        chatbotTurnstileGuard = window.createPublicTurnstileGuard({
            mount: turnstileMount,
            onVerified: (token) => {
                pendingTurnstileToken = String(token || '');
                retryPendingTurnstileMessage();
            },
            onError: (message) => {
                if (message) appendError(message);
            }
        });
        return chatbotTurnstileGuard;
    }

    function hideChatbotTurnstile() {
        if (turnstileMount) {
            turnstileMount.hidden = true;
        }
        if (chatbotTurnstileGuard) {
            chatbotTurnstileGuard.reset();
        }
    }

    async function retryPendingTurnstileMessage() {
        if (retryingAfterTurnstile || !pendingTurnstileRetry || !pendingTurnstileToken) return;
        const retryMessage = pendingTurnstileRetry.message || '';
        pendingTurnstileRetry = null;
        retryingAfterTurnstile = true;
        try {
            inputField.value = retryMessage;
            await sendMessage();
        } finally {
            retryingAfterTurnstile = false;
        }
    }

    async function handleChatbotTurnstileResponse(response, message, typingEl) {
        let data = null;
        try {
            data = await response.json();
        } catch (error) {
            data = null;
        }
        if (!data || !data.requires_turnstile) return false;

        removeTypingIndicator(typingEl);
        retractPendingUserMessage(message);
        pendingTurnstileRetry = { message };
        appendMessage('bot', data.message || '为了保护智能客服，请先完成人机验证。验证通过后，我会继续处理刚才的问题。');

        try {
            if (turnstileMount) turnstileMount.hidden = false;
            const guard = await ensureChatbotTurnstileGuard();
            await guard.ensureReady();
        } catch (error) {
            appendError('人机验证暂时无法加载，请稍后重试。');
        }
        return true;
    }

    async function getResponseErrorMessage(response) {
        const fallbackMessages = {
            400: '请求内容有误，请重新输入。',
            401: '当前会话未授权，请刷新页面后重试。',
            403: '当前请求暂时无法处理。',
            429: '请求过于频繁，请稍后再试。',
            500: '服务暂时开小差了，请稍后再试。',
            503: '智能客服暂时不可用，请稍后再试。'
        };
        let data = null;
        try {
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = (await response.text()).trim();
                if (text) {
                    return text.slice(0, 120);
                }
            }
        } catch (error) {
            data = null;
        }

        if (data && data.rate_limit === 'ip_per_day') {
            return '今日智能客服请求次数已达上限，请稍后再试。';
        }
        if (data && data.rate_limit === 'ip_per_minute') {
            return data.message ? String(data.message) : '请求过于频繁，请稍后再试。';
        }
        if (data && data.message) {
            return String(data.message);
        }
        if (data && data.error) {
            return String(data.error);
        }
        return fallbackMessages[response.status] || `请求失败（${response.status}），请稍后再试。`;
    }

    async function handleStreamingResponse(response, initialStatusIndicatorEl = null) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let botMessage = '';
        let messageEl = null;
        let hasError = false;
        let buffer = '';
        let recommendations = [];
        let statusUpdates = [];
        let statusIndicatorEl = initialStatusIndicatorEl || document.querySelector('.typing-message:last-child');
        const statusQueue = createAgentStatusQueue(statusIndicatorEl, statusUpdates);
        let contentRenderer = null;

        async function ensureMessageElement() {
            if (messageEl) return messageEl;
            if (statusIndicatorEl) {
                await statusQueue.drain();
                messageEl = prepareThinkingMessageForAnswer(statusIndicatorEl, statusUpdates);
                statusIndicatorEl = null;
            } else {
                messageEl = appendMessage('bot', '', true);
            }
            contentRenderer = createTypewriterRenderer(messageEl);
            if (statusUpdates.length) {
                compactAgentStatusPanel(messageEl, statusUpdates);
            }
            return messageEl;
        }

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;
                    const data = line.slice(6).trim();
                    if (!data) continue;
                    if (data === '[DONE]') continue;

                    try {
                        const parsed = JSON.parse(data);

                        if (parsed.error) {
                            hasError = true;
                            appendError(parsed.error);
                            continue;
                        }

                        if (parsed.status) {
                            statusQueue.push(parsed.status);
                            if (messageEl) {
                                compactAgentStatusPanel(messageEl, statusUpdates);
                            }
                            continue;
                        }

                        if (parsed.content) {
                            botMessage += parsed.content;
                            if (!messageEl) {
                                await ensureMessageElement();
                            }
                            contentRenderer.append(parsed.content);
                            continue;
                        }

                        if (Array.isArray(parsed.recommendations)) {
                            recommendations = parsed.recommendations;
                        }
                    } catch (e) {
                        // Not JSON, might be plain text
                        botMessage += data;
                        if (!messageEl) {
                            await ensureMessageElement();
                        }
                        contentRenderer.append(data);
                    }
                }
            }
        } catch (e) {
            console.error('Streaming error:', e);
            hasError = true;
            if (statusIndicatorEl) {
                await statusQueue.drain();
                removeTypingIndicator(statusIndicatorEl);
            }
            appendError('流式响应中断，请稍后重试。');
        }

        if (botMessage) {
            if (contentRenderer) {
                await contentRenderer.idle();
            }
            if (messageEl && recommendations.length) {
                await revealMessageRecommendations(messageEl, recommendations);
            }
            conversationHistory.push({ role: 'assistant', content: botMessage });
        } else if (!hasError) {
            if (statusIndicatorEl) {
                await statusQueue.drain();
                removeTypingIndicator(statusIndicatorEl);
            }
            appendError('未收到有效回复，请稍后重试。');
        }
    }

    function appendMessage(type, content, returnEl = false) {
        const messageHTML = `
            <div class="chat-message ${type}">
                <div class="message-avatar">
                    <i class="fas fa-${type === 'bot' ? 'robot' : 'user'}"></i>
                </div>
                <div class="message-body">
                    <div class="message-content">${formatMessage(content)}</div>
                </div>
            </div>
        `;

        messagesContainer.insertAdjacentHTML('beforeend', messageHTML);
        scrollToBottom();

        if (returnEl) {
            return messagesContainer.lastElementChild;
        }
    }

    function updateMessageContent(messageEl, content) {
        const contentEl = messageEl.querySelector('.message-content');
        if (contentEl) {
            contentEl.hidden = false;
            contentEl.innerHTML = formatMessage(content);
            scrollToBottom();
        }
    }

    async function renderMessageWithTypewriter(messageEl, content) {
        const renderer = createTypewriterRenderer(messageEl);
        renderer.append(content || '');
        await renderer.idle();
    }

    function createTypewriterRenderer(messageEl) {
        let targetText = '';
        let renderedLength = 0;
        let running = false;
        let idleResolvers = [];

        const resolveIdle = () => {
            const resolvers = idleResolvers;
            idleResolvers = [];
            resolvers.forEach(resolve => resolve());
        };

        const getStepSize = () => {
            const remaining = targetText.length - renderedLength;
            if (remaining > 280) return 18;
            if (remaining > 120) return 10;
            if (remaining > 40) return 5;
            return 2;
        };

        const pump = async () => {
            if (running) return;
            running = true;
            while (renderedLength < targetText.length) {
                renderedLength = Math.min(targetText.length, renderedLength + getStepSize());
                updateMessageContent(messageEl, targetText.slice(0, renderedLength));
                await delay(TYPEWRITER_DELAY_MS);
            }
            running = false;
            resolveIdle();
        };

        return {
            append(text) {
                if (!text) return;
                targetText += String(text);
                pump();
            },
            idle() {
                if (!running && renderedLength >= targetText.length) {
                    return Promise.resolve();
                }
                return new Promise(resolve => idleResolvers.push(resolve));
            }
        };
    }

    function findMessageRecommendationPanel(messageEl) {
        const nextEl = messageEl ? messageEl.nextElementSibling : null;
        if (nextEl && nextEl.classList.contains('recommendations-message')) {
            return nextEl;
        }
        return null;
    }

    function ensureMessageRecommendationPanel(messageEl) {
        if (!messageEl) return null;
        const existingPanel = findMessageRecommendationPanel(messageEl);
        if (existingPanel) return existingPanel;

        const panelHTML = `
            <div class="chat-message bot recommendations-message">
                <div class="message-avatar message-avatar-spacer" aria-hidden="true"></div>
                <div class="message-body">
                    <div class="chatbot-recommendations" hidden></div>
                </div>
            </div>
        `;
        messageEl.insertAdjacentHTML('afterend', panelHTML);
        return messageEl.nextElementSibling;
    }

    function removeMessageRecommendationPanel(messageEl) {
        const panel = findMessageRecommendationPanel(messageEl);
        if (panel) panel.remove();
    }

    function updateMessageRecommendations(messageEl, recommendations) {
        const cards = Array.isArray(recommendations) ? recommendations.filter(item => item && item.url && item.title) : [];
        if (!cards.length) {
            removeMessageRecommendationPanel(messageEl);
            return;
        }
        const panel = ensureMessageRecommendationPanel(messageEl);
        const container = panel ? panel.querySelector('.chatbot-recommendations') : null;
        if (!container) return;
        container.classList.remove('is-entering', 'is-visible');
        container.hidden = false;
        container.innerHTML = renderRecommendationCards(cards);
        scrollToBottom();
    }

    async function revealMessageRecommendations(messageEl, recommendations) {
        const cards = Array.isArray(recommendations) ? recommendations.filter(item => item && item.url && item.title) : [];
        if (!cards.length) {
            updateMessageRecommendations(messageEl, []);
            return;
        }

        await delay(RECOMMENDATIONS_REVEAL_DELAY_MS);
        const panel = ensureMessageRecommendationPanel(messageEl);
        const container = panel ? panel.querySelector('.chatbot-recommendations') : null;
        if (!container) return;
        container.innerHTML = renderRecommendationCards(cards);
        container.hidden = false;
        panel.classList.remove('is-visible');
        panel.classList.add('is-entering');
        scrollToBottom();

        await new Promise(resolve => {
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    panel.classList.add('is-visible');
                    scrollToBottom();
                    resolve();
                });
            });
        });
    }

    function prependAgentStatusSummary(messageEl, statusUpdates) {
        if (!messageEl || !Array.isArray(statusUpdates) || !statusUpdates.length) return;
        const body = messageEl.querySelector('.message-body');
        if (!body) return;
        const html = renderAgentStatusSummary(statusUpdates);
        const existing = body.querySelector('.chatbot-agent-summary');
        if (existing) {
            const template = document.createElement('template');
            template.innerHTML = html.trim();
            existing.replaceWith(template.content.firstElementChild);
            return;
        }
        body.insertAdjacentHTML('afterbegin', html);
    }

    function prepareThinkingMessageForAnswer(typingEl, statusUpdates = []) {
        if (!typingEl) return null;
        clearThinkingTimers(typingEl);
        typingEl.classList.remove('typing-message');
        typingEl.classList.add('has-agent-status');
        compactAgentStatusPanel(typingEl, statusUpdates);
        return typingEl;
    }

    function compactAgentStatusPanel(messageEl, statusUpdates = []) {
        if (!messageEl) return;
        const fallbackStatus = [{ label: '正在生成回答', detail: '已完成问题理解与站内检索' }];
        const updates = Array.isArray(statusUpdates) && statusUpdates.length ? statusUpdates : fallbackStatus;
        const html = renderAgentStatusSummary(updates);
        if (!html) return;

        const template = document.createElement('template');
        template.innerHTML = html.trim();
        const summaryEl = template.content.firstElementChild;
        if (!summaryEl) return;

        const existingSummary = messageEl.querySelector('.chatbot-agent-summary');
        if (existingSummary) {
            existingSummary.replaceWith(summaryEl);
            return;
        }

        const livePanel = messageEl.querySelector('.typing-indicator');
        if (livePanel) {
            livePanel.replaceWith(summaryEl);
            return;
        }

        const body = messageEl.querySelector('.message-body');
        if (body) {
            body.insertAdjacentElement('afterbegin', summaryEl);
        }
    }

    function renderRecommendationCards(recommendations) {
        const cards = Array.isArray(recommendations) ? recommendations.filter(item => item && item.url && item.title) : [];
        if (!cards.length) return '';
        return `
            <div class="chatbot-recommendations-title">你可能感兴趣</div>
            <div class="chatbot-recommendation-links">
                ${cards.map(item => `
                    <a class="chatbot-recommendation-link" href="${escapeAttr(item.url)}" target="_blank" rel="noopener">
                        <span class="chatbot-recommendation-name">${escapeHtml(cleanRecommendationTitle(item.title || ''))}</span>
                    </a>
                `).join('')}
            </div>
        `;
    }

    function cleanRecommendationTitle(title) {
        return String(title || '')
            .replace(/\s*-\s*元芯传感\s*$/i, '')
            .trim();
    }

    function renderAgentStatusSummary(statusUpdates) {
        const steps = Array.isArray(statusUpdates) ? statusUpdates.filter(item => item && item.label) : [];
        if (!steps.length) return '';
        const latest = steps[steps.length - 1];
        return `
            <div class="chatbot-agent-summary is-refreshing">
                <span class="chatbot-agent-summary-title">思考</span>
                <span class="chatbot-agent-summary-label">${escapeHtml(latest.label || '')}</span>
                ${latest.detail ? `<span class="chatbot-agent-summary-detail">${escapeHtml(latest.detail || '')}</span>` : ''}
            </div>
        `;
    }

    function mapRecommendationTypeLabel(type) {
        switch (String(type || '').trim()) {
            case 'product':
                return '产品';
            case 'solution':
                return '方案';
            case 'custom':
                return '定制';
            case 'contact':
                return '联系';
            default:
                return '推荐';
        }
    }

    function formatMessage(text) {
        // Enhanced markdown formatting
        let formatted = escapeHtml(text);

        // Code blocks (must be processed first to avoid interference)
        formatted = formatted.replace(/```(\w*)\n?([\s\S]*?)```/g, function (match, lang, code) {
            return '<pre><code>' + code.trim() + '</code></pre>';
        });

        // Inline code
        formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');

        // Headers (h1-h4)
        formatted = formatted.replace(/^#### (.+)$/gm, '<h4>$1</h4>');
        formatted = formatted.replace(/^### (.+)$/gm, '<h3>$1</h3>');
        formatted = formatted.replace(/^## (.+)$/gm, '<h2>$1</h2>');
        formatted = formatted.replace(/^# (.+)$/gm, '<h1>$1</h1>');

        // Bold (must come before italic)
        formatted = formatted.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
        formatted = formatted.replace(/__(.+?)__/g, '<strong>$1</strong>');

        // Italic
        formatted = formatted.replace(/\*(.+?)\*/g, '<em>$1</em>');
        formatted = formatted.replace(/_(.+?)_/g, '<em>$1</em>');

        // Strikethrough
        formatted = formatted.replace(/~~(.+?)~~/g, '<del>$1</del>');

        // Blockquotes
        formatted = formatted.replace(/^&gt; (.+)$/gm, '<blockquote>$1</blockquote>');

        // Horizontal rule
        formatted = formatted.replace(/^---+$/gm, '<hr>');
        formatted = formatted.replace(/^\*\*\*+$/gm, '<hr>');

        // Unordered lists
        formatted = formatted.replace(/^[\-\*] (.+)$/gm, '<li>$1</li>');

        // Ordered lists
        formatted = formatted.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

        // Wrap consecutive <li> tags in <ul>
        formatted = formatted.replace(/(<li>[\s\S]*?<\/li>)(?:\s*<br>)*(<li>)/g, '$1$2');
        formatted = formatted.replace(/(<li>[\s\S]*?<\/li>)+/g, '<ul>$&</ul>');

        // Links
        formatted = formatted.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

        // Auto-link URLs
        formatted = formatted.replace(/(^|[^"'>])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');

        // Line breaks (but not inside pre/code)
        formatted = formatted.replace(/\n/g, '<br>');

        // Clean up extra <br> after block elements
        formatted = formatted.replace(/<\/(h[1-4]|pre|blockquote|ul|li|hr)><br>/g, '</$1>');
        formatted = formatted.replace(/<br><(h[1-4]|pre|blockquote|ul)/g, '<$1');

        // Remove consecutive <br>s
        formatted = formatted.replace(/(<br>){3,}/g, '<br><br>');

        return formatted;
    }


    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function escapeAttr(text) {
        return escapeHtml(text).replace(/"/g, '&quot;');
    }

    function delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function createAgentStatusQueue(typingEl, statusUpdates) {
        const queue = [];
        let running = false;
        let flushed = false;

        const run = async () => {
            if (running) return;
            running = true;
            while (queue.length) {
                const status = queue.shift();
                statusUpdates.push(status);
                // 正文已开始流式输出后进入 flushed：状态只并入摘要，不再逐条动画/等待。
                if (flushed) continue;
                appendAgentStatusStep(typingEl, status);
                await delay(AGENT_STATUS_MIN_VISIBLE_MS);
            }
            running = false;
        };

        return {
            push(status) {
                if (!status || !status.label) return;
                // 已进入 flushed（正文在流式输出）后，新状态直接并入摘要，
                // 不再排队等待 run() 里可能尚未结束的上一条延时。
                if (flushed) {
                    statusUpdates.push(status);
                    return;
                }
                queue.push(status);
                run();
            },
            // 正文一旦开始流式输出就立即结束状态动画：把尚未展示的状态直接并入摘要并立即返回，
            // 不再等待每条状态的最小展示时间——否则会阻塞读取循环，导致模型输出被缓冲后一次性渲染（看起来不流式）。
            drain() {
                flushed = true;
                while (queue.length) {
                    statusUpdates.push(queue.shift());
                }
                return Promise.resolve();
            }
        };
    }

    function renderAgentStatusStep(label, detail = '', state = 'is-active') {
        const detailHtml = detail ? `<div class="agent-status-detail">${escapeHtml(detail)}</div>` : '';
        return `
            <div class="agent-status-item ${state}">
                <span class="agent-status-icon" aria-hidden="true"></span>
                <div class="agent-status-copy">
                    <div class="agent-status-label">${escapeHtml(label || '')}</div>
                    ${detailHtml}
                </div>
            </div>
        `;
    }

    function setAgentStatusItemState(item, state) {
        if (!item) return;
        item.classList.remove('is-active', 'is-complete', 'is-pending', 'is-refreshing');
        item.classList.add(state);
    }

    function activateDefaultThinkingStep(typingEl, index) {
        if (!typingEl) return;
        const items = Array.from(typingEl.querySelectorAll('.agent-status-item'));
        items.forEach((item, itemIndex) => {
            if (itemIndex < index) {
                setAgentStatusItemState(item, 'is-complete');
            } else if (itemIndex === index) {
                setAgentStatusItemState(item, 'is-active');
                item.classList.add('is-refreshing');
            } else {
                setAgentStatusItemState(item, 'is-pending');
            }
        });
        scrollToBottom();
    }

    function clearThinkingTimers(typingEl) {
        if (!typingEl || !Array.isArray(typingEl._statusTimers)) return;
        typingEl._statusTimers.forEach(timer => clearTimeout(timer));
        typingEl._statusTimers = [];
    }

    function showAgentStatusIndicator() {
        const typingHTML = `
            <div class="chat-message bot typing-message agent-thinking-message">
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="message-body">
                    <div class="typing-indicator">
                        <div class="agent-thinking-header">
                            <span>思考中</span>
                            <span class="agent-thinking-pulse" aria-hidden="true">
                                <span></span>
                                <span></span>
                                <span></span>
                            </span>
                        </div>
                        <div class="agent-status-list" aria-live="polite">
                            ${renderAgentStatusStep('正在阅读请求', '', 'is-active')}
                            ${renderAgentStatusStep('正在优化回复', '', 'is-pending')}
                        </div>
                    </div>
                    <div class="message-content" hidden></div>
                </div>
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', typingHTML);
        const typingEl = messagesContainer.lastElementChild;
        typingEl._statusTimers = [
            setTimeout(() => activateDefaultThinkingStep(typingEl, 1), 700),
            setTimeout(() => appendAgentStatusStep(typingEl, { label: '正在整理答案' }, { keepTimers: true }), 1800)
        ];
        scrollToBottom();
        return typingEl;
    }

    function appendAgentStatusStep(typingEl, status, options = {}) {
        if (!typingEl || !status || !status.label) return;
        const listEl = typingEl.querySelector('.agent-status-list');
        if (!listEl) return;
        if (!options.keepTimers) {
            clearThinkingTimers(typingEl);
        }
        listEl.querySelectorAll('.agent-status-item.is-pending').forEach(item => item.remove());
        listEl.querySelectorAll('.agent-status-item.is-active').forEach(item => {
            setAgentStatusItemState(item, 'is-complete');
        });
        listEl.insertAdjacentHTML(
            'beforeend',
            renderAgentStatusStep(status.label || '', status.detail || '', 'is-active is-refreshing')
        );
        while (listEl.children.length > 5) {
            listEl.firstElementChild.remove();
        }
        scrollToBottom();
    }

    function removeTypingIndicator(typingEl) {
        if (!typingEl) return;
        clearThinkingTimers(typingEl);
        typingEl.remove();
    }

    function appendError(message) {
        const errorHTML = `
            <div class="chat-error">
                <i class="fas fa-exclamation-circle"></i> ${escapeHtml(message)}
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', errorHTML);
        scrollToBottom();
    }

    function setInputEnabled(enabled) {
        inputField.disabled = !enabled;
        sendButton.disabled = !enabled;
        document.querySelectorAll('.chatbot-suggestion-pill').forEach((btn) => {
            btn.disabled = !enabled;
        });
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Expose API for external use
    window.MetachipChatbot = {
        open: openChatWindow,
        close: closeChatWindow,
        minimize: minimizeChatWindow,
        toggle: toggleChatWindow,
        clearHistory: clearChatHistory,
        newSession: function () {
            clearChatHistory();
        }
    };

})();
