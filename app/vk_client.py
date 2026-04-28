from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from typing import Any

import requests

from app.config import settings

logger = logging.getLogger(__name__)


class VKApiError(RuntimeError):
    def __init__(self, method: str, error: dict[str, Any]):
        self.method = method
        self.error = error
        code = error.get("error_code")
        message = error.get("error_msg")
        super().__init__(f"VK API error in {method}: {code} {message}")

    @property
    def code(self) -> int | None:
        raw = self.error.get("error_code")
        return int(raw) if isinstance(raw, int) or str(raw).isdigit() else None


@dataclass
class SentMessage:
    message_id: int | None = None
    conversation_message_id: int | None = None
    raw: Any = None


class VKClient:
    def __init__(self, token: str | None = None, api_version: str | None = None) -> None:
        self.token = token if token is not None else settings.vk_group_token
        self.api_version = api_version or settings.vk_api_version
        self.base_url = "https://api.vk.com/method"

    def enabled(self) -> bool:
        return bool(self.token)

    def call(self, method: str, **params: Any) -> Any:
        if not self.token:
            raise RuntimeError("VK_GROUP_TOKEN is not configured")
        payload = {**params, "access_token": self.token, "v": self.api_version}
        url = f"{self.base_url}/{method}"
        response = requests.post(url, data=payload, timeout=12)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            raise VKApiError(method, data["error"])
        return data.get("response")

    def send_message(
        self,
        peer_id: int,
        message: str,
        keyboard: str | None = None,
        disable_mentions: bool = True,
    ) -> SentMessage:
        params: dict[str, Any] = {
            "peer_id": peer_id,
            "message": message,
            "random_id": random.randint(1, 2_147_483_647),
        }
        if disable_mentions:
            params["disable_mentions"] = 1
        if keyboard:
            params["keyboard"] = keyboard
        raw = self.call("messages.send", **params)
        return parse_sent_message(raw)

    def edit_message(
        self,
        peer_id: int,
        message: str,
        message_id: int | None = None,
        conversation_message_id: int | None = None,
        keyboard: str | None = None,
    ) -> Any:
        params: dict[str, Any] = {"peer_id": peer_id, "message": message}
        if message_id is not None:
            params["message_id"] = message_id
        if conversation_message_id is not None:
            params["conversation_message_id"] = conversation_message_id
        if keyboard is not None:
            params["keyboard"] = keyboard
        return self.call("messages.edit", **params)

    def answer_event(self, event_id: str, user_id: int, peer_id: int, text: str) -> None:
        try:
            event_data = json.dumps({"type": "show_snackbar", "text": text}, ensure_ascii=False)
            self.call(
                "messages.sendMessageEventAnswer",
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=event_data,
            )
        except Exception as exc:  # pragma: no cover - snackbar is non-critical
            logger.warning("Could not answer VK message event: %s", exc)


def parse_sent_message(raw: Any) -> SentMessage:
    if isinstance(raw, int):
        return SentMessage(message_id=raw, raw=raw)
    if isinstance(raw, dict):
        message_id = raw.get("message_id") or raw.get("id")
        conversation_message_id = raw.get("conversation_message_id")
        return SentMessage(
            message_id=int(message_id) if message_id is not None and str(message_id).isdigit() else None,
            conversation_message_id=int(conversation_message_id)
            if conversation_message_id is not None and str(conversation_message_id).isdigit()
            else None,
            raw=raw,
        )
    return SentMessage(raw=raw)


vk = VKClient()
