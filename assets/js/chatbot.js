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

    // 会话ID（每次页面加载时生成新的）
    let sessionId = generateSessionId();

    // 对话历史（不持久化，关闭/刷新即清除）
    let conversationHistory = [];

    // DOM Elements
    let chatbotTrigger, chatbotWindow, messagesContainer, inputField, sendButton, suggestionTrack, resizeHandle;
    let hideWindowTimer = null;
    let lastTouchToggleAt = 0;
    let ignoreOutsideClickUntil = 0;
    let isResizing = false;
    let resizeStartX = 0;
    let resizeStartWidth = 0;
    let chatbotCustomWidth = null;

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

    const WAITING_STATUS_MESSAGES = [
        '元芯AI已收到您的问题',
        '元芯AI正在努力Thinking',
        '...'
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
        const right = Math.max(viewportPadding, window.innerWidth - triggerRect.right);
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

        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);

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
                    history: conversationHistory.slice(-10) // Send last 10 messages for context
                }),
                signal: controller.signal
            });

            if (!response.ok) {
                removeTypingIndicator(typingEl);
                throw new Error(`HTTP ${response.status}`);
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
                    removeTypingIndicator(typingEl);
                    appendMessage('bot', data.response, false, data.recommendations || []);
                    if (Array.isArray(data.status_updates) && data.status_updates.length) {
                        prependAgentStatusSummary(messagesContainer.lastElementChild, data.status_updates);
                    }
                    conversationHistory.push({ role: 'assistant', content: data.response });
                } else {
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

        async function ensureMessageElement() {
            if (messageEl) return messageEl;
            if (statusIndicatorEl) {
                await statusQueue.drain();
                removeTypingIndicator(statusIndicatorEl);
                statusIndicatorEl = null;
            }
            messageEl = appendMessage('bot', botMessage, true, recommendations);
            if (statusUpdates.length) {
                prependAgentStatusSummary(messageEl, statusUpdates);
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
                                prependAgentStatusSummary(messageEl, statusUpdates);
                            }
                            continue;
                        }

                        if (parsed.content) {
                            botMessage += parsed.content;
                            if (!messageEl) {
                                await ensureMessageElement();
                            } else {
                                updateMessageContent(messageEl, botMessage);
                            }
                            continue;
                        }

                        if (Array.isArray(parsed.recommendations)) {
                            recommendations = parsed.recommendations;
                            if (messageEl) {
                                updateMessageRecommendations(messageEl, recommendations);
                            }
                        }
                    } catch (e) {
                        // Not JSON, might be plain text
                        botMessage += data;
                        if (!messageEl) {
                            await ensureMessageElement();
                        } else {
                            updateMessageContent(messageEl, botMessage);
                        }
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
            if (messageEl && recommendations.length) {
                updateMessageRecommendations(messageEl, recommendations);
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

    function appendMessage(type, content, returnEl = false, recommendations = []) {
        const messageHTML = `
            <div class="chat-message ${type}">
                <div class="message-avatar">
                    <i class="fas fa-${type === 'bot' ? 'robot' : 'user'}"></i>
                </div>
                <div class="message-body">
                    <div class="message-content">${formatMessage(content)}</div>
                    ${type === 'bot' ? `<div class="chatbot-recommendations" ${recommendations.length ? '' : 'hidden'}>${renderRecommendationCards(recommendations)}</div>` : ''}
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
            contentEl.innerHTML = formatMessage(content);
            scrollToBottom();
        }
    }

    function updateMessageRecommendations(messageEl, recommendations) {
        const container = messageEl.querySelector('.chatbot-recommendations');
        if (!container) return;
        const cards = Array.isArray(recommendations) ? recommendations.filter(item => item && item.url && item.title) : [];
        if (!cards.length) {
            container.hidden = true;
            container.innerHTML = '';
            return;
        }
        container.hidden = false;
        container.innerHTML = renderRecommendationCards(cards);
        scrollToBottom();
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

    function renderRecommendationCards(recommendations) {
        const cards = Array.isArray(recommendations) ? recommendations.filter(item => item && item.url && item.title) : [];
        if (!cards.length) return '';
        return `
            <div class="chatbot-recommendations-title">你可能感兴趣</div>
            <div class="chatbot-recommendation-links">
                ${cards.map(item => `
                    <a class="chatbot-recommendation-link" href="${escapeAttr(item.url)}" target="_blank" rel="noopener">
                        <span class="chatbot-recommendation-type">${escapeHtml(mapRecommendationTypeLabel(item.type || 'overview'))}</span>
                        <span class="chatbot-recommendation-name">${escapeHtml(item.title || '')}</span>
                    </a>
                `).join('')}
            </div>
        `;
    }

    function renderAgentStatusSummary(statusUpdates) {
        const steps = Array.isArray(statusUpdates) ? statusUpdates.filter(item => item && item.label) : [];
        if (!steps.length) return '';
        const latest = steps[steps.length - 1];
        return `
            <div class="chatbot-agent-summary is-refreshing">
                <span class="chatbot-agent-summary-title">Agent</span>
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

    function showAgentStatusIndicator() {
        const typingHTML = `
            <div class="chat-message bot typing-message">
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="typing-indicator">
                    <div class="agent-status-list" aria-live="polite">
                        <div class="agent-status-item is-refreshing">
                            <div class="agent-status-label">元芯AI正在准备处理您的问题</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', typingHTML);
        scrollToBottom();
        return messagesContainer.lastElementChild;
    }

    function appendAgentStatusStep(typingEl, status) {
        if (!typingEl || !status || !status.label) return;
        const listEl = typingEl.querySelector('.agent-status-list');
        if (!listEl) return;
        const detail = status.detail ? `<div class="agent-status-detail">${escapeHtml(status.detail)}</div>` : '';
        listEl.innerHTML = `
            <div class="agent-status-item is-refreshing">
                <div class="agent-status-label">${escapeHtml(status.label || '')}</div>
                ${detail}
            </div>
        `;
        scrollToBottom();
    }

    function removeTypingIndicator(typingEl) {
        if (!typingEl) return;
        if (typingEl._statusTimer) {
            clearInterval(typingEl._statusTimer);
            typingEl._statusTimer = null;
        }
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
