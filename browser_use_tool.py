from __future__ import annotations

import os
from typing import Any, Dict, Optional

from browser_use_sdk import BrowserUse


def run_browser_task(*, task: str, llm: Optional[str] = None) -> Dict[str, Any]:
    """Run a Browser Use task and return its output."""
    api_key = os.getenv("BROWSER_USE_API_KEY", "")
    if not api_key:
        return {"status": "error", "error": "BROWSER_USE_API_KEY not set."}
    client = BrowserUse(api_key=api_key)
    task_obj = client.tasks.create_task(task=task, llm=llm or "browser-use-llm")
    result = task_obj.complete()
    output = getattr(result, "output", None)
    return {"status": "success", "output": output}
