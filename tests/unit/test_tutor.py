"""Unit tests for the LLM tutor module."""

from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from chenedusys.ai.tutor import (
    LLMTutor,
    LLMProvider,
    TutorResponse,
    SYSTEM_PROMPT,
    _encode_image,
    _parse_response,
)


class _mock_module:
    """Context manager to temporarily inject a mock module into sys.modules."""

    def __init__(self, name, mock):
        self._name = name
        self._mock = mock
        self._original = None

    def __enter__(self):
        import sys
        self._original = sys.modules.get(self._name)
        sys.modules[self._name] = self._mock
        return self

    def __exit__(self, *args):
        import sys
        if self._original is not None:
            sys.modules[self._name] = self._original
        else:
            sys.modules.pop(self._name, None)


def _sample_response() -> dict:
    return {
        "concepts": ["quadratic equations", "factoring", "Vieta's formulas"],
        "difficulty": "Medium",
        "difficulty_level": 3,
        "hints": [
            "Try to factor the quadratic expression.",
            "Look for two numbers that multiply to give the constant term and add to give the linear coefficient.",
            "The factors are (x+4) and (x-1).",
        ],
        "solution": "Step 1: Factor x^2 + 3x - 4 = (x+4)(x-1) = 0.\nStep 2: Set each factor to zero: x = -4 or x = 1.",
    }


class TestTutorResponse:

    def test_is_empty_when_no_content(self):
        resp = TutorResponse()
        assert resp.is_empty

    def test_is_not_empty_with_concepts(self):
        resp = TutorResponse(concepts=["algebra"])
        assert not resp.is_empty

    def test_is_not_empty_with_solution(self):
        resp = TutorResponse(solution="x = 5")
        assert not resp.is_empty


class TestParseResponse:

    def test_parse_valid_json(self):
        data = _sample_response()
        resp = _parse_response(json.dumps(data))
        assert resp.concepts == data["concepts"]
        assert resp.difficulty == "Medium"
        assert resp.difficulty_level == 3
        assert len(resp.hints) == 3
        assert "Step 1" in resp.solution

    def test_parse_json_in_code_fence(self):
        data = _sample_response()
        text = f"```json\n{json.dumps(data)}\n```"
        resp = _parse_response(text)
        assert resp.concepts == data["concepts"]

    def test_parse_json_in_plain_code_fence(self):
        data = _sample_response()
        text = f"```\n{json.dumps(data)}\n```"
        resp = _parse_response(text)
        assert resp.concepts == data["concepts"]

    def test_parse_invalid_json_returns_raw(self):
        text = "This is not JSON at all"
        resp = _parse_response(text)
        assert resp.is_empty
        assert resp.raw_response == text

    def test_parse_partial_json(self):
        data = {"concepts": ["algebra"]}
        resp = _parse_response(json.dumps(data))
        assert resp.concepts == ["algebra"]
        assert resp.difficulty == ""
        assert resp.hints == []

    def test_parse_with_whitespace(self):
        data = _sample_response()
        text = f"  \n  {json.dumps(data)}  \n  "
        resp = _parse_response(text)
        assert resp.concepts == data["concepts"]


class TestEncodeImage:

    def test_encode_produces_string(self):
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        result = _encode_image(img)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_is_valid_base64(self):
        import base64
        img = np.ones((50, 50, 3), dtype=np.uint8) * 128
        result = _encode_image(img)
        decoded = base64.b64decode(result)
        assert len(decoded) > 0


class TestLLMTutor:

    def test_default_model_anthropic(self):
        tutor = LLMTutor(provider=LLMProvider.ANTHROPIC)
        assert "claude" in tutor.model

    def test_default_model_openai(self):
        tutor = LLMTutor(provider=LLMProvider.OPENAI)
        assert "gpt" in tutor.model

    def test_not_configured_without_key(self):
        tutor = LLMTutor()
        assert not tutor.is_configured

    def test_configured_with_key(self):
        tutor = LLMTutor(api_key="test-key")
        assert tutor.is_configured

    def test_configure_updates_key(self):
        tutor = LLMTutor()
        tutor.configure(api_key="new-key")
        assert tutor.is_configured

    def test_configure_updates_model(self):
        tutor = LLMTutor()
        tutor.configure(model="custom-model")
        assert tutor.model == "custom-model"

    def test_configure_updates_provider(self):
        tutor = LLMTutor(provider=LLMProvider.ANTHROPIC)
        tutor.configure(provider=LLMProvider.OPENAI)
        assert tutor.provider == LLMProvider.OPENAI

    @pytest.mark.asyncio
    async def test_tutor_image_without_key_returns_empty(self):
        tutor = LLMTutor()
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        resp = await tutor.tutor_image(img)
        assert resp.is_empty

    @pytest.mark.asyncio
    async def test_tutor_question_without_key_returns_empty(self):
        tutor = LLMTutor()
        img = np.zeros((100, 100, 3), dtype=np.uint8)
        resp = await tutor.tutor_question(img)
        assert resp.is_empty

    @pytest.mark.asyncio
    async def test_anthropic_call_with_mock(self):
        """Test Anthropic API call with a mocked client."""
        import sys
        from unittest.mock import MagicMock, AsyncMock

        tutor = LLMTutor(
            provider=LLMProvider.ANTHROPIC,
            api_key="fake-key",
        )

        mock_response = _sample_response()
        mock_response_text = json.dumps(mock_response)

        mock_content = MagicMock()
        mock_content.text = mock_response_text
        mock_message = MagicMock()
        mock_message.content = [mock_content]
        mock_create = AsyncMock(return_value=mock_message)
        mock_messages = MagicMock()
        mock_messages.create = mock_create
        mock_client = MagicMock()
        mock_client.messages = mock_messages
        mock_anthropic = MagicMock()
        mock_anthropic.AsyncAnthropic = MagicMock(return_value=mock_client)

        with _mock_module("anthropic", mock_anthropic):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            resp = await tutor.tutor_image(img)
            assert not resp.is_empty
            assert resp.concepts == mock_response["concepts"]
            assert resp.difficulty == "Medium"

    @pytest.mark.asyncio
    async def test_openai_call_with_mock(self):
        """Test OpenAI API call with a mocked client."""
        import sys
        from unittest.mock import MagicMock, AsyncMock

        tutor = LLMTutor(
            provider=LLMProvider.OPENAI,
            api_key="fake-key",
        )

        mock_response = _sample_response()
        mock_response_text = json.dumps(mock_response)

        mock_message = MagicMock()
        mock_message.content = mock_response_text
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_create = AsyncMock(return_value=MagicMock(choices=[mock_choice]))
        mock_completions = MagicMock()
        mock_completions.create = mock_create
        mock_chat = MagicMock()
        mock_chat.completions = mock_completions
        mock_client = MagicMock()
        mock_client.chat = mock_chat
        mock_openai = MagicMock()
        mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)

        with _mock_module("openai", mock_openai):
            img = np.zeros((100, 100, 3), dtype=np.uint8)
            resp = await tutor.tutor_image(img)
            assert not resp.is_empty
            assert resp.concepts == mock_response["concepts"]


class TestSystemPrompt:

    def test_prompt_mentions_amc12(self):
        assert "AMC 12" in SYSTEM_PROMPT

    def test_prompt_requires_json(self):
        assert "JSON" in SYSTEM_PROMPT

    def test_prompt_includes_concepts(self):
        assert "concepts" in SYSTEM_PROMPT

    def test_prompt_includes_hints(self):
        assert "hints" in SYSTEM_PROMPT

    def test_prompt_includes_solution(self):
        assert "solution" in SYSTEM_PROMPT
