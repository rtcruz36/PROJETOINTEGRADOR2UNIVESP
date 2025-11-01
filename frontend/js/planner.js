const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const DAYS_OF_WEEK = [
    { value: 0, label: 'Segunda-feira', short: 'Seg' },
    { value: 1, label: 'Terça-feira', short: 'Ter' },
    { value: 2, label: 'Quarta-feira', short: 'Qua' },
    { value: 3, label: 'Quinta-feira', short: 'Qui' },
    { value: 4, label: 'Sexta-feira', short: 'Sex' },
    { value: 5, label: 'Sábado', short: 'Sáb' },
    { value: 6, label: 'Domingo', short: 'Dom' },
];

const COLOR_PALETTE = [
    '#2563eb',
    '#16a34a',
    '#f97316',
    '#9333ea',
    '#dc2626',
    '#0ea5e9',
    '#facc15',
    '#14b8a6',
    '#fb7185',
];

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    weekRange: document.getElementById('planner-week-range'),
    summary: document.getElementById('planner-summary'),
    weekGrid: document.getElementById('planner-week-grid'),
    emptyState: document.getElementById('planner-empty-state'),
    feedback: document.getElementById('planner-feedback'),
    courseLegend: document.getElementById('planner-course-legend'),
    refreshButton: document.getElementById('refresh-planner'),
    openCreatePlan: document.getElementById('open-create-plan'),
    planModal: document.getElementById('plan-modal'),
    planModalTitle: document.getElementById('plan-modal-title'),
    planForm: document.getElementById('plan-form'),
    planId: document.getElementById('plan-id'),
    planCourse: document.getElementById('plan-course'),
    planDay: document.getElementById('plan-day'),
    planMinutes: document.getElementById('plan-minutes'),
    planFormError: document.getElementById('plan-form-error'),
    planSubmit: document.getElementById('submit-plan-button'),
    planCancel: document.getElementById('cancel-plan-button'),
    planClose: document.getElementById('close-plan-modal'),
    planDelete: document.getElementById('delete-plan-button'),
    dayTemplate: document.getElementById('planner-day-template'),
    cardTemplate: document.getElementById('planner-card-template'),
};

