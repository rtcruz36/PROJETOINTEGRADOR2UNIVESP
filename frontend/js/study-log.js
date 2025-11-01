const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    form: document.getElementById('study-log-form'),
    submitButton: document.getElementById('study-submit'),
    formFeedback: document.getElementById('study-form-feedback'),
    courseSelect: document.getElementById('study-course'),
    topicSelect: document.getElementById('study-topic'),
    dateInput: document.getElementById('study-date'),
    minutesInput: document.getElementById('study-minutes'),
    notesInput: document.getElementById('study-notes'),
    timerStatus: document.getElementById('study-timer-status'),
    timerOutput: document.getElementById('study-timer-output'),
    timerStart: document.getElementById('study-timer-start'),
    timerPause: document.getElementById('study-timer-pause'),
    timerFinish: document.getElementById('study-timer-finish'),
    historyList: document.getElementById('study-history-list'),
    historyTemplate: document.getElementById('study-history-item-template'),
    historyEmpty: document.getElementById('study-history-empty'),
    historyFeedback: document.getElementById('study-history-feedback'),
    refreshHistory: document.getElementById('study-refresh-history'),
};

const state = {
    user: null,
    courses: [],
    logs: [],
    selectedCourseId: null,
    timer: {
        running: false,
        startedAt: null,
        elapsedSeconds: 0,
        intervalId: null,
    },
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);

    selectors.form?.addEventListener('submit', handleFormSubmit);
    selectors.courseSelect?.addEventListener('change', handleCourseChange);

    selectors.timerStart?.addEventListener('click', startTimer);
    selectors.timerPause?.addEventListener('click', pauseTimer);
    selectors.timerFinish?.addEventListener('click', finishTimer);

    selectors.refreshHistory?.addEventListener('click', () => loadHistory({ showStatus: true }));

    initializeForm();
    restoreSession();
});

function initializeForm() {
    if (selectors.dateInput) {
        selectors.dateInput.value = formatDateInput(new Date());
    }
    if (selectors.minutesInput) {
        selectors.minutesInput.value = 25;
    }
    updateTimerDisplay();
}

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadInitialData().catch((error) => {
        console.error('Falha ao carregar dados iniciais:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function loadInitialData() {
    setHistoryFeedback('Carregando dados...', 'neutral');

    const [user, courses, logs] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/learning/courses/'),
        apiFetch('/scheduling/logs/'),
    ]);

    state.user = user;
    updateGreeting(user);
    hideLogin();

    state.courses = normalizeCourses(courses);
    populateCourseOptions();

    state.logs = normalizeLogs(logs);
    renderHistory();
    clearHistoryFeedback();
}

async function loadHistory({ showStatus = false } = {}) {
    if (showStatus) {
        setHistoryFeedback('Atualizando histórico...', 'neutral');
    }

    try {
        const logs = await apiFetch('/scheduling/logs/');
        state.logs = normalizeLogs(logs);
        renderHistory();
        if (showStatus) {
            setHistoryFeedback('Histórico atualizado!', 'success');
        } else {
            clearHistoryFeedback();
        }
    } catch (error) {
        console.error('Erro ao carregar histórico:', error);
        setHistoryFeedback(error.message || 'Não foi possível carregar o histórico.', 'error');
    }
}

function normalizeCourses(courses) {
    const raw = Array.isArray(courses?.results) ? courses.results : Array.isArray(courses) ? courses : [];
    return raw.map((course) => ({
        id: Number(course.id),
        title: course.title,
        topics: Array.isArray(course.topics)
            ? course.topics.map((topic) => ({ id: Number(topic.id), title: topic.title }))
            : [],
    }));
}

function normalizeLogs(logs) {
    const raw = Array.isArray(logs?.results) ? logs.results : Array.isArray(logs) ? logs : [];
    return raw
        .map((log) => ({
            ...log,
            id: Number(log.id),
            course: Number(log.course),
            topic: log.topic !== null && log.topic !== undefined ? Number(log.topic) : null,
        }))
        .sort((a, b) => {
            const dateDiff = new Date(b.date).getTime() - new Date(a.date).getTime();
            if (dateDiff !== 0) {
                return dateDiff;
            }
            return new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime();
        });
}

function populateCourseOptions() {
    if (!selectors.courseSelect) {
        return;
    }

    const previousSelection = selectors.courseSelect.value;
    selectors.courseSelect.innerHTML = '<option value="">Selecione um curso</option>';

    const fragment = document.createDocumentFragment();
    state.courses.forEach((course) => {
        const option = document.createElement('option');
        option.value = String(course.id);
        option.textContent = course.title;
        fragment.appendChild(option);
    });

    selectors.courseSelect.appendChild(fragment);

    if (previousSelection && state.courses.some((course) => String(course.id) === previousSelection)) {
        selectors.courseSelect.value = previousSelection;
        state.selectedCourseId = Number(previousSelection);
    } else {
        state.selectedCourseId = null;
    }

    populateTopicOptions();
}

