const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const DIFFICULTY_LABELS = {
    EASY: 'Fácil',
    MODERATE: 'Moderada',
    HARD: 'Difícil',
    MIXED: 'Mista',
};

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    quizTitle: document.getElementById('quiz-title'),
    quizDescription: document.getElementById('quiz-description'),
    scoreDisplay: document.querySelector('.score-display'),
    scoreValue: document.getElementById('score-value'),
    scoreFeedback: document.getElementById('score-feedback'),
    statCorrect: document.getElementById('stat-correct'),
    statIncorrect: document.getElementById('stat-incorrect'),
    statTotal: document.getElementById('stat-total'),
    statDate: document.getElementById('stat-date'),
    retryQuiz: document.getElementById('retry-quiz'),
    nextQuiz: document.getElementById('next-quiz'),
    difficultyList: document.getElementById('difficulty-breakdown'),
    reviewContainer: document.getElementById('review-container'),
    reviewTemplate: document.getElementById('review-item-template'),
    difficultyTemplate: document.getElementById('difficulty-item-template'),
};

const state = {
    attemptId: null,
    quizId: null,
    attempt: null,
    user: null,
    quizzes: [],
    attempts: [],
};

document.addEventListener('DOMContentLoaded', () => {
    parseParams();

    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);
    selectors.retryQuiz?.addEventListener('click', handleRetryClick);
    selectors.nextQuiz?.addEventListener('click', handleNextQuizClick);

    restoreSession();
});

function parseParams() {
    const params = new URLSearchParams(window.location.search);
    const attemptIdParam = params.get('attemptId') || params.get('attempt_id');
    const quizIdParam = params.get('quizId') || params.get('quiz_id');
    state.attemptId = attemptIdParam ? Number(attemptIdParam) : null;
    state.quizId = quizIdParam ? Number(quizIdParam) : null;
}

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadResults().catch((error) => {
        console.error('Falha ao carregar os resultados:', error);
        clearTokens();
        showLogin('Sua sessão expirou. Entre novamente.');
    });
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    if (!selectors.loginForm) {
        return;
    }

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

        await loadResults();
        hideLogin();
    } catch (error) {
        console.error('Erro de login:', error);
        selectors.loginError.textContent = error.message || 'Erro inesperado ao entrar.';
    }
}

function handleLogout() {
    clearTokens();
    state.user = null;
    state.attempt = null;
    state.quizzes = [];
    showLogin();
}

function handleRetryClick(event) {
    if (!state.quizId) {
        event.preventDefault();
    }
}

function handleNextQuizClick(event) {
    if (selectors.nextQuiz?.getAttribute('aria-disabled') === 'true') {
        event.preventDefault();
    }
}

async function loadResults() {
    selectors.quizTitle.textContent = 'Carregando resultados...';
    selectors.quizDescription.textContent = '';
    selectors.scoreValue.textContent = '--%';
    selectors.scoreFeedback.textContent = '';
    selectors.statCorrect.textContent = '--';
    selectors.statIncorrect.textContent = '--';
    selectors.statTotal.textContent = '--';
    selectors.statDate.textContent = '--';
    selectors.difficultyList.innerHTML = '';
    selectors.reviewContainer.textContent = '';

    const [user, attempts] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch('/assessment/attempts/'),
    ]);

    state.user = user;
    updateGreeting(user);

    state.attempts = normalizeAttempts(attempts);

    if (!state.attemptId) {
        state.attemptId = findLatestAttemptId();
    }

    if (!state.attemptId) {
        renderEmptyState();
        hideLogin();
        return;
    }

    const [attempt, quizzes] = await Promise.all([
        apiFetch(`/assessment/attempts/${state.attemptId}/`),
        apiFetch('/assessment/quizzes/'),
    ]);

    state.attempt = attempt;
    state.quizId = attempt.quiz;
    state.quizzes = Array.isArray(quizzes) ? quizzes : [];

    renderAttempt();
    hideLogin();
}

function renderEmptyState() {
    selectors.quizTitle.textContent = 'Nenhum resultado encontrado';
    selectors.quizDescription.textContent = 'Envie uma tentativa de quiz para visualizar esta página.';
    selectors.reviewContainer.textContent = 'Ainda não há respostas para revisar.';
    selectors.retryQuiz?.setAttribute('aria-disabled', 'true');
    selectors.retryQuiz?.setAttribute('href', '#');
    selectors.nextQuiz?.setAttribute('aria-disabled', 'true');
    selectors.nextQuiz?.setAttribute('href', '#');
}

