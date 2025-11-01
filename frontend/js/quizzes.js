const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';
// Percentual mínimo para considerar um quiz como concluído com sucesso.
const COMPLETION_THRESHOLD = 80;

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    generateButton: document.getElementById('generate-quiz'),
    totalStat: document.getElementById('stat-total'),
    notStartedStat: document.getElementById('stat-not-started'),
    inProgressStat: document.getElementById('stat-in-progress'),
    completedStat: document.getElementById('stat-completed'),
    topicFilter: document.getElementById('filter-topic'),
    difficultyFilter: document.getElementById('filter-difficulty'),
    statusFilter: document.getElementById('filter-status'),
    searchFilter: document.getElementById('filter-search'),
    listContainer: document.getElementById('quiz-list-container'),
    listFeedback: document.getElementById('quiz-list-feedback'),
    topicTemplate: document.getElementById('topic-group-template'),
    quizTemplate: document.getElementById('quiz-card-template'),
    modal: document.getElementById('generate-quiz-modal'),
    modalClose: document.getElementById('close-generate-modal'),
    modalCancel: document.getElementById('cancel-generate'),
    modalForm: document.getElementById('generate-quiz-form'),
    modalTopic: document.getElementById('generate-topic'),
    modalEasy: document.getElementById('generate-easy'),
    modalModerate: document.getElementById('generate-moderate'),
    modalHard: document.getElementById('generate-hard'),
    modalSubmit: document.getElementById('submit-generate'),
    modalFeedback: document.getElementById('generate-feedback'),
};

const state = {
    user: null,
    topics: [],
    quizzes: [],
    attempts: [],
    enrichedQuizzes: [],
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);

    selectors.generateButton?.addEventListener('click', openGenerateModal);
    selectors.modalClose?.addEventListener('click', closeGenerateModal);
    selectors.modalCancel?.addEventListener('click', closeGenerateModal);
    selectors.modal?.addEventListener('click', (event) => {
        if (event.target === selectors.modal) {
            closeGenerateModal();
        }
    });

    selectors.modalForm?.addEventListener('submit', handleGenerateSubmit);

    selectors.topicFilter?.addEventListener('change', applyFilters);
    selectors.difficultyFilter?.addEventListener('change', applyFilters);
    selectors.statusFilter?.addEventListener('change', applyFilters);
    selectors.searchFilter?.addEventListener('input', debounce(applyFilters, 200));

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && selectors.modal?.getAttribute('aria-hidden') === 'false') {
            closeGenerateModal();
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

    loadQuizzes().catch((error) => {
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
            headers: { 'Content-Type': 'application/json' },
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

        await loadQuizzes();
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

async function loadQuizzes() {
    selectors.listFeedback.textContent = 'Carregando seus quizzes...';
    selectors.listContainer.innerHTML = '';

    const [user, topics, quizzes, attempts] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/learning/topics/'),
        apiFetch('/assessment/quizzes/'),
        apiFetch('/assessment/attempts/'),
    ]);

    state.user = user;
    updateGreeting(user);

    state.topics = Array.isArray(topics) ? topics : [];
    state.quizzes = Array.isArray(quizzes) ? quizzes : [];
    state.attempts = Array.isArray(attempts) ? attempts : [];

    state.enrichedQuizzes = state.quizzes.map((quiz) => enrichQuiz(quiz));

    populateTopicOptions();
    populateModalTopics();
    renderSummary();
    applyFilters();
}

function enrichQuiz(quiz) {
    const attempts = state.attempts.filter((attempt) => attempt.quiz === quiz.id);
    const latestAttempt = attempts
        .slice()
        .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at))[0];
    const bestScore = attempts.reduce((max, attempt) => Math.max(max, attempt.score ?? 0), 0);

    const status = determineStatus(attempts.length, bestScore);
    const difficulty = inferDifficulty(quiz.questions || []);

    return {
        ...quiz,
        topic_title: quiz.topic_title,
        attempts,
        latestAttempt,
        bestScore: attempts.length ? bestScore : null,
        status,
        difficulty,
    };
}