function populateTopicOptions() {
    if (!selectors.topicSelect) {
        return;
    }

    const course = state.courses.find((item) => item.id === state.selectedCourseId);

    selectors.topicSelect.innerHTML = '';
    if (!course) {
        selectors.topicSelect.disabled = true;
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Selecione um curso primeiro';
        selectors.topicSelect.appendChild(option);
        return;
    }

    selectors.topicSelect.disabled = false;
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Registrar sem tópico específico';
    selectors.topicSelect.appendChild(placeholder);

    course.topics.forEach((topic) => {
        const option = document.createElement('option');
        option.value = String(topic.id);
        option.textContent = topic.title;
        selectors.topicSelect.appendChild(option);
    });
}

function handleCourseChange(event) {
    const value = event.target.value;
    state.selectedCourseId = value ? Number(value) : null;
    populateTopicOptions();
}

async function handleFormSubmit(event) {
    event.preventDefault();

    if (!selectors.form) {
        return;
    }

    const formData = new FormData(selectors.form);
    const courseId = Number.parseInt(formData.get('course'), 10);
    const topicValue = formData.get('topic');
    const topicId = topicValue ? Number.parseInt(topicValue, 10) : null;
    const date = (formData.get('date') || '').toString();
    const minutes = Number.parseInt(formData.get('minutes_studied'), 10);
    const notes = (formData.get('notes') || '').toString().trim();

    if (!Number.isInteger(courseId)) {
        setFormFeedback('Selecione um curso válido.', 'error');
        return;
    }

    if (!date) {
        setFormFeedback('Informe a data do estudo.', 'error');
        return;
    }

    if (!Number.isFinite(minutes) || minutes < 1) {
        setFormFeedback('Informe uma quantidade válida de minutos estudados.', 'error');
        return;
    }

    try {
        toggleFormLoading(true);
        setFormFeedback('Salvando registro...', 'neutral');

        const payload = {
            course: courseId,
            topic: Number.isInteger(topicId) ? topicId : null,
            date,
            minutes_studied: minutes,
            notes: notes || null,
        };

        const created = await apiFetch('/scheduling/logs/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        state.logs.unshift(created);
        state.logs = normalizeLogs(state.logs);
        renderHistory();

        setFormFeedback('Registro salvo com sucesso!', 'success');
        focusMinutesField();
        resetFormPreservingSelections();
    } catch (error) {
        console.error('Erro ao salvar registro de estudo:', error);
        setFormFeedback(error.message || 'Não foi possível salvar o registro.', 'error');
    } finally {
        toggleFormLoading(false);
    }
}

function resetFormPreservingSelections() {
    if (!selectors.form) {
        return;
    }

    const currentCourse = selectors.courseSelect?.value || '';
    const currentTopic = selectors.topicSelect?.value || '';

    selectors.form.reset();
    initializeForm();

    if (selectors.courseSelect && currentCourse) {
        selectors.courseSelect.value = currentCourse;
        state.selectedCourseId = Number(currentCourse);
    } else {
        state.selectedCourseId = null;
    }

    populateTopicOptions();

    if (selectors.topicSelect && currentTopic && !selectors.topicSelect.disabled) {
        selectors.topicSelect.value = currentTopic;
    }
}

function focusMinutesField() {
    window.setTimeout(() => {
        selectors.minutesInput?.focus();
    }, 100);
}

function setFormFeedback(message, status) {
    if (!selectors.formFeedback) {
        return;
    }
    selectors.formFeedback.textContent = message || '';
    selectors.formFeedback.dataset.status = status || '';
}

function toggleFormLoading(isLoading) {
    if (selectors.submitButton) {
        selectors.submitButton.disabled = isLoading;
    }
    if (selectors.form) {
        selectors.form.classList.toggle('is-loading', isLoading);
    }
}

function renderHistory() {
    if (!selectors.historyList || !selectors.historyTemplate) {
        return;
    }

    selectors.historyList.innerHTML = '';

    const recent = state.logs.slice(0, 5);
    if (!recent.length) {
        if (selectors.historyEmpty) {
            selectors.historyEmpty.hidden = false;
        }
        return;
    }

    if (selectors.historyEmpty) {
        selectors.historyEmpty.hidden = true;
    }

    const fragment = document.createDocumentFragment();
    recent.forEach((log) => {
        const node = selectors.historyTemplate.content.firstElementChild.cloneNode(true);
        const courseElement = node.querySelector('.study-log-history__course');
        const topicElement = node.querySelector('.study-log-history__topic');
        const minutesElement = node.querySelector('.study-log-history__minutes');
        const dateElement = node.querySelector('.study-log-history__date');
        const notesElement = node.querySelector('.study-log-history__notes');

        const course = state.courses.find((item) => item.id === log.course);
        const topic = course?.topics.find((item) => item.id === log.topic);

        if (courseElement) {
            courseElement.textContent = course?.title || 'Curso removido';
        }

        if (topicElement) {
            topicElement.textContent = topic ? topic.title : 'Sem tópico específico';
        }

        if (minutesElement) {
            minutesElement.textContent = `${log.minutes_studied} min`;
        }

        if (dateElement) {
            dateElement.textContent = formatHumanDate(log.date);
            dateElement.dateTime = log.date;
        }

        if (notesElement) {
            notesElement.textContent = log.notes || 'Sem anotações adicionais.';
        }

        fragment.appendChild(node);
    });

    selectors.historyList.appendChild(fragment);
}

function setHistoryFeedback(message, status) {
    if (!selectors.historyFeedback) {
        return;
    }
    selectors.historyFeedback.textContent = message || '';
    selectors.historyFeedback.dataset.status = status || '';
}

function clearHistoryFeedback() {
    setHistoryFeedback('', '');
}

function startTimer() {
    if (state.timer.running) {
        return;
    }

    const now = Date.now();
    if (!state.timer.startedAt) {
        state.timer.startedAt = now - state.timer.elapsedSeconds * 1000;
    }

    state.timer.running = true;
    if (selectors.timerStatus) {
        selectors.timerStatus.textContent = 'Contagem em andamento';
    }
    state.timer.intervalId = window.setInterval(tickTimer, 1000);
    tickTimer();
}

function pauseTimer() {
    if (!state.timer.running) {
        return;
    }

    window.clearInterval(state.timer.intervalId);
    state.timer.intervalId = null;
    state.timer.elapsedSeconds = Math.max(
        state.timer.elapsedSeconds,
        Math.floor((Date.now() - (state.timer.startedAt || Date.now())) / 1000)
    );
    state.timer.startedAt = null;
    state.timer.running = false;
    if (selectors.timerStatus) {
        selectors.timerStatus.textContent = 'Timer pausado';
    }
    updateTimerDisplay();
}

function finishTimer() {
    if (state.timer.running) {
        pauseTimer();
    }

    if (state.timer.elapsedSeconds <= 0) {
        if (selectors.timerStatus) {
            selectors.timerStatus.textContent = 'Nenhum tempo contabilizado ainda.';
        }
        return;
    }

    const minutes = Math.max(1, Math.round(state.timer.elapsedSeconds / 60));
    if (selectors.minutesInput) {
        selectors.minutesInput.value = minutes;
    }
    setFormFeedback(`Tempo preenchido automaticamente: ${minutes} minuto(s).`, 'success');
    if (selectors.timerStatus) {
        selectors.timerStatus.textContent = `Sessão finalizada (${minutes} min).`;
    }

    resetTimer({ keepStatus: true });
    focusMinutesField();
}

function tickTimer() {
    if (!state.timer.running || !state.timer.startedAt) {
        return;
    }
    state.timer.elapsedSeconds = Math.floor((Date.now() - state.timer.startedAt) / 1000);
    updateTimerDisplay();
}

function resetTimer({ keepStatus = false } = {}) {
    window.clearInterval(state.timer.intervalId);
    state.timer.intervalId = null;
    state.timer.running = false;
    state.timer.startedAt = null;
    state.timer.elapsedSeconds = 0;
    updateTimerDisplay();
    if (!keepStatus && selectors.timerStatus) {
        selectors.timerStatus.textContent = 'Pronto para começar';
    }
}

function updateTimerDisplay() {
    if (!selectors.timerOutput) {
        return;
    }
    const minutes = Math.floor(state.timer.elapsedSeconds / 60);
    const seconds = state.timer.elapsedSeconds % 60;
    selectors.timerOutput.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }
    if (!user) {
        selectors.greeting.textContent = 'Olá!';
        return;
    }
    const name = user.first_name?.trim() || user.username || user.email?.split('@')[0] || 'Estudante';
    selectors.greeting.textContent = `Olá, ${name}!`;
}

function showLogin(message) {
    if (message && selectors.loginError) {
        selectors.loginError.textContent = message;
    }
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = false;
    }
}

function hideLogin() {
    if (selectors.loginError) {
        selectors.loginError.textContent = '';
    }
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = true;
    }
}

function handleLogout() {
    clearTokens();
    showLogin();
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    if (!selectors.loginForm || !selectors.loginError) {
        return;
    }

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

        await loadInitialData();
        hideLogin();
    } catch (error) {
        console.error('Erro de login:', error);
        selectors.loginError.textContent = error.message || 'Erro inesperado ao entrar.';
    }
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

function formatHumanDate(dateString) {
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) {
        return dateString;
    }
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
}

function formatDateInput(date) {
    return date.toISOString().slice(0, 10);
}
