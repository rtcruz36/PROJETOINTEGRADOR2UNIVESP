const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    coursesCount: document.getElementById('courses-count'),
    topicsInProgress: document.getElementById('topics-in-progress'),
    quizzesCompleted: document.getElementById('quizzes-completed'),
    streakInfo: document.getElementById('streak-info'),
    studyTotal: document.getElementById('study-total'),
    chartCanvas: document.getElementById('study-time-chart'),
    sessionsList: document.getElementById('upcoming-sessions'),
    sessionTemplate: document.getElementById('session-item-template'),
    recommendedQuiz: document.getElementById('recommended-quiz'),
    progressPercentage: document.getElementById('progress-percentage'),
    progressDetail: document.getElementById('progress-detail'),
    progressRing: document.querySelector('.progress-ring__progress'),
    courseLibraryList: document.getElementById('course-library-list'),
    courseLibraryEmpty: document.getElementById('course-library-empty'),
    courseStatusFilter: document.getElementById('course-status-filter'),
    courseSortOrder: document.getElementById('course-sort-order'),
    addCourseButton: document.getElementById('add-course-button'),
    createPlanModal: document.getElementById('create-plan-modal'),
    createPlanForm: document.getElementById('create-plan-form'),
    createPlanError: document.getElementById('create-plan-error'),
    createPlanCancel: document.getElementById('cancel-create-plan'),
    createPlanSubmit: document.getElementById('submit-create-plan'),
};

const state = {
    chart: null,
    courseLibrary: [],
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton.addEventListener('click', handleLogout);

    if (selectors.courseStatusFilter) {
        selectors.courseStatusFilter.addEventListener('change', renderCourseLibrary);
    }
    if (selectors.courseSortOrder) {
        selectors.courseSortOrder.addEventListener('change', renderCourseLibrary);
    }
    if (selectors.addCourseButton) {
        selectors.addCourseButton.addEventListener('click', openCreatePlanModal);
    }
    if (selectors.createPlanCancel) {
        selectors.createPlanCancel.addEventListener('click', closeCreatePlanModal);
    }
    if (selectors.createPlanForm) {
        selectors.createPlanForm.addEventListener('submit', handleCreatePlanSubmit);
    }
    if (selectors.createPlanModal) {
        selectors.createPlanModal.addEventListener('click', (event) => {
            if (event.target === selectors.createPlanModal) {
                closeCreatePlanModal();
            }
        });
    }

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && isCreatePlanModalOpen()) {
            closeCreatePlanModal();
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

    loadDashboard().catch((error) => {
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

        await loadDashboard();
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

async function loadDashboard() {
    const [user, courses, attempts, logs, reminders, recommended, engagement] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/learning/courses/'),
        apiFetch('/assessment/attempts/'),
        apiFetch('/scheduling/logs/'),
        apiFetch('/scheduling/reminders/'),
        apiFetch('/assessment/quizzes/recommended/', {}, { allowEmpty: true }),
        apiFetch('/analytics/engagement-metrics/'),
    ]);

    updateGreeting(user);

    const summary = buildSummaryStats(courses, attempts, engagement);
    renderSummary(summary);

    const studySeries = buildStudySeries(logs);
    renderStudyChart(studySeries);

    renderSessions(reminders?.reminders || []);
    renderRecommendedQuiz(recommended);
    renderProgress(summary.progress);
    updateCourseLibrary(courses);
}

function updateGreeting(user) {
    if (!user) {
        selectors.greeting.textContent = 'Olá!';
        return;
    }
    const name = user.first_name?.trim() || user.username || user.email || 'Estudante';
    selectors.greeting.textContent = `Olá, ${name}!`;
}

function renderSummary(summary) {
    selectors.coursesCount.textContent = summary.totalCourses;
    selectors.topicsInProgress.textContent = summary.topicsInProgress;
    selectors.quizzesCompleted.textContent = summary.quizzesCompleted;
    if (summary.streak.current || summary.streak.best) {
        selectors.streakInfo.textContent = `${summary.streak.current} dia(s) • Recorde ${summary.streak.best}`;
    } else {
        selectors.streakInfo.textContent = 'Nenhum registro recente';
    }

    selectors.studyTotal.textContent = `${summary.studyTotal} minutos totais`;
}

function renderProgress(progress) {
    selectors.progressPercentage.textContent = `${progress.percentage}%`;
    selectors.progressDetail.textContent = `${progress.completed} de ${progress.total} subtópicos`;
    const circumference = 2 * Math.PI * 54;
    const offset = circumference * (1 - progress.percentage / 100);
    if (selectors.progressRing) {
        selectors.progressRing.style.strokeDashoffset = offset;
    }
}

function renderStudyChart(series) {
    if (!state.chart) {
        state.chart = new Chart(selectors.chartCanvas, {
            type: 'line',
            data: {
                labels: series.labels,
                datasets: [
                    {
                        label: 'Minutos estudados',
                        data: series.values,
                        borderColor: '#4c6ef5',
                        backgroundColor: 'rgba(76, 110, 245, 0.12)',
                        tension: 0.35,
                        fill: true,
                        pointRadius: 5,
                        pointBackgroundColor: '#4c6ef5',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Minutos',
                        },
                    },
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                },
            },
        });
    } else {
        state.chart.data.labels = series.labels;
        state.chart.data.datasets[0].data = series.values;
        state.chart.update();
    }
}