function determineStatus(attemptCount, bestScore) {
    if (!attemptCount) {
        return 'NOT_STARTED';
    }

    if ((bestScore ?? 0) >= COMPLETION_THRESHOLD) {
        return 'COMPLETED';
    }

    return 'IN_PROGRESS';
}

function inferDifficulty(questions) {
    if (!Array.isArray(questions) || !questions.length) {
        return { code: 'MIXED', label: 'Sem questões' };
    }

    const counts = { EASY: 0, MODERATE: 0, HARD: 0 };
    questions.forEach((question) => {
        if (question?.difficulty && counts[question.difficulty] !== undefined) {
            counts[question.difficulty] += 1;
        }
    });

    const activeDifficulties = Object.entries(counts).filter(([, value]) => value > 0);
    if (activeDifficulties.length === 1) {
        const [code] = activeDifficulties[0];
        return { code, label: difficultyLabel(code) };
    }

    if (!activeDifficulties.length) {
        return { code: 'MIXED', label: 'Sem questões' };
    }

    const dominant = activeDifficulties.reduce((prev, current) => (current[1] > prev[1] ? current : prev));
    if (dominant[1] >= questions.length * 0.6) {
        return { code: dominant[0], label: `${difficultyLabel(dominant[0])} predominante` };
    }

    return { code: 'MIXED', label: 'Mista' };
}

function difficultyLabel(code) {
    switch (code) {
        case 'EASY':
            return 'Fácil';
        case 'MODERATE':
            return 'Moderada';
        case 'HARD':
            return 'Difícil';
        default:
            return 'Mista';
    }
}

function populateTopicOptions() {
    if (!selectors.topicFilter) {
        return;
    }

    const previousSelection = selectors.topicFilter.value;
    selectors.topicFilter.innerHTML = '<option value="all">Todos os tópicos</option>';

    state.topics
        .slice()
        .sort((a, b) => a.title.localeCompare(b.title))
        .forEach((topic) => {
            const option = document.createElement('option');
            option.value = String(topic.id);
            option.textContent = topic.title;
            selectors.topicFilter.append(option);
        });

    if (previousSelection && [...selectors.topicFilter.options].some((option) => option.value === previousSelection)) {
        selectors.topicFilter.value = previousSelection;
    }
}

function populateModalTopics() {
    if (!selectors.modalTopic) {
        return;
    }

    selectors.modalTopic.innerHTML = '';

    if (!state.topics.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'Nenhum tópico disponível';
        option.disabled = true;
        selectors.modalTopic.append(option);
        selectors.modalTopic.value = '';
        selectors.modalSubmit.disabled = true;
        selectors.modalFeedback.textContent = 'Cadastre um curso e tópicos para gerar novos quizzes.';
        selectors.generateButton?.setAttribute('disabled', 'disabled');
        return;
    }

    selectors.modalSubmit.disabled = false;
    selectors.modalFeedback.textContent = '';
    selectors.generateButton?.removeAttribute('disabled');

    state.topics
        .slice()
        .sort((a, b) => a.title.localeCompare(b.title))
        .forEach((topic) => {
            const option = document.createElement('option');
            option.value = String(topic.id);
            option.textContent = topic.title;
            selectors.modalTopic.append(option);
        });
}

function renderSummary() {
    const totals = state.enrichedQuizzes.reduce(
        (acc, quiz) => {
            acc.total += 1;
            acc[quiz.status] += 1;
            return acc;
        },
        { total: 0, NOT_STARTED: 0, IN_PROGRESS: 0, COMPLETED: 0 }
    );

    selectors.totalStat.textContent = totals.total;
    selectors.notStartedStat.textContent = totals.NOT_STARTED;
    selectors.inProgressStat.textContent = totals.IN_PROGRESS;
    selectors.completedStat.textContent = totals.COMPLETED;
}

