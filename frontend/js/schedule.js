const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';
const SCHEDULE_STORAGE_KEY = 'pi2-generated-schedule';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    scheduleTopicTitle: document.getElementById('schedule-topic-title'),
    scheduleCourseTitle: document.getElementById('schedule-course-title'),
    scheduleGeneratedAt: document.getElementById('schedule-generated-at'),
    scheduleFeedback: document.getElementById('schedule-feedback'),
    regenerateButton: document.getElementById('regenerate-schedule'),
    acceptButton: document.getElementById('accept-schedule'),
    summaryTotalMinutes: document.getElementById('summary-total-minutes'),
    summaryTotalSessions: document.getElementById('summary-total-sessions'),
    summaryDaysWithStudy: document.getElementById('summary-days-with-study'),
    summaryAverageSession: document.getElementById('summary-average-session'),
    weekGrid: document.getElementById('schedule-week-grid'),
    emptyState: document.getElementById('schedule-empty-state'),
    dayTemplate: document.getElementById('schedule-day-template'),
    sessionTemplate: document.getElementById('schedule-session-template'),
};

const state = {
    user: null,
    schedule: null,
    scheduleMeta: {
        topicId: null,
        savedAt: null,
        acceptedAt: null,
    },
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);
    selectors.regenerateButton?.addEventListener('click', handleRegenerateSchedule);
    selectors.acceptButton?.addEventListener('click', handleAcceptSchedule);

    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    initializeApp().catch((error) => {
        console.error('Falha ao carregar cronograma:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function initializeApp() {
    const [user] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
    ]);

    state.user = user;
    updateGreeting(user);

    await initializeSchedule();
    hideLogin();
}

async function initializeSchedule() {
    const stored = readStoredSchedule();
    if (stored?.schedule) {
        state.schedule = stored.schedule;
        state.scheduleMeta = {
            topicId: stored.topicId ?? stored.schedule?.topic?.id ?? null,
            savedAt: stored.savedAt ?? null,
            acceptedAt: stored.acceptedAt ?? null,
        };
        renderSchedule();
        return;
    }

    const topicIdFromUrl = getTopicIdFromUrl();
    if (topicIdFromUrl) {
        await regenerateScheduleForTopic(topicIdFromUrl, { resetAcceptance: true, announce: false });
        return;
    }

    renderSchedule();
    setScheduleFeedback('info', 'Gere um cronograma a partir do dashboard para visualizar os detalhes aqui.');
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

        await initializeApp();
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

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }

    const name = user?.first_name || user?.username || 'Olá!';
    selectors.greeting.textContent = `Olá, ${name}!`;
}

function renderSchedule() {
    const schedule = state.schedule;
    if (!schedule) {
        if (selectors.scheduleTopicTitle) {
            selectors.scheduleTopicTitle.textContent = 'Nenhum cronograma disponível';
        }
        if (selectors.scheduleCourseTitle) {
            selectors.scheduleCourseTitle.textContent = 'Gere um cronograma com a IA para visualizar aqui.';
        }
        if (selectors.scheduleGeneratedAt) {
            selectors.scheduleGeneratedAt.textContent = '';
        }
        resetSummary();
        clearWeekGrid();
        toggleEmptyState(true);
        syncAcceptanceState();
        return;
    }

    if (selectors.scheduleTopicTitle) {
        selectors.scheduleTopicTitle.textContent = schedule.topic?.title || 'Cronograma gerado pela IA';
    }
    if (selectors.scheduleCourseTitle) {
        selectors.scheduleCourseTitle.textContent = schedule.topic?.course_title
            ? `Disciplina: ${schedule.topic.course_title}`
            : '';
    }

    updateGeneratedAt();
    renderSummary(schedule);
    renderTimeline(schedule);
    toggleEmptyState(false);
    syncAcceptanceState();
}

function resetSummary() {
    setSummaryValue(selectors.summaryTotalMinutes, '--');
    setSummaryValue(selectors.summaryTotalSessions, '--');
    setSummaryValue(selectors.summaryDaysWithStudy, '--');
    setSummaryValue(selectors.summaryAverageSession, '--');
}