function renderSessions(reminders) {
    selectors.sessionsList.innerHTML = '';
    if (!reminders.length) {
        const emptyMessage = document.createElement('li');
        emptyMessage.className = 'session-item';
        emptyMessage.innerHTML = '<div class="session-date">—</div><div class="session-info"><p class="session-message">Nenhum compromisso programado.</p><span class="session-duration">Crie metas de estudo para receber lembretes.</span></div>';
        selectors.sessionsList.appendChild(emptyMessage);
        return;
    }

    const upcoming = reminders
        .map((reminder) => ({
            ...reminder,
            date: new Date(reminder.scheduled_date),
        }))
        .filter((item) => !Number.isNaN(item.date.valueOf()))
        .sort((a, b) => a.date - b.date)
        .slice(0, 5);

    const dateFormatter = new Intl.DateTimeFormat('pt-BR', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
    });

    upcoming.forEach((reminder) => {
        const node = selectors.sessionTemplate.content.cloneNode(true);
        node.querySelector('.session-date').textContent = dateFormatter.format(reminder.date);
        node.querySelector('.session-message').textContent = reminder.message;
        node.querySelector('.session-duration').textContent = `${reminder.minutes_planned} minutos`;
        selectors.sessionsList.appendChild(node);
    });
}

function renderRecommendedQuiz(payload) {
    const container = selectors.recommendedQuiz;
    container.innerHTML = '';

    if (!payload || payload.detail) {
        const message = payload?.detail || 'Nenhum quiz disponível no momento. Gere novos quizzes para continuar praticando!';
        const paragraph = document.createElement('p');
        paragraph.textContent = message;
        container.appendChild(paragraph);
        return;
    }

    const { quiz, message } = payload;
    if (!quiz) {
        const paragraph = document.createElement('p');
        paragraph.textContent = 'Nenhum quiz disponível no momento.';
        container.appendChild(paragraph);
        return;
    }

    const title = document.createElement('h3');
    title.textContent = quiz.title;
    container.appendChild(title);

    if (quiz.topic_title) {
        const topic = document.createElement('span');
        topic.className = 'panel-subtitle';
        topic.textContent = `Tópico: ${quiz.topic_title}`;
        container.appendChild(topic);
    }

    if (quiz.description) {
        const description = document.createElement('p');
        description.textContent = quiz.description;
        container.appendChild(description);
    }

    if (message) {
        const recommendation = document.createElement('p');
        recommendation.className = 'panel-subtitle';
        recommendation.textContent = message;
        container.appendChild(recommendation);
    }

    const link = document.createElement('a');
    link.href = `#/quizzes/${quiz.id}`;
    link.textContent = 'Ver detalhes do quiz';
    container.appendChild(link);
}