function applyFilters() {
    if (!selectors.listContainer) {
        return;
    }

    const filters = {
        topic: selectors.topicFilter?.value || 'all',
        difficulty: selectors.difficultyFilter?.value || 'all',
        status: selectors.statusFilter?.value || 'all',
        search: selectors.searchFilter?.value?.trim().toLowerCase() || '',
    };

    const filtered = state.enrichedQuizzes.filter((quiz) => {
        if (filters.topic !== 'all' && String(quiz.topic) !== filters.topic) {
            return false;
        }
        if (filters.difficulty !== 'all') {
            if (filters.difficulty === 'MIXED') {
                if (quiz.difficulty.code !== 'MIXED') {
                    return false;
                }
            } else if (quiz.difficulty.code !== filters.difficulty) {
                return false;
            }
        }
        if (filters.status !== 'all' && quiz.status !== filters.status) {
            return false;
        }
        if (filters.search) {
            const haystack = `${quiz.title} ${quiz.description || ''}`.toLowerCase();
            if (!haystack.includes(filters.search)) {
                return false;
            }
        }
        return true;
    });

    renderQuizList(filtered);
}

function renderQuizList(quizzes) {
    selectors.listContainer.innerHTML = '';

    if (!quizzes.length) {
        selectors.listFeedback.textContent = state.enrichedQuizzes.length
            ? 'Nenhum quiz corresponde aos filtros selecionados.'
            : 'Você ainda não possui quizzes cadastrados. Gere um novo quiz para começar.';
        return;
    }

    selectors.listFeedback.textContent = `${quizzes.length} ${
        quizzes.length === 1 ? 'quiz encontrado' : 'quizzes encontrados'
    }.`;

    const topicsMap = new Map();
    state.topics.forEach((topic) => {
        topicsMap.set(topic.id, topic.title);
    });

    const groups = quizzes.reduce((acc, quiz) => {
        if (!acc.has(quiz.topic)) {
            acc.set(quiz.topic, []);
        }
        acc.get(quiz.topic).push(quiz);
        return acc;
    }, new Map());

    const sortedGroups = [...groups.entries()].sort((a, b) => {
        const titleA = topicsMap.get(a[0]) || 'Outros';
        const titleB = topicsMap.get(b[0]) || 'Outros';
        return titleA.localeCompare(titleB);
    });

    sortedGroups.forEach(([topicId, topicQuizzes]) => {
        const topicTitle = topicsMap.get(topicId) || 'Tópico desconhecido';
        const group = selectors.topicTemplate.content.firstElementChild.cloneNode(true);
        const title = group.querySelector('.quiz-topic-group__title');
        const count = group.querySelector('.quiz-topic-group__count');
        const list = group.querySelector('.quiz-topic-group__list');

        title.textContent = topicTitle;
        count.textContent = `${topicQuizzes.length} ${
            topicQuizzes.length === 1 ? 'quiz disponível' : 'quizzes disponíveis'
        }`;

        const sortedQuizzes = topicQuizzes.slice().sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

        sortedQuizzes.forEach((quiz) => {
            const card = selectors.quizTemplate.content.firstElementChild.cloneNode(true);
            card.querySelector('.quiz-card__title').textContent = quiz.title;
            card.querySelector('.quiz-card__description').textContent = quiz.description || 'Sem descrição disponível.';
            card.querySelector('.quiz-card__questions').textContent = quiz.total_questions;
            card.querySelector('.quiz-card__difficulty').textContent = quiz.difficulty.label;

            const badge = card.querySelector('[data-status]');
            badge.dataset.status = quiz.status;
            badge.textContent = statusLabel(quiz.status);

            const score = quiz.bestScore;
            card.querySelector('.quiz-card__score').textContent = score == null ? '—' : `${Math.round(score)}%`;

            const createdAt = new Date(quiz.created_at);
            const timeElement = card.querySelector('.quiz-card__date');
            timeElement.dateTime = createdAt.toISOString();
            timeElement.textContent = `Criado em ${formatDate(createdAt)}`;

            const topicLink = card.querySelector('[data-topic-link]');
            topicLink.href = `study.html?topicId=${encodeURIComponent(quiz.topic)}`;
            topicLink.textContent = 'Ver tópico';

            list.append(card);
        });

        selectors.listContainer.append(group);
    });
}

