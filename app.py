from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from queue import Queue
from urllib.parse import urlencode

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    stream_with_context,
)
from werkzeug.utils import secure_filename
from flask_cors import CORS
import redis

from main import (
    reset_tool_event_sink,
    set_tool_event_sink,
    stream_agent_events,
    tool_generate_image,
    tool_generate_video,
)
from merge_videos import insert_video, _parse_timestamp

load_dotenv()

app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_STORE_PATH = Path(os.getenv("GMAIL_TOKEN_STORE_PATH", ".gmail_tokens.json"))
RECENT_PROMPTS_KEY = os.getenv("REDIS_RECENT_PROMPTS_KEY", "recent_prompts")
RECENT_PROMPTS_LIMIT = int(os.getenv("REDIS_RECENT_PROMPTS_LIMIT", "25"))


def _get_redis_client() -> "redis.Redis | None":
    url = (os.getenv("REDIS_URL") or "").strip()
    if not url:
        return None
    try:
        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:
        return None


def _store_recent_prompt(prompt: str) -> None:
    client = _get_redis_client()
    if not client:
        return
    payload = json.dumps(
        {
            "prompt": prompt,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
    )
    try:
        pipe = client.pipeline()
        pipe.lpush(RECENT_PROMPTS_KEY, payload)
        pipe.ltrim(RECENT_PROMPTS_KEY, 0, max(RECENT_PROMPTS_LIMIT - 1, 0))
        pipe.execute()
    except Exception:
        pass


def _get_recent_prompts() -> list[dict]:
    client = _get_redis_client()
    if not client:
        return []
    try:
        raw_items = client.lrange(RECENT_PROMPTS_KEY, 0, max(RECENT_PROMPTS_LIMIT - 1, 0))
    except Exception:
        return []
    items: list[dict] = []
    for raw in raw_items:
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"prompt": raw}
        if isinstance(parsed, dict):
            items.append(parsed)
        else:
            items.append({"prompt": str(parsed)})
    return items


def _gmail_connected() -> bool:
    if os.getenv("GMAIL_REFRESH_TOKEN"):
        return True
    if not TOKEN_STORE_PATH.exists():
        return False
    try:
        data = json.loads(TOKEN_STORE_PATH.read_text())
    except Exception:
        return False
    token = data.get("refresh_token")
    return isinstance(token, str) and bool(token)


@app.get("/")
def index():
    return render_template(
        "index.html",
        gmaps_embed_api_key=os.getenv("GMAPS_EMBED_API_KEY", ""),
        gmail_client_id=os.getenv("GMAIL_CLIENT_ID", ""),
        gmail_connected=_gmail_connected(),
    )


@app.get("/tools")
def tools_page():
    return render_template("tools.html")


@app.post("/api/generate-image")
def api_generate_image():
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    model = data.get("model")
    out_path = data.get("out_path")
    if not description:
        return jsonify({"status": "error", "error": "description is required"}), 400
    result = tool_generate_image(
        description=description,
        model=model,
        out_path=out_path,
    )
    return jsonify(result)


@app.post("/api/generate-video")
def api_generate_video():
    data = request.get_json(silent=True) or {}
    description = (data.get("description") or "").strip()
    image_url = (data.get("image_url") or "").strip()
    if not description or not image_url:
        return jsonify({"status": "error", "error": "description and image_url are required"}), 400
    result = tool_generate_video(
        description=description,
        image_url=image_url,
        duration_seconds=int(data.get("duration_seconds") or 8),
        model=data.get("model"),
        timeout=int(data.get("timeout") or 180),
        output_dir=data.get("output_dir") or "generated",
        title=data.get("title"),
    )
    return jsonify(result)


@app.post("/api/agent")
def api_agent():
    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"status": "error", "error": "prompt is required"}), 400
    _store_recent_prompt(prompt)

    def event_stream():
        queue: Queue = Queue()

        def sink(event):
            queue.put(event)

        def run():
            token = set_tool_event_sink(sink)
            try:
                queue.put({"type": "status", "message": "planning"})
                for event in stream_agent_events(prompt):
                    if event.get("final"):
                        queue.put({"type": "final", "result": event})
                    else:
                        queue.put(event)
            except Exception as exc:
                queue.put({"type": "error", "error": str(exc)})
            finally:
                reset_tool_event_sink(token)
                queue.put(None)

        threading.Thread(target=run, daemon=True).start()

        while True:
            item = queue.get()
            if item is None:
                break
            payload = json.dumps(item, default=str)
            yield f"data: {payload}\n\n"

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


