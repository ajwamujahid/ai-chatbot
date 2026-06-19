let selectedAgent = 'general';
    const initialMessages = window.initialMessages || [];
    let sessions = window.initialSessions || [];
    let activeSessionId = window.activeSessionId || null;

    function getTime() {
        return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
    }

    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 140) + 'px';
    }

    function iconSvg(name) {
        const icons = {
            pin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 17v5"/><path d="M5 17h14"/><path d="M8 3h8l-1 8 3 4H6l3-4Z"/></svg>',
            unpin: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m3 3 18 18"/><path d="M12 17v5"/><path d="M8 3h8l-1 8 3 4"/><path d="M7.5 15H6l2.1-2.8"/></svg>',
            sun: '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/></svg>',
            moon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 14.5A7.5 7.5 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z"/></svg>',
            copy: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v1"/></svg>',
            refresh: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12a9 9 0 0 1-15.5 6.2"/><path d="M3 12A9 9 0 0 1 18.5 5.8"/><path d="M18 2v5h5"/><path d="M6 22v-5H1"/></svg>',
            thumbsUp: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v11H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z"/><path d="M7 10l4-8a3 3 0 0 1 3 3v4h5a2 2 0 0 1 2 2l-1 8a2 2 0 0 1-2 2H7"/></svg>',
            thumbsDown: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V3H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2Z"/><path d="M7 14l4 8a3 3 0 0 0 3-3v-4h5a2 2 0 0 0 2-2l-1-8a2 2 0 0 0-2-2H7"/></svg>',
            edit: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>'
        };
        return icons[name] || '';
    }

    function applyTheme(theme) {
        const isLight = theme === 'light';
        document.body.classList.toggle('light-theme', isLight);
        localStorage.setItem('chat_theme', isLight ? 'light' : 'dark');
        updateThemeButton();
    }

    function updateThemeButton() {
        const button = document.getElementById('theme-btn');
        if (!button) return;

        const isLight = document.body.classList.contains('light-theme');
        button.innerHTML = iconSvg(isLight ? 'moon' : 'sun');
        button.title = isLight ? 'Dark theme' : 'Light theme';
    }

    function toggleTheme() {
        const isLight = document.body.classList.contains('light-theme');
        applyTheme(isLight ? 'dark' : 'light');
    }

    function handleKey(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    }

    function scrollToBottom() {
        const box = document.getElementById('chat-box');
        box.scrollTop = box.scrollHeight;
    }

    function clearMessageNodes() {
        const box = document.getElementById('chat-box');
        Array.from(box.children).forEach(child => {
            if (child.id !== 'typing-wrapper') child.remove();
        });
    }

    function renderMessages(messages) {
        clearMessageNodes();
        if (!messages.length) {
            addMessage(
                'Assalam o Alaikum! Main OpenAI Agents SDK par bana assistant hun. Aap coding, study, ya planning ke liye kuch bhi pooch sakte hain.',
                'bot'
            );
            return;
        }
        messages.forEach(message => {
            addMessage(message.content, message.role === 'user' ? 'user' : 'bot', {
                provider: message.provider,
                agent: message.agent,
                messageId: message.id,
                feedback: message.feedback
            });
        });
    }

    function updateSessionSelect(newSessions, newActiveSessionId) {
        sessions = newSessions || sessions;
        activeSessionId = newActiveSessionId || activeSessionId;

        const select = document.getElementById('session-select');
        if (!select) return;

        select.innerHTML = sessions.map(session => {
            const count = session.message_count ? ` · ${session.message_count} msgs` : '';
            const pin = session.pinned ? 'Pinned · ' : '';
            const selected = Number(session.id) === Number(activeSessionId) ? 'selected' : '';
            return `<option value="${session.id}" ${selected}>${escapeHTML(pin + session.title + count)}</option>`;
        }).join('');
        updatePinButton();
    }

    function updatePinButton() {
        const button = document.getElementById('pin-session-btn');
        if (!button) return;

        const activeSession = sessions.find(item => Number(item.id) === Number(activeSessionId));
        const isPinned = Boolean(activeSession?.pinned);
        button.innerHTML = iconSvg(isPinned ? 'unpin' : 'pin');
        button.title = isPinned ? 'Unpin session' : 'Pin session';
        button.setAttribute('aria-label', button.title);
        button.classList.toggle('pin-active', isPinned);
    }

    async function refreshSessions() {
        const res = await fetch('/sessions');
        if (!res.ok) return;
        const data = await res.json();
        updateSessionSelect(data.sessions, data.active_session_id);
    }

    let searchTimer = null;

    function renderSearchResults(results) {
        const panel = document.getElementById('search-results');
        if (!panel) return;

        if (!results.length) {
            panel.hidden = false;
            panel.innerHTML = '<div class="search-empty">Koi result nahi mila.</div>';
            return;
        }

        panel.hidden = false;
        panel.innerHTML = results.map(result => {
            const titlePrefix = result.session_pinned ? 'Pinned · ' : '';
            const title = escapeHTML(titlePrefix + result.session_title);
            const role = result.role ? `${result.role}: ` : '';
            const preview = escapeHTML(`${role}${result.preview}`);
            return `
                <button class="search-result" onclick="openSearchResult(${result.session_id})">
                    <div class="search-result-title">${title}</div>
                    <div class="search-result-preview">${preview}</div>
                </button>
            `;
        }).join('');
    }

    function searchChats(query) {
        const panel = document.getElementById('search-results');
        const cleanQuery = query.trim();
        clearTimeout(searchTimer);

        if (!cleanQuery) {
            if (panel) {
                panel.hidden = true;
                panel.innerHTML = '';
            }
            return;
        }

        searchTimer = setTimeout(async () => {
            const res = await fetch(`/search?q=${encodeURIComponent(cleanQuery)}`);
            if (!res.ok) return;
            const data = await res.json();
            renderSearchResults(data.results || []);
        }, 250);
    }

    async function openSearchResult(sessionId) {
        await selectSession(sessionId);
        const input = document.getElementById('search-input');
        const panel = document.getElementById('search-results');
        if (input) input.value = '';
        if (panel) {
            panel.hidden = true;
            panel.innerHTML = '';
        }
    }

    function usePrompt(text) {
        const input = document.getElementById('user-input');
        input.value = text;
        autoResize(input);
        input.focus();
    }

    async function uploadFile(file) {
        if (!file) return;

        const status = document.getElementById('file-status');
        const formData = new FormData();
        formData.append('file', file);
        status.textContent = 'Uploading...';

        try {
            const res = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            const contentType = res.headers.get('content-type') || '';
            const data = contentType.includes('application/json')
                ? await res.json()
                : { error: await res.text() };

            if (!res.ok) {
                status.textContent = data.error || 'Upload failed';
                return;
            }

            status.textContent = `Attached: ${data.filename} (${data.chars} chars)`;
            if (data.summary) {
                addMessage(`File analysis ready:\n${data.summary}`, 'bot', {
                    provider: data.filename.toLowerCase().endsWith('.csv') ? 'Pandas' : 'pypdf',
                    agent: 'Data'
                });
            }
            usePrompt(`Is attached file ka summary banao: ${data.filename}`);
        } catch (e) {
            status.textContent = 'Upload failed';
        }
    }

    async function clearFile() {
        const status = document.getElementById('file-status');
        await fetch('/upload/clear', { method: 'POST' });
        document.getElementById('file-input').value = '';
        status.textContent = 'No file attached';
    }

    function setAgent(agent) {
        selectedAgent = agent;
        document.querySelectorAll('.agent-chip').forEach(chip => {
            chip.classList.toggle('active', chip.dataset.agent === agent);
        });
        document.getElementById('user-input').focus();
    }

    function escapeHTML(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    async function copyMessage(button) {
        const message = button.closest('.msg-content')?.dataset.rawText || '';
        if (!message) return;

        try {
            await navigator.clipboard.writeText(message);
        } catch (e) {
            const textarea = document.createElement('textarea');
            textarea.value = message;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            document.execCommand('copy');
            textarea.remove();
        }

        const oldHTML = button.innerHTML;
        const oldTitle = button.title;
        button.textContent = 'Done';
        button.disabled = true;
        setTimeout(() => {
            button.innerHTML = oldHTML;
            button.title = oldTitle;
            button.disabled = false;
        }, 1200);
    }

    function findPreviousUserMessage(button) {
        let messageNode = button.closest('.message')?.previousElementSibling;
        while (messageNode) {
            if (messageNode.classList.contains('user')) {
                return messageNode.querySelector('.msg-content')?.dataset.rawText || '';
            }
            messageNode = messageNode.previousElementSibling;
        }
        return '';
    }

    function findNextAssistantMessage(button) {
        let messageNode = button.closest('.message')?.nextElementSibling;
        while (messageNode) {
            if (messageNode.classList.contains('bot') && messageNode.id !== 'typing-wrapper') {
                return {
                    node: messageNode,
                    bubble: messageNode.querySelector('.msg-bubble'),
                    content: messageNode.querySelector('.msg-content')
                };
            }
            messageNode = messageNode.nextElementSibling;
        }
        return null;
    }

    function setMessageText(messageEl, text) {
        if (!messageEl?.content || !messageEl?.bubble) return;
        messageEl.content.dataset.rawText = text;
        messageEl.bubble.innerHTML = escapeHTML(text).replace(/\n/g, '<br>');
    }

    async function regenerateMessage(button) {
        const previousMessage = findPreviousUserMessage(button);
        if (!previousMessage) {
            addMessage('Regenerate ke liye pehle user message nahi mila.', 'bot', {
                provider: 'Local',
                agent: 'Session'
            });
            return;
        }
        await sendMessage(previousMessage);
    }

    function updateFeedbackButtons(contentEl, feedback) {
        contentEl.dataset.feedback = feedback || '';
        contentEl.querySelectorAll('.feedback-btn').forEach(button => {
            button.classList.toggle('active', button.dataset.feedback === feedback);
        });
    }

    async function submitFeedback(button, feedback) {
        const contentEl = button.closest('.msg-content');
        const messageId = contentEl?.dataset.messageId;
        if (!messageId) return;

        const currentFeedback = contentEl.dataset.feedback || '';
        const nextFeedback = currentFeedback === feedback ? '' : feedback;
        updateFeedbackButtons(contentEl, nextFeedback);

        const res = await fetch('/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message_id: messageId, feedback: nextFeedback })
        });

        if (!res.ok) {
            updateFeedbackButtons(contentEl, currentFeedback);
        }
    }

    async function editUserMessage(button) {
        const contentEl = button.closest('.msg-content');
        const message = contentEl?.dataset.rawText || '';
        if (!message) return;

        const updatedMessage = prompt('Message edit karein:', message);
        if (updatedMessage === null) return;

        const cleanMessage = updatedMessage.trim();
        if (!cleanMessage || cleanMessage === message) return;

        const messageId = contentEl.dataset.messageId;
        const assistantMessage = findNextAssistantMessage(button);
        const assistantMessageId = assistantMessage?.content?.dataset.messageId || '';
        if (messageId) {
            const oldAssistantText = assistantMessage?.content?.dataset.rawText || '';
            button.disabled = true;
            contentEl.dataset.rawText = cleanMessage;
            contentEl.querySelector('.msg-bubble').innerHTML = escapeHTML(cleanMessage).replace(/\n/g, '<br>');

            if (assistantMessage && assistantMessageId) {
                setMessageText(assistantMessage, 'Thinking...');
                assistantMessage.bubble.classList.add('streaming');
            }

            try {
                const endpoint = assistantMessageId ? '/message/edit-regenerate' : '/message/edit';
                const payload = assistantMessageId
                    ? {
                        user_message_id: messageId,
                        assistant_message_id: assistantMessageId,
                        content: cleanMessage,
                        agent: selectedAgent
                    }
                    : { message_id: messageId, content: cleanMessage };

                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();

                if (!res.ok) {
                    throw new Error(data.error || 'Message update nahi hua.');
                }

                if (assistantMessage && data.response) {
                    setMessageText(assistantMessage, data.response);
                    assistantMessage.bubble.classList.remove('streaming');
                    setMessageMeta(assistantMessage, {
                        provider: data.provider,
                        agent: data.agent
                    });
                    updateFeedbackButtons(assistantMessage.content, '');
                }
                refreshSessions();
            } catch (e) {
                contentEl.dataset.rawText = message;
                contentEl.querySelector('.msg-bubble').innerHTML = escapeHTML(message).replace(/\n/g, '<br>');
                if (assistantMessage) {
                    setMessageText(assistantMessage, oldAssistantText || 'Response regenerate nahi hua.');
                    assistantMessage.bubble.classList.remove('streaming');
                }
                addMessage(e.message || 'Message edit nahi hua.', 'bot', {
                    provider: 'Error',
                    agent: selectedAgent
                });
            } finally {
                button.disabled = false;
            }
            return;
        }

        contentEl.dataset.rawText = cleanMessage;
        contentEl.querySelector('.msg-bubble').innerHTML = escapeHTML(cleanMessage).replace(/\n/g, '<br>');
    }

    function addMessage(text, role, meta = null) {
        const box = document.getElementById('chat-box');
        const typing = document.getElementById('typing-wrapper');
        const div = document.createElement('div');
        const safeText = escapeHTML(text).replace(/\n/g, '<br>');
        const safeProvider = meta?.provider ? escapeHTML(meta.provider) : '';
        const safeAgent = meta?.agent ? escapeHTML(meta.agent) : '';
        const metaHTML = safeProvider || safeAgent
            ? `<div class="msg-meta">
                ${safeAgent ? `<span class="meta-pill">${safeAgent}</span>` : ''}
                ${safeProvider ? `<span class="meta-pill">${safeProvider}</span>` : ''}
            </div>`
            : '';
        let actionsHTML = '';
        if (role === 'bot') {
            actionsHTML = `<button class="copy-btn" onclick="copyMessage(this)" type="button" title="Copy response" aria-label="Copy response">${iconSvg('copy')}</button>
               <button class="copy-btn" onclick="regenerateMessage(this)" type="button" title="Regenerate response" aria-label="Regenerate response">${iconSvg('refresh')}</button>
               <button class="copy-btn feedback-btn" data-feedback="up" onclick="submitFeedback(this, 'up')" type="button" title="Good response" aria-label="Good response">${iconSvg('thumbsUp')}</button>
               <button class="copy-btn feedback-btn" data-feedback="down" onclick="submitFeedback(this, 'down')" type="button" title="Bad response" aria-label="Bad response">${iconSvg('thumbsDown')}</button>`;
        }
        if (role === 'user') {
            actionsHTML = `<button class="copy-btn" onclick="editUserMessage(this)" type="button" title="Edit and resend" aria-label="Edit and resend">${iconSvg('edit')}</button>`;
        }
        div.className = `message ${role}`;
        div.innerHTML = `
            <div class="msg-avatar" aria-label="${role === 'user' ? 'User' : 'Assistant'}">
                ${role === 'user' ? '👤' : '✦'}
            </div>
            <div class="msg-content">
                <div class="msg-bubble">${safeText}</div>
                <div class="msg-footer">
                    <div class="msg-time">${getTime()}</div>
                    ${actionsHTML}
                </div>
                ${metaHTML}
            </div>`;
        const contentEl = div.querySelector('.msg-content');
        contentEl.dataset.rawText = text;
        if (meta?.messageId) contentEl.dataset.messageId = meta.messageId;
        updateFeedbackButtons(contentEl, meta?.feedback || '');
        box.insertBefore(div, typing);
        scrollToBottom();
        return {
            bubble: div.querySelector('.msg-bubble'),
            content: div.querySelector('.msg-content'),
            node: div
        };
    }

    function setMessageId(messageEl, messageId) {
        if (!messageId) return;
        messageEl.content.dataset.messageId = messageId;
    }

    function setUserMessageId(messageEl, messageId) {
        if (!messageId) return;
        messageEl.content.dataset.messageId = messageId;
    }

    function setMessageMeta(messageEl, meta) {
        if (!meta?.provider && !meta?.agent) return;

        const oldMeta = messageEl.content.querySelector('.msg-meta');
        if (oldMeta) oldMeta.remove();

        const safeProvider = meta.provider ? escapeHTML(meta.provider) : '';
        const safeAgent = meta.agent ? escapeHTML(meta.agent) : '';
        const metaDiv = document.createElement('div');
        metaDiv.className = 'msg-meta';
        metaDiv.innerHTML = `
            ${safeAgent ? `<span class="meta-pill">${safeAgent}</span>` : ''}
            ${safeProvider ? `<span class="meta-pill">${safeProvider}</span>` : ''}
        `;
        messageEl.content.appendChild(metaDiv);
    }

    window.addEventListener('DOMContentLoaded', () => {
        applyTheme(localStorage.getItem('chat_theme') || 'dark');
        updatePinButton();
        renderMessages(initialMessages);
    });

    async function newSession() {
        const res = await fetch('/sessions/new', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            addMessage(data.error || 'New chat create nahi hua.', 'bot', { provider: 'Error' });
            return;
        }

        updateSessionSelect(data.sessions, data.active_session_id);
        renderMessages(data.messages || []);
        document.getElementById('file-input').value = '';
        document.getElementById('file-status').textContent = 'No file attached';
        document.getElementById('user-input').focus();
    }

    async function togglePinSession() {
        const activeSession = sessions.find(item => Number(item.id) === Number(activeSessionId));
        const nextPinned = !activeSession?.pinned;
        const res = await fetch('/sessions/pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pinned: nextPinned })
        });
        const data = await res.json();
        if (!res.ok) {
            addMessage(data.error || 'Session pin update nahi hui.', 'bot', { provider: 'Error' });
            return;
        }

        updateSessionSelect(data.sessions, data.active_session_id);
    }

    async function selectSession(sessionId) {
        const res = await fetch('/sessions/select', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId })
        });
        const data = await res.json();
        if (!res.ok) {
            addMessage(data.error || 'Session switch nahi hui.', 'bot', { provider: 'Error' });
            updateSessionSelect(sessions, activeSessionId);
            return;
        }

        updateSessionSelect(data.sessions, data.active_session_id);
        renderMessages(data.messages || []);
        document.getElementById('file-input').value = '';
        document.getElementById('file-status').textContent = 'No file attached';
        document.getElementById('user-input').focus();
    }

    async function renameSession() {
        const activeSession = sessions.find(item => Number(item.id) === Number(activeSessionId));
        const currentTitle = activeSession?.title || 'Chat';
        const title = prompt('Session ka new naam likho:', currentTitle);
        if (title === null) return;

        const cleanTitle = title.trim();
        if (!cleanTitle) {
            addMessage('Session naam empty nahi ho sakta.', 'bot', { provider: 'Local', agent: 'Session' });
            return;
        }

        const res = await fetch('/sessions/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: cleanTitle })
        });
        const data = await res.json();
        if (!res.ok) {
            addMessage(data.error || 'Session rename nahi hui.', 'bot', { provider: 'Error' });
            return;
        }

        updateSessionSelect(data.sessions, data.active_session_id);
    }

    async function deleteSession() {
        const activeSession = sessions.find(item => Number(item.id) === Number(activeSessionId));
        const currentTitle = activeSession?.title || 'current chat';
        const ok = confirm(`"${currentTitle}" delete karni hai? Ye chat history permanently remove ho jayegi.`);
        if (!ok) return;

        const res = await fetch('/sessions/delete', { method: 'POST' });
        const data = await res.json();
        if (!res.ok) {
            addMessage(data.error || 'Session delete nahi hui.', 'bot', { provider: 'Error' });
            return;
        }

        updateSessionSelect(data.sessions, data.active_session_id);
        renderMessages(data.messages || []);
        document.getElementById('file-input').value = '';
        document.getElementById('file-status').textContent = 'No file attached';
        document.getElementById('user-input').focus();
    }

    async function sendMessage(forcedMessage = '') {
        const input = document.getElementById('user-input');
        const btn = document.getElementById('send-btn');
        const message = forcedMessage.trim() || input.value.trim();
        if (!message) return;

        const userMessage = addMessage(message, 'user');
        if (!forcedMessage) {
            input.value = '';
            input.style.height = 'auto';
        }

        btn.disabled = true;
        const botMessage = addMessage('Thinking...', 'bot', { provider: 'Streaming', agent: selectedAgent });
        botMessage.bubble.classList.add('streaming');
        let fullReply = '';
        let streamMeta = { provider: 'Streaming', agent: selectedAgent };

        try {
            const res = await fetch('/chat/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message, agent: selectedAgent })
            });

            if (!res.body) throw new Error('Streaming not supported');

            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop();

                for (const line of lines) {
                    if (!line.trim()) continue;
                    const event = JSON.parse(line);

                    if (event.type === 'meta') {
                        streamMeta = { provider: event.provider, agent: event.agent };
                        setMessageMeta(botMessage, streamMeta);
                    }

                    if (event.type === 'chunk') {
                        fullReply += event.text;
                        botMessage.bubble.innerHTML = escapeHTML(fullReply).replace(/\n/g, '<br>');
                        botMessage.content.dataset.rawText = fullReply;
                        scrollToBottom();
                    }

                    if (event.type === 'error') {
                        fullReply = event.message;
                        botMessage.bubble.innerHTML = escapeHTML(fullReply).replace(/\n/g, '<br>');
                        botMessage.content.dataset.rawText = fullReply;
                        botMessage.bubble.classList.remove('streaming');
                        setMessageMeta(botMessage, { provider: 'Error', agent: streamMeta.agent });
                    }

                    if (event.type === 'done') {
                        botMessage.bubble.classList.remove('streaming');
                        setMessageMeta(botMessage, { provider: event.provider, agent: event.agent });
                        setMessageId(botMessage, event.message_id);
                        setUserMessageId(userMessage, event.user_message_id);
                    }
                }
            }

            botMessage.bubble.classList.remove('streaming');
        } catch (e) {
            botMessage.bubble.innerHTML = 'Kuch masla ho gaya! Dobara try karo.';
            botMessage.bubble.classList.remove('streaming');
            setMessageMeta(botMessage, { provider: 'Error', agent: selectedAgent });
        }

        btn.disabled = false;
        refreshSessions();
        input.focus();
    }

    async function clearChat() {
        await fetch('/clear', { method: 'POST' });
        clearMessageNodes();
        const session = sessions.find(item => Number(item.id) === Number(activeSessionId));
        if (session) session.message_count = 0;
        updateSessionSelect(sessions, activeSessionId);
    }
