// Мини-приложение «Вечер по настроению»: экраны и переходы между ними.
// Устройство: state хранит всё, что видно на экране; render() перерисовывает текущий экран целиком;
// кнопки помечены data-action, а один обработчик кликов решает, что делать.
import { createInvite, getInvite, getMe, getPick } from "./api.js";

const WebApp = window.WebApp;
const inMax = Boolean(WebApp?.initData); // true — открыто внутри МАКС, false — в обычном браузере

// id совпадают с server/picker.py. ink — цвет текста на плитке, чтобы читался на её фоне
const MOODS = [
  { id: "charged", title: "Заряжен(а)", hint: "Музыка и танцы", emoji: "⚡", color: "#FF5B22", ink: "#FFFFFF" },
  { id: "release", title: "Выпустить пар", hint: "Спорт и смех", emoji: "🥊", color: "#FFC83D", ink: "#1B1300" },
  { id: "exhale", title: "Хочу выдохнуть", hint: "Природа и тишина", emoji: "🌿", color: "#B9E4CC", ink: "#0B2A1B" },
  { id: "blue", title: "Погрустить красиво", hint: "Арт и кино", emoji: "🌧", color: "#3F5BDB", ink: "#FFFFFF" },
  { id: "learn", title: "Узнать новое", hint: "Лекции и мастер-классы", emoji: "🧠", color: "#0F7C86", ink: "#FFFFFF" },
  { id: "wild", title: "Удиви меня", hint: "Три разных настроения", emoji: "🎲", color: "#6D4BFF", ink: "#FFFFFF", wild: true },
];
const moodById = (id) => MOODS.find((mood) => mood.id === id);

const DAYS = [
  { id: "today", title: "Сегодня" },
  { id: "tomorrow", title: "Завтра" },
  { id: "saturday", title: "В субботу" },
];
const BUDGET_MAX = 300; // как в server/picker.py
const ANSWERS = [
  { id: "going", title: "Иду" },
  { id: "maybe", title: "Может" },
  { id: "no", title: "Не могу" },
];
const POLL_MS = 4000; // как часто обновлять счётчик ответов
const TZ = "Europe/Moscow"; // Казань живёт по московскому времени

const state = {
  screen: "mood", // mood → setup → results → plan → invite
  history: [], // откуда пришли — для кнопки «Назад»
  mood: null,
  day: "today",
  budget: false,
  loading: false,
  error: null,
  results: [],
  event: null, // выбранное событие
  invite: null, // {invite_id, sent}
  answers: [],
  me: null, // кто открыл и из какого чата — от /api/me
};

// ---------- Переходы ----------

function go(screen) {
  state.history.push(state.screen);
  state.screen = screen;
  state.error = null;
  render();
}

function back() {
  if (!state.history.length) return;
  state.screen = state.history.pop();
  state.error = null;
  render();
}

function restart() {
  state.history = [];
  state.screen = "mood";
  state.invite = null;
  render();
}

// ---------- Действия ----------

async function loadPick() {
  state.loading = true;
  state.error = null;
  render();
  try {
    const data = await getPick(state.mood, state.day, state.budget);
    state.results = data.results;
  } catch (error) {
    state.error = error.message;
  }
  state.loading = false;
  render();
}

async function sendInvite() {
  state.loading = true;
  state.error = null;
  render();
  try {
    state.invite = await createInvite(state.event.id);
    state.answers = [];
    state.loading = false;
    go("invite");
    pollAnswers();
  } catch (error) {
    state.loading = false;
    state.error = error.message;
    render();
  }
}

// Пока открыт экран приглашения, раз в 4 секунды спрашиваем сервер, кто что ответил
let pollTimer = null;
async function pollAnswers() {
  clearTimeout(pollTimer);
  if (state.screen !== "invite" || !state.invite) return;
  try {
    const data = await getInvite(state.invite.invite_id);
    const changed = JSON.stringify(data.answers) !== JSON.stringify(state.answers);
    state.answers = data.answers;
    if (changed && state.screen === "invite") render();
  } catch {
    // сеть мигнула — попробуем в следующий раз
  }
  pollTimer = setTimeout(pollAnswers, POLL_MS);
}

function openTicket() {
  const url = state.event?.ticket_url;
  if (!url) return;
  if (WebApp?.openLink && inMax) WebApp.openLink(url);
  else window.open(url, "_blank", "noopener");
}

function tap() {
  try {
    WebApp?.HapticFeedback?.impactOccurred?.("light"); // лёгкая вибрация в МАКС, если есть
  } catch {
    // в браузере вибрации нет — и ладно
  }
}

// Один обработчик на все кнопки: смотрим на data-action
document.addEventListener("click", (e) => {
  const button = e.target.closest("[data-action]");
  if (!button || button.disabled) return;
  const { action, id } = button.dataset;
  tap();
  if (action === "mood") {
    state.mood = id;
    go("setup");
  } else if (action === "day") {
    state.day = id;
    render();
  } else if (action === "budget") {
    state.budget = !state.budget;
    render();
  } else if (action === "show") {
    go("results");
    loadPick();
  } else if (action === "retry") {
    loadPick();
  } else if (action === "choose") {
    state.event = state.results.find((r) => r.event.id === id).event;
    go("plan");
  } else if (action === "invite") {
    sendInvite();
  } else if (action === "ticket") {
    openTicket();
  } else if (action === "back") {
    back();
  } else if (action === "restart") {
    restart();
  } else if (action === "done") {
    if (inMax) WebApp.close();
    else restart();
  }
});

