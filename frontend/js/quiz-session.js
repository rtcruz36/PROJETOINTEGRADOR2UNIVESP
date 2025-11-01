const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    questionCounter: document.getElementById('question-counter'),
    quizTitle: document.getElementById('quiz-title'),
    quizTopic: document.getElementById('quiz-topic'),
    quizDescription: document.getElementById('quiz-description'),
    attemptSummary: document.getElementById('attempt-summary'),
    questionText: document.getElementById('question-text'),
    questionChoices: document.getElementById('question-choices'),
    markReview: document.getElementById('mark-review'),
    questionFeedback: document.getElementById('question-feedback'),
    prevQuestion: document.getElementById('prev-question'),
    nextQuestion: document.getElementById('next-question'),
    submitQuiz: document.getElementById('submit-quiz'),
    questionProgress: document.getElementById('question-progress'),
    progressSummary: document.getElementById('progress-summary'),
    progressTemplate: document.getElementById('progress-button-template'),
    timerEnabled: document.getElementById('timer-enabled'),
    timerStatus: document.getElementById('timer-status'),
    timerOutput: document.getElementById('timer-output'),
    timerStart: document.getElementById('timer-start'),
    timerPause: document.getElementById('timer-pause'),
    timerReset: document.getElementById('timer-reset'),
    timerDuration: document.getElementById('timer-duration'),
    resultsPanel: document.getElementById('results-panel'),
    resultScore: document.getElementById('result-score'),
    resultCorrect: document.getElementById('result-correct'),
    resultIncorrect: document.getElementById('result-incorrect'),
    resultDate: document.getElementById('result-date'),
    resultsList: document.getElementById('results-list'),
    resultItemTemplate: document.getElementById('result-item-template'),
};

const state = {
    quizId: null,
    quiz: null,
    user: null,
    attempts: [],
    currentIndex: 0,
    answers: new Map(),
    review: new Set(),
    submittedAttempt: null,
    timer: {
        enabled: true,
        duration: 15 * 60,
        remaining: 15 * 60,
        running: false,
        intervalId: null,
    },
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);

    selectors.prevQuestion?.addEventListener('click', () => moveToQuestion(state.currentIndex - 1));
    selectors.nextQuestion?.addEventListener('click', () => moveToQuestion(state.currentIndex + 1));
    selectors.submitQuiz?.addEventListener('click', handleSubmitAttempt);
    selectors.markReview?.addEventListener('click', toggleReviewMark);

    selectors.timerEnabled?.addEventListener('change', handleTimerToggle);
    selectors.timerStart?.addEventListener('click', startTimer);
    selectors.timerPause?.addEventListener('click', pauseTimer);
    selectors.timerReset?.addEventListener('click', resetTimer);
    selectors.timerDuration?.addEventListener('change', handleTimerDurationChange);

    state.quizId = parseQuizId();
    selectors.questionChoices?.setAttribute('aria-labelledby', 'question-text');

    restoreSession();
});

function parseQuizId() {
    const params = new URLSearchParams(window.location.search);
    const raw = params.get('quizId') || params.get('quiz_id');
    return raw ? Number(raw) : null;
}

function restoreSession() {
    if (!state.quizId) {
        selectors.questionText.textContent = 'Nenhum quiz informado. Volte à central e escolha um quiz para resolver.';
        selectors.questionChoices.innerHTML = '';
        disableInteraction();
        return;
    }

    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadQuiz().catch((error) => {
        console.error('Falha ao carregar o quiz:', error);
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

        await loadQuiz();
        hideLogin();
    } catch (error) {
        console.error('Erro de login:', error);
        selectors.loginError.textContent = error.message || 'Erro inesperado ao entrar.';
    }
}

function handleLogout() {
    pauseTimer();
    clearTokens();
    showLogin();
}

async function loadQuiz() {
    if (!state.quizId) {
        return;
    }

    selectors.questionFeedback.textContent = '';
    delete selectors.questionFeedback.dataset.status;
    selectors.questionCounter.textContent = 'Carregando quiz...';
    selectors.questionChoices.innerHTML = '';

    const [user, quiz, attemptsData] = await Promise.all([
        apiFetch('/accounts/auth/users/me/'),
        apiFetch(`/assessment/quizzes/${state.quizId}/`),
        apiFetch('/assessment/attempts/'),
    ]);

    state.user = user;
    updateGreeting(user);

    state.quiz = quiz;
    state.currentIndex = 0;
    state.answers.clear();
    state.review.clear();
    state.submittedAttempt = null;

    const attempts = normalizeAttempts(attemptsData).filter((attempt) => attempt.quiz === quiz.id);
    state.attempts = attempts.sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at));

    selectors.quizTitle.textContent = quiz.title || 'Quiz sem título';
    selectors.quizTopic.textContent = quiz.topic_title ? `Tópico: ${quiz.topic_title}` : '';
    selectors.quizDescription.textContent = quiz.description || 'Sem descrição disponível.';

    renderAttemptSummary();
    renderResultsPanel();

    if (!Array.isArray(quiz.questions) || quiz.questions.length === 0) {
        selectors.questionCounter.textContent = 'Nenhuma questão disponível.';
        selectors.questionText.textContent = 'Este quiz ainda não possui questões cadastradas.';
        disableInteraction();
        hideLogin();
        return;
    }

    selectors.questionCounter.textContent = `Questão 1 de ${quiz.questions.length}`;
    selectors.questionText.textContent = '';

    enableInteraction();
    renderQuestion();
    updateNavigationState();
    updateProgress();
    resetTimer();
    hideLogin();
}