const state = {
    user: null,
    courses: [],
    courseColors: new Map(),
    week: null,
    plans: new Map(),
    draggingPlanId: null,
    feedbackTimeout: null,
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);
    selectors.refreshButton?.addEventListener('click', () => reloadPlanner({ showStatus: true }));
    selectors.openCreatePlan?.addEventListener('click', () => openCreatePlanModal());

    selectors.planCancel?.addEventListener('click', closePlanModal);
    selectors.planClose?.addEventListener('click', closePlanModal);
    selectors.planForm?.addEventListener('submit', handlePlanFormSubmit);
    selectors.planDelete?.addEventListener('click', handlePlanDelete);

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && isPlanModalOpen()) {
            closePlanModal();
        }
    });

    populateDayOptions();
    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    reloadPlanner({ showStatus: true }).catch((error) => {
        console.error('Falha ao carregar planejador:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function reloadPlanner({ showStatus = false } = {}) {
    if (showStatus) {
        setFeedback('Atualizando planejador...', 'neutral', 0);
    }

    togglePlannerLoading(true);

    try {
        const [user, courses, week, plans] = await Promise.all([
            apiFetch('/accounts/auth/users/me/'),
            apiFetch('/learning/courses/'),
            apiFetch('/scheduling/current-week/'),
            apiFetch('/scheduling/plans/'),
        ]);

        state.user = user;
        updateGreeting(user);

        state.courses = Array.isArray(courses) ? courses : [];
        assignCourseColors(state.courses);

        state.week = normalizeWeek(week);
        const planEntries = Array.isArray(plans) ? plans : [];
        state.plans = new Map(planEntries.map((plan) => [plan.id, plan]));

        populateCourseOptions();
        renderWeek();
        renderLegend();
        renderSummary();
        hideLogin();

        if (showStatus) {
            setFeedback('Planejador atualizado!', 'success');
        } else {
            clearFeedback();
        }
    } catch (error) {
        console.error('Erro ao atualizar planejador:', error);
        setFeedback(error.message || 'Não foi possível carregar o planejador.', 'error', 0);
        throw error;
    } finally {
        togglePlannerLoading(false);
    }
}

function handleLogout() {
    clearTokens();
    showLogin();
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

        await reloadPlanner({ showStatus: true });
        hideLogin();
    } catch (error) {
        console.error('Erro de login:', error);
        selectors.loginError.textContent = error.message || 'Erro inesperado ao entrar.';
    }
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

function togglePlannerLoading(isLoading) {
    if (selectors.refreshButton) {
        selectors.refreshButton.disabled = isLoading;
    }
    if (selectors.openCreatePlan) {
        selectors.openCreatePlan.disabled = isLoading;
    }
}

function updateGreeting(user) {
    if (!user) {
        selectors.greeting.textContent = 'Olá!';
        return;
    }
    const name = user.first_name?.trim() || user.username || user.email || 'Estudante';
    selectors.greeting.textContent = `Olá, ${name}!`;
}

function assignCourseColors(courses) {
    const currentColors = new Map(state.courseColors);
    let paletteIndex = currentColors.size;

    courses.forEach((course) => {
        if (!currentColors.has(course.id)) {
            const color = COLOR_PALETTE[paletteIndex % COLOR_PALETTE.length];
            currentColors.set(course.id, color);
            paletteIndex += 1;
        }
    });

    // Remove colors for courses that no longer exist
    Array.from(currentColors.keys()).forEach((courseId) => {
        if (!courses.some((course) => course.id === courseId)) {
            currentColors.delete(courseId);
        }
    });

    state.courseColors = currentColors;
}

function normalizeWeek(week) {
    if (!week || typeof week !== 'object') {
        return null;
    }
    const normalizedDays = Array.isArray(week.days)
        ? [...week.days].sort((a, b) => a.day_of_week - b.day_of_week)
        : [];

    return {
        week_start: week.week_start,
        week_end: week.week_end,
        total_planned_minutes: week.total_planned_minutes || 0,
        total_completed_minutes: week.total_completed_minutes || 0,
        days: normalizedDays.map((day) => ({
            ...day,
            planned_sessions: Array.isArray(day.planned_sessions) ? day.planned_sessions : [],
        })),
    };
}

function renderWeek() {
    if (!selectors.weekGrid) {
        return;
    }

    selectors.weekGrid.innerHTML = '';

    if (!state.week || state.week.days.length === 0) {
        selectors.emptyState.hidden = false;
        return;
    }

    selectors.emptyState.hidden = true;

    state.week.days.forEach((day) => {
        const dayNode = renderDayColumn(day);
        selectors.weekGrid.appendChild(dayNode);
    });
}

function renderDayColumn(day) {
    const template = selectors.dayTemplate?.content;
    if (!template) {
        return document.createElement('div');
    }

    const fragment = template.cloneNode(true);
    const dayElement = fragment.querySelector('.planner-day');
    const titleElement = fragment.querySelector('.planner-day__title');
    const dateElement = fragment.querySelector('.planner-day__date');
    const minutesElement = fragment.querySelector('.planner-day__minutes');
    const dropzone = fragment.querySelector('.planner-day__dropzone');
    const addButton = fragment.querySelector('.planner-day__add');

    if (dayElement) {
        dayElement.dataset.day = String(day.day_of_week);
    }

    if (titleElement) {
        titleElement.textContent = day.day_name || getDayLabel(day.day_of_week);
    }

    if (dateElement) {
        dateElement.textContent = formatDayDate(day.date);
    }

    if (minutesElement) {
        const planned = Number.parseInt(day.planned_minutes, 10) || 0;
        const completed = Number.parseInt(day.completed_minutes, 10) || 0;
        const plannedText = `${formatMinutes(planned)} planejados`;
        const completedText = completed ? ` • ${formatMinutes(completed)} concluídos` : '';
        minutesElement.textContent = plannedText + completedText;
    }

    if (addButton) {
        addButton.addEventListener('click', () => openCreatePlanModal({ dayOfWeek: day.day_of_week }));
    }

    if (dropzone) {
        dropzone.dataset.dayOfWeek = String(day.day_of_week);
        dropzone.addEventListener('dragover', handleDropzoneDragOver);
        dropzone.addEventListener('dragenter', handleDropzoneDragEnter);
        dropzone.addEventListener('dragleave', handleDropzoneDragLeave);
        dropzone.addEventListener('drop', handleDropzoneDrop);

        const sessions = day.planned_sessions.map((session) => normalizePlanSession(session, day.day_of_week));

        if (sessions.length === 0) {
            dropzone.classList.add('is-empty');
        } else {
            dropzone.classList.remove('is-empty');
            const fragmentCards = document.createDocumentFragment();
            sessions.forEach((session) => {
                const card = createPlanCard(session);
                fragmentCards.appendChild(card);
            });
            dropzone.appendChild(fragmentCards);
        }
    }

    return fragment;
}

function normalizePlanSession(session, dayOfWeek) {
    const planId = session.plan_id ?? session.id;
    const plan = state.plans.get(planId);

    const courseId = session.course_id ?? plan?.course ?? null;
    const courseTitle = session.course_title || plan?.course_title || 'Curso';
    const minutesPlanned = session.minutes_planned ?? plan?.minutes_planned ?? 0;

    return {
        id: planId,
        courseId,
        courseTitle,
        minutesPlanned,
        dayOfWeek,
    };
}

function createPlanCard(planSession) {
    const template = selectors.cardTemplate?.content;
    if (!template) {
        return document.createElement('div');
    }

    const fragment = template.cloneNode(true);
    const card = fragment.querySelector('.planner-card');
    const colorElement = fragment.querySelector('.planner-card__color');
    const courseElement = fragment.querySelector('.planner-card__course');
    const minutesElement = fragment.querySelector('.planner-card__minutes');
    const editButton = fragment.querySelector('.planner-card__edit');

    const color = getCourseColor(planSession.courseId);

    card.dataset.planId = String(planSession.id);
    card.dataset.courseId = planSession.courseId ? String(planSession.courseId) : '';
    card.dataset.dayOfWeek = String(planSession.dayOfWeek);
    card.style.borderLeftColor = color;

    if (colorElement) {
        colorElement.style.backgroundColor = color;
        colorElement.style.color = color;
    }

    if (courseElement) {
        courseElement.textContent = planSession.courseTitle;
    }

    if (minutesElement) {
        minutesElement.textContent = formatMinutes(planSession.minutesPlanned);
    }

    card.addEventListener('dragstart', handleCardDragStart);
    card.addEventListener('dragend', handleCardDragEnd);

    if (editButton) {
        editButton.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            openEditPlanModal(planSession.id);
        });
    }

    return card;
}

