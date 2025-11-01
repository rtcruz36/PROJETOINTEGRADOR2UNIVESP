const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const urlParams = new URLSearchParams(window.location.search);
const initialTopicId = Number.parseInt(urlParams.get('topicId'), 10) || null;
const initialSubtopicId = Number.parseInt(urlParams.get('subtopicId'), 10) || null;

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    focusTopicTitle: document.getElementById('focus-topic-title'),
    focusProgress: document.getElementById('focus-progress'),
    focusSubtopicTitle: document.getElementById('focus-subtopic-title'),
    focusSubtopicDetails: document.getElementById('focus-subtopic-details'),
    markCompleteButton: document.getElementById('mark-complete'),
    prevSubtopicButton: document.getElementById('prev-subtopic'),
    nextSubtopicButton: document.getElementById('next-subtopic'),
    topicSelector: document.getElementById('topic-selector'),
    subtopicSelector: document.getElementById('subtopic-selector'),
    subtopicsList: document.getElementById('subtopics-list'),
    subtopicsSummary: document.getElementById('subtopics-summary'),
    timerOutput: document.getElementById('timer-output'),
    timerStatus: document.getElementById('timer-status'),
    timerStart: document.getElementById('timer-start'),
    timerPause: document.getElementById('timer-pause'),
    timerReset: document.getElementById('timer-reset'),
    timerDuration: document.getElementById('timer-duration'),
    noteForm: document.getElementById('quick-note-form'),
    noteMinutes: document.getElementById('note-minutes'),
    noteContent: document.getElementById('note-content'),
    noteFeedback: document.getElementById('note-feedback'),
    notesList: document.getElementById('notes-list'),
    chatMessages: document.getElementById('chat-messages'),
    chatForm: document.getElementById('chat-form'),
    chatInput: document.getElementById('chat-input'),
    chatStatus: document.getElementById('chat-status'),
    chatTemplate: document.getElementById('chat-message-template'),
};

const state = {
    user: null,
    topics: [],
    topic: null,
    course: null,
    subtopics: [],
    currentIndex: 0,
    studyLogs: [],
    chatHistory: [],
    timer: {
        defaultSeconds: 25 * 60,
        remainingSeconds: 25 * 60,
        elapsedSeconds: 0,
        running: false,
        intervalId: null,
    },
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);

    selectors.topicSelector?.addEventListener('change', (event) => {
        const topicId = Number.parseInt(event.target.value, 10) || null;
        if (topicId) {
            setActiveTopic(topicId).catch((error) => console.error(error));
        }
    });

    selectors.subtopicSelector?.addEventListener('change', (event) => {
        const subtopicId = Number.parseInt(event.target.value, 10) || null;
        if (Number.isInteger(subtopicId)) {
            focusSubtopicById(subtopicId);
        }
    });

    selectors.subtopicsList?.addEventListener('click', (event) => {
        const button = event.target.closest('[data-subtopic-id]');
        if (button) {
            const subtopicId = Number.parseInt(button.dataset.subtopicId, 10);
            if (Number.isInteger(subtopicId)) {
                focusSubtopicById(subtopicId);
            }
        }
    });

    selectors.markCompleteButton?.addEventListener('click', handleToggleCompletion);
    selectors.prevSubtopicButton?.addEventListener('click', () => moveSubtopic(-1));
    selectors.nextSubtopicButton?.addEventListener('click', () => moveSubtopic(1));

    selectors.timerStart?.addEventListener('click', startTimer);
    selectors.timerPause?.addEventListener('click', pauseTimer);
    selectors.timerReset?.addEventListener('click', resetTimer);
    selectors.timerDuration?.addEventListener('change', handleDurationChange);

    selectors.noteForm?.addEventListener('submit', handleNoteSubmit);

    selectors.chatForm?.addEventListener('submit', handleChatSubmit);
    selectors.chatInput?.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
            event.preventDefault();
            selectors.chatForm.requestSubmit();
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            pauseTimer();
        }
    });

    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadStudyEnvironment().catch((error) => {
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

        await loadStudyEnvironment();
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

async function loadStudyEnvironment() {
    selectors.focusTopicTitle.textContent = 'Carregando seus tópicos...';
    selectors.focusProgress.textContent = '';

    const [user, topics] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/learning/topics/'),
    ]);

    state.user = user;
    updateGreeting(user);

    state.topics = Array.isArray(topics) ? topics : [];
    populateTopicSelector();

    if (!state.topics.length) {
        handleEmptyTopics();
        return;
    }

    const topicId = determineInitialTopicId();
    await setActiveTopic(topicId, { focusSubtopicId: initialSubtopicId });
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

    if (!state.topics.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Nenhum tópico disponível';
        selectors.topicSelector.appendChild(option);
        selectors.topicSelector.disabled = true;
        return;
    }

    selectors.topicSelector.disabled = false;

    state.topics
        .slice()
        .sort((a, b) => a.order - b.order)
        .forEach((topic) => {
            const option = document.createElement('option');
            option.value = topic.id;
            option.textContent = topic.title;
            selectors.topicSelector.appendChild(option);
        });
}

