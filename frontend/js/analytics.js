const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    correlationSummary: document.getElementById('correlation-summary'),
    correlationInterpretation: document.getElementById('correlation-interpretation'),
    progressSummary: document.getElementById('progress-summary'),
    engagementSummary: document.getElementById('engagement-summary'),
    correlationStatus: document.getElementById('correlation-status'),
    correlationCount: document.getElementById('correlation-count'),
    progressStatus: document.getElementById('progress-status'),
    progressTotal: document.getElementById('progress-total'),
    heatmapStatus: document.getElementById('heatmap-status'),
    heatmapGrid: document.getElementById('heatmap-grid'),
    topicsStatus: document.getElementById('topics-status'),
    topicsTableBody: document.getElementById('topics-table-body'),
    topicsEmpty: document.getElementById('topics-empty'),
};

const charts = {
    correlation: null,
    progress: null,
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);

    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadAnalytics().catch((error) => {
        console.error('Falha ao carregar analytics:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function loadAnalytics() {
    setStatus(selectors.correlationStatus, 'Carregando correlação...');
    setStatus(selectors.progressStatus, 'Carregando evolução das notas...');
    setStatus(selectors.heatmapStatus, 'Carregando heatmap de estudos...');
    setStatus(selectors.topicsStatus, 'Carregando comparação de tópicos...');

    const [user, dashboard, logs] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/analytics/dashboard/'),
        apiFetch('/scheduling/logs/'),
    ]);

    updateGreeting(user);
    hideLogin();

    renderCorrelation(dashboard?.study_effectiveness);
    renderProgress(dashboard?.score_progression);
    renderEngagement(dashboard?.engagement_metrics);
    renderTopics(dashboard?.topic_comparison);
    renderHeatmap(normalizeCollection(logs));
}

function renderCorrelation(payload) {
    if (!payload) {
        setStatus(selectors.correlationStatus, 'Não foi possível carregar os dados de correlação.');
        selectors.correlationSummary.textContent = '';
        selectors.correlationInterpretation.textContent = '';
        setText(selectors.correlationCount, '0');
        destroyChart('correlation');
        return;
    }

    const coefficient = payload.correlation_coefficient;
    const points = Array.isArray(payload.topic_data) ? payload.topic_data : [];
    const dataset = points.map((item) => ({
        x: item.total_minutes_studied,
        y: item.average_quiz_score,
        label: item.topic_title,
    }));

    if (!dataset.length) {
        selectors.correlationSummary.textContent = 'Coeficiente indisponível.';
        selectors.correlationInterpretation.textContent = payload.interpretation;
        setText(selectors.correlationCount, '0');
        setStatus(selectors.correlationStatus, payload.interpretation);
        destroyChart('correlation');
        return;
    }

    selectors.correlationSummary.textContent = `Coeficiente de Pearson: ${
        typeof coefficient === 'number' ? coefficient.toFixed(2) : '—'
    }`;
    selectors.correlationInterpretation.textContent = payload.interpretation;
    setText(selectors.correlationCount, String(payload.data_points || dataset.length));
    setStatus(selectors.correlationStatus, `Tópicos analisados: ${dataset.length}`);

    const context = document.getElementById('correlation-chart');
    if (!context) {
        return;
    }

    if (!charts.correlation) {
        charts.correlation = new Chart(context, {
            type: 'scatter',
            data: {
                datasets: [
                    {
                        label: 'Tópicos',
                        data: dataset,
                        parsing: false,
                        backgroundColor: '#4c6ef5',
                        borderColor: '#364fc7',
                        pointRadius: 6,
                        pointHoverRadius: 8,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Minutos estudados',
                        },
                        beginAtZero: true,
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Nota média (%)',
                        },
                        suggestedMin: 0,
                        suggestedMax: 100,
                    },
                },
                plugins: {
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const label = context.raw?.label || 'Tópico';
                                return `${label}: ${context.formattedValue}`;
                            },
                        },
                    },
                },
            },
        });
    } else {
        charts.correlation.data.datasets[0].data = dataset;
        charts.correlation.update();
    }
}

function renderProgress(payload) {
    if (!payload) {
        setStatus(selectors.progressStatus, 'Não foi possível carregar a evolução das notas.');
        selectors.progressSummary.textContent = '';
        setText(selectors.progressTotal, '0');
        destroyChart('progress');
        return;
    }

    selectors.progressSummary.textContent = payload.trend_summary || '';
    setText(selectors.progressTotal, String(payload.total_attempts || 0));

    const timeline = Array.isArray(payload.timeline) ? payload.timeline : [];

    if (!timeline.length) {
        setStatus(selectors.progressStatus, 'Ainda não há tentativas suficientes para montar a linha do tempo.');
        destroyChart('progress');
        return;
    }

    setStatus(selectors.progressStatus, `Dias acompanhados: ${timeline.length}`);

    const labels = timeline.map((entry) => formatDateLabel(entry.date));
    const values = timeline.map((entry) => entry.average_score);

    const context = document.getElementById('progress-chart');
    if (!context) {
        return;
    }

    if (!charts.progress) {
        charts.progress = new Chart(context, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Nota média',
                        data: values,
                        borderColor: '#4c6ef5',
                        backgroundColor: 'rgba(76, 110, 245, 0.15)',
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        suggestedMax: 100,
                        title: {
                            display: true,
                            text: 'Nota média (%)',
                        },
                    },
                },
                plugins: {
                    legend: { display: false },
                },
            },
        });
    } else {
        charts.progress.data.labels = labels;
        charts.progress.data.datasets[0].data = values;
        charts.progress.update();
    }
}

