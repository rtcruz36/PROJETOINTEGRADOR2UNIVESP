const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    topicSelector: document.getElementById('topic-selector'),
    topicFeedback: document.getElementById('topic-feedback'),
    contextTitle: document.getElementById('context-title'),
    contextCourse: document.getElementById('context-course'),
    contextSubtopics: document.getElementById('context-subtopics'),
    contextPlan: document.getElementById('context-plan'),
    quickSuggestions: document.getElementById('quick-suggestions'),
    chatMessages: document.getElementById('chat-messages'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    chatStatus: document.getElementById('chat-status'),
    chatTemplate: document.getElementById('chat-message-template'),
};

const state = {
    user: null,
    topics: [],
    currentTopicId: undefined,
    currentTopic: null,
    currentCourse: null,
    chatHistory: [],
    inputHistory: [],
    inputHistoryIndex: null,
    conversations: new Map(),
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);
    selectors.topicSelector?.addEventListener('change', handleTopicChange);
    selectors.chatForm?.addEventListener('submit', handleChatSubmit);
    selectors.chatInput?.addEventListener('keydown', handleChatInputKeydown);
    selectors.quickSuggestions?.addEventListener('click', handleSuggestionClick);

    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadChatEnvironment().catch((error) => {
        console.error('Falha ao restaurar sessão:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    selectors.loginError.textContent = '';

    const formData = new FormData(selectors.loginForm);
    const email = formData.get('email');
    const password = formData.get('password');

    try {
        const response = await fetch(`${API_BASE_URL}/accounts/auth/jwt/create/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ email, password }),
        });

        if (!response.ok) {
            const errorData = await safeJson(response);
            const detail = errorData?.detail || 'Não foi possível realizar o login.';
            throw new Error(detail);
        }

        const data = await response.json();
        saveTokens({ access: data.access, refresh: data.refresh });
        selectors.loginForm.reset();

        await loadChatEnvironment();
        hideLogin();
    } catch (error) {
        console.error('Erro de login:', error);
        selectors.loginError.textContent = error.message || 'Erro inesperado ao entrar.';
    }
}

function handleLogout() {
    clearTokens();
    showLogin();
}

function showLogin(message) {
    if (message) {
        selectors.loginError.textContent = message;
    }
    selectors.loginOverlay.hidden = false;
}

function hideLogin() {
    selectors.loginError.textContent = '';
    selectors.loginOverlay.hidden = true;
}

async function loadChatEnvironment() {
    setTopicFeedback('Carregando seus tópicos...', 'loading');
    setChatStatus('Selecione um contexto para começar ou envie sua dúvida.', '');

    const [user, topics] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/learning/topics/'),
    ]);

    state.user = user;
    updateGreeting(user);

    state.topics = Array.isArray(topics)
        ? topics
              .slice()
              .sort((a, b) => {
                  const orderDiff = (a.order || 0) - (b.order || 0);
                  if (orderDiff !== 0) {
                      return orderDiff;
                  }
                  return String(a.title || '').localeCompare(String(b.title || ''));
              })
        : [];
    populateTopicSelector();

    const initialTopicId = state.topics.length ? state.topics[0].id : null;
    await setActiveTopic(initialTopicId);
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }
    if (user?.first_name) {
        selectors.greeting.textContent = `Olá, ${user.first_name}!`;
    } else if (user?.email) {
        selectors.greeting.textContent = `Olá, ${user.email.split('@')[0]}!`;
    } else {
        selectors.greeting.textContent = 'Olá!';
    }
}

function populateTopicSelector() {
    if (!selectors.topicSelector) {
        return;
    }

    selectors.topicSelector.innerHTML = '';

    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Sem contexto específico';
    selectors.topicSelector.appendChild(defaultOption);

    if (!state.topics.length) {
        selectors.topicSelector.disabled = false;
        setTopicFeedback(
            'Você ainda não possui tópicos cadastrados. O StudyBot responderá sem contexto.',
            'info',
        );
        return;
    }

    selectors.topicSelector.disabled = false;

    state.topics
        .slice()
        .sort((a, b) => (a.order || 0) - (b.order || 0))
        .forEach((topic) => {
            const option = document.createElement('option');
            option.value = topic.id;
            option.textContent = topic.title;
            selectors.topicSelector.appendChild(option);
        });

    selectors.topicSelector.value = state.currentTopicId ?? '';
}

async function handleTopicChange(event) {
    const value = event.target.value;
    const topicId = value ? Number.parseInt(value, 10) : null;
    await setActiveTopic(Number.isNaN(topicId) ? null : topicId);
}

async function setActiveTopic(topicId) {
    if (state.currentTopicId === topicId) {
        return;
    }

    state.currentTopicId = topicId || null;
    setTopicFeedback('Atualizando contexto do StudyBot...', 'loading');

    if (!topicId) {
        state.currentTopic = null;
        state.currentCourse = null;
        selectors.topicSelector.value = '';
        updateContextPanel();
        loadConversationForTopic(null);
        setTopicFeedback('Conversa sem contexto específico. Pergunte o que quiser!', 'success');
        return;
    }

    try {
        const topic = await apiFetch(`/learning/topics/${encodeURIComponent(topicId)}/`);
        state.currentTopic = topic;
        selectors.topicSelector.value = topicId;

        if (topic.course) {
            try {
                const course = await apiFetch(`/learning/courses/${encodeURIComponent(topic.course)}/`);
                state.currentCourse = course;
            } catch (error) {
                console.warn('Não foi possível carregar os detalhes do curso:', error);
                state.currentCourse = null;
            }
        } else {
            state.currentCourse = null;
        }

        updateContextPanel();
        loadConversationForTopic(topicId);
        setTopicFeedback('Contexto atualizado com sucesso.', 'success');
    } catch (error) {
        console.error('Erro ao carregar o tópico selecionado:', error);
        state.currentTopic = null;
        state.currentCourse = null;
        selectors.topicSelector.value = '';
        updateContextPanel();
        loadConversationForTopic(null);
        setTopicFeedback(error.message || 'Não foi possível carregar o tópico selecionado.', 'error');
    }
}

function updateContextPanel() {
    const topicTitle = state.currentTopic?.title || 'Nenhum tópico selecionado';
    selectors.contextTitle.textContent = topicTitle;

    const courseTitle = state.currentCourse?.title;
    selectors.contextCourse.textContent = courseTitle ? `Curso: ${courseTitle}` : '';

    if (!state.currentTopic) {
        selectors.contextSubtopics.textContent = 'Selecione um tópico para contextualizar suas perguntas.';
        selectors.contextPlan.textContent =
            'Escolha um tópico para visualizar o plano sugerido pela IA.';
        renderQuickSuggestions();
        return;
    }

    const subtopics = Array.isArray(state.currentTopic?.subtopics)
        ? state.currentTopic.subtopics
        : [];
    if (subtopics.length) {
        selectors.contextSubtopics.textContent = `${subtopics.length} subtópico(s) cadastrados.`;
    } else {
        selectors.contextSubtopics.textContent = 'Sem subtópicos registrados para este tópico.';
    }

    const plan = (state.currentTopic?.suggested_study_plan || '').trim();
    selectors.contextPlan.textContent = plan
        ? plan
        : 'Nenhum plano sugerido disponível para este tópico ainda. Use o StudyBot para construir um!';

    renderQuickSuggestions();
}

function renderQuickSuggestions() {
    if (!selectors.quickSuggestions) {
        return;
    }

    selectors.quickSuggestions.innerHTML = '';

    const topicTitle = state.currentTopic?.title || 'este conteúdo';
    const suggestions = [
        {
            id: 'explain',
            text: `Explique ${topicTitle}`,
        },
        {
            id: 'examples',
            text: `Dê exemplos sobre ${topicTitle}`,
        },
    ];

    suggestions.forEach((suggestion) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'quick-suggestion';
        button.dataset.intent = suggestion.id;
        button.dataset.payload = suggestion.text;
        button.textContent = suggestion.text;
        selectors.quickSuggestions.appendChild(button);
    });
}

function handleSuggestionClick(event) {
    const button = event.target.closest('button[data-payload]');
    if (!button) {
        return;
    }

    const payload = button.dataset.payload;
    if (!payload || !selectors.chatInput) {
        return;
    }

    selectors.chatInput.value = payload;
    selectors.chatInput.focus();
    selectors.chatInput.setSelectionRange(payload.length, payload.length);
    setChatStatus('Sugestão adicionada ao campo de mensagem.', 'info');
}

async function handleChatSubmit(event) {
    event.preventDefault();

    const question = selectors.chatInput.value.trim();
    if (!question) {
        setChatStatus('Digite uma pergunta para o StudyBot.', 'error');
        return;
    }

    const historySnapshot = state.chatHistory.slice(-10).map((message) => ({
        role: message.role,
        content: message.content,
    }));

    appendChatMessage({ role: 'user', content: question });
    selectors.chatInput.value = '';

    state.inputHistory.push(question);
    if (state.inputHistory.length > 50) {
        state.inputHistory = state.inputHistory.slice(-50);
    }
    state.inputHistoryIndex = state.inputHistory.length;
    saveConversationState();

    setChatStatus('Processando sua pergunta...', 'loading');
    selectors.chatMessages.setAttribute('aria-busy', 'true');

    try {
        const payload = {
            question,
            history: historySnapshot,
            topic_id: state.currentTopic?.id ?? null,
        };

        const response = await apiFetch('/chat/ask/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        const answer = response?.content || 'Não recebi uma resposta do StudyBot.';
        appendChatMessage({ role: 'assistant', content: answer });
        setChatStatus('Tudo certo! Continue explorando suas dúvidas.', 'success');
    } catch (error) {
        console.error('Erro ao enviar pergunta para o StudyBot:', error);
        setChatStatus(error.message || 'Não foi possível enviar sua pergunta.', 'error');
    } finally {
        selectors.chatMessages.setAttribute('aria-busy', 'false');
    }
}

function handleChatInputKeydown(event) {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        selectors.chatForm.requestSubmit();
        return;
    }

    if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') {
        return;
    }

    if (event.shiftKey) {
        return;
    }

    const { selectionStart, selectionEnd, value } = event.target;
    const atStart = selectionStart === 0 && selectionEnd === 0;
    const atEnd = selectionStart === value.length && selectionEnd === value.length;

    if (event.key === 'ArrowUp' && atStart) {
        event.preventDefault();
        navigateInputHistory(-1);
    } else if (event.key === 'ArrowDown' && atEnd) {
        event.preventDefault();
        navigateInputHistory(1);
    }
}

function navigateInputHistory(step) {
    if (!state.inputHistory.length || !selectors.chatInput) {
        return;
    }

    if (state.inputHistoryIndex === null) {
        state.inputHistoryIndex = state.inputHistory.length;
    }

    let nextIndex = state.inputHistoryIndex + step;
    if (nextIndex < 0) {
        nextIndex = 0;
    }
    if (nextIndex > state.inputHistory.length) {
        nextIndex = state.inputHistory.length;
    }

    state.inputHistoryIndex = nextIndex;

    if (nextIndex === state.inputHistory.length) {
        selectors.chatInput.value = '';
    } else {
        selectors.chatInput.value = state.inputHistory[nextIndex];
    }

    const caret = selectors.chatInput.value.length;
    selectors.chatInput.setSelectionRange(caret, caret);
}

function loadConversationForTopic(topicId) {
    const key = getConversationKey(topicId);
    const conversation = state.conversations.get(key);

    state.chatHistory = conversation?.messages?.slice() || [];
    state.inputHistory = conversation?.inputHistory?.slice() || [];
    state.inputHistoryIndex = state.inputHistory.length;

    renderChatHistory();
    if (!state.chatHistory.length) {
        setChatStatus('Envie sua primeira pergunta para iniciar a conversa.', 'info');
    } else {
        setChatStatus('Conversa carregada. Continue de onde parou!', 'success');
    }
}

function renderChatHistory() {
    if (!selectors.chatMessages) {
        return;
    }

    selectors.chatMessages.innerHTML = '';
    state.chatHistory.forEach((message) => {
        appendChatMessage(message, { persist: false });
    });
    selectors.chatMessages.scrollTop = selectors.chatMessages.scrollHeight;
    selectors.chatMessages.setAttribute('aria-busy', 'false');
}

function appendChatMessage(message, { persist = true } = {}) {
    if (!selectors.chatTemplate || !selectors.chatMessages) {
        return;
    }

    const normalized = normalizeMessage(message);
    const element = createChatElement(normalized);
    selectors.chatMessages.appendChild(element);
    selectors.chatMessages.scrollTop = selectors.chatMessages.scrollHeight;

    if (persist) {
        state.chatHistory.push(normalized);
        if (state.chatHistory.length > 40) {
            state.chatHistory = state.chatHistory.slice(-40);
        }
        saveConversationState();
    }
}

function normalizeMessage(message) {
    const role = message.role === 'assistant' ? 'assistant' : 'user';
    const timestamp = message.timestamp || new Date().toISOString();
    return {
        role,
        content: message.content,
        timestamp,
    };
}

function createChatElement(message) {
    const clone = selectors.chatTemplate.content.firstElementChild.cloneNode(true);
    clone.classList.add(`chat-message--${message.role}`);
    clone.querySelector('.chat-author').textContent = message.role === 'assistant' ? 'StudyBot' : 'Você';

    const timestamp = new Date(message.timestamp);
    clone.querySelector('.chat-timestamp').textContent = Number.isNaN(timestamp.getTime())
        ? ''
        : timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
          });

    clone.querySelector('.chat-content').textContent = message.content;
    return clone;
}

function saveConversationState() {
    const key = getConversationKey(state.currentTopicId);
    state.conversations.set(key, {
        messages: state.chatHistory.slice(),
        inputHistory: state.inputHistory.slice(),
    });
}

function getConversationKey(topicId) {
    return topicId ? `topic-${topicId}` : 'global';
}

function setChatStatus(message, status) {
    if (!selectors.chatStatus) {
        return;
    }
    selectors.chatStatus.textContent = message || '';
    selectors.chatStatus.dataset.status = status || '';
}

function setTopicFeedback(message, status) {
    if (!selectors.topicFeedback) {
        return;
    }
    selectors.topicFeedback.textContent = message || '';
    selectors.topicFeedback.dataset.status = status || '';
}

function loadTokens() {
    try {
        const stored = window.localStorage.getItem(STORAGE_KEY);
        return stored ? JSON.parse(stored) : null;
    } catch (error) {
        console.warn('Não foi possível carregar os tokens salvos:', error);
        return null;
    }
}

function saveTokens(tokens) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
    } catch (error) {
        console.warn('Não foi possível salvar os tokens:', error);
    }
}

function clearTokens() {
    try {
        window.localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
        console.warn('Não foi possível limpar os tokens:', error);
    }
}

async function refreshAccessToken(refreshToken) {
    const response = await fetch(`${API_BASE_URL}/accounts/auth/jwt/refresh/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh: refreshToken }),
    });

    if (!response.ok) {
        throw new Error('Não foi possível atualizar a sessão.');
    }

    const data = await response.json();
    if (!data?.access) {
        throw new Error('Resposta inválida ao atualizar token.');
    }

    const tokens = loadTokens() || {};
    tokens.access = data.access;
    saveTokens(tokens);
    return data.access;
}

