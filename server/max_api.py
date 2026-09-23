"""Тонкая обёртка над Bot API МАКС. Документация: https://dev.max.ru/docs-api"""
import httpx

BASE_URL = "https://platform-api.max.ru"


class MaxApi:
    def __init__(self, token: str):
        # timeout больше, чем long polling (30 сек), иначе запрос оборвётся раньше ответа
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": token},
            timeout=httpx.Timeout(45.0),
        )

    async def close(self) -> None:
        await self._http.aclose()

    async def _call(self, method: str, path: str, *, params=None, json=None) -> dict:
        resp = await self._http.request(method, path, params=params, json=json)
        resp.raise_for_status()
        return resp.json()

    async def me(self) -> dict:
        return await self._call("GET", "/me")

    async def get_updates(self, marker: int | None = None, timeout: int = 30) -> dict:
        """Long polling: ждёт до `timeout` секунд, пока в чатах что-то произойдёт."""
        params = {"timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        return await self._call("GET", "/updates", params=params)

    async def send_message(self, chat_id: int, text: str, buttons: list | None = None) -> dict:
        return await self._call("POST", "/messages", params={"chat_id": chat_id}, json=message_body(text, buttons))

    async def answer_callback(
        self,
        callback_id: str,
        *,
        text: str | None = None,
        buttons: list | None = None,
        notification: str | None = None,
    ) -> dict:
        """Ответ на нажатие кнопки. Если передать text — исходное сообщение заменится на новое."""
        body: dict = {}
        if text is not None:
            body["message"] = message_body(text, buttons)
        if notification:
            body["notification"] = notification
        return await self._call("POST", "/answers", params={"callback_id": callback_id}, json=body)


def message_body(text: str, buttons: list | None = None) -> dict:
    body: dict = {"text": text}
    if buttons:
        body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
    return body


def callback_button(text: str, payload: str) -> dict:
    return {"type": "callback", "text": text, "payload": payload}


def link_button(text: str, url: str) -> dict:
    return {"type": "link", "text": text, "url": url}
