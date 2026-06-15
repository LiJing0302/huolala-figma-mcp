"""
VLM 多模态调用 Provider：通过环境变量选择后端，统一返回 {ret, data: {output}} 格式。
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import requests

_logger = logging.getLogger(__name__)

_JSON_SUFFIX = "\n只输出 JSON 对象，不要 markdown 代码块或额外说明。"


def is_vlm_enabled() -> bool:
    provider = os.environ.get("MDAP_VLM_PROVIDER", "none").strip().lower()
    return provider not in ("", "none")


def get_vlm_timeout(default: int = 90) -> int:
    """VLM HTTP 调用与 pipeline 等待异步任务的超时（秒），由 MDAP_VLM_TIMEOUT 控制。"""
    raw = os.environ.get("MDAP_VLM_TIMEOUT", "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _success(content: str) -> dict:
    return {"ret": 0, "data": {"output": content}}


def _failure(msg: str, ret: int = -1) -> dict:
    return {"ret": ret, "msg": msg, "data": {"output": ""}}


class VlmProvider(Protocol):
    def invoke(self, text: str, image: str) -> dict:
        ...


class NoneVlmProvider:
    def invoke(self, text: str, image: str) -> dict:
        _logger.info("VLM 未启用（MDAP_VLM_PROVIDER=none）")
        return _failure("VLM provider disabled")


class OpenAICompatibleVlmProvider:
    """OpenAI Chat Completions 兼容接口（OpenAI / Azure / 通义 / DeepSeek 等）。"""

    def __init__(self) -> None:
        self.api_key = os.environ.get("MDAP_VLM_API_KEY", "").strip()
        self.base_url = os.environ.get("MDAP_VLM_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/")
        self.model = os.environ.get("MDAP_VLM_MODEL", "gpt-4o").strip()
        self.timeout = get_vlm_timeout()

    def invoke(self, text: str, image: str) -> dict:
        if not self.api_key:
            return _failure("未配置 MDAP_VLM_API_KEY")

        url = f"{self.base_url}/chat/completions"
        payload: dict = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text + _JSON_SUFFIX},
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                }
            ],
        }
        if os.environ.get("MDAP_VLM_JSON_MODE", "true").strip().lower() in ("1", "true", "yes"):
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not content:
                return _failure("VLM 返回空内容")
            return _success(content)
        except Exception as exc:
            _logger.error("OpenAI 兼容 VLM 调用失败: %s", exc, exc_info=True)
            return _failure(str(exc))


class WorkflowVlmProvider:
    """可选：兼容旧版 workflow/run 协议（URL 与 workflow_id 均通过环境变量配置）。"""

    def __init__(self) -> None:
        self.api_url = os.environ.get("MDAP_VLM_WORKFLOW_URL", "").strip()
        self.workflow_id = os.environ.get("MDAP_VLM_WORKFLOW_ID", "").strip()
        self.user_id = os.environ.get("MDAP_VLM_USER_ID", "anonymous").strip()
        self.server_app_id = os.environ.get("MDAP_VLM_SERVER_APP_ID", "").strip()
        self.timeout = get_vlm_timeout()

    def invoke(self, text: str, image: str) -> dict:
        if not self.api_url or not self.workflow_id:
            return _failure("未配置 MDAP_VLM_WORKFLOW_URL 或 MDAP_VLM_WORKFLOW_ID")

        payload = {
            "workflow_id": self.workflow_id,
            "enable_heartbeat": False,
            "user_id": self.user_id,
            "parameters": {
                "BOT_USER_INPUT": text,
                "image": image,
            },
        }
        headers = {"Content-Type": "application/json"}
        if self.server_app_id:
            headers["Server-App-Id"] = self.server_app_id

        try:
            response = requests.post(self.api_url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            _logger.error("Workflow VLM 调用失败: %s", exc, exc_info=True)
            return _failure(str(exc))


_provider: VlmProvider | None = None


def get_vlm_provider() -> VlmProvider:
    global _provider
    if _provider is not None:
        return _provider

    kind = os.environ.get("MDAP_VLM_PROVIDER", "none").strip().lower()
    if kind in ("", "none"):
        _provider = NoneVlmProvider()
    elif kind in ("openai", "openai_compatible"):
        _provider = OpenAICompatibleVlmProvider()
    elif kind == "workflow":
        _provider = WorkflowVlmProvider()
    else:
        raise ValueError(
            f"不支持的 MDAP_VLM_PROVIDER={kind!r}，可选: none, openai, openai_compatible, workflow"
        )
    return _provider
