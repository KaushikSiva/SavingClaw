from __future__ import annotations

import os
from typing import Any, Dict, Optional

from google import genai
from google.genai import types


def google_search_answer(
    *, prompt: str, model: str = "gemini-2.5-flash"
) -> Dict[str, Any]:
    """Answer a question using Google Search grounding."""
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return {"status": "error", "error": "GOOGLE_API_KEY not set."}
    client = genai.Client(api_key=api_key)
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    config = types.GenerateContentConfig(tools=[grounding_tool])
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=config,
    )
    text = getattr(response, "text", None)
    return {"status": "success", "text": text}