function renderQuestion() {
    if (!state.quiz || !state.quiz.questions?.length) {
        return;
    }

    const question = state.quiz.questions[state.currentIndex];
    selectors.questionCounter.textContent = `Questão ${state.currentIndex + 1} de ${state.quiz.questions.length}`;
    selectors.questionText.textContent = question.question_text || 'Questão sem enunciado';
    selectors.questionChoices.innerHTML = '';

    const selected = state.answers.get(question.id)?.answer ?? null;
    const choices = normalizeChoices(question.choices);

    choices.forEach(([key, value]) => {
        const listItem = document.createElement('li');
        listItem.className = 'question-choice';

        const input = document.createElement('input');
        input.type = 'radio';
        input.name = 'question-choice';
        input.id = `question-${question.id}-choice-${key}`;
        input.value = key;
        input.checked = selected === key;
        input.addEventListener('change', () => {
            handleChoiceSelection(question.id, key);
        });

        const label = document.createElement('label');
        label.setAttribute('for', input.id);
        label.innerHTML = `
            <span class="question-choice__key">${escapeHtml(key)}</span>
            <span>${escapeHtml(value)}</span>
        `;

        listItem.append(input, label);
        selectors.questionChoices.append(listItem);
    });

    updateMarkButton();
    updateNavigationState();
    updateProgress();
}

function moveToQuestion(index) {
    if (!state.quiz || !state.quiz.questions?.length) {
        return;
    }

    const bounded = Math.max(0, Math.min(index, state.quiz.questions.length - 1));
    if (bounded === state.currentIndex) {
        return;
    }

    state.currentIndex = bounded;
    selectors.questionFeedback.textContent = '';
    delete selectors.questionFeedback.dataset.status;
    renderQuestion();
}

function handleChoiceSelection(questionId, answerKey) {
    state.answers.set(questionId, { answer: answerKey });
    updateProgress();
}

function toggleReviewMark() {
    if (!state.quiz) {
        return;
    }

    const question = state.quiz.questions[state.currentIndex];
    if (!question) {
        return;
    }

    if (state.review.has(question.id)) {
        state.review.delete(question.id);
    } else {
        state.review.add(question.id);
    }

    updateMarkButton();
    updateProgress();
}

function updateMarkButton() {
    if (!state.quiz) {
        return;
    }

    const question = state.quiz.questions[state.currentIndex];
    if (!question || !selectors.markReview) {
        return;
    }

    const marked = state.review.has(question.id);
    selectors.markReview.setAttribute('aria-pressed', marked ? 'true' : 'false');
    selectors.markReview.textContent = marked ? 'Remover marcação' : 'Marcar para revisão';
}

function updateNavigationState() {
    const total = state.quiz?.questions?.length ?? 0;
    selectors.prevQuestion.disabled = state.currentIndex <= 0;
    selectors.nextQuestion.disabled = state.currentIndex >= total - 1;
}

function updateProgress() {
    if (!state.quiz) {
        return;
    }

    const container = selectors.questionProgress;
    if (!container || !selectors.progressTemplate) {
        return;
    }

    container.innerHTML = '';
    const template = selectors.progressTemplate.content.firstElementChild;
    const total = state.quiz.questions.length;
    let answered = 0;
    let marked = 0;

    state.quiz.questions.forEach((question, index) => {
        const button = template.cloneNode(true);
        button.textContent = index + 1;
        button.dataset.questionIndex = String(index);
        button.addEventListener('click', () => moveToQuestion(index));

        if (index === state.currentIndex) {
            button.classList.add('is-current');
        }
        if (state.answers.has(question.id)) {
            button.classList.add('is-answered');
            answered += 1;
        }
        if (state.review.has(question.id)) {
            button.classList.add('is-marked');
            marked += 1;
        }

        container.append(button);
    });

    selectors.progressSummary.textContent = `Respondidas: ${answered}/${total} • Marcadas: ${marked}`;
}