function renderAttempt() {
    const attempt = state.attempt;
    if (!attempt) {
        renderEmptyState();
        return;
    }

    const quiz = state.quizzes.find((item) => item.id === attempt.quiz);

    selectors.quizTitle.textContent = attempt.quiz_title || quiz?.title || 'Quiz sem título';
    selectors.quizDescription.textContent = quiz?.description || '';

    const score = attempt.score != null ? Math.round(attempt.score) : null;
    selectors.scoreValue.textContent = score != null ? `${score}%` : '--%';
    selectors.scoreFeedback.textContent = score != null ? buildScoreFeedback(score) : '';

    triggerScoreAnimation();

    const correct = attempt.correct_answers_count ?? 0;
    const incorrect = attempt.incorrect_answers_count ?? 0;
    const total = correct + incorrect;

    selectors.statCorrect.textContent = correct;
    selectors.statIncorrect.textContent = incorrect;
    selectors.statTotal.textContent = total;
    selectors.statDate.textContent = formatDate(attempt.completed_at);

    if (state.quizId) {
        selectors.retryQuiz?.setAttribute('href', `quiz.html?quizId=${state.quizId}`);
        selectors.retryQuiz?.removeAttribute('aria-disabled');
    }

    renderDifficultyBreakdown(attempt);
    renderReview(attempt);
    updateNextQuizAction();
}

function renderDifficultyBreakdown(attempt) {
    selectors.difficultyList.innerHTML = '';
    if (!Array.isArray(attempt.answers) || !attempt.answers.length) {
        const item = document.createElement('li');
        item.textContent = 'Não foi possível calcular os acertos por dificuldade.';
        item.className = 'difficulty-item';
        selectors.difficultyList.append(item);
        return;
    }

    const buckets = new Map();

    attempt.answers.forEach((answer) => {
        const difficulty = answer.question?.difficulty || 'UNKNOWN';
        if (!buckets.has(difficulty)) {
            buckets.set(difficulty, { total: 0, correct: 0 });
        }
        const bucket = buckets.get(difficulty);
        bucket.total += 1;
        if (answer.is_correct) {
            bucket.correct += 1;
        }
    });

    const template = selectors.difficultyTemplate?.content.firstElementChild;
    const entries = Array.from(buckets.entries()).sort((a, b) => a[0].localeCompare(b[0]));

    entries.forEach(([difficulty, stats]) => {
        const item = template ? template.cloneNode(true) : document.createElement('li');
        const percent = stats.total ? Math.round((stats.correct / stats.total) * 100) : 0;
        const titleEl = item.querySelector('.difficulty-item__title');
        const ratioEl = item.querySelector('.difficulty-item__ratio');
        const barEl = item.querySelector('.difficulty-item__bar');
        const barFillEl = item.querySelector('.difficulty-item__bar-fill');
        const detailsEl = item.querySelector('.difficulty-item__details');

        const label = DIFFICULTY_LABELS[difficulty] || 'Não informada';

        if (titleEl) {
            titleEl.textContent = label;
        }

        if (ratioEl) {
            ratioEl.textContent = `${stats.correct} de ${stats.total}`;
        }

        if (barEl) {
            barEl.setAttribute('aria-valuenow', String(percent));
        }

        if (barFillEl) {
            requestAnimationFrame(() => {
                barFillEl.style.width = `${percent}%`;
            });
        }

        if (detailsEl) {
            detailsEl.textContent = percent >= 70
                ? 'Ótimo desempenho nesta dificuldade.'
                : percent >= 40
                    ? 'Desempenho intermediário, vale revisar.'
                    : 'Considere revisar conteúdo desta dificuldade.';
        }

        selectors.difficultyList.append(item);
    });
}

function renderReview(attempt) {
    selectors.reviewContainer.innerHTML = '';
    if (!Array.isArray(attempt.answers) || !attempt.answers.length) {
        const empty = document.createElement('p');
        empty.textContent = 'Nenhuma resposta encontrada para esta tentativa.';
        selectors.reviewContainer.append(empty);
        return;
    }

    const template = selectors.reviewTemplate?.content.firstElementChild;

    attempt.answers.forEach((answer, index) => {
        const element = template ? template.cloneNode(true) : document.createElement('article');
        const status = answer.is_correct ? 'correct' : 'incorrect';
        element.dataset.status = status;

        const questionTitle = element.querySelector('.review-item__title');
        const questionText = element.querySelector('.review-item__question');
        const badge = element.querySelector('.review-item__badge');
        const answerEl = element.querySelector('.review-item__answer');
        const correctEl = element.querySelector('.review-item__correct');
        const difficultyEl = element.querySelector('.review-item__difficulty');
        const explanationEl = element.querySelector('.review-item__explanation-text');

        const question = answer.question;
        const questionLabel = question?.question_text || `Questão ${index + 1}`;

        if (questionTitle) {
            questionTitle.textContent = `Questão ${index + 1}`;
        }

        if (questionText) {
            questionText.textContent = questionLabel;
        }

        if (badge) {
            badge.dataset.statusText = status;
            badge.textContent = answer.is_correct ? 'Correta' : 'Incorreta';
        }

        if (answerEl) {
            answerEl.textContent = resolveChoiceLabel(question?.choices, answer.user_answer) || answer.user_answer || '—';
        }

        if (correctEl) {
            correctEl.textContent = resolveChoiceLabel(question?.choices, answer.correct_answer) || answer.correct_answer || '—';
        }

        if (difficultyEl) {
            difficultyEl.textContent = formatDifficulty(question?.difficulty);
        }

        if (explanationEl) {
            explanationEl.textContent = answer.explanation || 'Sem explicação cadastrada para esta pergunta.';
        }

        selectors.reviewContainer.append(element);
    });
}