function populateSubtopicSelector() {
    if (!selectors.subtopicSelector) {
        return;
    }

    selectors.subtopicSelector.innerHTML = '';

    if (!state.subtopics.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Nenhum subtópico cadastrado';
        selectors.subtopicSelector.appendChild(option);
        selectors.subtopicSelector.disabled = true;
        return;
    }

    selectors.subtopicSelector.disabled = false;

    state.subtopics.forEach((subtopic, index) => {
        const option = document.createElement('option');
        option.value = subtopic.id;
        option.textContent = `${index + 1}. ${subtopic.title}`;
        selectors.subtopicSelector.appendChild(option);
    });

    const current = state.subtopics[state.currentIndex];
    if (current) {
        selectors.subtopicSelector.value = current.id;
    }
}

function determineInitialTopicId() {
    if (initialTopicId) {
        const exists = state.topics.some((topic) => Number(topic.id) === initialTopicId);
        if (exists) {
            return initialTopicId;
        }
    }
    return state.topics[0]?.id;
}

async function setActiveTopic(topicId, { focusSubtopicId = null } = {}) {
    if (!topicId) {
        handleEmptyTopics();
        return;
    }

    selectors.topicSelector.value = topicId;
    selectors.focusTopicTitle.textContent = 'Carregando subtópicos...';
    selectors.focusProgress.textContent = '';

    try {
        const topic = await apiFetch(`/learning/topics/${encodeURIComponent(topicId)}/`);
        state.topic = topic;
        state.subtopics = Array.isArray(topic.subtopics)
            ? topic.subtopics.slice().sort((a, b) => a.order - b.order)
            : [];

        await loadCourseDetail(topic.course);
        resetChat();
        selectInitialSubtopic(focusSubtopicId);
        populateSubtopicSelector();
        renderFocusView();
        setNoteFeedback('', '');
        await loadQuickNotes();
        resetTimer();
    } catch (error) {
        console.error('Erro ao carregar o tópico:', error);
        selectors.focusTopicTitle.textContent = 'Não foi possível carregar o tópico selecionado.';
        selectors.focusProgress.textContent = error.message || '';
    }
}

async function loadCourseDetail(courseId) {
    if (!courseId) {
        state.course = null;
        return;
    }

    try {
        const course = await apiFetch(`/learning/courses/${encodeURIComponent(courseId)}/`);
        state.course = course;
    } catch (error) {
        console.warn('Não foi possível carregar os detalhes do curso:', error);
        state.course = null;
    }
}

function selectInitialSubtopic(focusSubtopicId = null) {
    if (!state.subtopics.length) {
        state.currentIndex = 0;
        return;
    }

    if (focusSubtopicId) {
        const index = state.subtopics.findIndex((item) => Number(item.id) === Number(focusSubtopicId));
        if (index >= 0) {
            state.currentIndex = index;
            return;
        }
    }

    state.currentIndex = 0;
}

function renderFocusView() {
    const topicTitle = state.topic?.title || 'Tópico não encontrado';
    const courseTitle = state.course?.title ? `${state.course.title} • ` : '';
    selectors.focusTopicTitle.textContent = `${courseTitle}${topicTitle}`;

    renderSubtopicList();
    renderCurrentSubtopic();
    updateProgressIndicators();
    updateControlsAvailability();
}

function resetChat() {
    if (selectors.chatMessages) {
        selectors.chatMessages.innerHTML = '';
    }
    state.chatHistory = [];
    setChatStatus('Converse com o StudyBot para tirar dúvidas sobre este tópico.', '');
}