function renderSummary(schedule) {
    const weeklyPlan = Array.isArray(schedule?.weekly_plan) ? schedule.weekly_plan : [];
    const summary = schedule?.summary ?? {};

    const totalMinutes = typeof summary.total_estimated_minutes === 'number'
        ? summary.total_estimated_minutes
        : weeklyPlan.reduce((acc, day) => acc + Number(day.allocated_minutes || 0), 0);

    const totalSessions = weeklyPlan.reduce((acc, day) => {
        const sessions = Array.isArray(day.sessions) ? day.sessions : [];
        return acc + sessions.length;
    }, 0);

    const daysWithStudy = typeof summary.days_with_study === 'number'
        ? summary.days_with_study
        : weeklyPlan.filter((day) => Array.isArray(day.sessions) && day.sessions.length > 0).length;

    const averageSession = totalSessions ? Math.round(totalMinutes / totalSessions) : 0;

    setSummaryValue(selectors.summaryTotalMinutes, totalMinutes);
    setSummaryValue(selectors.summaryTotalSessions, totalSessions);
    setSummaryValue(selectors.summaryDaysWithStudy, daysWithStudy);
    setSummaryValue(selectors.summaryAverageSession, totalSessions ? averageSession : '--');
}

function renderTimeline(schedule) {
    if (!selectors.weekGrid) {
        return;
    }

    clearWeekGrid();

    const weeklyPlan = Array.isArray(schedule?.weekly_plan) ? [...schedule.weekly_plan] : [];
    if (!weeklyPlan.length) {
        toggleEmptyState(true);
        return;
    }

    weeklyPlan.sort((a, b) => (a.day_of_week ?? 0) - (b.day_of_week ?? 0));

    const fragment = document.createDocumentFragment();

    weeklyPlan.forEach((day) => {
        const dayElement = createDayElement(day);
        fragment.appendChild(dayElement);
    });

    selectors.weekGrid.appendChild(fragment);
}

function createDayElement(day) {
    const template = selectors.dayTemplate?.content?.firstElementChild;
    const element = template ? template.cloneNode(true) : document.createElement('article');

    if (!template) {
        element.className = 'schedule-day';
        const header = document.createElement('header');
        header.className = 'schedule-day__header';
        header.innerHTML = '<div><h3 class="schedule-day__title"></h3><p class="schedule-day__date"></p></div><span class="schedule-day__minutes"></span>';
        element.appendChild(header);
        element.appendChild(Object.assign(document.createElement('ol'), { className: 'schedule-day__sessions' }));
    }

    const titleEl = element.querySelector('.schedule-day__title');
    const dateEl = element.querySelector('.schedule-day__date');
    const minutesEl = element.querySelector('.schedule-day__minutes');
    const sessionsList = element.querySelector('.schedule-day__sessions');

    if (titleEl) {
        titleEl.textContent = day.day_name || 'Dia';
    }

    if (dateEl) {
        const date = computeUpcomingDate(day.day_of_week);
        dateEl.textContent = date ? formatLongDate(date) : '';
    }

    if (minutesEl) {
        const minutes = Number(day.allocated_minutes || 0);
        minutesEl.textContent = minutes ? `${minutes} min` : 'Sem estudo';
    }

    if (sessionsList) {
        sessionsList.innerHTML = '';
        const sessions = Array.isArray(day.sessions) ? day.sessions : [];
        if (!sessions.length) {
            const empty = document.createElement('li');
            empty.className = 'schedule-day__empty';
            empty.textContent = 'Nenhuma sessão planejada para este dia.';
            sessionsList.appendChild(empty);
        } else {
            sessions.forEach((session, index) => {
                const sessionEl = createSessionElement(session, index + 1, day.day_name);
                sessionsList.appendChild(sessionEl);
            });
        }
    }

    return element;
}

