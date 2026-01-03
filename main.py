from __future__ import annotations

import json
import os
import re
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.adk.agents import LlmAgent

from browser_use_tool import run_browser_task
from generate_image import generate_image_from_synopsis
from google_search_tool import google_search_answer
from gmail_read import read_today_emails
from gmaps_grounding import ground_location
from sadtalker_generate import generate_video_from_prompt
from tts_generic import list_voices, speak
from video_generate import generate_video
from video_postprocess import (
    append_image_and_endcard,
    concat_videos,
    concat_videos_many,
)
from youtube_read import get_categorized_videos
from youtube_upload import upload_video

load_dotenv()


_tool_event_sink: ContextVar[Optional[callable]] = ContextVar(
    "tool_event_sink", default=None
)


def set_tool_event_sink(sink):
    return _tool_event_sink.set(sink)


def reset_tool_event_sink(token) -> None:
    _tool_event_sink.reset(token)


def _emit_tool_event(payload: Dict[str, Any]) -> None:
    sink = _tool_event_sink.get()
    if sink:
        sink(payload)


def _emit_tool_call(tool: str, payload: Dict[str, Any]) -> None:
    _emit_tool_event({"type": "tool_call", "tool": tool, "input": payload})


def _emit_tool_result(tool: str, result: Dict[str, Any]) -> None:
    _emit_tool_event({"type": "tool_result", "tool": tool, "output": result})