function renderSummary() {
    if (!selectors.weekRange || !selectors.summary || !state.week) {
        return;
    }

    selectors.weekRange.textContent = formatWeekRange(state.week.week_start, state.week.week_end);

    const planned = Number.parseInt(state.week.total_planned_minutes, 10) || 0;
    const completed = Number.parseInt(state.week.total_completed_minutes, 10) || 0;
    const plannedText = planned ? `${formatMinutes(planned)} planejados` : 'Nenhum minuto planejado';
    const completedText = completed ? `${formatMinutes(completed)} concluídos` : 'Ainda não concluído';

    selectors.summary.textContent = `${plannedText} • ${completedText}`;
}

function renderLegend() {
    if (!selectors.courseLegend) {
        return;
    }

    selectors.courseLegend.innerHTML = '';

    const coursesInWeek = new Map();

    state.week?.days.forEach((day) => {
        day.planned_sessions.forEach((session) => {
            const courseId = session.course_id ?? state.plans.get(session.plan_id)?.course;
            if (!courseId) {
                return;
            }
            const existing = coursesInWeek.get(courseId);
            if (!existing) {
                const title = session.course_title
                    || state.plans.get(session.plan_id)?.course_title
                    || state.courses.find((course) => course.id === courseId)?.title
                    || 'Curso';
                coursesInWeek.set(courseId, title);
            }
        });
    });

    if (coursesInWeek.size === 0) {
        const item = document.createElement('li');
        item.classList.add('planner-course-legend__empty');
        item.textContent = 'Nenhum curso planejado nesta semana.';
        selectors.courseLegend.appendChild(item);
        return;
    }

    const fragment = document.createDocumentFragment();
    coursesInWeek.forEach((title, courseId) => {
        const item = document.createElement('li');
        const colorIndicator = document.createElement('span');
        colorIndicator.className = 'planner-course-legend__color';
        const color = getCourseColor(courseId);
        colorIndicator.style.backgroundColor = color;
        colorIndicator.style.color = color;

        const label = document.createElement('span');
        label.className = 'planner-course-legend__label';
        label.textContent = title;

        item.appendChild(colorIndicator);
        item.appendChild(label);
        fragment.appendChild(item);
    });

    selectors.courseLegend.appendChild(fragment);
}

