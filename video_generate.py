from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import requests


class VideoGenerationError(Exception):
    pass


def build_video_prompt(
    *,
    description: str,
    duration_seconds: int,
    title: Optional[str] = None,
    safe: bool = False,
) -> str:
    parts = [f"Create a {duration_seconds}s video based on this description."]
    if title:
        parts.append(f"Title context: {title}")
    parts.append(f"Description: {sanitize_text(description)}")
    if safe:
        parts.append("Keep content PG-friendly. Avoid violence, drugs, and explicit material.")
    return " ".join(p for p in parts if p)


def sanitize_text(text: str) -> str:
    return " ".join(text.split()).strip()


def generate_video(
    *,
    description: str,
    image_url: str,
    duration_seconds: int,
    fal_api_key: str,
    model: str,
    timeout: int,
    output_dir: str = "generated",
    title: Optional[str] = None,
) -> Dict[str, Any]:
    log = logging.getLogger(__name__)
    if not fal_api_key:
        raise VideoGenerationError("FAL_API_KEY not set")

    final_image_url = _normalize_image_url(image_url)

    duration_effective = max(1, duration_seconds)
    duration_str = f"{duration_effective}s"

    def make_payload(prompt_text: str) -> dict:
        return {
            "prompt": prompt_text,
            "image_url": final_image_url,
            "duration": duration_str,
            "resolution": "720p",
            "generate_audio": True,
        }

    prompt = build_video_prompt(
        description=description,
        duration_seconds=duration_effective,
        title=title,
        safe=False,
    )
    payload = make_payload(prompt)

    headers = {"Authorization": f"Key {fal_api_key}", "Content-Type": "application/json"}
    submit_url = f"https://fal.run/{model}"

    log.info("FAL.ai request to %s", submit_url)
    response = requests.post(submit_url, json=payload, headers=headers, timeout=timeout)
    if response.status_code != 200:
        result = _maybe_json(response)
        err_type = None
        det = result.get("detail") if isinstance(result, dict) else None
        if isinstance(det, list) and det and isinstance(det[0], dict):
            err_type = det[0].get("type")
        if response.status_code == 422 and err_type == "content_policy_violation":
            log.info("Retrying with safe prompt")
            payload2 = make_payload(
                build_video_prompt(
                    description=description,
                    duration_seconds=duration_effective,
                    title=title,
                    safe=True,
                )
            )
            response2 = requests.post(submit_url, json=payload2, headers=headers, timeout=timeout)
            if response2.status_code != 200:
                raise VideoGenerationError(f"FAL.ai API error ({response2.status_code}): {response2.text}")
            result = response2.json()
        else:
            raise VideoGenerationError(f"FAL.ai API error ({response.status_code}): {response.text}")
    else:
        result = response.json()

    if "video" in result and "url" in result["video"]:
        video_url = result["video"]["url"]
        local_file = download_video_file(video_url, output_dir)
        return {
            "video_url": video_url,
            "local_file": local_file,
            "duration": duration_effective,
            "prompt": prompt,
            "model": model,
            "status": "completed",
        }
    if "request_id" in result:
        return poll_video_completion(result["request_id"], fal_api_key, model, timeout, output_dir)
    raise VideoGenerationError(f"Unexpected response format: {result}")


def poll_video_completion(
    request_id: str,
    fal_api_key: str,
    model: str,
    timeout: int,
    output_dir: str,
) -> Dict[str, Any]:
    import time

    headers = {"Authorization": f"Key {fal_api_key}"}
    status_url = f"https://fal.run/{model}/requests/{request_id}"
    start_time = time.time()
    while time.time() - start_time < timeout:
        response = requests.get(status_url, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
        status = result.get("status", "unknown")
        if status == "completed":
            if "video" in result and "url" in result["video"]:
                video_url = result["video"]["url"]
                local_file = download_video_file(video_url, output_dir)
                return {
                    "video_url": video_url,
                    "local_file": local_file,
                    "duration": result.get("duration", 8),
                    "model": model,
                    "status": "completed",
                    "request_id": request_id,
                }
            raise VideoGenerationError("Video completed but no URL found in response")
        if status in ("failed", "error"):
            error_msg = result.get("error", "Unknown error occurred")
            raise VideoGenerationError(f"Video generation failed: {error_msg}")
        if status in ("queued", "in_progress"):
            time.sleep(5)
            continue
    raise VideoGenerationError(f"Video generation timed out after {timeout} seconds")


def download_video_file(video_url: str, output_dir: str) -> str:
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    filepath = Path(output_dir) / "video.mp4"
    try:
        filepath.unlink(missing_ok=True)
    except Exception:
        pass
    response = requests.get(video_url, stream=True, timeout=60)
    response.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
    return str(filepath)


def _normalize_image_url(image_url: str) -> str:
    if image_url.startswith(("http://localhost", "http://127.0.0.1")):
        try:
            img_response = requests.get(image_url, timeout=10)
            img_response.raise_for_status()
            content_type = img_response.headers.get("content-type", "image/jpeg")
            if not content_type.startswith("image/"):
                content_type = "image/png" if image_url.lower().endswith(".png") else "image/jpeg"
            image_data = base64.b64encode(img_response.content).decode("utf-8")
            return f"data:{content_type};base64,{image_data}"
        except requests.exceptions.RequestException as e:
            raise VideoGenerationError(f"Cannot access local image URL {image_url}: {e}") from e
    if not image_url.startswith(("http://", "https://")):
        raise VideoGenerationError("image_url must be a valid HTTP/HTTPS URL")
    try:
        img_response = requests.head(image_url, timeout=10)
        if img_response.status_code != 200:
            raise VideoGenerationError(f"Image URL not accessible: HTTP {img_response.status_code}")
    except requests.exceptions.RequestException as e:
        raise VideoGenerationError(f"Cannot access image URL {image_url}: {e}") from e
    return image_url


def _maybe_json(response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"text": response.text}