function createSessionElement(session, index, dayName) {
    const template = selectors.sessionTemplate?.content?.firstElementChild;
    const element = template ? template.cloneNode(true) : document.createElement('li');

    if (!template) {
        element.className = 'schedule-session';
        const header = document.createElement('header');
        header.className = 'schedule-session__header';
        const title = document.createElement('strong');
        title.className = 'schedule-session__title';
        const time = document.createElement('span');
        time.className = 'schedule-session__time';
        header.appendChild(title);
        header.appendChild(time);
        element.appendChild(header);
        const difficulty = document.createElement('p');
        difficulty.className = 'schedule-session__difficulty';
        element.appendChild(difficulty);
    }

    const titleEl = element.querySelector('.schedule-session__title');
    const timeEl = element.querySelector('.schedule-session__time');
    const difficultyEl = element.querySelector('.schedule-session__difficulty');

    if (titleEl) {
        const subtopic = session?.subtopic || `Sessão ${index}`;
        titleEl.textContent = subtopic;
    }

    if (timeEl) {
        const minutes = Number(session?.estimated_time || 0);
        timeEl.textContent = minutes ? `${minutes} min` : 'Tempo não informado';
    }

    if (difficultyEl) {
        const difficulty = normalizeDifficulty(session?.difficulty);
        difficultyEl.textContent = difficulty ? `Dificuldade: ${difficulty}` : 'Dificuldade não informada';
        const suffix = difficultyClassSuffix(difficulty);
        difficultyEl.className = 'schedule-session__difficulty';
        if (suffix) {
            difficultyEl.classList.add(`schedule-session__difficulty--${suffix}`);
        }
    }

    element.dataset.subtopic = session?.subtopic || '';
    element.dataset.dayName = dayName || '';

    return element;
}

function normalizeDifficulty(value) {
    if (!value) {
        return '';
    }
    const normalized = value.toString().trim().toLowerCase();
    if (normalized.includes('fácil') || normalized.includes('facil')) {
        return 'Fácil';
    }
    if (normalized.includes('médio') || normalized.includes('medio')) {
        return 'Médio';
    }
    if (normalized.includes('difícil') || normalized.includes('dificil')) {
        return 'Difícil';
    }
    return value;
}

function difficultyClassSuffix(label) {
    if (!label) {
        return '';
    }
    const normalized = label
        .toString()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .toLowerCase();

    if (normalized.includes('facil')) {
        return 'facil';
    }
    if (normalized.includes('medio')) {
        return 'medio';
    }
    if (normalized.includes('dificil')) {
        return 'dificil';
    }
    return '';
}

function clearWeekGrid() {
    if (selectors.weekGrid) {
        selectors.weekGrid.innerHTML = '';
    }
}

function toggleEmptyState(shouldShow) {
    if (!selectors.emptyState) {
        return;
    }
    selectors.emptyState.hidden = !shouldShow;
}

function setSummaryValue(element, value) {
    if (!element) {
        return;
    }
    element.textContent = value === undefined || value === null || value === '' ? '--' : String(value);
}

function setScheduleFeedback(status, message) {
    if (!selectors.scheduleFeedback) {
        return;
    }

    selectors.scheduleFeedback.hidden = !message;
    if (message) {
        selectors.scheduleFeedback.dataset.status = status || 'info';
        selectors.scheduleFeedback.textContent = message;
    } else {
        delete selectors.scheduleFeedback.dataset.status;
        selectors.scheduleFeedback.textContent = '';
    }
}

function updateGeneratedAt() {
    if (!selectors.scheduleGeneratedAt) {
        return;
    }

    const savedAt = state.scheduleMeta?.savedAt;
    const acceptedAt = state.scheduleMeta?.acceptedAt;

    const pieces = [];
    if (savedAt) {
        const savedDate = parseDate(savedAt);
        if (savedDate) {
            pieces.push(`Cronograma gerado em ${formatDateTime(savedDate)}`);
        }
    }
    if (acceptedAt) {
        const acceptedDate = parseDate(acceptedAt);
        if (acceptedDate) {
            pieces.push(`Aceito em ${formatDateTime(acceptedDate)}`);
        }
    }

    selectors.scheduleGeneratedAt.textContent = pieces.join(' · ');
}