function renderSubtopicList() {
    if (!selectors.subtopicsList) {
        return;
    }

    selectors.subtopicsList.innerHTML = '';

    if (!state.subtopics.length) {
        const emptyItem = document.createElement('li');
        emptyItem.className = 'course-placeholder';
        emptyItem.textContent = 'Nenhum subtópico cadastrado para este tópico.';
        selectors.subtopicsList.appendChild(emptyItem);
        selectors.subtopicsSummary.textContent = 'Adicione subtópicos no dashboard para utilizar o modo foco.';
        disableStudyControls(true);
        return;
    }

    disableStudyControls(false);

    const fragment = document.createDocumentFragment();
    state.subtopics.forEach((subtopic, index) => {
        const item = document.createElement('li');
        if (index === state.currentIndex) {
            item.dataset.active = 'true';
        }

        const info = document.createElement('div');
        info.className = 'subtopic-info';

        const title = document.createElement('h4');
        title.textContent = subtopic.title;
        info.appendChild(title);

        if (subtopic.details) {
            const details = document.createElement('p');
            details.textContent = subtopic.details;
            info.appendChild(details);
        }

        const statusWrapper = document.createElement('div');
        statusWrapper.className = 'subtopic-status';
        const statusIcon = document.createElement('span');
        statusIcon.textContent = subtopic.is_completed ? '✅' : '⏳';
        const statusLabel = document.createElement('span');
        statusLabel.textContent = subtopic.is_completed ? 'Concluído' : 'Em aberto';
        statusWrapper.appendChild(statusIcon);
        statusWrapper.appendChild(statusLabel);
        info.appendChild(statusWrapper);

        const actions = document.createElement('div');
        actions.className = 'subtopic-actions';
        const focusButton = document.createElement('button');
        focusButton.type = 'button';
        focusButton.className = 'ghost-button ghost-button--small';
        focusButton.dataset.subtopicId = subtopic.id;
        focusButton.textContent = index === state.currentIndex ? 'Focando agora' : 'Estudar';
        focusButton.disabled = index === state.currentIndex;
        actions.appendChild(focusButton);

        item.appendChild(info);
        item.appendChild(actions);
        fragment.appendChild(item);
    });

    selectors.subtopicsList.appendChild(fragment);

    const total = state.subtopics.length;
    const completed = state.subtopics.filter((item) => item.is_completed).length;
    selectors.subtopicsSummary.textContent = `${completed} de ${total} subtópicos concluídos`;
}

function renderCurrentSubtopic() {
    const current = state.subtopics[state.currentIndex];

    if (!current) {
        selectors.focusSubtopicTitle.textContent = 'Nenhum subtópico selecionado';
        selectors.focusSubtopicDetails.textContent = '';
        selectors.markCompleteButton.disabled = true;
        selectors.prevSubtopicButton.disabled = true;
        selectors.nextSubtopicButton.disabled = true;
        selectors.subtopicSelector.value = '';
        selectors.noteForm?.classList.add('is-disabled');
        return;
    }

    selectors.focusSubtopicTitle.textContent = current.title;
    selectors.focusSubtopicDetails.textContent = current.details || 'Aproveite o modo foco para aprofundar neste conteúdo.';
    selectors.markCompleteButton.disabled = false;
    selectors.prevSubtopicButton.disabled = state.currentIndex === 0;
    selectors.nextSubtopicButton.disabled = state.currentIndex >= state.subtopics.length - 1;
    selectors.subtopicSelector.value = current.id;
    selectors.noteForm?.classList.remove('is-disabled');

    updateCompletionButtonLabel(current.is_completed);
}

function updateCompletionButtonLabel(isCompleted) {
    if (!selectors.markCompleteButton) {
        return;
    }
    selectors.markCompleteButton.textContent = isCompleted ? 'Reabrir subtópico' : 'Marcar como concluído';
}

function updateProgressIndicators() {
    if (!state.subtopics.length) {
        selectors.focusProgress.textContent = '';
        return;
    }
    const position = state.currentIndex + 1;
    const total = state.subtopics.length;
    selectors.focusProgress.textContent = `Subtópico ${position} de ${total}`;
}