function updateCourseLibrary(coursesData) {
    if (!selectors.courseLibraryList) {
        return;
    }

    const rawCourses = Array.isArray(coursesData?.results) ? coursesData.results : coursesData || [];
    state.courseLibrary = rawCourses.map((course) => decorateCourse(course));
    renderCourseLibrary();
}

function decorateCourse(course) {
    const topics = Array.isArray(course?.topics) ? course.topics : [];
    let totalSubtopics = 0;
    let completedSubtopics = 0;

    topics.forEach((topic) => {
        const subtopics = Array.isArray(topic?.subtopics) ? topic.subtopics : [];
        totalSubtopics += subtopics.length;
        completedSubtopics += subtopics.filter((item) => item?.is_completed).length;
    });

    const percentage = totalSubtopics === 0 ? 0 : Math.round((completedSubtopics / totalSubtopics) * 100);
    const status = totalSubtopics > 0 && completedSubtopics === totalSubtopics ? 'completed' : 'in-progress';

    return {
        ...course,
        topics,
        totalSubtopics,
        completedSubtopics,
        progressPercentage: percentage,
        status,
    };
}

function renderCourseLibrary() {
    if (!selectors.courseLibraryList) {
        return;
    }

    const statusValue = selectors.courseStatusFilter?.value || 'all';
    const filteredCourses = getFilteredCourses();
    selectors.courseLibraryList.innerHTML = '';

    if (!filteredCourses.length) {
        if (selectors.courseLibraryEmpty) {
            const message = statusValue === 'all'
                ? 'Nenhum curso cadastrado ainda. Adicione uma disciplina para começar seu plano de estudos.'
                : 'Nenhum curso encontrado para os filtros selecionados.';
            selectors.courseLibraryEmpty.textContent = message;
            selectors.courseLibraryEmpty.hidden = false;
        }
        return;
    }

    if (selectors.courseLibraryEmpty) {
        selectors.courseLibraryEmpty.hidden = true;
    }

    const fragment = document.createDocumentFragment();
    filteredCourses.forEach((course) => {
        fragment.appendChild(buildCourseCard(course));
    });

    selectors.courseLibraryList.appendChild(fragment);
}

function getFilteredCourses() {
    const status = selectors.courseStatusFilter?.value || 'all';
    const sortOrder = selectors.courseSortOrder?.value || 'alphabetical';

    let courses = [...state.courseLibrary];

    if (status !== 'all') {
        courses = courses.filter((course) => course.status === status);
    }

    courses.sort((a, b) => {
        if (sortOrder === 'recent') {
            const aDate = parseDate(a.updated_at || a.created_at);
            const bDate = parseDate(b.updated_at || b.created_at);
            return bDate - aDate;
        }
        return a.title.localeCompare(b.title, 'pt-BR', { sensitivity: 'base' });
    });

    return courses;
}