function statusLabel(status) {
    switch (status) {
        case 'NOT_STARTED':
            return 'Não iniciado';
        case 'IN_PROGRESS':
            return 'Em progresso';
        case 'COMPLETED':
            return 'Concluído';
        default:
            return status;
    }
}

function formatDate(date) {
    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    });
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }

    if (!user) {
        selectors.greeting.textContent = 'Olá!';
        return;
    }

    const firstName = (user.first_name || user.email || '');
    selectors.greeting.textContent = firstName ? `Olá, ${firstName.split(' ')[0]}!` : 'Olá!';
}

function openGenerateModal() {
    if (!selectors.modal || selectors.generateButton?.hasAttribute('disabled')) {
        return;
    }

    selectors.modal.setAttribute('aria-hidden', 'false');
    selectors.modal.classList.add('is-open');
    selectors.modalTopic?.focus();
}

function closeGenerateModal() {
    if (!selectors.modal) {
        return;
    }

    selectors.modal.setAttribute('aria-hidden', 'true');
    selectors.modal.classList.remove('is-open');
    selectors.modalForm?.reset();
    selectors.modalFeedback.textContent = '';
    selectors.modalSubmit.disabled = false;
}

async function handleGenerateSubmit(event) {
    event.preventDefault();

    if (!selectors.modalTopic?.value) {
        selectors.modalFeedback.textContent = 'Selecione um tópico para gerar o quiz.';
        return;
    }

    const numEasy = Number.parseInt(selectors.modalEasy.value, 10) || 0;
    const numModerate = Number.parseInt(selectors.modalModerate.value, 10) || 0;
    const numHard = Number.parseInt(selectors.modalHard.value, 10) || 0;
    const total = numEasy + numModerate + numHard;

    if (total === 0) {
        selectors.modalFeedback.textContent = 'Configure pelo menos uma pergunta para gerar o quiz.';
        return;
    }

    selectors.modalSubmit.disabled = true;
    selectors.modalFeedback.textContent = 'Gerando quiz, aguarde...';

    try {
        const payload = {
            topic_id: Number.parseInt(selectors.modalTopic.value, 10),
            num_easy: numEasy,
            num_moderate: numModerate,
            num_hard: numHard,
        };

        const createdQuiz = await apiFetch('/assessment/generate-quiz/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        const quizTitle = createdQuiz?.title || createdQuiz?.quiz_title;
        selectors.modalFeedback.textContent = quizTitle
            ? `Quiz "${quizTitle}" criado com sucesso! Atualizando a lista...`
            : 'Quiz criado com sucesso! Atualizando a lista...';
        await loadQuizzes();
        closeGenerateModal();
    } catch (error) {
        console.error('Erro ao gerar quiz:', error);
        selectors.modalFeedback.textContent = error.message || 'Não foi possível gerar o quiz.';
    } finally {
        selectors.modalSubmit.disabled = false;
    }
}

function debounce(fn, delay = 200) {
    let timeoutId;
    return function debounced(...args) {
        window.clearTimeout(timeoutId);
        timeoutId = window.setTimeout(() => fn.apply(this, args), delay);
    };
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

async function apiFetch(path, options = {}, { allowEmpty = false, retryOn401 = true } = {}) {
    const tokens = loadTokens();
    if (!tokens?.access) {
        throw new Error('Sessão inválida. Faça login novamente.');
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
            showLogin('Sua sessão expirou. Entre novamente.');
            throw new Error('Sessão expirada.');
        }
        return apiFetch(path, options, { allowEmpty, retryOn401: false });
    }

    if (response.status === 204 && allowEmpty) {
        return null;
    }

    const data = await safeJson(response);

    if (!response.ok) {
        const detail = data?.error || data?.detail || 'Erro ao se comunicar com o servidor.';
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