function updateControlsAvailability() {
    const hasSubtopics = Boolean(state.subtopics.length);
    selectors.timerStart.disabled = !hasSubtopics;
    selectors.timerPause.disabled = !hasSubtopics;
    selectors.timerReset.disabled = !hasSubtopics;
    selectors.noteMinutes.disabled = !hasSubtopics;
    selectors.noteContent.disabled = !hasSubtopics;
    selectors.chatInput.disabled = !hasSubtopics;
    const chatSubmit = selectors.chatForm?.querySelector('button[type="submit"]');
    if (chatSubmit) {
        chatSubmit.disabled = !hasSubtopics;
    }
}

function disableStudyControls(disabled) {
    selectors.markCompleteButton.disabled = disabled;
    selectors.prevSubtopicButton.disabled = disabled;
    selectors.nextSubtopicButton.disabled = disabled;
    selectors.timerStart.disabled = disabled;
    selectors.timerPause.disabled = disabled;
    selectors.timerReset.disabled = disabled;
    selectors.timerDuration.disabled = disabled;
    selectors.noteMinutes.disabled = disabled;
    selectors.noteContent.disabled = disabled;
    selectors.chatInput.disabled = disabled;
    const submitButton = selectors.chatForm?.querySelector('button[type="submit"]');
    if (submitButton) {
        submitButton.disabled = disabled;
    }
    if (selectors.noteForm) {
        selectors.noteForm.classList.toggle('is-disabled', Boolean(disabled));
    }
}

function focusSubtopicById(subtopicId) {
    const index = state.subtopics.findIndex((item) => Number(item.id) === Number(subtopicId));
    if (index >= 0) {
        state.currentIndex = index;
        renderFocusView();
        resetTimer();
    }
}

function moveSubtopic(delta) {
    if (!state.subtopics.length) {
        return;
    }

    const newIndex = state.currentIndex + delta;
    if (newIndex < 0 || newIndex >= state.subtopics.length) {
        return;
    }

    state.currentIndex = newIndex;
    renderFocusView();
    resetTimer();
}

async function handleToggleCompletion() {
    const current = state.subtopics[state.currentIndex];
    if (!current) {
        return;
    }

    const newValue = !current.is_completed;

    try {
        const payload = { is_completed: newValue };
        const updated = await apiFetch(`/learning/subtopics/${encodeURIComponent(current.id)}/`, {
            method: 'PATCH',
            body: JSON.stringify(payload),
        });

        state.subtopics[state.currentIndex] = { ...current, ...updated };
        renderFocusView();
        setNoteFeedback(newValue ? 'Subtópico marcado como concluído.' : 'Subtópico reaberto para revisão.', 'success');
    } catch (error) {
        console.error('Erro ao atualizar o subtópico:', error);
        setNoteFeedback(error.message || 'Não foi possível atualizar o subtópico.', 'error');
    }
}

function startTimer() {
    if (state.timer.running || !state.subtopics.length) {
        return;
    }

    if (state.timer.remainingSeconds <= 0) {
        state.timer.remainingSeconds = state.timer.defaultSeconds;
    }

    state.timer.running = true;
    selectors.timerStatus.textContent = 'Em andamento';

    state.timer.intervalId = window.setInterval(() => {
        state.timer.remainingSeconds = Math.max(0, state.timer.remainingSeconds - 1);
        state.timer.elapsedSeconds += 1;
        updateTimerDisplay();

        if (state.timer.remainingSeconds === 0) {
            pauseTimer();
            selectors.timerStatus.textContent = 'Tempo concluído! Faça uma pausa.';
            syncNoteMinutes();
        }
    }, 1000);
}

function pauseTimer() {
    if (!state.timer.running) {
        return;
    }

    window.clearInterval(state.timer.intervalId);
    state.timer.intervalId = null;
    state.timer.running = false;
    selectors.timerStatus.textContent = 'Timer pausado';
    syncNoteMinutes();
}

function resetTimer() {
    window.clearInterval(state.timer.intervalId);
    state.timer.intervalId = null;
    state.timer.running = false;

    const minutes = Number.parseInt(selectors.timerDuration?.value, 10);
    if (Number.isFinite(minutes) && minutes > 0) {
        state.timer.defaultSeconds = minutes * 60;
    }

    state.timer.remainingSeconds = state.timer.defaultSeconds;
    state.timer.elapsedSeconds = 0;
    selectors.timerStatus.textContent = 'Pronto para começar';
    updateTimerDisplay();
    syncNoteMinutes();
}

