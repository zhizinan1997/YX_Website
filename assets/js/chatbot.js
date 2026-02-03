/**
 * 元芯传感 - AI智能客服
 * 支持上下文对话和知识库检索
 */

(function () {
    'use strict';

    // 会话ID（每次页面加载时生成新的）
    let sessionId = generateSessionId();

    // 对话历史（不持久化，关闭/刷新即清除）
    let conversationHistory = [];

    // DOM Elements
    let chatbotTrigger, chatbotWindow, messagesContainer, inputField, sendButton;

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
        // Create floating trigger button
        const triggerHTML = `
            <button class="chatbot-trigger" id="chatbotTrigger" aria-label="打开智能客服">
                <i class="fas fa-robot"></i>
                <i class="fas fa-times"></i>
            </button>
        `;

        // Create chat window
        const windowHTML = `
            <div class="chatbot-window" id="chatbotWindow" style="display: none;">
                <div class="chatbot-header">
                    <div class="chatbot-avatar">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="chatbot-info">
                        <h4>元芯智能助手</h4>
                        <span>在线服务中</span>
                    </div>
                    <button class="chatbot-close" id="chatbotClose" aria-label="关闭">
                        <i class="fas fa-times"></i>
                    </button>
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
                    <textarea class="chatbot-input" id="chatbotInput" placeholder="输入您的问题..." rows="1"></textarea>
                    <button class="chatbot-send" id="chatbotSend" aria-label="发送">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        `;

        // Append to body
        document.body.insertAdjacentHTML('beforeend', triggerHTML);
        document.body.insertAdjacentHTML('beforeend', windowHTML);

        // Get DOM references
        chatbotTrigger = document.getElementById('chatbotTrigger');
        chatbotWindow = document.getElementById('chatbotWindow');
        messagesContainer = document.getElementById('chatbotMessages');
        inputField = document.getElementById('chatbotInput');
        sendButton = document.getElementById('chatbotSend');
    }

    function bindEvents() {
        // Toggle chat window
        chatbotTrigger.addEventListener('click', toggleChatWindow);
        document.getElementById('chatbotClose').addEventListener('click', closeChatWindow);

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
            if (e.target.classList.contains('quick-action-btn')) {
                const question = e.target.getAttribute('data-question');
                if (question) {
                    inputField.value = question;
                    sendMessage();
                }
            }
        });

        // Close on outside click (optional)
        document.addEventListener('click', (e) => {
            if (chatbotWindow.classList.contains('open') &&
                !chatbotWindow.contains(e.target) &&
                !chatbotTrigger.contains(e.target)) {
                // Optionally close on outside click
                // closeChatWindow();
            }
        });
    }

    function toggleChatWindow() {
        if (chatbotWindow.classList.contains('open')) {
            closeChatWindow();
        } else {
            openChatWindow();
        }
    }

    function openChatWindow() {
        chatbotWindow.style.display = 'flex';
        // Force reflow
        chatbotWindow.offsetHeight;
        chatbotWindow.classList.add('open');
        chatbotTrigger.classList.add('active');
        inputField.focus();
    }

    function closeChatWindow() {
        chatbotWindow.classList.remove('open');
        chatbotTrigger.classList.remove('active');

        // Wait for transition (300ms) then hide
        setTimeout(() => {
            chatbotWindow.style.display = 'none';
            // 关闭时清除对话记录
            clearChatHistory();
        }, 300);
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

        // Show typing indicator
        const typingEl = showTypingIndicator();

        // Disable input while processing
        setInputEnabled(false);

        try {
            const response = await fetch('/api/chatbot/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    session_id: sessionId,
                    history: conversationHistory.slice(-10) // Send last 10 messages for context
                })
            });

            // Remove typing indicator
            typingEl.remove();

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            // Check if it's a streaming response
            const contentType = response.headers.get('content-type');

            if (contentType && contentType.includes('text/event-stream')) {
                // Handle streaming response
                await handleStreamingResponse(response);
            } else {
                // Handle regular JSON response
                const data = await response.json();
                if (data.success) {
                    appendMessage('bot', data.response);
                    conversationHistory.push({ role: 'assistant', content: data.response });
                } else {
                    appendError(data.message || '抱歉，出现了一些问题。');
                }
            }
        } catch (error) {
            typingEl.remove();
            console.error('Chat error:', error);
            appendError('网络连接失败，请稍后重试。');
        } finally {
            setInputEnabled(true);
            inputField.focus();
        }
    }

    async function handleStreamingResponse(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let botMessage = '';
        let messageEl = null;

        try {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const data = line.slice(6);
                        if (data === '[DONE]') {
                            break;
                        }
                        try {
                            const parsed = JSON.parse(data);
                            if (parsed.content) {
                                botMessage += parsed.content;
                                if (!messageEl) {
                                    messageEl = appendMessage('bot', botMessage, true);
                                } else {
                                    updateMessageContent(messageEl, botMessage);
                                }
                            }
                        } catch (e) {
                            // Not JSON, might be plain text
                            botMessage += data;
                            if (!messageEl) {
                                messageEl = appendMessage('bot', botMessage, true);
                            } else {
                                updateMessageContent(messageEl, botMessage);
                            }
                        }
                    }
                }
            }
        } catch (e) {
            console.error('Streaming error:', e);
        }

        if (botMessage) {
            conversationHistory.push({ role: 'assistant', content: botMessage });
        }
    }

    function appendMessage(type, content, returnEl = false) {
        const messageHTML = `
            <div class="chat-message ${type}">
                <div class="message-avatar">
                    <i class="fas fa-${type === 'bot' ? 'robot' : 'user'}"></i>
                </div>
                <div class="message-content">${formatMessage(content)}</div>
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

    function showTypingIndicator() {
        const typingHTML = `
            <div class="chat-message bot typing-message">
                <div class="message-avatar">
                    <i class="fas fa-robot"></i>
                </div>
                <div class="typing-indicator">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
            </div>
        `;
        messagesContainer.insertAdjacentHTML('beforeend', typingHTML);
        scrollToBottom();
        return messagesContainer.lastElementChild;
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
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Expose API for external use
    window.MetachipChatbot = {
        open: openChatWindow,
        close: closeChatWindow,
        toggle: toggleChatWindow,
        clearHistory: clearChatHistory,
        newSession: function () {
            clearChatHistory();
        }
    };

})();