function buildCourseCard(course) {
    const card = document.createElement('article');
    card.className = 'course-card';

    const header = document.createElement('div');
    header.className = 'course-card-header';

    const title = document.createElement('h3');
    title.textContent = course.title;
    header.appendChild(title);

    const statusBadge = document.createElement('span');
    statusBadge.className = `course-status ${course.status === 'completed' ? 'course-status--completed' : ''}`;
    statusBadge.textContent = course.status === 'completed' ? 'Concluído' : 'Em andamento';
    header.appendChild(statusBadge);

    card.appendChild(header);

    if (course.description) {
        const description = document.createElement('p');
        description.className = 'course-card-description';
        description.textContent = course.description;
        card.appendChild(description);
    }

    const progress = document.createElement('div');
    progress.className = 'course-progress';

    const summary = document.createElement('span');
    summary.className = 'course-progress-summary';
    summary.textContent = `${course.progressPercentage}% concluído`;
    progress.appendChild(summary);

    const bar = document.createElement('div');
    bar.className = 'course-progress-bar';
    const fill = document.createElement('div');
    fill.className = 'course-progress-fill';
    fill.style.width = `${course.progressPercentage}%`;
    bar.appendChild(fill);
    progress.appendChild(bar);

    const detail = document.createElement('span');
    detail.className = 'course-progress-detail';
    detail.textContent = course.totalSubtopics
        ? `${course.completedSubtopics} de ${course.totalSubtopics} subtópicos`
        : 'Nenhum subtópico cadastrado';
    progress.appendChild(detail);

    card.appendChild(progress);

    const metadata = document.createElement('ul');
    metadata.className = 'course-metadata';

    const topicsItem = document.createElement('li');
    topicsItem.textContent = `${course.topics.length} tópico(s)`;
    metadata.appendChild(topicsItem);

    const formattedDate = formatHumanDate(course.updated_at || course.created_at);
    if (formattedDate) {
        const updatedItem = document.createElement('li');
        updatedItem.textContent = `Atualizado em ${formattedDate}`;
        metadata.appendChild(updatedItem);
    }

    card.appendChild(metadata);

    return card;
}

function parseDate(value) {
    if (!value) {
        return 0;
    }
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? 0 : date.valueOf();
}

function formatHumanDate(value) {
    if (!value) {
        return '';
    }
    const date = new Date(value);
    if (Number.isNaN(date.valueOf())) {
        return '';
    }
    return new Intl.DateTimeFormat('pt-BR', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    }).format(date);
}

function openCreatePlanModal() {
    if (!selectors.createPlanModal) {
        return;
    }
    selectors.createPlanError.textContent = '';
    selectors.createPlanForm?.reset();
    selectors.createPlanModal.hidden = false;
    document.body.classList.add('modal-open');
    const firstInput = selectors.createPlanForm?.querySelector('input, textarea');
    firstInput?.focus();
}

function closeCreatePlanModal() {
    if (!selectors.createPlanModal) {
        return;
    }
    selectors.createPlanModal.hidden = true;
    document.body.classList.remove('modal-open');
    selectors.createPlanError.textContent = '';
}

function isCreatePlanModalOpen() {
    return Boolean(selectors.createPlanModal && !selectors.createPlanModal.hidden);
}

async function handleCreatePlanSubmit(event) {
    event.preventDefault();
    if (!selectors.createPlanForm) {
        return;
    }

    selectors.createPlanError.textContent = '';

    const formData = new FormData(selectors.createPlanForm);
    const payload = {
        course_title: (formData.get('course_title') || '').toString().trim(),
        topic_title: (formData.get('topic_title') || '').toString().trim(),
        course_description: (formData.get('course_description') || '').toString().trim(),
    };

    if (!payload.course_title || !payload.topic_title) {
        selectors.createPlanError.textContent = 'Informe o nome do curso e o primeiro tópico.';
        return;
    }

    const submitButton = selectors.createPlanSubmit;
    const originalLabel = submitButton?.textContent;
    if (submitButton) {
        submitButton.disabled = true;
        submitButton.textContent = 'Criando...';
    }

    try {
        await apiFetch('/learning/create-study-plan/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });
        await loadDashboard();
        closeCreatePlanModal();
    } catch (error) {
        console.error('Erro ao criar curso:', error);
        selectors.createPlanError.textContent = error.message || 'Não foi possível criar o curso.';
    } finally {
        if (submitButton) {
            submitButton.disabled = false;
            submitButton.textContent = originalLabel || 'Criar curso';
        }
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
