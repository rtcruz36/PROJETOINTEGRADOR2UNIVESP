const API_BASE_URL = (document.body.dataset.apiBase || 'http://localhost:8000/api').replace(/\/$/, '');
const STORAGE_KEY = 'pi2-dashboard-auth';

const selectors = {
    loginOverlay: document.getElementById('login-overlay'),
    loginForm: document.getElementById('login-form'),
    loginError: document.getElementById('login-error'),
    logoutButton: document.getElementById('logout-button'),
    greeting: document.getElementById('user-greeting'),
    profileForm: document.getElementById('profile-form'),
    saveProfileButton: document.getElementById('save-profile-button'),
    profileFeedback: document.getElementById('profile-feedback'),
    nameInput: document.getElementById('profile-name'),
    emailInput: document.getElementById('profile-email'),
    bioInput: document.getElementById('profile-bio'),
    notificationsToggle: document.getElementById('notifications-toggle'),
    themeSelect: document.getElementById('theme-select'),
    photoInput: document.getElementById('profile-photo-input'),
    removePhotoButton: document.getElementById('remove-photo-button'),
    photoPreview: document.getElementById('profile-photo-preview'),
    photoPlaceholder: document.getElementById('profile-photo-placeholder'),
    statDays: document.getElementById('stat-days'),
    statHours: document.getElementById('stat-hours'),
    statStreak: document.getElementById('stat-streak'),
    statBestStreak: document.getElementById('stat-best-streak'),
};

const state = {
    photoFile: null,
    photoCleared: false,
    previewObjectUrl: null,
};

document.addEventListener('DOMContentLoaded', () => {
    selectors.loginForm?.addEventListener('submit', handleLoginSubmit);
    selectors.logoutButton?.addEventListener('click', handleLogout);
    selectors.profileForm?.addEventListener('submit', handleProfileSubmit);
    selectors.photoInput?.addEventListener('change', handlePhotoSelection);
    selectors.removePhotoButton?.addEventListener('click', handlePhotoRemoval);

    restoreSession();
});