function openCreatePlanModal({ dayOfWeek = null } = {}) {
    if (!selectors.planForm || !selectors.planModal) {
        return;
    }

    selectors.planForm.reset();
    selectors.planForm.dataset.mode = 'create';
    selectors.planModalTitle.textContent = 'Adicionar plano';
    selectors.planFormError.textContent = '';
    selectors.planDelete.hidden = true;
    selectors.planId.value = '';
    selectors.planMinutes.value = 60;
    selectors.planSubmit.textContent = 'Adicionar plano';

    if (typeof dayOfWeek === 'number') {
        selectors.planDay.value = String(dayOfWeek);
    }

    ensureCourseAvailability();
    selectors.planModal.hidden = false;
    document.body.classList.add('modal-open');
    selectors.planCourse?.focus();
}

function openEditPlanModal(planId) {
    if (!selectors.planForm || !selectors.planModal) {
        return;
    }

    const plan = state.plans.get(planId);
    if (!plan) {
        setFeedback('Não foi possível localizar o plano selecionado.', 'error');
        return;
    }

    selectors.planForm.dataset.mode = 'edit';
    selectors.planModalTitle.textContent = 'Editar plano';
    selectors.planFormError.textContent = '';
    selectors.planDelete.hidden = false;
    selectors.planSubmit.textContent = 'Salvar alterações';

    selectors.planId.value = plan.id;
    selectors.planCourse.value = plan.course ? String(plan.course) : '';
    selectors.planDay.value = String(plan.day_of_week);
    selectors.planMinutes.value = plan.minutes_planned;

    ensureCourseAvailability();
    selectors.planModal.hidden = false;
    document.body.classList.add('modal-open');
    selectors.planCourse?.focus();
}

function ensureCourseAvailability() {
    if (!selectors.planCourse || !selectors.planSubmit) {
        return;
    }

    if (state.courses.length === 0) {
        selectors.planCourse.disabled = true;
        selectors.planSubmit.disabled = true;
        selectors.planFormError.textContent = 'Cadastre um curso no dashboard para criar planos.';
    } else {
        selectors.planCourse.disabled = false;
        selectors.planSubmit.disabled = false;
        if (selectors.planFormError.textContent === 'Cadastre um curso no dashboard para criar planos.') {
            selectors.planFormError.textContent = '';
        }
    }
}

function closePlanModal() {
    if (!selectors.planModal) {
        return;
    }

    selectors.planModal.hidden = true;
    selectors.planFormError.textContent = '';
    document.body.classList.remove('modal-open');
}

function isPlanModalOpen() {
    return Boolean(selectors.planModal && !selectors.planModal.hidden);
}