// ---------- Форматирование ----------

// Экранируем текст из данных, чтобы он не превратился в HTML
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => `&#${ch.charCodeAt(0)};`);
}

const dayKey = (date) => date.toLocaleDateString("en-CA", { timeZone: TZ }); // 2026-09-26

function whenLabel(event) {
  if (!event.starts_at) return "В любое время";
  const start = new Date(event.starts_at);
  const time = start.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
  const now = new Date();
  let day;
  if (dayKey(start) === dayKey(now)) day = "Сегодня";
  else if (dayKey(start) === dayKey(new Date(now.getTime() + 864e5))) day = "Завтра";
  else day = start.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long", timeZone: TZ });
  return `${day[0].toUpperCase()}${day.slice(1)}, ${time}`;
}

const priceLabel = (price) => (price ? `${price} ₽` : "Бесплатно");

// Куда уйдёт приглашение — так же решает сервер (invite_chat_id в server/main.py)
function hasChat() {
  const me = state.me;
  if (!me) return inMax; // /api/me не ответил — в МАКС почти всегда есть чат
  return Boolean((me.chat?.id && me.chat.type !== "DIALOG") || /^chat-?\d+$/.test(me.start_param || ""));
}

// ---------- Экраны ----------

// Стрелка рисунком, а не символом «←»: у символа свои отступы шрифта, и он съезжает с центра
const BACK_ICON = `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"
  stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>`;

function header({ backButton = true, title = "Вечер", extra = "" } = {}) {
  // Внутри МАКС «Назад» — системная кнопка сверху, свою рисуем только в браузере
  const showBack = backButton && !inMax;
  return `
    <header class="top">
      ${showBack ? `<button class="icon-btn" data-action="back" aria-label="Назад">${BACK_ICON}</button>` : ""}
      <span class="top-title">${title}</span>
      ${extra}
    </header>`;
}

function moodScreen() {
  const tiles = MOODS.map(
    (mood) => `
      <button class="tile ${mood.wild ? "tile-wild" : ""}" style="--mood:${mood.color};--ink:${mood.ink}"
              data-action="mood" data-id="${mood.id}">
        <span class="tile-emoji">${mood.emoji}</span>
        <span class="tile-title">${mood.title}</span>
        <span class="tile-hint">${mood.hint}</span>
      </button>`
  ).join("");
  return `
    ${header({ backButton: false, extra: `<span class="chip-city">Казань</span>` })}
    <section class="screen">
      <h1>Какое у тебя настроение?</h1>
      <p class="lead">Выбери одно — подберём три варианта на вечер, а не сто.</p>
      <div class="tiles">${tiles}</div>
      <p class="note">Демо: события, даты и цены условные.</p>
    </section>`;
}

function setupScreen() {
  const mood = moodById(state.mood);
  const days = DAYS.map(
    (day) => `
      <button class="chip ${state.day === day.id ? "is-on" : ""}" data-action="day" data-id="${day.id}">
        ${day.title}
      </button>`
  ).join("");
  return `
    <div class="mood-page" style="--mood:${mood.color};--ink:${mood.ink}">
      ${header()}
      <section class="screen">
        <div class="mood-head">
          <span class="mood-emoji">${mood.emoji}</span>
          <h1>${mood.title}</h1>
        </div>
        <h2>Когда?</h2>
        <div class="chips">${days}</div>
        <h2>Деньги</h2>
        <button class="switch-row" data-action="budget" role="switch" aria-checked="${state.budget}">
          <span>
            <span class="switch-title">Бюджет поджимает</span>
            <span class="switch-hint">Сначала то, что до ${BUDGET_MAX} ₽</span>
          </span>
          <span class="switch ${state.budget ? "is-on" : ""}"></span>
        </button>
      </section>
      <div class="bar">
        <button class="btn btn-ink" data-action="show">Показать 3 варианта</button>
      </div>
    </div>`;
}

function resultCard(result, index) {
  const { event } = result;
  const mood = moodById(result.mood);
  const top = index === 0;
  // В «Удиви меня» у каждого события своё настроение — подписываем его
  const moodTag = state.mood === "wild" ? `<span class="tag">${mood.emoji} ${mood.title}</span>` : "";
  const budgetTag = result.over_budget ? `<span class="tag tag-warn">дороже ${BUDGET_MAX} ₽</span>` : "";
  return `
    <article class="card ${top ? "card-top" : ""}">
      ${top ? `<span class="card-label">Мы бы пошли сюда</span>` : ""}
      <span class="card-when">${whenLabel(event)}</span>
      <h3>${esc(event.title)}</h3>
      <span class="card-place">${esc(event.place)}</span>
      <p class="card-why">${esc(event.why)}</p>
      ${moodTag || budgetTag ? `<div class="tags">${moodTag}${budgetTag}</div>` : ""}
      <div class="card-foot">
        <span class="price">${priceLabel(event.price)}</span>
        <button class="btn-small" data-action="choose" data-id="${esc(event.id)}">Выбрать</button>
      </div>
    </article>`;
}

