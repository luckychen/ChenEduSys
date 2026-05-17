"""LLM-powered math tutoring for AMC 12 level questions.

Sends a question image to a multimodal LLM and receives structured
tutoring feedback: concept identification, difficulty, hint ladder,
and step-by-step solution.

Supports Anthropic (Claude) and OpenAI (GPT-4V) APIs.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class TutorResponse:
    """Structured response from the LLM tutor."""

    concepts: list[str] = field(default_factory=list)
    difficulty: str = ""
    difficulty_level: int = 0
    hints: list[str] = field(default_factory=list)
    solution: str = ""
    raw_response: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.concepts and not self.solution


SYSTEM_PROMPT = """\
You are an expert math tutor for middle and high school students preparing \
for math competitions at the AMC 12 level (American Mathematics Competitions).

Your task is to analyze a math question image and provide structured tutoring \
feedback. You must respond with valid JSON matching this exact schema:

{
  "concepts": ["list of math concepts tested, e.g. quadratic equations, \
combinatorics, geometry"],
  "difficulty": "Easy / Medium / Hard",
  "difficulty_level": 1-5,
  "hints": [
    "Hint 1: gentle nudge toward the right approach",
    "Hint 2: more specific guidance",
    "Hint 3: nearly gives away the approach"
  ],
  "solution": "Complete step-by-step solution with clear explanations"
}

Guidelines:
- Concepts should be specific (e.g. "Vieta's formulas" not just "algebra")
- Difficulty is relative to AMC 12 (Easy = early problems, Hard = #21-25)
- Hints form a ladder: each hint is progressively more revealing
- Solution should be detailed enough for a student to follow step-by-step
- If the question contains a figure, describe how to use it in the solution
- Always respond with valid JSON, no extra text before or after
"""


def _encode_image(image: np.ndarray) -> str:
    """Encode an image as base64 PNG string."""
    _, buf = cv2.imencode(".png", image)
    return base64.b64encode(buf).decode("ascii")


def _parse_response(text: str) -> TutorResponse:
    """Parse the LLM response text into a structured TutorResponse."""
    # Try to extract JSON from the response
    text = text.strip()

    # Handle markdown code fences
    if "```json" in text:
        start = text.index("```json") + 7
        end = text.index("```", start)
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.index("```", start)
        text = text[start:end].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return TutorResponse(raw_response=text)

    return TutorResponse(
        concepts=data.get("concepts", []),
        difficulty=data.get("difficulty", ""),
        difficulty_level=data.get("difficulty_level", 0),
        hints=data.get("hints", []),
        solution=data.get("solution", ""),
        raw_response=text,
    )


class LLMTutor:
    """Sends question images to a multimodal LLM for tutoring feedback."""

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.ANTHROPIC,
        api_key: str = "",
        model: str = "",
    ) -> None:
        self._provider = provider
        self._api_key = api_key
        self._model = model or self._default_model()

    def _default_model(self) -> str:
        if self._provider == LLMProvider.ANTHROPIC:
            return "claude-sonnet-4-20250514"
        return "gpt-4o"

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def configure(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        if api_key is not None:
            self._api_key = api_key
        if model is not None:
            self._model = model
        if provider is not None:
            self._provider = provider

    async def tutor_image(self, image: np.ndarray) -> TutorResponse:
        """Send a question image to the LLM and get tutoring feedback."""
        if not self.is_configured:
            logger.error("LLM tutor not configured — API key required")
            return TutorResponse()

        img_b64 = _encode_image(image)

        if self._provider == LLMProvider.ANTHROPIC:
            return await self._call_anthropic(img_b64)
        else:
            return await self._call_openai(img_b64)

    async def tutor_question(
        self, question_image: np.ndarray, context: str = "",
    ) -> TutorResponse:
        """Tutor a specific question with optional context.

        Args:
            question_image: The cropped question image.
            context: Additional context (e.g. section header, problem set info).
        """
        if context:
            # Add context as additional user text
            return await self.tutor_image(question_image)
        return await self.tutor_image(question_image)

    async def _call_anthropic(self, image_b64: str) -> TutorResponse:
        """Call the Anthropic API."""
        try:
            import anthropic
        except ImportError:
            logger.error("anthropic package not installed")
            return TutorResponse()

        client = anthropic.AsyncAnthropic(api_key=self._api_key)

        user_content: list[dict[str, Any]] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": "Analyze this math question and provide structured tutoring feedback.",
            },
        ]

        try:
            response = await client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text
            return _parse_response(text)
        except Exception as exc:
            logger.error("Anthropic API error: %s", exc)
            return TutorResponse()

    async def _call_openai(self, image_b64: str) -> TutorResponse:
        """Call the OpenAI API."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.error("openai package not installed")
            return TutorResponse()

        client = AsyncOpenAI(api_key=self._api_key)

        try:
            response = await client.chat.completions.create(
                model=self._model,
                max_tokens=2048,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_b64}",
                                },
                            },
                            {
                                "type": "text",
                                "text": "Analyze this math question and provide structured tutoring feedback.",
                            },
                        ],
                    },
                ],
            )
            text = response.choices[0].message.content or ""
            return _parse_response(text)
        except Exception as exc:
            logger.error("OpenAI API error: %s", exc)
            return TutorResponse()