async function apiFetch(path, options = {}, { allowEmpty = false, retryOn401 = true } = {}) {
    const tokens = loadTokens();
    if (!tokens?.access) {
        throw new Error('Sessão inválida');
    }

    const url = `${API_BASE_URL}${path}`;
    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${tokens.access}`);
    if (!headers.has('Content-Type') && options.body) {
        headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(url, { ...options, headers });

    if (response.status === 401 && retryOn401 && tokens.refresh) {
        try {
            const newAccess = await refreshAccessToken(tokens.refresh);
            headers.set('Authorization', `Bearer ${newAccess}`);
            const retryResponse = await fetch(url, { ...options, headers, body: options.body });
            return await handleApiResponse(retryResponse, allowEmpty);
        } catch (error) {
            clearTokens();
            throw error;
        }
    }

    return handleApiResponse(response, allowEmpty);
}

async function handleApiResponse(response, allowEmpty) {
    if (!response.ok) {
        const errorData = await safeJson(response);
        const detail =
            errorData?.detail || errorData?.error || 'Ocorreu um erro ao comunicar com o servidor.';
        throw new Error(detail);
    }

    if (response.status === 204 || response.headers.get('Content-Length') === '0') {
        return allowEmpty ? null : {};
    }

    const data = await safeJson(response);
    if (data === null && !allowEmpty) {
        throw new Error('Resposta inesperada do servidor.');
    }
    return data;
}

async function safeJson(response) {
    try {
        return await response.clone().json();
    } catch (error) {
        return null;
    }
}