function syncAcceptanceState() {
    const button = selectors.acceptButton;
    if (!button) {
        return;
    }

    const hasSchedule = Boolean(state.schedule);
    const hasSessions = hasSchedule && getScheduleSessions(state.schedule).length > 0;
    const accepted = Boolean(state.scheduleMeta?.acceptedAt);

    if (accepted) {
        button.disabled = true;
        button.textContent = 'Cronograma aceito';
    } else {
        button.disabled = !hasSessions;
        button.textContent = 'Aceitar cronograma';
    }
}

function getScheduleSessions(schedule) {
    const weeklyPlan = Array.isArray(schedule?.weekly_plan) ? schedule.weekly_plan : [];
    return weeklyPlan.flatMap((day) => (Array.isArray(day.sessions) ? day.sessions : []));
}

async function handleRegenerateSchedule() {
    const topicId = state.schedule?.topic?.id || state.scheduleMeta?.topicId || getTopicIdFromUrl();
    if (!topicId) {
        setScheduleFeedback('info', 'Selecione um tópico no dashboard para gerar o cronograma.');
        return;
    }

    await regenerateScheduleForTopic(topicId, { resetAcceptance: true, announce: true });
}

async function regenerateScheduleForTopic(topicId, { resetAcceptance = false, announce = true } = {}) {
    const button = selectors.regenerateButton;
    const originalLabel = button?.textContent;

    if (button) {
        button.disabled = true;
        button.textContent = 'Gerando...';
    }

    setScheduleFeedback('loading', 'Gerando cronograma com base nas suas metas de estudo...');

    try {
        const response = await apiFetch('/scheduling/generate-schedule/', {
            method: 'POST',
            body: JSON.stringify({ topic_id: Number(topicId) }),
        });

        const savedAt = new Date().toISOString();
        state.schedule = response;
        state.scheduleMeta = {
            topicId: response?.topic?.id ?? Number(topicId) ?? null,
            savedAt,
            acceptedAt: resetAcceptance ? null : state.scheduleMeta?.acceptedAt ?? null,
        };
        persistScheduleState();
        renderSchedule();

        if (announce) {
            setScheduleFeedback('success', 'Novo cronograma gerado com sucesso.');
        } else {
            setScheduleFeedback('', '');
        }
    } catch (error) {
        console.error('Erro ao gerar cronograma:', error);
        setScheduleFeedback('error', error.message || 'Não foi possível gerar o cronograma.');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalLabel || 'Gerar novamente';
        }
    }
}