async function handlePlanFormSubmit(event) {
    event.preventDefault();
    if (!selectors.planForm) {
        return;
    }

    selectors.planFormError.textContent = '';

    const formData = new FormData(selectors.planForm);
    const mode = selectors.planForm.dataset.mode || 'create';

    const payload = {
        course: Number.parseInt(formData.get('course'), 10),
        day_of_week: Number.parseInt(formData.get('day_of_week'), 10),
        minutes_planned: Number.parseInt(formData.get('minutes_planned'), 10),
    };

    if (!Number.isInteger(payload.course) || !Number.isInteger(payload.day_of_week) || !Number.isInteger(payload.minutes_planned)) {
        selectors.planFormError.textContent = 'Preencha todos os campos do plano.';
        return;
    }

    selectors.planSubmit.disabled = true;
    selectors.planSubmit.textContent = mode === 'edit' ? 'Salvando...' : 'Adicionando...';

    try {
        if (mode === 'edit') {
            const planId = Number.parseInt(formData.get('plan_id'), 10);
            if (!Number.isInteger(planId)) {
                throw new Error('Plano inválido');
            }
            await apiFetch(`/scheduling/plans/${planId}/`, {
                method: 'PATCH',
                body: JSON.stringify(payload),
            });
            setFeedback('Plano atualizado com sucesso.', 'success');
        } else {
            await apiFetch('/scheduling/plans/', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            setFeedback('Novo plano criado com sucesso.', 'success');
        }

        closePlanModal();
        await reloadPlanner();
    } catch (error) {
        console.error('Erro ao salvar plano:', error);
        selectors.planFormError.textContent = error.message || 'Não foi possível salvar o plano.';
        setFeedback(error.message || 'Não foi possível salvar o plano.', 'error');
    } finally {
        selectors.planSubmit.disabled = false;
        selectors.planSubmit.textContent = mode === 'edit' ? 'Salvar alterações' : 'Adicionar plano';
    }
}

async function handlePlanDelete() {
    const planId = Number.parseInt(selectors.planId?.value, 10);
    if (!Number.isInteger(planId)) {
        return;
    }

    const confirmation = window.confirm('Deseja realmente remover este plano de estudo?');
    if (!confirmation) {
        return;
    }

    selectors.planDelete.disabled = true;

    try {
        await apiFetch(`/scheduling/plans/${planId}/`, { method: 'DELETE' }, { allowEmpty: true });
        setFeedback('Plano removido.', 'success');
        closePlanModal();
        await reloadPlanner();
    } catch (error) {
        console.error('Erro ao remover plano:', error);
        selectors.planFormError.textContent = error.message || 'Não foi possível remover o plano.';
        setFeedback(error.message || 'Não foi possível remover o plano.', 'error');
    } finally {
        selectors.planDelete.disabled = false;
    }
}

function handleDropzoneDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
}

function handleDropzoneDragEnter(event) {
    event.preventDefault();
    const dropzone = event.currentTarget;
    dropzone.classList.add('is-over');
}

function handleDropzoneDragLeave(event) {
    const dropzone = event.currentTarget;
    dropzone.classList.remove('is-over');
}

async function handleDropzoneDrop(event) {
    event.preventDefault();
    const dropzone = event.currentTarget;
    dropzone.classList.remove('is-over');

    const planIdRaw = event.dataTransfer.getData('text/plain');
    const planId = planIdRaw ? Number.parseInt(planIdRaw, 10) : state.draggingPlanId;
    const dayOfWeek = Number.parseInt(dropzone.dataset.dayOfWeek, 10);

    if (!Number.isInteger(planId) || !Number.isInteger(dayOfWeek)) {
        return;
    }

    const plan = state.plans.get(planId);
    if (!plan) {
        setFeedback('Não foi possível localizar o plano selecionado.', 'error');
        return;
    }

    if (plan.day_of_week === dayOfWeek) {
        return;
    }

    try {
        setFeedback('Atualizando plano...', 'neutral', 0);
        await apiFetch(`/scheduling/plans/${planId}/`, {
            method: 'PATCH',
            body: JSON.stringify({ day_of_week: dayOfWeek }),
        });
        setFeedback('Plano movido para o novo dia.', 'success');
        await reloadPlanner();
    } catch (error) {
        console.error('Erro ao mover plano:', error);
        setFeedback(error.message || 'Não foi possível mover o plano.', 'error');
    }
}