function disableInteraction() {
    selectors.prevQuestion.disabled = true;
    selectors.nextQuestion.disabled = true;
    selectors.submitQuiz.disabled = true;
    selectors.markReview.disabled = true;
}

function enableInteraction() {
    selectors.prevQuestion.disabled = false;
    selectors.nextQuestion.disabled = false;
    selectors.submitQuiz.disabled = false;
    selectors.markReview.disabled = false;
}

async function handleSubmitAttempt() {
    if (!state.quiz) {
        return;
    }

    const answeredQuestions = state.quiz.questions
        .map((question) => ({ question, answer: state.answers.get(question.id) }))
        .filter((entry) => entry.answer?.answer);

    if (!answeredQuestions.length) {
        selectors.questionFeedback.textContent = 'Responda ao menos uma questão antes de enviar.';
        selectors.questionFeedback.dataset.status = 'error';
        return;
    }

    const total = state.quiz.questions.length;
    const answeredCount = answeredQuestions.length;
    const markedCount = state.quiz.questions.reduce(
        (count, question) => (state.review.has(question.id) ? count + 1 : count),
        0
    );

    const confirmMessage = [
        `Você respondeu ${answeredCount} de ${total} questões.`,
        markedCount ? `${markedCount} ${markedCount === 1 ? 'questão marcada' : 'questões marcadas'} para revisão.` : '',
        'Deseja enviar suas respostas agora?',
    ]
        .filter(Boolean)
        .join('\n');

    if (!window.confirm(confirmMessage)) {
        return;
    }

    selectors.submitQuiz.disabled = true;
    selectors.questionFeedback.textContent = 'Enviando suas respostas...';
    delete selectors.questionFeedback.dataset.status;

    const payload = {
        quiz_id: state.quiz.id,
        answers: answeredQuestions.map(({ question, answer }) => ({
            question_id: question.id,
            user_answer: answer.answer,
        })),
    };

    try {
        const attempt = await apiFetch('/assessment/submit-attempt/', {
            method: 'POST',
            body: JSON.stringify(payload),
        });

        selectors.questionFeedback.textContent = 'Tentativa enviada com sucesso!';
        selectors.questionFeedback.dataset.status = 'success';
        state.submittedAttempt = attempt;
        state.attempts = [attempt, ...state.attempts].sort(
            (a, b) => new Date(b.completed_at) - new Date(a.completed_at)
        );
        renderAttemptSummary();
        renderResultsPanel();
    } catch (error) {
        console.error('Falha ao enviar tentativa:', error);
        selectors.questionFeedback.textContent = error.message || 'Não foi possível enviar suas respostas.';
        selectors.questionFeedback.dataset.status = 'error';
    } finally {
        selectors.submitQuiz.disabled = false;
    }
}

function renderAttemptSummary() {
    if (!state.attempts.length) {
        selectors.attemptSummary.textContent = 'Nenhuma tentativa enviada ainda.';
        return;
    }

    const latest = state.attempts[0];
    const date = latest.completed_at ? new Date(latest.completed_at) : null;
    const score = latest.score != null ? `${Math.round(latest.score)}%` : '—';
    const formattedDate = date ? date.toLocaleString('pt-BR') : '—';
    selectors.attemptSummary.textContent = `Última tentativa: ${score} em ${formattedDate}`;
}