async function handleAcceptSchedule() {
    if (!state.schedule) {
        setScheduleFeedback('info', 'Gere um cronograma antes de aceitá-lo.');
        return;
    }

    const payloads = buildStudyLogPayloads(state.schedule);
    if (!payloads.length) {
        setScheduleFeedback('info', 'Este cronograma ainda não possui sessões com duração estimada para registrar.');
        return;
    }

    const button = selectors.acceptButton;
    const originalLabel = button?.textContent;

    if (button) {
        button.disabled = true;
        button.textContent = 'Registrando...';
    }

    setScheduleFeedback('loading', 'Registrando sessões planejadas no seu histórico de estudo...');

    let createdCount = 0;

    try {
        for (const payload of payloads) {
            await apiFetch('/scheduling/logs/', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            createdCount += 1;
        }

        state.scheduleMeta.acceptedAt = new Date().toISOString();
        persistScheduleState();
        updateGeneratedAt();
        syncAcceptanceState();

        setScheduleFeedback('success', `Cronograma aceito! ${createdCount} sessão(ões) foram registradas como planejamento futuro.`);
    } catch (error) {
        console.error('Erro ao registrar cronograma:', error);
        setScheduleFeedback('error', error.message || 'Não foi possível registrar as sessões planejadas.');
        if (button) {
            button.disabled = false;
        }
    } finally {
        if (button) {
            button.textContent = state.scheduleMeta?.acceptedAt ? 'Cronograma aceito' : originalLabel || 'Aceitar cronograma';
        }
    }
}

function buildStudyLogPayloads(schedule) {
    const topicId = schedule?.topic?.id ?? null;
    const courseId = schedule?.topic?.course_id ?? null;
    if (!courseId) {
        return [];
    }

    const weeklyPlan = Array.isArray(schedule?.weekly_plan) ? schedule.weekly_plan : [];
    const payloads = [];

    weeklyPlan.forEach((day) => {
        const sessions = Array.isArray(day.sessions) ? day.sessions : [];
        if (!sessions.length) {
            return;
        }

        const targetDate = computeUpcomingDate(day.day_of_week);
        const dateIso = targetDate ? formatISODate(targetDate) : null;

        sessions.forEach((session, index) => {
            const minutes = Number(session?.estimated_time || 0);
            if (!dateIso || !minutes) {
                return;
            }

            payloads.push({
                course: courseId,
                topic: topicId,
                date: dateIso,
                minutes_studied: minutes,
                notes: buildSessionNotes(session, index + 1, day.day_name),
            });
        });
    });

    return payloads;
}

function buildSessionNotes(session, index, dayName) {
    const pieces = [];
    if (dayName) {
        pieces.push(`Dia: ${dayName}`);
    }
    const subtopic = session?.subtopic;
    if (subtopic) {
        pieces.push(`Subtópico: ${subtopic}`);
    }
    const difficulty = normalizeDifficulty(session?.difficulty);
    if (difficulty) {
        pieces.push(`Dificuldade sugerida: ${difficulty}`);
    }
    pieces.push('Registrado automaticamente pelo Assistente de Estudos.');
    return pieces.join(' | ');
}

function computeUpcomingDate(dayOfWeek) {
    if (typeof dayOfWeek !== 'number') {
        return null;
    }

    const today = new Date();
    const todayWeekday = (today.getDay() + 6) % 7; // converte para semana iniciando na segunda-feira
    const diff = (dayOfWeek - todayWeekday + 7) % 7;

    const target = new Date(today);
    target.setHours(0, 0, 0, 0);
    target.setDate(today.getDate() + diff);
    return target;
}

function formatISODate(date) {
    if (!(date instanceof Date)) {
        return '';
    }
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function formatLongDate(date) {
    if (!(date instanceof Date)) {
        return '';
    }
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
    });
}

function parseDate(value) {
    if (!value) {
        return null;
    }
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? null : date;
}

function formatDateTime(date) {
    if (!(date instanceof Date)) {
        return '';
    }
    return date.toLocaleString('pt-BR', {
        dateStyle: 'short',
        timeStyle: 'short',
    });
}

function getTopicIdFromUrl() {
    try {
        const url = new URL(window.location.href);
        const value = url.searchParams.get('topicId');
        return value ? Number(value) : null;
    } catch (error) {
        return null;
    }
}

function readStoredSchedule() {
    try {
        const raw = sessionStorage.getItem(SCHEDULE_STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        console.warn('Não foi possível ler o cronograma armazenado:', error);
        return null;
    }
}

function persistScheduleState() {
    try {
        if (!state.schedule) {
            sessionStorage.removeItem(SCHEDULE_STORAGE_KEY);
            return;
        }

        const payload = {
            schedule: state.schedule,
            topicId: state.scheduleMeta?.topicId ?? state.schedule?.topic?.id ?? null,
            savedAt: state.scheduleMeta?.savedAt ?? new Date().toISOString(),
            acceptedAt: state.scheduleMeta?.acceptedAt ?? null,
        };

        sessionStorage.setItem(SCHEDULE_STORAGE_KEY, JSON.stringify(payload));
    } catch (error) {
        console.warn('Não foi possível salvar o cronograma:', error);
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
