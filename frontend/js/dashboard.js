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
};

const state = {
    chart: null,
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton.addEventListener('click', handleLogout);
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