function handleDurationChange() {
    const minutes = Number.parseInt(selectors.timerDuration.value, 10);
    if (!Number.isFinite(minutes) || minutes < 5 || minutes > 120) {
        selectors.timerDuration.value = Math.round(state.timer.defaultSeconds / 60);
        return;
    }

    state.timer.defaultSeconds = minutes * 60;
    if (!state.timer.running) {
        state.timer.remainingSeconds = state.timer.defaultSeconds;
        state.timer.elapsedSeconds = 0;
        updateTimerDisplay();
        syncNoteMinutes();
    }
}

function updateTimerDisplay() {
    const minutes = Math.floor(state.timer.remainingSeconds / 60);
    const seconds = state.timer.remainingSeconds % 60;
    selectors.timerOutput.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function syncNoteMinutes() {
    if (!selectors.noteMinutes) {
        return;
    }
    const elapsedMinutes = Math.max(0, Math.round(state.timer.elapsedSeconds / 60));
    const fallback = Math.max(1, Math.round(state.timer.defaultSeconds / 60));
    selectors.noteMinutes.value = Math.max(1, elapsedMinutes || fallback);
}

async function loadQuickNotes() {
    if (!state.topic) {
        selectors.notesList.innerHTML = '';
        return;
    }

    try {
        const logs = await apiFetch('/scheduling/logs/');
        state.studyLogs = Array.isArray(logs)
            ? logs.filter((log) => Number(log.topic) === Number(state.topic.id))
            : [];
        renderNotes();
    } catch (error) {
        console.error('Erro ao carregar notas rápidas:', error);
        state.studyLogs = [];
        selectors.notesList.innerHTML = '';
        const item = document.createElement('li');
        item.textContent = 'Não foi possível carregar suas notas de estudo.';
        selectors.notesList.appendChild(item);
    }
}

function renderNotes() {
    selectors.notesList.innerHTML = '';

    if (!state.studyLogs.length) {
        const emptyItem = document.createElement('li');
        emptyItem.textContent = 'Nenhuma nota registrada ainda. Utilize o formulário para registrar seus aprendizados.';
        selectors.notesList.appendChild(emptyItem);
        return;
    }

    const fragment = document.createDocumentFragment();

    state.studyLogs
        .slice()
        .sort((a, b) => new Date(b.date) - new Date(a.date))
        .forEach((log) => {
            const item = document.createElement('li');

            const header = document.createElement('header');
            const title = document.createElement('h4');
            title.textContent = `${log.minutes_studied} minuto(s)`;
            const time = document.createElement('time');
            time.dateTime = log.date;
            time.textContent = formatHumanDate(log.date);
            header.appendChild(title);
            header.appendChild(time);

            const content = document.createElement('p');
            content.textContent = log.notes || 'Sem anotações adicionais.';

            item.appendChild(header);
            item.appendChild(content);
            fragment.appendChild(item);
        });

    selectors.notesList.appendChild(fragment);
}

async function handleNoteSubmit(event) {
    event.preventDefault();
    const current = state.subtopics[state.currentIndex];
    if (!current || !state.topic) {
        setNoteFeedback('Selecione um subtópico para registrar suas notas.', 'error');
        return;
    }

    const minutes = Number.parseInt(selectors.noteMinutes.value, 10);
    const content = selectors.noteContent.value.trim();

    if (!Number.isFinite(minutes) || minutes < 1) {
        setNoteFeedback('Informe uma quantidade válida de minutos estudados.', 'error');
        return;
    }

    if (!content) {
        setNoteFeedback('Digite alguma anotação para salvar.', 'error');
        return;
    }

    try {
        const payload = {
            course: state.topic.course,
            topic: state.topic.id,
            date: new Date().toISOString().slice(0, 10),
            minutes_studied: minutes,
            notes: `[${current.title}] ${content}`,
        };

        const created = await apiFetch('/scheduling/logs/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        state.studyLogs.unshift(created);
        renderNotes();
        setNoteFeedback('Nota salva com sucesso!', 'success');
        selectors.noteForm.reset();
        syncNoteMinutes();
    } catch (error) {
        console.error('Erro ao salvar nota rápida:', error);
        setNoteFeedback(error.message || 'Não foi possível salvar sua nota.', 'error');
    }
}

function setNoteFeedback(message, status) {
    if (!selectors.noteFeedback) {
        return;
    }
    selectors.noteFeedback.textContent = message || '';
    selectors.noteFeedback.dataset.status = status || '';
}

async function handleChatSubmit(event) {
    event.preventDefault();
    const current = state.subtopics[state.currentIndex];
    if (!current) {
        setChatStatus('Selecione um subtópico antes de enviar dúvidas.', 'error');
        return;
    }

    const question = selectors.chatInput.value.trim();
    if (!question) {
        setChatStatus('Digite uma pergunta para o StudyBot.', 'error');
        return;
    }

    const historySnapshot = state.chatHistory.slice(-10);

    appendChatMessage({ role: 'user', content: question });
    selectors.chatInput.value = '';
    setChatStatus('Processando sua pergunta...', 'loading');
    selectors.chatMessages.setAttribute('aria-busy', 'true');

    try {
        const payload = {
            question,
            history: historySnapshot,
            topic_id: state.topic?.id ?? null,
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

function appendChatMessage(message) {
    if (!selectors.chatTemplate || !selectors.chatMessages) {
        return;
    }

    const clone = selectors.chatTemplate.content.firstElementChild.cloneNode(true);
    const role = message.role === 'assistant' ? 'assistant' : 'user';
    clone.classList.add(`chat-message--${role}`);
    clone.querySelector('.chat-author').textContent = role === 'assistant' ? 'StudyBot' : 'Você';
    const timestamp = new Date();
    clone.querySelector('.chat-timestamp').textContent = timestamp.toLocaleTimeString([], {
        hour: '2-digit',
        minute: '2-digit',
    });
    clone.querySelector('.chat-content').textContent = message.content;

    selectors.chatMessages.appendChild(clone);
    selectors.chatMessages.scrollTop = selectors.chatMessages.scrollHeight;

    state.chatHistory.push({ role, content: message.content });
    if (state.chatHistory.length > 20) {
        state.chatHistory = state.chatHistory.slice(-20);
    }
}

function setChatStatus(message, status) {
    if (!selectors.chatStatus) {
        return;
    }
    selectors.chatStatus.textContent = message || '';
    selectors.chatStatus.dataset.status = status || '';
}

function handleEmptyTopics() {
    selectors.focusTopicTitle.textContent = 'Nenhum tópico disponível';
    selectors.focusProgress.textContent = 'Crie um curso e um tópico no dashboard para utilizar o modo foco.';
    disableStudyControls(true);
    resetChat();
    setNoteFeedback('', '');
    selectors.subtopicsList.innerHTML = '';
    const emptyItem = document.createElement('li');
    emptyItem.textContent = 'Sem tópicos cadastrados.';
    selectors.subtopicsList.appendChild(emptyItem);
}

async function apiFetch(path, options = {}, { allowEmpty = false, retryOn401 = true } = {}) {
    const tokens = loadTokens();
    if (!tokens?.access) {
        throw new Error('Sessão inválida');
    }

    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${tokens.access}`);
    headers.set('Accept', 'application/json');
    if (options.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers,
    });

    if (response.status === 401 && retryOn401) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
            throw new Error('Sessão expirada');
        }
        return apiFetch(path, options, { allowEmpty, retryOn401: false });
    }

    if (response.status === 204 && allowEmpty) {
        return null;
    }

    const data = await safeJson(response);

    if (!response.ok) {
        const detail = data?.detail || 'Erro ao carregar dados.';
        throw new Error(detail);
    }

    return data;
}

async function safeJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return null;
    }
}

function saveTokens(tokens) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

function loadTokens() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        console.warn('Não foi possível ler os tokens armazenados:', error);
        return null;
    }
}

function clearTokens() {
    localStorage.removeItem(STORAGE_KEY);
}

async function refreshAccessToken() {
    const tokens = loadTokens();
    if (!tokens?.refresh) {
        return false;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/accounts/auth/jwt/refresh/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                Accept: 'application/json',
            },
            body: JSON.stringify({ refresh: tokens.refresh }),
        });

        if (!response.ok) {
            clearTokens();
            return false;
        }

        const data = await response.json();
        saveTokens({ access: data.access, refresh: data.refresh || tokens.refresh });
        return true;
    } catch (error) {
        console.error('Falha ao atualizar token:', error);
        clearTokens();
        return false;
    }
}

function formatHumanDate(value) {
    if (!value) {
        return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    });
}