def tool_generate_image(
    *,
    description: str,
    model: Optional[str] = None,
    out_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a single image from a text description."""
    tool_name = "tool_generate_image"
    _emit_tool_call(
        tool_name,
        {"description": description, "model": model, "out_path": out_path},
    )
    model_name = model or os.getenv("IMAGE_MODEL", "models/gemini-2.5-flash-image-preview")
    out = out_path or "generated_image.png"
    try:
        path = generate_image_from_synopsis(
            synopsis=description, model_name=model_name, out_path=out
        )
        result = {"status": "success", "path": path, "model": model_name}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_generate_video(
    *,
    description: str,
    image_url: str,
    duration_seconds: int = 8,
    model: Optional[str] = None,
    timeout: int = 180,
    output_dir: str = "generated",
    title: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a short video from a description and reference image URL."""
    tool_name = "tool_generate_video"
    _emit_tool_call(
        tool_name,
        {
            "description": description,
            "image_url": image_url,
            "duration_seconds": duration_seconds,
            "model": model,
            "timeout": timeout,
            "output_dir": output_dir,
            "title": title,
        },
    )
    model_name = model or os.getenv("FAL_MODEL", "")
    if not model_name:
        result = {"status": "error", "error": "FAL_MODEL not set and no model provided."}
        _emit_tool_result(tool_name, result)
        return result
    try:
        result = generate_video(
            description=description,
            image_url=image_url,
            duration_seconds=duration_seconds,
            fal_api_key=os.getenv("FAL_API_KEY", ""),
            model=model_name,
            timeout=timeout,
            output_dir=output_dir,
            title=title,
        )
        result["status"] = "success"
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_tts_list_voices(*, provider: str = "elevenlabs") -> Dict[str, Any]:
    """List available voices for the selected TTS provider."""
    tool_name = "tool_tts_list_voices"
    _emit_tool_call(tool_name, {"provider": provider})
    try:
        voices = list_voices(provider)
        result = {"status": "success", "voices": voices, "provider": provider}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_tts_speak(
    *,
    text: str,
    voice_id: str,
    provider: str = "elevenlabs",
    model_id: Optional[str] = None,
    output_path: Optional[str] = None,
    play_audio: bool = False,
    voice_settings: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Generate speech audio from text."""
    tool_name = "tool_tts_speak"
    _emit_tool_call(
        tool_name,
        {
            "text": text,
            "voice_id": voice_id,
            "provider": provider,
            "model_id": model_id,
            "output_path": output_path,
            "play_audio": play_audio,
            "voice_settings": voice_settings,
        },
    )
    try:
        path = speak(
            text,
            voice_id,
            provider=provider,
            model_id=model_id,
            output_path=Path(output_path) if output_path else None,
            play_audio=play_audio,
            voice_settings=voice_settings,
        )
        result = {"status": "success", "path": str(path), "provider": provider}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_sadtalker_generate(
    *,
    prompt: str,
    reference_image: Optional[str] = None,
    repo_path: Optional[str] = None,
    result_dir: Optional[str] = None,
    checkpoint_dir: Optional[str] = None,
    device: str = "cpu",
) -> Dict[str, Any]:
    """Run SadTalker to generate a talking-head video."""
    tool_name = "tool_sadtalker_generate"
    reference_image = reference_image or os.getenv("PHOTO_PATH", "")
    result_dir = result_dir or os.getenv("SADTALKER_RESULT_DIR")
    if not reference_image:
        result = {
            "status": "error",
            "error": "reference_image is required (or set PHOTO_PATH).",
        }
        _emit_tool_result(tool_name, result)
        return result
    _emit_tool_call(
        tool_name,
        {
            "prompt": prompt,
            "reference_image": reference_image,
            "repo_path": repo_path,
            "result_dir": result_dir,
            "checkpoint_dir": checkpoint_dir,
            "device": device,
        },
    )
    try:
        result = generate_video_from_prompt(
            prompt=prompt,
            reference_image=Path(reference_image),
            repo_path=Path(repo_path) if repo_path else None,
            result_dir=Path(result_dir) if result_dir else None,
            checkpoint_dir=Path(checkpoint_dir) if checkpoint_dir else None,
            device=device,
        )
        payload = {
            "status": "success",
            "video_path": str(result.video_path),
            "result_dir": str(result.result_dir),
        }
        _emit_tool_result(tool_name, payload)
        return payload
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_video_append_image_endcard(
    *,
    video_path: str,
    image_path: Optional[str] = None,
    out_path: Optional[str] = None,
    image_seconds: float = 2.0,
    endcard_seconds: float = 2.0,
    endcard_text: str = "Coming soon.",
) -> Dict[str, Any]:
    """Append a still image and a simple end card to a video."""
    tool_name = "tool_video_append_image_endcard"
    _emit_tool_call(
        tool_name,
        {
            "video_path": video_path,
            "image_path": image_path,
            "out_path": out_path,
            "image_seconds": image_seconds,
            "endcard_seconds": endcard_seconds,
            "endcard_text": endcard_text,
        },
    )
    try:
        vp = Path(video_path)
        out = Path(out_path) if out_path else vp.with_name("video_with_endcard.mp4")
        append_image_and_endcard(
            video_path=vp,
            image_path=Path(image_path) if image_path else None,
            out_path=out,
            image_seconds=image_seconds,
            endcard_seconds=endcard_seconds,
            endcard_text=endcard_text,
        )
        result = {"status": "success", "path": str(out)}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_video_concat(
    *, input1: str, input2: str, out_path: str
) -> Dict[str, Any]:
    """Concatenate two videos back-to-back."""
    tool_name = "tool_video_concat"
    _emit_tool_call(
        tool_name, {"input1": input1, "input2": input2, "out_path": out_path}
    )
    try:
        out = concat_videos(input1, input2, Path(out_path))
        result = {"status": "success", "path": out}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_video_concat_many(
    *, inputs: List[str], out_path: str
) -> Dict[str, Any]:
    """Concatenate multiple videos in order."""
    tool_name = "tool_video_concat_many"
    _emit_tool_call(tool_name, {"inputs": inputs, "out_path": out_path})
    try:
        out = concat_videos_many(inputs, Path(out_path))
        result = {"status": "success", "path": out}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_youtube_search(
    *,
    queries: List[str],
    max_results: int = 50,
    days: int = 2,
    categories: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, Any]:
    """Search YouTube and return categorized results."""
    tool_name = "tool_youtube_search"
    _emit_tool_call(
        tool_name,
        {
            "queries": queries,
            "max_results": max_results,
            "days": days,
            "categories": categories,
        },
    )
    try:
        data = get_categorized_videos(
            queries=queries, max_results=max_results, days=days, categories=categories
        )
        result = {"status": "success", "results": data}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_youtube_upload(
    *,
    access_token: str,
    file_path: str,
    title: str,
    description: str,
    privacy_status: str = "unlisted",
) -> Dict[str, Any]:
    """Upload a video to YouTube (resumable)."""
    tool_name = "tool_youtube_upload"
    _emit_tool_call(
        tool_name,
        {
            "access_token": "***",
            "file_path": file_path,
            "title": title,
            "description": description,
            "privacy_status": privacy_status,
        },
    )
    try:
        data = upload_video(
            access_token=access_token,
            file_path=file_path,
            title=title,
            description=description,
            privacy_status=privacy_status,
        )
        result = {"status": "success", **data}
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_gmaps_grounding(
    *,
    query: str,
    api_key: Optional[str] = None,
    include_details: bool = True,
    details_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Look up a location using Google Maps/Places APIs."""
    tool_name = "tool_gmaps_grounding"
    _emit_tool_call(
        tool_name,
        {
            "query": query,
            "api_key": "***" if api_key else None,
            "include_details": include_details,
            "details_fields": details_fields,
        },
    )
    try:
        result = ground_location(
            query=query,
            api_key=api_key,
            include_details=include_details,
            details_fields=details_fields,
        )
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_gmail_read_today(
    *,
    access_token: Optional[str] = None,
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    refresh_token: Optional[str] = None,
    user_id: str = "me",
    max_results: int = 10,
    query: Optional[str] = None,
    include_body: bool = False,
) -> Dict[str, Any]:
    """Read today's Gmail messages via the Gmail API."""
    tool_name = "tool_gmail_read_today"
    _emit_tool_call(
        tool_name,
        {
            "access_token": "***" if access_token else None,
            "client_id": "***" if client_id else None,
            "client_secret": "***" if client_secret else None,
            "refresh_token": "***" if refresh_token else None,
            "user_id": user_id,
            "max_results": max_results,
            "query": query,
            "include_body": include_body,
        },
    )
    try:
        result = read_today_emails(
            access_token=access_token,
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            user_id=user_id,
            max_results=max_results,
            query=query,
            include_body=include_body,
        )
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_browser_use(
    *,
    task: str,
    llm: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a browser-use task via the Browser Use SDK."""
    tool_name = "tool_browser_use"
    _emit_tool_call(tool_name, {"task": task, "llm": llm})
    try:
        result = run_browser_task(task=task, llm=llm)
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def tool_google_search(
    *,
    prompt: str,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Answer using Google Search grounding via Gemini."""
    tool_name = "tool_google_search"
    _emit_tool_call(tool_name, {"prompt": prompt, "model": model})
    try:
        result = google_search_answer(prompt=prompt, model=model or "gemini-2.5-flash")
        _emit_tool_result(tool_name, result)
        return result
    except Exception as exc:
        result = {"status": "error", "error": str(exc)}
        _emit_tool_result(tool_name, result)
        return result


def _event_to_payload(event) -> Optional[Dict[str, Any]]:
    payload: Dict[str, Any] = {
        "type": "agent_event",
        "author": getattr(event, "author", None),
        "partial": getattr(event, "partial", None),
        "turn_complete": getattr(event, "turnComplete", None),
        "final": bool(getattr(event, "is_final_response", lambda: False)()),
    }
    error_msg = getattr(event, "errorMessage", None)
    if error_msg:
        payload["error"] = error_msg
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    texts: List[str] = []
    if parts:
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(text)
            function_call = getattr(part, "functionCall", None)
            if function_call:
                payload["function_call"] = {
                    "name": getattr(function_call, "name", None),
                    "args": getattr(function_call, "args", None),
                }
            function_response = getattr(part, "functionResponse", None)
            if function_response:
                payload["function_response"] = {
                    "name": getattr(function_response, "name", None),
                    "response": getattr(function_response, "response", None),
                }
    if texts:
        payload["text"] = "".join(texts)
    if payload.get("text") or payload.get("error") or payload.get("function_call") or payload.get("function_response"):
        return payload
    if payload.get("final"):
        return payload
    return None


def _extract_gmaps_query(prompt: str) -> str:
    match = re.search(r'query\s*[:=]\s*"([^"]+)"', prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    match = re.search(r"query\s*[:=]\s*([^\n]+)", prompt, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    match = re.search(r'"([^"]+)"', prompt)
    if match:
        return match.group(1).strip()
    return prompt.strip()


def _summarize_gmaps_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"GMaps grounding failed: {result.get('error', 'Unknown error')}"
    summary = result.get("summary") or {}
    details = result.get("details") or {}
    name = summary.get("name") or details.get("name") or "Location"
    address = summary.get("formatted_address") or details.get("formatted_address")
    location = summary.get("location") or (details.get("geometry") or {}).get("location") or {}
    lat = location.get("lat")
    lng = location.get("lng")
    rating = summary.get("rating") or details.get("rating")
    total = summary.get("user_ratings_total") or details.get("user_ratings_total")
    website = details.get("website")
    hours = (details.get("opening_hours") or {}).get("weekday_text") or []

    parts = [str(name)]
    if address:
        parts.append(f"is located at {address}.")
    if lat is not None and lng is not None:
        parts.append(f"Coordinates: {lat}, {lng}.")
    if rating is not None and total is not None:
        parts.append(f"Rating: {rating} ({total} reviews).")
    elif rating is not None:
        parts.append(f"Rating: {rating}.")
    if website:
        parts.append(f"Website: {website}.")
    if hours:
        parts.append("Hours: " + "; ".join(str(item) for item in hours) + ".")
    return " ".join(parts)


def _summarize_gmail_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"Gmail read failed: {result.get('error', 'Unknown error')}"
    messages = result.get("messages") or []
    if not messages:
        return "No emails found for today."
    lines = ["Today's emails:"]
    for item in messages[:10]:
        subject = item.get("subject") or "(no subject)"
        sender = item.get("from") or "(unknown sender)"
        date = item.get("date") or ""
        lines.append(f"- {subject} — {sender} {date}".strip())
    return "\n".join(lines)


def _summarize_google_search_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"Google search failed: {result.get('error', 'Unknown error')}"
    text = result.get("text")
    if text:
        return str(text)
    return "Google search returned no text."


def _summarize_browser_use_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"Browser task failed: {result.get('error', 'Unknown error')}"
    output = result.get("output")
    if output:
        return str(output)
    return "Browser task completed with no output."


def _summarize_image_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"Image generation failed: {result.get('error', 'Unknown error')}"
    path = result.get("path") or result.get("output")
    model = result.get("model")
    if path and model:
        return f"Image generated at {path} using {model}."
    if path:
        return f"Image generated at {path}."
    return "Image generated."


def _summarize_video_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"Video generation failed: {result.get('error', 'Unknown error')}"
    path = result.get("path") or result.get("output") or result.get("video_path")
    if path:
        return f"Video generated at {path}."
    return "Video generated."


def _summarize_tts_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"TTS failed: {result.get('error', 'Unknown error')}"
    path = result.get("path") or result.get("output")
    if path:
        return f"Audio generated at {path}."
    return "Audio generated."


def _summarize_youtube_search_result(result: Dict[str, Any]) -> str:
    if result.get("status") != "success":
        return f"YouTube search failed: {result.get('error', 'Unknown error')}"
    return "YouTube search completed."


def _run_tool_chain(tools: List[str], prompt: str) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for tool in tools:
        if tool == "tool_gmaps_grounding":
            query = _extract_gmaps_query(prompt)
            output = tool_gmaps_grounding(query=query)
        elif tool == "tool_gmail_read_today":
            output = tool_gmail_read_today()
        elif tool == "tool_google_search":
            output = tool_google_search(prompt=prompt)
        elif tool == "tool_browser_use":
            output = tool_browser_use(task=prompt)
        elif tool == "tool_generate_image":
            output = tool_generate_image(description=prompt)
        elif tool == "tool_generate_video":
            image_url = _extract_first_url(prompt)
            if not image_url:
                output = {
                    "status": "error",
                    "error": "Video generation requires an image_url in the prompt.",
                }
            else:
                output = tool_generate_video(description=prompt, image_url=image_url)
        elif tool == "tool_tts_speak":
            voice_id = os.getenv("TTS_DEFAULT_VOICE_ID", "")
            if not voice_id:
                voices_result = tool_tts_list_voices()
                voices = voices_result.get("voices") if isinstance(voices_result, dict) else None
                if isinstance(voices, list) and voices:
                    voice_id = str(voices[0])
            if not voice_id:
                output = {
                    "status": "error",
                    "error": "TTS requires a voice_id. Set TTS_DEFAULT_VOICE_ID or provide one.",
                }
            else:
                text = _extract_quoted_text(prompt)
                output = tool_tts_speak(text=text, voice_id=voice_id)
        elif tool == "tool_youtube_search":
            output = tool_youtube_search(queries=[prompt])
        else:
            output = {"status": "error", "error": f"Unsupported tool in chain: {tool}"}
        results.append({"tool": tool, "output": output})
    return results


def _extract_quoted_text(prompt: str) -> str:
    match = re.search(r'"([^"]+)"', prompt)
    if match:
        return match.group(1).strip()
    return prompt.strip()


def _extract_first_url(prompt: str) -> Optional[str]:
    match = re.search(r"https?://\\S+", prompt)
    if match:
        return match.group(0).rstrip(").,")
    return None


def _select_tools_via_llm(prompt: str) -> List[str]:
    if os.getenv("USE_LLM_TOOL_ROUTER", "1") != "1":
        return []
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return []
    model = os.getenv("TOOL_ROUTER_MODEL", "gemini-2.0-flash")
    client = genai.Client(api_key=api_key)
    tool_list = [
        "tool_generate_image",
        "tool_generate_video",
        "tool_tts_list_voices",
        "tool_tts_speak",
        "tool_sadtalker_generate",
        "tool_video_append_image_endcard",
        "tool_video_concat",
        "tool_video_concat_many",
        "tool_youtube_search",
        "tool_youtube_upload",
        "tool_gmaps_grounding",
        "tool_gmail_read_today",
        "tool_browser_use",
        "tool_google_search",
    ]
    router_prompt = (
        "You are a tool router. Choose which tools to use for the user prompt.\n"
        f"Available tools: {', '.join(tool_list)}\n"
        "Return JSON only: {\"tools\": [\"tool_name\", ...]}.\n"
        f"User prompt: {prompt}"
    )
    try:
        response = client.models.generate_content(
            model=model,
            contents=router_prompt,
            config={"response_mime_type": "application/json"},
        )
        data = json.loads(getattr(response, "text", "") or "{}")
        tools = data.get("tools") or []
        if isinstance(tools, list):
            return [str(item) for item in tools if item]
    except Exception:
        return []
    return []


def stream_agent_events(prompt: str):
    """Yield agent events using the ADK InMemoryRunner."""
    from google.adk.runners import InMemoryRunner, types as runner_types

    runner = InMemoryRunner(agent=root_agent)
    strict_tool_mode = os.getenv("STRICT_TOOL_MODE", "1") == "1"
    router_tools = _select_tools_via_llm(prompt)
    prompt_lower = prompt.lower()
    requires_gmaps = (
        "gmaps" in prompt_lower
        or "grounding" in prompt_lower
        or "map" in prompt_lower
        or "maps" in prompt_lower
        or "location" in prompt_lower
        or "place" in prompt_lower
        or "tool_gmaps_grounding" in router_tools
    )
    requires_gmail = "gmail" in prompt_lower or "email" in prompt_lower
    requires_google_search = (
        "google search" in prompt_lower
        or "search google" in prompt_lower
        or "tool_google_search" in router_tools
    )
    requires_browser_use = (
        "browser use" in prompt_lower
        or "browser task" in prompt_lower
        or "chrome" in prompt_lower
        or "website" in prompt_lower
        or "tool_browser_use" in router_tools
    )
    requires_image = (
        "image" in prompt_lower
        or "draw" in prompt_lower
        or "picture" in prompt_lower
        or "tool_generate_image" in router_tools
    )
    requires_video = (
        "video" in prompt_lower
        or "animate" in prompt_lower
        or "tool_generate_video" in router_tools
    )
    requires_tts = (
        "tts" in prompt_lower
        or "speak" in prompt_lower
        or "audio" in prompt_lower
        or "voice" in prompt_lower
        or "tool_tts_speak" in router_tools
    )
    requires_youtube_search = (
        "youtube" in prompt_lower
        and ("search" in prompt_lower or "find" in prompt_lower or "trending" in prompt_lower)
    ) or "tool_youtube_search" in router_tools
    saw_gmaps = False
    saw_gmail = False
    saw_google_search = False
    saw_browser_use = False
    saw_generate_image = False
    saw_generate_video = False
    saw_tts = False
    saw_youtube_search = False
    saw_any_tool = False
    session_service = runner.session_service
    user_id = "local"
    session_id = "default"
    app_name = runner.app_name
    existing = session_service.get_session_sync(
        app_name=app_name, user_id=user_id, session_id=session_id
    )
    if existing is None:
        session_service.create_session_sync(
            app_name=app_name, user_id=user_id, session_id=session_id
        )
    message = runner_types.Content(
        role="user", parts=[runner_types.Part(text=prompt)]
    )
    for event in runner.run(user_id=user_id, session_id=session_id, new_message=message):
        payload = _event_to_payload(event)
        if payload:
            function_call = payload.get("function_call") or {}
            function_response = payload.get("function_response") or {}
            if function_call.get("name") == "tool_gmaps_grounding":
                saw_gmaps = True
                saw_any_tool = True
            if function_response.get("name") == "tool_gmaps_grounding":
                saw_gmaps = True
                saw_any_tool = True
            if function_call.get("name") == "tool_gmail_read_today":
                saw_gmail = True
                saw_any_tool = True
            if function_response.get("name") == "tool_gmail_read_today":
                saw_gmail = True
                saw_any_tool = True
            if function_call.get("name") == "tool_google_search":
                saw_google_search = True
                saw_any_tool = True
            if function_response.get("name") == "tool_google_search":
                saw_google_search = True
                saw_any_tool = True
            if function_call.get("name") == "tool_browser_use":
                saw_browser_use = True
                saw_any_tool = True
            if function_response.get("name") == "tool_browser_use":
                saw_browser_use = True
                saw_any_tool = True
            if function_call.get("name") == "tool_generate_image":
                saw_generate_image = True
                saw_any_tool = True
            if function_response.get("name") == "tool_generate_image":
                saw_generate_image = True
                saw_any_tool = True
            if function_call.get("name") == "tool_generate_video":
                saw_generate_video = True
                saw_any_tool = True
            if function_response.get("name") == "tool_generate_video":
                saw_generate_video = True
                saw_any_tool = True
            if function_call.get("name") == "tool_tts_speak":
                saw_tts = True
                saw_any_tool = True
            if function_response.get("name") == "tool_tts_speak":
                saw_tts = True
                saw_any_tool = True
            if function_call.get("name") == "tool_youtube_search":
                saw_youtube_search = True
                saw_any_tool = True
            if function_response.get("name") == "tool_youtube_search":
                saw_youtube_search = True
                saw_any_tool = True
            if payload.get("final") and requires_gmaps and not saw_gmaps:
                query = _extract_gmaps_query(prompt)
                result = tool_gmaps_grounding(query=query)
                summary = _summarize_gmaps_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_gmail and not saw_gmail:
                result = tool_gmail_read_today()
                summary = _summarize_gmail_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_google_search and not saw_google_search:
                result = tool_google_search(prompt=prompt)
                summary = _summarize_google_search_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_browser_use and not saw_browser_use:
                result = tool_browser_use(task=prompt)
                summary = _summarize_browser_use_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_image and not saw_generate_image:
                result = tool_generate_image(description=prompt)
                summary = _summarize_image_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_video and not saw_generate_video:
                image_url = _extract_first_url(prompt)
                if not image_url:
                    yield {
                        "type": "final",
                        "result": {
                            "type": "agent_event",
                            "author": payload.get("author"),
                            "final": True,
                            "error": "Video generation requires an image_url. Provide a URL in the prompt.",
                        },
                    }
                    return
                result = tool_generate_video(description=prompt, image_url=image_url)
                summary = _summarize_video_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_tts and not saw_tts:
                voice_id = os.getenv("TTS_DEFAULT_VOICE_ID", "")
                if not voice_id:
                    voices_result = tool_tts_list_voices()
                    voices = voices_result.get("voices") if isinstance(voices_result, dict) else None
                    if isinstance(voices, list) and voices:
                        voice_id = str(voices[0])
                if not voice_id:
                    yield {
                        "type": "final",
                        "result": {
                            "type": "agent_event",
                            "author": payload.get("author"),
                            "final": True,
                            "error": "TTS requires a voice_id. Set TTS_DEFAULT_VOICE_ID or provide one.",
                        },
                    }
                    return
                text = _extract_quoted_text(prompt)
                result = tool_tts_speak(text=text, voice_id=voice_id)
                summary = _summarize_tts_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and requires_youtube_search and not saw_youtube_search:
                result = tool_youtube_search(queries=[prompt])
                summary = _summarize_youtube_search_result(result)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": summary,
                    },
                }
                return
            if payload.get("final") and strict_tool_mode and router_tools and not saw_any_tool:
                chain_results = _run_tool_chain(router_tools, prompt)
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "text": json.dumps(chain_results, indent=2),
                    },
                }
                return
            if payload.get("final") and strict_tool_mode and not saw_any_tool:
                yield {
                    "type": "final",
                    "result": {
                        "type": "agent_event",
                        "author": payload.get("author"),
                        "final": True,
                        "error": "Strict mode: no tool was called. Please retry with a tool-specific request.",
                    },
                }
                return
            yield payload


root_agent = LlmAgent(
    name="ProjectAgent",
    model="gemini-2.0-flash",
    description="Runs project utilities via tools.",
    instruction=(
        "First produce a short plan, then use the available tools to complete "
        "the user's request. When a tool is required, CALL THE TOOL (do not "
        "output tool-call text or markdown). Outputs may include text, audio, "
        "image, video, or any combination. Use tools when needed. For SadTalker "
        "requests, the prompt is the spoken text. If PHOTO_PATH is set, use it "
        "as the reference image by default and do not ask about avatar "
        "appearance. Only ask for missing spoken text or required paths. "
        "Tool selection triggers: use tool_gmaps_grounding for location/place "
        "queries or when user mentions gmaps/grounding/maps/coordinates; use "
        "tool_gmail_read_today for Gmail/email reads; use tool_google_search "
        "for web search or questions needing fresh facts; use tool_browser_use "
        "for multi-step browsing tasks (browser use/website/chrome tasks); use "
        "tool_generate_image for image generation (image/draw/picture prompts); "
        "use tool_generate_video for video generation (video/animate prompts with image URL); "
        "use tool_tts_speak for speech/audio generation; use tool_youtube_search "
        "for YouTube searches. "
        "If you cannot "
        "call a required tool, explain the limitation and ask for the missing "
        "configuration."
    ),
    tools=[
        tool_generate_image,
        tool_generate_video,
        tool_tts_list_voices,
        tool_tts_speak,
        tool_sadtalker_generate,
        tool_video_append_image_endcard,
        tool_video_concat,
        tool_video_concat_many,
        tool_youtube_search,
        tool_youtube_upload,
        tool_gmaps_grounding,
        tool_gmail_read_today,
        tool_browser_use,
        tool_google_search,
    ],
)