function updateNextQuizAction() {
    if (!selectors.nextQuiz) {
        return;
    }

    if (!Array.isArray(state.quizzes) || state.quizzes.length <= 1) {
        selectors.nextQuiz.setAttribute('aria-disabled', 'true');
        selectors.nextQuiz.setAttribute('href', '#');
        return;
    }

    const sorted = state.quizzes.slice().sort((a, b) => (a.title || '').localeCompare(b.title || ''));
    const currentIndex = sorted.findIndex((quiz) => quiz.id === state.quizId);

    if (currentIndex === -1) {
        selectors.nextQuiz.setAttribute('aria-disabled', 'true');
        selectors.nextQuiz.setAttribute('href', '#');
        return;
    }

    let nextIndex = (currentIndex + 1) % sorted.length;
    if (sorted[nextIndex].id === state.quizId) {
        selectors.nextQuiz.setAttribute('aria-disabled', 'true');
        selectors.nextQuiz.setAttribute('href', '#');
        return;
    }

    const nextQuiz = sorted[nextIndex];
    selectors.nextQuiz.href = `quiz.html?quizId=${nextQuiz.id}`;
    selectors.nextQuiz.removeAttribute('aria-disabled');
}

function findLatestAttemptId() {
    if (!Array.isArray(state.attempts) || !state.attempts.length) {
        return null;
    }

    let attempts = state.attempts;
    if (state.quizId) {
        attempts = attempts.filter((attempt) => attempt.quiz === state.quizId);
    }

    if (!attempts.length) {
        return null;
    }

    const latest = attempts
        .slice()
        .sort((a, b) => new Date(b.completed_at || 0) - new Date(a.completed_at || 0))[0];

    return latest?.id ?? null;
}

function buildScoreFeedback(score) {
    if (score >= 90) {
        return 'Excelente desempenho! Continue assim.';
    }
    if (score >= 75) {
        return 'Ótimo trabalho! Pequenos ajustes podem levar à perfeição.';
    }
    if (score >= 50) {
        return 'Bom esforço! Revise as questões incorretas para consolidar o conhecimento.';
    }
    return 'Ótimo momento para revisar o conteúdo e tentar novamente.';
}

function triggerScoreAnimation() {
    if (!selectors.scoreDisplay) {
        return;
    }

    selectors.scoreDisplay.classList.remove('score-display--animate');
    void selectors.scoreDisplay.offsetWidth;
    selectors.scoreDisplay.classList.add('score-display--animate');
}

function formatDate(value) {
    if (!value) {
        return '—';
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return '—';
    }
    return date.toLocaleString('pt-BR');
}

function formatDifficulty(code) {
    if (!code) {
        return 'Não informada';
    }
    return DIFFICULTY_LABELS[code] || 'Não informada';
}

function resolveChoiceLabel(choices, key) {
    if (!choices || !key) {
        return null;
    }

    if (Array.isArray(choices)) {
        const index = choices.findIndex(([choiceKey]) => String(choiceKey).toUpperCase() === String(key).toUpperCase());
        return index !== -1 ? choices[index][1] : null;
    }

    const entries = Object.entries(choices);
    for (const [choiceKey, value] of entries) {
        if (String(choiceKey).toUpperCase() === String(key).toUpperCase()) {
            return value;
        }
    }
    return null;
}

function normalizeAttempts(raw) {
    if (!raw) {
        return [];
    }

    if (Array.isArray(raw)) {
        return raw;
    }

    if (Array.isArray(raw.results)) {
        return raw.results;
    }

    return [];
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }
    const name = user?.first_name || user?.email;
    selectors.greeting.textContent = name ? `Olá, ${name}!` : 'Olá!';
}

function showLogin(message) {
    if (message) {
        selectors.loginError.textContent = message;
    }
    selectors.loginOverlay?.removeAttribute('hidden');
    selectors.loginOverlay?.setAttribute('aria-hidden', 'false');
}

function hideLogin() {
    selectors.loginError.textContent = '';
    selectors.loginOverlay?.setAttribute('hidden', 'hidden');
    selectors.loginOverlay?.setAttribute('aria-hidden', 'true');
}

function loadTokens() {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (error) {
        console.warn('Não foi possível carregar tokens do armazenamento.', error);
        return null;
    }
}

function saveTokens(tokens) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens));
}

function clearTokens() {
    localStorage.removeItem(STORAGE_KEY);
}

async function apiFetch(path, options = {}) {
    const tokens = loadTokens();
    const headers = {
        'Content-Type': 'application/json',
        ...(options.headers || {}),
    };

    if (tokens?.access) {
        headers.Authorization = `Bearer ${tokens.access}`;
    }

    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers,
    });

    if (response.status === 204) {
        return null;
    }

    const data = await safeJson(response);

    if (!response.ok) {
        const message = data?.detail || data?.error || 'Erro ao comunicar com o servidor.';
        throw new Error(message);
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
