# -*- coding: utf-8 -*-
"""Vertex Gemini client. Never falls back to the Firestore service account."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from copilot.rates import PINNED_LOCATION, PINNED_MODEL_ID, THINKING_LEVEL


class ModelError(RuntimeError):
    def __init__(self, message: str, *, dispatched: bool):
        super().__init__(message)
        self.dispatched = dispatched


@dataclass
class ModelResult:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    thoughts_tokens: int | None
    total_tokens: int | None


class GeminiClient:
    def __init__(self, env: dict[str, str] | None = None):
        source = os.environ if env is None else env
        self.project = (source.get("GOOGLE_CLOUD_PROJECT") or "").strip()
        self.location = (source.get("GOOGLE_CLOUD_LOCATION") or PINNED_LOCATION).strip()
        self.model_id = (source.get("COPILOT_MODEL_ID") or PINNED_MODEL_ID).strip()
        self.credentials_json = (source.get("COPILOT_GOOGLE_CREDENTIALS_JSON") or "").strip()
        self.credentials_file = (source.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        self.configured = bool(self.project and self.model_id == PINNED_MODEL_ID and (self.credentials_json or self.credentials_file))

    def generate(self, *, system: str, user: str, max_output_tokens: int) -> ModelResult:
        if not self.configured:
            raise ModelError("Gemini credentials are not configured", dispatched=False)
        if self.model_id != PINNED_MODEL_ID or self.location != PINNED_LOCATION:
            raise ModelError("model or location does not match the pinned rate card", dispatched=False)
        try:
            from google import genai
            from google.genai import types
            from google.oauth2 import service_account
        except Exception as exc:
            raise ModelError("google-genai SDK is not installed", dispatched=False) from exc
        credentials = None
        if self.credentials_json:
            info = json.loads(self.credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
        try:
            client = genai.Client(
                vertexai=True,
                project=self.project,
                location=self.location,
                credentials=credentials,
            )
            # Request is about to be sent. Later failures keep the reservation.
            dispatched = True
            response = client.models.generate_content(
                model=self.model_id,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=0.2,
                    max_output_tokens=max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                ),
            )
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(str(exc), dispatched=locals().get("dispatched", False)) from exc
        usage = getattr(response, "usage_metadata", None)
        prompt = getattr(usage, "prompt_token_count", None) if usage else None
        candidates = getattr(usage, "candidates_token_count", None) if usage else None
        thoughts = getattr(usage, "thoughts_token_count", None) if usage else None
        total = getattr(usage, "total_token_count", None) if usage else None
        return ModelResult(
            text=getattr(response, "text", "") or "",
            input_tokens=prompt,
            output_tokens=candidates,
            thoughts_tokens=thoughts,
            total_tokens=total,
        )