function restoreSession() {
    const tokens = loadTokens();
    if (!tokens?.access) {
        showLogin();
        return;
    }

    loadProfilePage().catch((error) => {
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
                Accept: 'application/json',
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

        await loadProfilePage();
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
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = false;
    }
}

function hideLogin() {
    selectors.loginError.textContent = '';
    if (selectors.loginOverlay) {
        selectors.loginOverlay.hidden = true;
    }
}

async function loadProfilePage() {
    const [profileResult, statsResult] = await Promise.allSettled([
        apiFetch('/accounts/profile/'),
        apiFetch('/scheduling/statistics/', {}, { allowEmpty: true }),
    ]);

    if (profileResult.status !== 'fulfilled') {
        throw profileResult.reason;
    }

    applyProfileData(profileResult.value);

    if (statsResult.status === 'fulfilled') {
        renderStatistics(statsResult.value);
    } else {
        console.error('Erro ao carregar estatísticas de estudo:', statsResult.reason);
        renderStatistics(null);
    }
}

function applyProfileData(data) {
    if (!data) {
        return;
    }

    if (selectors.greeting) {
        const name = data.first_name || data.username || '';
        selectors.greeting.textContent = name ? `Olá, ${name}!` : 'Olá!';
    }

    if (selectors.nameInput) {
        selectors.nameInput.value = data.first_name || '';
    }

    if (selectors.emailInput) {
        selectors.emailInput.value = data.email || '';
    }

    if (selectors.bioInput) {
        selectors.bioInput.value = data.profile?.bio || '';
    }

    if (selectors.notificationsToggle) {
        selectors.notificationsToggle.checked = Boolean(data.preferences?.notifications_enabled);
    }

    if (selectors.themeSelect) {
        const theme = data.preferences?.theme || 'system';
        if (Array.from(selectors.themeSelect.options).some((option) => option.value === theme)) {
            selectors.themeSelect.value = theme;
        } else {
            selectors.themeSelect.value = 'system';
        }
    }

    const photoUrl = resolveMediaUrl(data.profile?.profile_picture);
    setPhotoPreview(photoUrl);
    selectors.photoInput.value = '';
    state.photoFile = null;
    state.photoCleared = false;
}

function renderStatistics(statistics) {
    if (!statistics) {
        if (selectors.statDays) selectors.statDays.textContent = '--';
        if (selectors.statHours) selectors.statHours.textContent = '--';
        if (selectors.statStreak) selectors.statStreak.textContent = '--';
        if (selectors.statBestStreak) selectors.statBestStreak.textContent = '';
        return;
    }

    const totals = statistics.totals || {};
    const streaks = statistics.streaks || {};

    if (selectors.statDays) {
        const days = Number(totals.active_days) || 0;
        selectors.statDays.textContent = days.toLocaleString('pt-BR');
    }

    if (selectors.statHours) {
        const minutes = Number(totals.minutes_studied) || 0;
        const hours = minutes / 60;
        const formatted = hours.toLocaleString('pt-BR', {
            minimumFractionDigits: hours > 0 && hours < 10 ? 1 : 0,
            maximumFractionDigits: 1,
        });
        selectors.statHours.textContent = `${formatted} h`;
    }

    if (selectors.statStreak) {
        const current = Number(streaks.current_streak) || 0;
        selectors.statStreak.textContent = `${current} dia(s)`;
    }

    if (selectors.statBestStreak) {
        const best = Number(streaks.longest_streak) || 0;
        selectors.statBestStreak.textContent = best ? `Recorde: ${best} dia(s)` : '';
    }
}

function resolveMediaUrl(path) {
    if (!path) {
        return '';
    }
    try {
        return new URL(path, `${API_BASE_URL}/`).href;
    } catch (error) {
        return path;
    }
}

function handlePhotoSelection(event) {
    const [file] = event.target.files || [];
    if (!file) {
        return;
    }

    state.photoFile = file;
    state.photoCleared = false;

    const objectUrl = URL.createObjectURL(file);
    setPhotoPreview(objectUrl, { isObjectUrl: true });
}

function handlePhotoRemoval() {
    state.photoFile = null;
    state.photoCleared = true;
    if (selectors.photoInput) {
        selectors.photoInput.value = '';
    }
    setPhotoPreview('');
}

function setPhotoPreview(src, { isObjectUrl = false } = {}) {
    if (!selectors.photoPreview || !selectors.photoPlaceholder) {
        return;
    }

    if (state.previewObjectUrl && state.previewObjectUrl !== src) {
        URL.revokeObjectURL(state.previewObjectUrl);
        state.previewObjectUrl = null;
    }

    if (src) {
        selectors.photoPreview.src = src;
        selectors.photoPreview.style.display = 'block';
        selectors.photoPlaceholder.hidden = true;
        if (selectors.removePhotoButton) {
            selectors.removePhotoButton.disabled = false;
        }
        if (isObjectUrl) {
            state.previewObjectUrl = src;
        }
    } else {
        selectors.photoPreview.src = '';
        selectors.photoPreview.style.display = 'none';
        selectors.photoPlaceholder.hidden = false;
        if (selectors.removePhotoButton) {
            selectors.removePhotoButton.disabled = true;
        }
    }
}

async function handleProfileSubmit(event) {
    event.preventDefault();
    if (!selectors.profileForm) {
        return;
    }

    setProfileFeedback('', '');

    const button = selectors.saveProfileButton;
    const originalLabel = button?.textContent;
    if (button) {
        button.disabled = true;
        button.textContent = 'Salvando...';
    }

    const formData = new FormData();
    const name = selectors.nameInput?.value?.trim() || '';
    const email = selectors.emailInput?.value?.trim() || '';
    const bio = selectors.bioInput?.value?.trim() || '';
    const notifications = selectors.notificationsToggle?.checked ? 'true' : 'false';
    const theme = selectors.themeSelect?.value || 'system';

    formData.append('first_name', name);
    formData.append('email', email);
    formData.append('profile.bio', bio);
    formData.append('preferences.notifications_enabled', notifications);
    formData.append('preferences.theme', theme);

    if (state.photoFile) {
        formData.append('profile.profile_picture', state.photoFile);
    } else if (state.photoCleared) {
        formData.append('profile.profile_picture', '');
    }

    try {
        const data = await apiFetch(
            '/accounts/profile/',
            {
                method: 'PATCH',
                body: formData,
            },
            { allowEmpty: false, retryOn401: true },
        );

        applyProfileData(data);
        setProfileFeedback('Perfil atualizado com sucesso.', 'success');
    } catch (error) {
        console.error('Erro ao atualizar perfil:', error);
        setProfileFeedback(error.message || 'Não foi possível salvar as alterações.', 'error');
    } finally {
        if (button) {
            button.disabled = false;
            button.textContent = originalLabel || 'Salvar alterações';
        }
    }
}

function setProfileFeedback(message, status) {
    if (!selectors.profileFeedback) {
        return;
    }
    selectors.profileFeedback.textContent = message || '';
    if (status) {
        selectors.profileFeedback.dataset.status = status;
    } else {
        delete selectors.profileFeedback.dataset.status;
    }
}

async function apiFetch(path, options = {}, { allowEmpty = false, retryOn401 = true } = {}) {
    const tokens = loadTokens();
    if (!tokens?.access) {
        throw new Error('Sessão inválida. Entre novamente.');
    }

    const headers = new Headers(options.headers || {});
    headers.set('Authorization', `Bearer ${tokens.access}`);

    const isFormData = options.body instanceof FormData;
    if (!isFormData) {
        headers.set('Accept', headers.get('Accept') || 'application/json');
        if (options.body && !headers.has('Content-Type')) {
            headers.set('Content-Type', 'application/json');
        }
    } else {
        headers.set('Accept', headers.get('Accept') || 'application/json');
    }

    const formDataEntries = isFormData ? Array.from(options.body.entries()) : null;

    const response = await fetch(`${API_BASE_URL}${path}`, {
        ...options,
        headers,
    });

    if (response.status === 401 && retryOn401) {
        const refreshed = await refreshAccessToken();
        if (!refreshed) {
            throw new Error('Sessão expirada. Entre novamente.');
        }
        const retryOptions = { ...options };
        if (isFormData && formDataEntries) {
            const cloned = new FormData();
            formDataEntries.forEach(([key, value]) => {
                cloned.append(key, value);
            });
            retryOptions.body = cloned;
        }
        return apiFetch(path, retryOptions, { allowEmpty, retryOn401: false });
    }

    if (allowEmpty && response.status === 204) {
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