function resultsScreen() {
  const mood = moodById(state.mood);
  let body;
  if (state.loading) {
    body = `<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div>`;
  } else if (state.error) {
    body = `
      <div class="empty">
        <p>${esc(state.error)}</p>
        <button class="btn btn-accent" data-action="retry">Попробовать ещё раз</button>
      </div>`;
  } else if (!state.results.length) {
    body = `
      <div class="empty">
        <span class="empty-emoji">🫥</span>
        <p>На этот день под такое настроение ничего не нашлось. Попробуй другой день.</p>
        <button class="btn btn-accent" data-action="back">Выбрать другой день</button>
      </div>`;
  } else {
    body = state.results.map(resultCard).join("");
  }
  return `
    ${header()}
    <section class="screen" style="--mood:${mood.color};--ink:${mood.ink}">
      <h1>${mood.emoji} ${mood.title}</h1>
      <p class="lead">${DAYS.find((d) => d.id === state.day).title}${state.budget ? ` · до ${BUDGET_MAX} ₽` : ""}</p>
      ${body}
    </section>
    <div class="bar">
      <button class="btn btn-ghost" data-action="restart">Другое настроение</button>
    </div>`;
}

function planScreen() {
  const event = state.event;
  const mood = moodById(state.mood);
  const chat = hasChat();
  return `
    ${header({ title: "План" })}
    <section class="screen" style="--mood:${mood.color};--ink:${mood.ink}">
      <article class="card card-top card-plan">
        <h3>${esc(event.title)}</h3>
        <p class="card-why">${esc(event.why)}</p>
      </article>
      <dl class="facts">
        <div><dt>Где</dt><dd>${esc(event.place)}</dd></div>
        <div><dt>Когда</dt><dd>${whenLabel(event)}</dd></div>
        <div><dt>Цена</dt><dd>${priceLabel(event.price)}</dd></div>
      </dl>
      ${event.ticket_url ? `<button class="btn btn-ghost" data-action="ticket">Билеты на сайте организатора ↗</button>` : ""}
      ${state.error ? `<p class="error">${esc(state.error)}</p>` : ""}
    </section>
    <div class="bar">
      <p class="bar-hint">${
        chat
          ? "Бот пришлёт в чат карточку «Иду / Может / Не могу»"
          : "Бот пришлёт карточку тебе в чат с ним — её можно переслать друзьям"
      }</p>
      <button class="btn btn-accent" data-action="invite" ${state.loading ? "disabled" : ""}>
        ${state.loading ? "Отправляем…" : chat ? "Позвать чат" : "Отправить себе"}
      </button>
    </div>`;
}

function inviteScreen() {
  const event = state.event;
  const columns = ANSWERS.map((answer) => {
    const names = state.answers.filter((a) => a.answer === answer.id).map((a) => a.name);
    return `
      <div class="count count-${answer.id}">
        <span class="count-num">${names.length}</span>
        <span class="count-title">${answer.title}</span>
        <span class="count-names">${names.map(esc).join(", ") || "—"}</span>
      </div>`;
  }).join("");
  const status = state.invite.sent
    ? `<p class="lead">Карточка уже в чате. Ответы появятся здесь сами.</p>`
    : `<p class="note note-warn">Бот выключен (локальный запуск): приглашение сохранено, но в чат не отправлено.</p>`;
  return `
    ${header({ title: "Приглашение" })}
    <section class="screen">
      <div class="sent-badge">✓</div>
      <h1>Позвали!</h1>
      ${status}
      <article class="card">
        <span class="card-when">${whenLabel(event)}</span>
        <h3>${esc(event.title)}</h3>
        <span class="card-place">${esc(event.place)}</span>
      </article>
      <div class="counts">${columns}</div>
      <p class="note"><span class="live-dot"></span>Обновляется само</p>
    </section>
    <div class="bar">
      <button class="btn btn-accent" data-action="done">Готово</button>
    </div>`;
}

const SCREENS = { mood: moodScreen, setup: setupScreen, results: resultsScreen, plan: planScreen, invite: inviteScreen };

function render() {
  const app = document.getElementById("app");
  app.innerHTML = SCREENS[state.screen]();
  app.dataset.screen = state.screen;
  // Системная кнопка «Назад» в МАКС: показываем везде, кроме первого экрана
  if (state.history.length) WebApp?.BackButton?.show?.();
  else WebApp?.BackButton?.hide?.();
}

// ---------- Запуск ----------

WebApp?.ready?.();
WebApp?.BackButton?.onClick?.(back);
render();
getMe()
  .then((me) => (state.me = me))
  .catch(() => {}); // не страшно: без /api/me просто подпись кнопки будет общей