@app.get("/api/recent-prompts")
def api_recent_prompts():
    return jsonify({"status": "success", "items": _get_recent_prompts()})


@app.get("/files")
def serve_file():
    raw_path = request.args.get("path", "")
    if not raw_path:
        abort(400)
    base_dir = Path.cwd().resolve()
    file_path = Path(raw_path).expanduser().resolve()
    try:
        file_path.relative_to(base_dir)
    except ValueError:
        abort(403)
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(str(file_path), conditional=True)


@app.post("/api/merge-videos")
def api_merge_videos():
    if "video1" not in request.files or "video2" not in request.files:
        return jsonify({"status": "error", "error": "video1 and video2 are required"}), 400
    video1 = request.files["video1"]
    video2 = request.files["video2"]
    timestamp_raw = request.form.get("timestamp", "")
    if not timestamp_raw:
        return jsonify({"status": "error", "error": "timestamp is required"}), 400

    filename1 = secure_filename(video1.filename or "video1.mp4")
    filename2 = secure_filename(video2.filename or "video2.mp4")
    id_prefix = uuid.uuid4().hex
    path1 = UPLOAD_DIR / f"{id_prefix}_{filename1}"
    path2 = UPLOAD_DIR / f"{id_prefix}_{filename2}"
    video1.save(path1)
    video2.save(path2)

    try:
        timestamp = _parse_timestamp(timestamp_raw)
    except Exception:
        return jsonify({"status": "error", "error": "invalid timestamp format"}), 400

    out_path = UPLOAD_DIR / f"{id_prefix}_merged.mp4"
    try:
        from moviepy import VideoFileClip  # type: ignore
    except Exception:
        from moviepy.editor import VideoFileClip  # type: ignore

    v2 = VideoFileClip(str(path2))
    try:
        ad_duration = float(v2.duration or 0)
    finally:
        try:
            v2.close()
        except Exception:
            pass

    try:
        merged = insert_video(
            video1_path=str(path1),
            video2_path=str(path2),
            timestamp=timestamp,
            out_path=str(out_path),
        )
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500

    return jsonify(
        {
            "status": "success",
            "path": merged,
            "ad_start": timestamp,
            "ad_end": timestamp + ad_duration,
        }
    )


@app.get("/oauth/gmail/start")
def gmail_oauth_start():
    client_id = os.getenv("GMAIL_CLIENT_ID", "")
    redirect_uri = os.getenv(
        "GMAIL_OAUTH_REDIRECT_URI", "http://localhost:7171/oauth/gmail/callback"
    )
    if not client_id or not redirect_uri:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "GMAIL_CLIENT_ID and GMAIL_OAUTH_REDIRECT_URI are required.",
                }
            ),
            400,
        )
    scope = "https://www.googleapis.com/auth/gmail.readonly"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        "prompt": "consent",
    }
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}")


@app.get("/oauth/gmail/callback")
def gmail_oauth_callback():
    error = request.args.get("error")
    if error:
        return jsonify({"status": "error", "error": error}), 400
    code = request.args.get("code", "")
    if not code:
        return jsonify({"status": "error", "error": "Missing code parameter."}), 400
    client_id = os.getenv("GMAIL_CLIENT_ID", "")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET", "")
    redirect_uri = os.getenv(
        "GMAIL_OAUTH_REDIRECT_URI", "http://localhost:7171/oauth/gmail/callback"
    )
    if not client_id or not client_secret or not redirect_uri:
        return (
            jsonify(
                {
                    "status": "error",
                    "error": "GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_OAUTH_REDIRECT_URI are required.",
                }
            ),
            400,
        )
    try:
        import requests

        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri,
            },
            timeout=20,
        )
        token_resp.raise_for_status()
    except Exception as exc:
        return jsonify({"status": "error", "error": str(exc)}), 500

    payload = token_resp.json()
    refresh_token = payload.get("refresh_token")
    access_token = payload.get("access_token")
    if refresh_token:
        try:
            TOKEN_STORE_PATH.write_text(
                json.dumps(
                    {
                        "refresh_token": refresh_token,
                        "access_token": access_token,
                    },
                    indent=2,
                )
            )
        except Exception:
            pass
    return render_template(
        "oauth_result.html",
        refresh_token=refresh_token or "",
        access_token=access_token or "",
    )


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7171"))
    app.run(host="0.0.0.0", port=port, debug=False)
