// Все запросы к серверу. Адреса относительные: мини-приложение и API раздаёт один сервер.
// Формат ответов — контракт API в CLAUDE.md.

// Подпись МАКС: строка, которую мессенджер передаёт мини-приложению при запуске.
// В обычном браузере её нет — тогда сервер с DEV_AUTH=1 подставит тестового пользователя.
const initData = () => window.WebApp?.initData || "";

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (initData()) headers["X-Max-Init-Data"] = initData();
  if (options.body) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(path, { ...options, headers });
  } catch {
    throw new Error("Не получилось связаться с сервером. Проверь интернет и попробуй ещё раз.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    // Сервер присылает ошибку как {"detail": "текст по-русски"} — его и показываем
    throw new Error(typeof body.detail === "string" ? body.detail : `Ошибка сервера (${res.status})`);
  }
  return body;
}

// Три события под настроение: {mood, day, budget, results: [{event, mood, score, over_budget}]}
export function getPick(mood, day, budget) {
  const params = new URLSearchParams({ mood, day, budget: budget ? "1" : "0" });
  return request(`/api/pick?${params}`);
}

// Кто и из какого чата открыл мини-приложение: {user, chat, start_param}
export const getMe = () => request("/api/me");

// Позвать чат: бот пришлёт карточку события. Ответ {invite_id, sent}
export const createInvite = (eventId) =>
  request("/api/invites", { method: "POST", body: JSON.stringify({ event_id: eventId }) });

// Ответы друзей для живого счётчика: {invite_id, event, answers: [{name, answer}]}
export const getInvite = (inviteId) => request(`/api/invites/${inviteId}`);
