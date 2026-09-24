// Все запросы к серверу. Адреса относительные: мини-приложение и API раздаёт один сервер.
// Формат ответов — контракт API в CLAUDE.md.

// Подпись МАКС: строка, которую мессенджер передаёт мини-приложению при запуске.
// В обычном браузере её нет — тогда сервер с DEV_AUTH=1 подставит тестового пользователя.
const initData = () => window.WebApp?.initData || "";

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (initData()) headers["X-Max-Init-Data"] = initData();
  if (options.body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { ...options, headers });
  if (!res.ok) {
    // Сервер присылает ошибку как {"detail": "текст по-русски"} — его и показываем
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Ошибка сервера (${res.status})`);
  }
  return res.json();
}

// Три события под настроение: {mood, day, budget, results: [{event, mood, score, over_budget}]}
export const getPick = (mood, day, budget) =>
  request(`/api/pick?mood=${mood}&day=${day}&budget=${budget ? 1 : 0}`);

// Кто и из какого чата открыл мини-приложение: {user, chat, start_param}
export const getMe = () => request("/api/me");

// Позвать чат: бот пришлёт карточку события. Ответ {invite_id, sent}
export const createInvite = (eventId) =>
  request("/api/invites", { method: "POST", body: JSON.stringify({ event_id: eventId }) });

// Ответы друзей для живого счётчика: {invite_id, event, answers: [{name, answer}]}
export const getInvite = (inviteId) => request(`/api/invites/${inviteId}`);