function handleCardDragStart(event) {
    const card = event.currentTarget;
    card.classList.add('is-dragging');
    const planId = Number.parseInt(card.dataset.planId, 10);
    state.draggingPlanId = planId;

    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', String(planId));
}

function handleCardDragEnd(event) {
    event.currentTarget.classList.remove('is-dragging');
    state.draggingPlanId = null;
}

function populateDayOptions() {
    if (!selectors.planDay) {
        return;
    }

    selectors.planDay.innerHTML = '';
    DAYS_OF_WEEK.forEach((day) => {
        const option = document.createElement('option');
        option.value = String(day.value);
        option.textContent = day.label;
        selectors.planDay.appendChild(option);
    });
}

function populateCourseOptions() {
    if (!selectors.planCourse) {
        return;
    }

    const previousSelection = selectors.planCourse.value;
    selectors.planCourse.innerHTML = '';

    const fragment = document.createDocumentFragment();
    state.courses.forEach((course) => {
        const option = document.createElement('option');
        option.value = String(course.id);
        option.textContent = course.title;
        fragment.appendChild(option);
    });

    selectors.planCourse.appendChild(fragment);

    if (state.courses.some((course) => String(course.id) === previousSelection)) {
        selectors.planCourse.value = previousSelection;
    }

    ensureCourseAvailability();
}

function getCourseColor(courseId) {
    if (!courseId) {
        return '#475569';
    }
    return state.courseColors.get(courseId) || '#475569';
}

function getDayLabel(dayOfWeek) {
    const entry = DAYS_OF_WEEK.find((day) => day.value === dayOfWeek);
    return entry ? entry.label : 'Dia';
}

function formatMinutes(totalMinutes) {
    const minutes = Number.isFinite(totalMinutes) ? Math.max(totalMinutes, 0) : 0;
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;

    if (hours === 0) {
        return `${minutes} min`;
    }

    if (remainder === 0) {
        return hours === 1 ? '1h' : `${hours}h`;
    }

    return `${hours}h ${remainder}min`;
}

function formatDayDate(dateString) {
    if (!dateString) {
        return '';
    }

    const date = new Date(dateString);
    if (Number.isNaN(date.valueOf())) {
        return '';
    }

    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: 'short',
    }).format(date);
}

function formatWeekRange(start, end) {
    if (!start || !end) {
        return 'Semana atual';
    }

    const formatter = new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: 'short',
    });

    const startText = formatter.format(new Date(start));
    const endText = formatter.format(new Date(end));

    return `${startText} – ${endText}`;
}

function setFeedback(message, type = 'neutral', dismissAfter = 4000) {
    if (!selectors.feedback) {
        return;
    }

    selectors.feedback.textContent = message || '';
    selectors.feedback.classList.remove('is-error', 'is-success');

    if (type === 'error') {
        selectors.feedback.classList.add('is-error');
    } else if (type === 'success') {
        selectors.feedback.classList.add('is-success');
    }

    if (state.feedbackTimeout) {
        window.clearTimeout(state.feedbackTimeout);
        state.feedbackTimeout = null;
    }

    if (message && dismissAfter > 0) {
        state.feedbackTimeout = window.setTimeout(() => {
            clearFeedback();
        }, dismissAfter);
    }
}

function clearFeedback() {
    if (!selectors.feedback) {
        return;
    }
    selectors.feedback.textContent = '';
    selectors.feedback.classList.remove('is-error', 'is-success');
    if (state.feedbackTimeout) {
        window.clearTimeout(state.feedbackTimeout);
        state.feedbackTimeout = null;
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
