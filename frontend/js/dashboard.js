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
    courseDetailPanel: document.getElementById('course-detail-panel'),
    courseDetailEmpty: document.getElementById('course-detail-empty'),
    courseDetailContent: document.getElementById('course-detail-content'),
    courseDetailTitle: document.getElementById('course-detail-title'),
    courseDetailDescription: document.getElementById('course-detail-description'),
    courseDetailProgressFill: document.getElementById('course-detail-progress-fill'),
    courseDetailProgressSummary: document.getElementById('course-detail-progress-summary'),
    courseSelectedTopic: document.getElementById('course-selected-topic'),
    courseTopicsList: document.getElementById('course-topics-list'),
    generateScheduleButton: document.getElementById('generate-schedule-button'),
    scheduleFeedback: document.getElementById('schedule-feedback'),
    courseTabButtons: Array.from(document.querySelectorAll('[data-course-tab]')),
    courseTabPanels: Array.from(document.querySelectorAll('[data-course-panel]')),
    courseQuizzesList: document.getElementById('course-quizzes-list'),
    courseQuizzesMessage: document.getElementById('course-quizzes-message'),
    courseStatisticsContent: document.getElementById('course-statistics-content'),
};

const state = {
    chart: null,
    courseLibrary: [],
    selectedCourseId: null,
    selectedTopicId: null,
    activeCourseTab: 'overview',
    topicQuizzes: new Map(),
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

    if (selectors.generateScheduleButton) {
        selectors.generateScheduleButton.addEventListener('click', handleGenerateScheduleClick);
    }

    if (selectors.courseTabButtons?.length) {
        selectors.courseTabButtons.forEach((button) => {
            button.addEventListener('click', () => {
                activateCourseTab(button.dataset.courseTab);
            });
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

function buildSummaryStats(coursesData, attemptsData, engagement) {
    const courses = Array.isArray(coursesData?.results) ? coursesData.results : coursesData || [];
    const attempts = Array.isArray(attemptsData?.results) ? attemptsData.results : attemptsData || [];

    let totalCourses = courses.length;
    let topicsInProgress = 0;
    let totalSubtopics = 0;
    let completedSubtopics = 0;

    courses.forEach((course) => {
        const topics = course.topics || [];
        topics.forEach((topic) => {
            const subtopics = topic.subtopics || [];
            const completed = subtopics.filter((sub) => sub.is_completed).length;
            if (subtopics.length > 0 && completed < subtopics.length) {
                topicsInProgress += 1;
            }
            totalSubtopics += subtopics.length;
            completedSubtopics += completed;
        });
    });

    const percentage = totalSubtopics === 0 ? 0 : Math.round((completedSubtopics / totalSubtopics) * 100);
    const studyTotal = calculateStudyTotalMinutes(engagement);

    return {
        totalCourses,
        topicsInProgress,
        quizzesCompleted: attempts.length,
        studyTotal,
        streak: {
            current: engagement?.current_streak || 0,
            best: engagement?.best_streak || 0,
        },
        progress: {
            total: totalSubtopics,
            completed: completedSubtopics,
            percentage,
        },
    };
}

function calculateStudyTotalMinutes(engagement) {
    const total = engagement?.total_minutes_last_7_days;
    return typeof total === 'number' && !Number.isNaN(total) ? total : 0;
}

function buildStudySeries(logsData) {
    const logs = Array.isArray(logsData?.results) ? logsData.results : logsData || [];
    const today = new Date();
    const days = [];
    for (let offset = 6; offset >= 0; offset -= 1) {
        const date = new Date(today);
        date.setDate(today.getDate() - offset);
        days.push(date);
    }

    const minutesPerDay = new Map(days.map((date) => [formatIsoDate(date), 0]));

    logs.forEach((log) => {
        if (!log.date || typeof log.minutes_studied !== 'number') {
            return;
        }
        const dayKey = log.date;
        if (minutesPerDay.has(dayKey)) {
            const current = minutesPerDay.get(dayKey) ?? 0;
            minutesPerDay.set(dayKey, current + log.minutes_studied);
        }
    });

    const formatter = new Intl.DateTimeFormat('pt-BR', { weekday: 'short', day: '2-digit' });
    const labels = [];
    const values = [];

    minutesPerDay.forEach((minutes, isoDate) => {
        const date = new Date(`${isoDate}T00:00:00`);
        labels.push(capitalize(formatter.format(date)));
        values.push(minutes);
    });

    const studyTotal = Array.from(minutesPerDay.values()).reduce((acc, value) => acc + value, 0);
    selectors.studyTotal.textContent = `${studyTotal} minutos totais`;

    return { labels, values };
}

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

function formatIsoDate(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

function updateCourseLibrary(coursesData) {
    if (!selectors.courseLibraryList) {
        return;
    }

    const rawCourses = Array.isArray(coursesData?.results) ? coursesData.results : coursesData || [];
    state.courseLibrary = rawCourses.map((course) => decorateCourse(course));

    const validTopicIds = new Set();
    state.courseLibrary.forEach((course) => {
        course.topics.forEach((topic) => {
            validTopicIds.add(topic.id);
        });
    });

    state.topicQuizzes = new Map(
        Array.from(state.topicQuizzes.entries()).filter(([topicId]) => validTopicIds.has(Number(topicId))),
    );

    if (!state.courseLibrary.length) {
        state.selectedCourseId = null;
        state.selectedTopicId = null;
        updateCourseDetail(null);
        renderCourseLibrary();
        return;
    }

    if (!state.selectedCourseId || !state.courseLibrary.some((course) => course.id === state.selectedCourseId)) {
        state.selectedCourseId = state.courseLibrary[0].id;
    }

    const selectedCourse = getSelectedCourse();
    if (selectedCourse) {
        if (!state.selectedTopicId || !selectedCourse.topics.some((topic) => topic.id === state.selectedTopicId)) {
            state.selectedTopicId = selectedCourse.topics[0]?.id || null;
        }
    } else {
        state.selectedTopicId = null;
    }

    renderCourseLibrary();
    updateCourseDetail(selectedCourse || null);
}

function decorateCourse(course) {
    const topics = Array.isArray(course?.topics) ? course.topics : [];
    let totalSubtopics = 0;
    let completedSubtopics = 0;

    const decoratedTopics = topics.map((topic) => {
        const subtopics = Array.isArray(topic?.subtopics) ? topic.subtopics : [];
        const topicTotal = subtopics.length;
        const topicCompleted = subtopics.filter((item) => item?.is_completed).length;

        totalSubtopics += topicTotal;
        completedSubtopics += topicCompleted;

        return {
            ...topic,
            subtopics,
            totalSubtopics: topicTotal,
            completedSubtopics: topicCompleted,
            progressPercentage: topicTotal === 0 ? 0 : Math.round((topicCompleted / topicTotal) * 100),
        };
    });

    const percentage = totalSubtopics === 0 ? 0 : Math.round((completedSubtopics / totalSubtopics) * 100);
    const status = totalSubtopics > 0 && completedSubtopics === totalSubtopics ? 'completed' : 'in-progress';

    return {
        ...course,
        topics: decoratedTopics,
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

    let selectionChanged = false;

    if (!filteredCourses.length) {
        if (selectors.courseLibraryEmpty) {
            const message = statusValue === 'all'
                ? 'Nenhum curso cadastrado ainda. Adicione uma disciplina para começar seu plano de estudos.'
                : 'Nenhum curso encontrado para os filtros selecionados.';
            selectors.courseLibraryEmpty.textContent = message;
            selectors.courseLibraryEmpty.hidden = false;
        }
        if (state.selectedCourseId !== null || state.selectedTopicId !== null) {
            state.selectedCourseId = null;
            state.selectedTopicId = null;
            selectionChanged = true;
        }
        if (selectionChanged) {
            updateCourseDetail(null);
        }
        return;
    }

    if (selectors.courseLibraryEmpty) {
        selectors.courseLibraryEmpty.hidden = true;
    }

    if (!filteredCourses.some((course) => course.id === state.selectedCourseId)) {
        state.selectedCourseId = filteredCourses[0]?.id ?? null;
        state.selectedTopicId = filteredCourses[0]?.topics[0]?.id || null;
        selectionChanged = true;
    }

    const fragment = document.createDocumentFragment();
    filteredCourses.forEach((course) => {
        fragment.appendChild(buildCourseCard(course));
    });

    selectors.courseLibraryList.appendChild(fragment);

    if (selectionChanged) {
        updateCourseDetail(getSelectedCourse());
    }
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
    card.dataset.courseId = String(course.id);
    card.setAttribute('role', 'button');
    card.tabIndex = 0;
    if (course.id === state.selectedCourseId) {
        card.classList.add('course-card--active');
    }

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

    card.addEventListener('click', () => handleCourseSelection(course.id));
    card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            handleCourseSelection(course.id);
        }
    });

    return card;
}

function handleCourseSelection(courseId) {
    if (state.selectedCourseId === courseId) {
        return;
    }
    state.selectedCourseId = courseId;

    const course = getSelectedCourse();
    if (!course) {
        state.selectedTopicId = null;
        updateCourseDetail(null);
        renderCourseLibrary();
        return;
    }

    if (!course.topics.some((topic) => topic.id === state.selectedTopicId)) {
        state.selectedTopicId = course.topics[0]?.id || null;
    }

    resetScheduleFeedback();
    updateCourseDetail(course);
    renderCourseLibrary();
}

function getSelectedCourse() {
    if (!state.selectedCourseId) {
        return null;
    }
    return state.courseLibrary.find((course) => course.id === state.selectedCourseId) || null;
}

function getSelectedTopic(course = getSelectedCourse()) {
    if (!course) {
        return null;
    }
    return course.topics.find((topic) => topic.id === state.selectedTopicId) || null;
}

function updateCourseDetail(course) {
    if (!selectors.courseDetailPanel) {
        return;
    }

    resetScheduleFeedback();

    if (!course) {
        if (selectors.courseDetailEmpty) {
            selectors.courseDetailEmpty.hidden = false;
        }
        if (selectors.courseDetailContent) {
            selectors.courseDetailContent.hidden = true;
        }
        if (selectors.courseDetailTitle) {
            selectors.courseDetailTitle.textContent = 'Selecione um curso';
        }
        if (selectors.courseDetailDescription) {
            selectors.courseDetailDescription.textContent =
                'Escolha uma disciplina na biblioteca para visualizar os tópicos e gerar um cronograma.';
        }
        renderCourseTopics(null);
        renderCourseQuizzes(null);
        renderCourseStatistics(null);
        activateCourseTab('overview');
        return;
    }

    if (selectors.courseDetailEmpty) {
        selectors.courseDetailEmpty.hidden = true;
    }
    if (selectors.courseDetailContent) {
        selectors.courseDetailContent.hidden = false;
    }

    if (selectors.courseDetailTitle) {
        selectors.courseDetailTitle.textContent = course.title;
    }
    if (selectors.courseDetailDescription) {
        selectors.courseDetailDescription.textContent = course.description
            ? course.description
            : 'Este curso ainda não possui uma descrição cadastrada.';
    }

    if (selectors.courseDetailProgressFill) {
        const progressValue = Math.max(0, Math.min(Number(course.progressPercentage) || 0, 100));
        selectors.courseDetailProgressFill.style.width = `${progressValue}%`;
    }
    if (selectors.courseDetailProgressSummary) {
        const total = course.totalSubtopics || 0;
        selectors.courseDetailProgressSummary.textContent = `${course.completedSubtopics} de ${total} subtópicos concluídos`;
    }

    renderCourseTopics(course);
    renderCourseQuizzes(state.selectedTopicId);
    renderCourseStatistics(course);
    activateCourseTab(state.activeCourseTab);
}

function renderCourseTopics(course) {
    if (!selectors.courseTopicsList || !selectors.courseSelectedTopic) {
        return;
    }

    selectors.courseTopicsList.innerHTML = '';

    if (!course) {
        selectors.courseSelectedTopic.textContent = 'Nenhum tópico selecionado';
        if (selectors.generateScheduleButton) {
            selectors.generateScheduleButton.disabled = true;
        }
        return;
    }

    const topics = Array.isArray(course.topics) ? [...course.topics] : [];
    topics.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));

    if (!topics.length) {
        selectors.courseSelectedTopic.textContent = 'Nenhum tópico disponível';
        if (selectors.generateScheduleButton) {
            selectors.generateScheduleButton.disabled = true;
        }
        const emptyMessage = document.createElement('p');
        emptyMessage.className = 'course-placeholder';
        emptyMessage.textContent = 'Cadastre tópicos para acompanhar o progresso desta disciplina.';
        selectors.courseTopicsList.appendChild(emptyMessage);
        return;
    }

    const fragment = document.createDocumentFragment();

    topics.forEach((topic) => {
        const container = document.createElement('article');
        container.className = 'course-topic';
        if (topic.id === state.selectedTopicId) {
            container.classList.add('course-topic--active');
        }

        const headerButton = document.createElement('button');
        headerButton.type = 'button';
        headerButton.className = 'course-topic-header';
        headerButton.addEventListener('click', () => handleTopicSelection(topic.id));

        const info = document.createElement('div');
        const title = document.createElement('h3');
        title.textContent = topic.title;
        info.appendChild(title);

        const summary = document.createElement('span');
        summary.textContent = topic.totalSubtopics
            ? `${topic.completedSubtopics} de ${topic.totalSubtopics} subtópicos concluídos`
            : 'Nenhum subtópico cadastrado';
        info.appendChild(summary);

        if (topic.suggested_study_plan) {
            const suggestion = document.createElement('span');
            suggestion.textContent = topic.suggested_study_plan;
            info.appendChild(suggestion);
        }

        const meta = document.createElement('div');
        meta.className = 'course-topic-meta';
        const percentage = document.createElement('strong');
        percentage.textContent = `${topic.progressPercentage}%`;
        meta.appendChild(percentage);
        const label = document.createElement('span');
        label.textContent = 'Concluído';
        meta.appendChild(label);

        headerButton.appendChild(info);
        headerButton.appendChild(meta);
        container.appendChild(headerButton);

        const subtopicsList = document.createElement('ul');
        subtopicsList.className = 'course-subtopics';

        if (!topic.subtopics.length) {
            const emptyItem = document.createElement('li');
            emptyItem.className = 'course-placeholder';
            emptyItem.textContent = 'Nenhum subtópico cadastrado para este tópico.';
            subtopicsList.appendChild(emptyItem);
        } else {
            topic.subtopics.forEach((subtopic) => {
                const item = document.createElement('li');
                item.className = 'course-subtopic';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = Boolean(subtopic.is_completed);
                checkbox.disabled = true;
                const checkboxId = `topic-${topic.id}-subtopic-${subtopic.id}`;
                checkbox.id = checkboxId;
                item.appendChild(checkbox);

                const labelNode = document.createElement('label');
                labelNode.setAttribute('for', checkboxId);
                labelNode.textContent = subtopic.title;

                if (subtopic.details) {
                    const details = document.createElement('span');
                    details.textContent = subtopic.details;
                    labelNode.appendChild(details);
                }

                item.appendChild(labelNode);

                const actions = document.createElement('div');
                actions.className = 'course-subtopic-actions';
                const focusLink = document.createElement('a');
                focusLink.className = 'ghost-button ghost-button--small';
                focusLink.href = `study.html?topicId=${topic.id}&subtopicId=${subtopic.id}`;
                focusLink.textContent = 'Estudar';
                actions.appendChild(focusLink);
                item.appendChild(actions);

                subtopicsList.appendChild(item);
            });
        }

        container.appendChild(subtopicsList);
        fragment.appendChild(container);
    });

    selectors.courseTopicsList.appendChild(fragment);

    const selectedTopic = topics.find((topic) => topic.id === state.selectedTopicId) || topics[0];
    selectors.courseSelectedTopic.textContent = selectedTopic
        ? `Cronograma focado no tópico: ${selectedTopic.title}`
        : 'Nenhum tópico selecionado';

    if (selectors.generateScheduleButton) {
        selectors.generateScheduleButton.disabled = !selectedTopic || !selectedTopic.totalSubtopics;
    }
}

function handleTopicSelection(topicId) {
    if (state.selectedTopicId === topicId) {
        return;
    }
    state.selectedTopicId = topicId;
    const course = getSelectedCourse();
    renderCourseTopics(course);
    resetScheduleFeedback();

    if (state.activeCourseTab === 'quizzes') {
        ensureTopicQuizzes(topicId);
    } else {
        renderCourseQuizzes(topicId);
    }
}

function activateCourseTab(tabName = 'overview') {
    if (!selectors.courseTabButtons?.length || !selectors.courseTabPanels?.length) {
        return;
    }

    const normalized = ['overview', 'quizzes', 'statistics'].includes(tabName) ? tabName : 'overview';
    state.activeCourseTab = normalized;

    selectors.courseTabButtons.forEach((button) => {
        const isActive = button.dataset.courseTab === normalized;
        button.classList.toggle('is-active', isActive);
        button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });

    selectors.courseTabPanels.forEach((panel) => {
        const isActive = panel.dataset.coursePanel === normalized;
        panel.classList.toggle('is-active', isActive);
        panel.hidden = !isActive;
    });

    if (normalized === 'quizzes') {
        renderCourseQuizzes(state.selectedTopicId);
        ensureTopicQuizzes(state.selectedTopicId);
    } else if (normalized === 'statistics') {
        renderCourseStatistics(getSelectedCourse());
    } else if (normalized === 'overview') {
        renderCourseTopics(getSelectedCourse());
    }
}

function renderCourseQuizzes(topicId) {
    if (!selectors.courseQuizzesList || !selectors.courseQuizzesMessage) {
        return;
    }

    selectors.courseQuizzesList.innerHTML = '';
    selectors.courseQuizzesMessage.dataset.status = '';

    const course = getSelectedCourse();
    if (!course) {
        selectors.courseQuizzesMessage.textContent = 'Selecione um curso para visualizar os quizzes disponíveis.';
        return;
    }
    const topic = course?.topics.find((item) => item.id === topicId) || null;

    if (!topic) {
        selectors.courseQuizzesMessage.textContent = 'Selecione um tópico para ver os quizzes relacionados.';
        return;
    }

    const normalizedId = Number(topic.id);
    const cacheEntry = state.topicQuizzes.get(normalizedId);

    if (!cacheEntry) {
        selectors.courseQuizzesMessage.textContent = 'Selecione a aba Quizzes para carregar as atividades deste tópico.';
        return;
    }

    if (cacheEntry.status === 'loading') {
        selectors.courseQuizzesMessage.dataset.status = 'loading';
        selectors.courseQuizzesMessage.textContent = 'Carregando quizzes...';
        return;
    }

    if (cacheEntry.status === 'error') {
        selectors.courseQuizzesMessage.dataset.status = 'error';
        selectors.courseQuizzesMessage.textContent = cacheEntry.message || 'Não foi possível carregar os quizzes.';
        return;
    }

    const quizzes = Array.isArray(cacheEntry.items) ? cacheEntry.items : [];

    if (!quizzes.length) {
        selectors.courseQuizzesMessage.textContent = 'Nenhum quiz cadastrado para este tópico ainda.';
        return;
    }

    selectors.courseQuizzesMessage.textContent = `Quizzes disponíveis para ${topic.title}:`;

    const fragment = document.createDocumentFragment();
    quizzes.forEach((quiz) => {
        const item = document.createElement('li');
        item.className = 'course-quiz-item';

        const title = document.createElement('h4');
        title.textContent = quiz.title || 'Quiz sem título';
        item.appendChild(title);

        if (quiz.description) {
            const description = document.createElement('p');
            description.textContent = quiz.description;
            item.appendChild(description);
        }

        const metadata = document.createElement('p');
        metadata.className = 'course-placeholder';
        const totalQuestions = quiz.total_questions ?? quiz.questions?.length ?? 0;
        const createdAt = formatHumanDate(quiz.created_at);
        metadata.textContent = createdAt
            ? `${totalQuestions} pergunta(s) • Criado em ${createdAt}`
            : `${totalQuestions} pergunta(s)`;
        item.appendChild(metadata);

        fragment.appendChild(item);
    });

    selectors.courseQuizzesList.appendChild(fragment);
}

async function ensureTopicQuizzes(topicId) {
    const normalizedId = Number(topicId);
    if (!normalizedId) {
        renderCourseQuizzes(null);
        return;
    }

    const existing = state.topicQuizzes.get(normalizedId);
    if (existing && existing.status === 'loaded') {
        renderCourseQuizzes(normalizedId);
        return;
    }

    state.topicQuizzes.set(normalizedId, { status: 'loading' });
    renderCourseQuizzes(normalizedId);

    try {
        const data = await apiFetch(`/assessment/quizzes/?topic=${encodeURIComponent(normalizedId)}`);
        const items = Array.isArray(data?.results) ? data.results : data || [];
        state.topicQuizzes.set(normalizedId, { status: 'loaded', items });
        renderCourseQuizzes(normalizedId);
    } catch (error) {
        console.error('Erro ao carregar quizzes do tópico:', error);
        state.topicQuizzes.set(normalizedId, {
            status: 'error',
            message: error.message || 'Não foi possível carregar os quizzes deste tópico.',
        });
        renderCourseQuizzes(normalizedId);
    }
}

function renderCourseStatistics(course) {
    if (!selectors.courseStatisticsContent) {
        return;
    }

    selectors.courseStatisticsContent.innerHTML = '';

    if (!course) {
        return;
    }

    const topics = Array.isArray(course.topics) ? course.topics : [];
    const completedTopics = topics.filter((topic) => topic.totalSubtopics > 0 && topic.totalSubtopics === topic.completedSubtopics).length;
    const activeTopics = Math.max(topics.length - completedTopics, 0);
    const completionRate = course.totalSubtopics
        ? Math.round((course.completedSubtopics / course.totalSubtopics) * 100)
        : 0;

    const stats = [
        { label: 'Tópicos cadastrados', value: topics.length },
        { label: 'Tópicos concluídos', value: completedTopics },
        { label: 'Subtópicos concluídos', value: course.completedSubtopics },
        { label: 'Taxa de conclusão', value: `${completionRate}%` },
    ];

    if (activeTopics > 0) {
        stats.push({ label: 'Tópicos em andamento', value: activeTopics });
    }

    const fragment = document.createDocumentFragment();
    stats.forEach((stat) => {
        const card = document.createElement('div');
        card.className = 'course-stat-card';
        const value = document.createElement('strong');
        value.textContent = String(stat.value);
        const label = document.createElement('span');
        label.textContent = stat.label;
        card.appendChild(value);
        card.appendChild(label);
        fragment.appendChild(card);
    });

    selectors.courseStatisticsContent.appendChild(fragment);
}

async function handleGenerateScheduleClick() {
    const course = getSelectedCourse();
    if (!course) {
        setScheduleFeedback('error', 'Selecione um curso para gerar o cronograma.');
        return;
    }

    const topic = getSelectedTopic(course);
    if (!topic) {
        setScheduleFeedback('error', 'Selecione um tópico para gerar o cronograma.');
        return;
    }

    if (!topic.totalSubtopics) {
        setScheduleFeedback('error', 'Este tópico ainda não possui subtópicos suficientes para gerar um cronograma.');
        return;
    }

    const button = selectors.generateScheduleButton;
    const originalLabel = button?.textContent;
    if (button) {
        button.disabled = true;
        button.textContent = 'Gerando...';
    }

    setScheduleFeedback('loading', 'Gerando cronograma com base nas suas metas de estudo...');

    try {
        const response = await apiFetch('/scheduling/generate-schedule/', {
            method: 'POST',
            body: JSON.stringify({ topic_id: topic.id }),
        });

        const totalMinutes = response?.summary?.total_estimated_minutes ?? 0;
        const daysWithStudy = response?.summary?.days_with_study ?? 0;
        const pieces = [`Cronograma criado para ${response?.topic?.title || topic.title}.`];

        if (totalMinutes) {
            pieces.push(`${totalMinutes} minuto(s) distribuído(s) na semana.`);
        }

        if (daysWithStudy) {
            pieces.push(`${daysWithStudy} dia(s) com sessões planejadas.`);
        }

        setScheduleFeedback('success', pieces.join(' '));
    } catch (error) {
        console.error('Erro ao gerar cronograma:', error);
        setScheduleFeedback('error', error.message || 'Não foi possível gerar o cronograma.');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalLabel || 'Gerar cronograma de estudo';
        }
    }
}

function resetScheduleFeedback() {
    setScheduleFeedback('', '');
}

function setScheduleFeedback(status, message) {
    if (!selectors.scheduleFeedback) {
        return;
    }
    if (status) {
        selectors.scheduleFeedback.dataset.status = status;
    } else {
        delete selectors.scheduleFeedback.dataset.status;
    }
    selectors.scheduleFeedback.textContent = message || '';
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