function renderResultsPanel() {
    const attempt = state.submittedAttempt || state.attempts[0];
    if (!attempt) {
        selectors.resultsPanel?.setAttribute('hidden', 'hidden');
        return;
    }

    selectors.resultsPanel?.removeAttribute('hidden');
    selectors.resultScore.textContent = attempt.score != null ? `${Math.round(attempt.score)}%` : '—';
    selectors.resultCorrect.textContent = attempt.correct_answers_count ?? '—';
    selectors.resultIncorrect.textContent = attempt.incorrect_answers_count ?? '—';
    const completedAt = attempt.completed_at ? new Date(attempt.completed_at) : null;
    selectors.resultDate.textContent = completedAt ? completedAt.toLocaleString('pt-BR') : '—';

    selectors.resultsList.innerHTML = '';
    if (!Array.isArray(attempt.answers) || !selectors.resultItemTemplate) {
        return;
    }

    const template = selectors.resultItemTemplate.content.firstElementChild;

    attempt.answers.forEach((answer, index) => {
        const item = template.cloneNode(true);
        const questionTitle = item.querySelector('.results-item__question');
        const answerText = item.querySelector('.results-item__answer');
        const status = item.querySelector('.results-item__status');

        if (questionTitle) {
            const baseTitle = answer.question?.question_text || `Questão ${index + 1}`;
            questionTitle.textContent = baseTitle;
        }

        if (answerText) {
            const value = resolveChoiceLabel(answer.question?.choices, answer.user_answer);
            answerText.textContent = value || answer.user_answer || '—';
        }

        if (status) {
            const statusKey = answer.is_correct ? 'correct' : 'incorrect';
            status.dataset.status = statusKey;
            status.textContent = answer.is_correct ? 'Correta' : 'Incorreta';
        }

        selectors.resultsList.append(item);
    });
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

function normalizeChoices(choices) {
    if (!choices) {
        return [];
    }

    if (Array.isArray(choices)) {
        return choices.map((choice, index) => [String.fromCharCode(65 + index), choice]);
    }

    return Object.entries(choices).sort((a, b) => a[0].localeCompare(b[0]));
}

function resolveChoiceLabel(choices, key) {
    if (!key) {
        return null;
    }

    if (choices) {
        if (Array.isArray(choices)) {
            const index = Number(key);
            if (!Number.isNaN(index) && choices[index] !== undefined) {
                return choices[index];
            }
        } else if (choices[key] !== undefined) {
            return choices[key];
        }
    }

    return null;
}

function handleTimerToggle() {
    state.timer.enabled = Boolean(selectors.timerEnabled?.checked);
    if (!state.timer.enabled) {
        pauseTimer('Timer desativado');
        selectors.timerStatus.textContent = 'Timer desativado';
        selectors.timerStart.disabled = true;
        selectors.timerPause.disabled = true;
        selectors.timerReset.disabled = true;
        selectors.timerDuration.disabled = true;
    } else {
        selectors.timerStatus.textContent = 'Pronto para iniciar';
        selectors.timerStart.disabled = false;
        selectors.timerPause.disabled = false;
        selectors.timerReset.disabled = false;
        selectors.timerDuration.disabled = false;
        resetTimer();
    }
}

function handleTimerDurationChange() {
    const minutes = Number(selectors.timerDuration?.value);
    if (Number.isFinite(minutes) && minutes >= 1 && minutes <= 180) {
        if (state.timer.running) {
            pauseTimer();
        }
        state.timer.duration = Math.round(minutes * 60);
        state.timer.remaining = state.timer.duration;
        updateTimerOutput();
        selectors.timerStatus.textContent = 'Duração ajustada';
    }
}

function startTimer() {
    if (!state.timer.enabled || state.timer.running) {
        return;
    }

    state.timer.running = true;
    selectors.timerStart.disabled = true;
    selectors.timerPause.disabled = false;
    selectors.timerStatus.textContent = 'Timer em andamento';

    state.timer.intervalId = window.setInterval(() => {
        state.timer.remaining -= 1;
        if (state.timer.remaining <= 0) {
            state.timer.remaining = 0;
            updateTimerOutput();
            pauseTimer('Tempo encerrado!');
            return;
        }
        updateTimerOutput();
    }, 1000);
}

function pauseTimer(statusMessage = 'Timer pausado') {
    if (!state.timer.running) {
        if (statusMessage) {
            selectors.timerStatus.textContent = statusMessage;
        }
        selectors.timerStart.disabled = !state.timer.enabled;
        selectors.timerPause.disabled = true;
        return;
    }

    state.timer.running = false;
    selectors.timerStart.disabled = !state.timer.enabled;
    selectors.timerPause.disabled = true;
    if (statusMessage) {
        selectors.timerStatus.textContent = statusMessage;
    }

    if (state.timer.intervalId) {
        window.clearInterval(state.timer.intervalId);
        state.timer.intervalId = null;
    }
}

function resetTimer() {
    if (state.timer.intervalId) {
        window.clearInterval(state.timer.intervalId);
        state.timer.intervalId = null;
    }

    state.timer.running = false;
    state.timer.remaining = state.timer.duration;
    selectors.timerStart.disabled = !state.timer.enabled;
    selectors.timerPause.disabled = true;
    selectors.timerReset.disabled = !state.timer.enabled;
    selectors.timerStatus.textContent = state.timer.enabled ? 'Pronto para iniciar' : 'Timer desativado';
    updateTimerOutput();
}

function updateTimerOutput() {
    const minutes = Math.floor(state.timer.remaining / 60);
    const seconds = state.timer.remaining % 60;
    selectors.timerOutput.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function updateGreeting(user) {
    if (!selectors.greeting) {
        return;
    }
    const displayName = (user?.first_name && user.first_name.trim()) || user?.email || '';
    selectors.greeting.textContent = displayName ? `Olá, ${displayName}!` : 'Olá!';
}

function showLogin(message) {
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = false;
    }
    if (message) {
        selectors.loginError.textContent = message;
    }
}

function hideLogin() {
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = true;
    }
    selectors.loginError.textContent = '';
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

async function safeJson(response) {
    try {
        return await response.json();
    } catch (error) {
        return null;
    }
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