function renderEngagement(payload) {
    if (!payload) {
        selectors.engagementSummary.textContent = '';
        return;
    }

    selectors.engagementSummary.textContent = payload.summary || '';
}

function renderHeatmap(logs) {
    const grid = selectors.heatmapGrid;
    if (!grid) {
        return;
    }

    grid.innerHTML = '';

    const normalized = Array.isArray(logs)
        ? logs.map((log) => ({
              minutes: Number(log.minutes_studied) || 0,
              createdAt: log.created_at,
          }))
        : [];

    if (!normalized.length) {
        setStatus(selectors.heatmapStatus, 'Nenhum registro de estudo encontrado.');
        return;
    }

    const matrix = Array.from({ length: 7 }, () => Array(24).fill(0));
    normalized.forEach((entry) => {
        const date = new Date(entry.createdAt || entry.date);
        if (Number.isNaN(date.getTime())) {
            return;
        }
        const minutes = entry.minutes;
        if (!minutes) {
            return;
        }
        const jsDay = date.getDay();
        const mappedDay = (jsDay + 6) % 7; // transforma domingo=0 em domingo=6
        const hour = date.getHours();
        matrix[mappedDay][hour] += minutes;
    });

    const maxValue = matrix.reduce(
        (max, row) => Math.max(max, ...row),
        0
    );

    const dayLabels = [
        'Segunda',
        'Terça',
        'Quarta',
        'Quinta',
        'Sexta',
        'Sábado',
        'Domingo',
    ];
    const hourLabels = Array.from({ length: 24 }, (_, index) => `${index.toString().padStart(2, '0')}h`);

    // Cabeçalho vazio
    grid.appendChild(createHeatmapLabel(''));
    hourLabels.forEach((label) => {
        grid.appendChild(createHeatmapLabel(label));
    });

    dayLabels.forEach((dayLabel, dayIndex) => {
        grid.appendChild(createHeatmapLabel(dayLabel));
        matrix[dayIndex].forEach((value, hourIndex) => {
            const intensity = maxValue ? value / maxValue : 0;
            const cell = document.createElement('div');
            cell.className = 'heatmap-cell';
            cell.dataset.value = value;
            cell.style.background = intensity
                ? `rgba(76, 110, 245, ${0.18 + intensity * 0.6})`
                : 'rgba(148, 163, 184, 0.12)';

            if (value > 0) {
                const tooltip = document.createElement('span');
                tooltip.className = 'heatmap-cell__tooltip';
                tooltip.textContent = `${dayLabel} • ${hourLabels[hourIndex]}: ${value} min`;
                cell.appendChild(tooltip);
            }

            grid.appendChild(cell);
        });
    });

    setStatus(selectors.heatmapStatus, `Registros analisados: ${normalized.length}`);
}

function renderTopics(payload) {
    const tbody = selectors.topicsTableBody;
    if (!tbody) {
        return;
    }

    tbody.innerHTML = '';

    const topics = Array.isArray(payload?.by_topic) ? payload.by_topic.slice() : [];

    if (!topics.length) {
        selectors.topicsEmpty?.removeAttribute('hidden');
        setStatus(selectors.topicsStatus, 'Sem tópicos para comparar até o momento.');
        return;
    }

    selectors.topicsEmpty?.setAttribute('hidden', '');
    setStatus(selectors.topicsStatus, `Total de tópicos analisados: ${topics.length}`);

    topics.sort((a, b) => {
        const scoreA = typeof a.average_score === 'number' ? a.average_score : -Infinity;
        const scoreB = typeof b.average_score === 'number' ? b.average_score : -Infinity;
        if (scoreA === scoreB) {
            return (b.total_minutes || 0) - (a.total_minutes || 0);
        }
        return scoreB - scoreA;
    });

    topics.forEach((topic) => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${topic.topic_title}</td>
            <td>${topic.course_title}</td>
            <td>${topic.total_minutes}</td>
            <td>${topic.session_count}</td>
            <td>${topic.attempt_count}</td>
            <td>${
                typeof topic.average_score === 'number' ? topic.average_score.toFixed(2) : '—'
            }</td>
        `;
        tbody.appendChild(row);
    });
}

function setStatus(node, message) {
    if (!node) {
        return;
    }
    node.textContent = message || '';
}

function setText(node, value) {
    if (!node) {
        return;
    }
    node.textContent = value;
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }
    const name = user?.first_name || user?.email || 'Olá!';
    selectors.greeting.textContent = `Olá, ${name.split(' ')[0]}!`;
}

function destroyChart(key) {
    if (charts[key]) {
        charts[key].destroy();
        charts[key] = null;
    }
}

function createHeatmapLabel(text) {
    const label = document.createElement('div');
    label.className = 'heatmap-grid__label';
    label.textContent = text;
    return label;
}

function formatDateLabel(value) {
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
    });
}

function normalizeCollection(payload) {
    if (Array.isArray(payload?.results)) {
        return payload.results;
    }
    if (Array.isArray(payload)) {
        return payload;
    }
    return [];
}

function showLogin(message) {
    if (selectors.loginError && message) {
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

        await loadAnalytics();
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
