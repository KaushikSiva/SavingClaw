"""Generic text-to-speech helpers with pluggable providers."""

from __future__ import annotations

import os
import platform
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

import requests

DEFAULT_OUTPUT_DIR = Path("tts_output")


class TTSProvider(Protocol):
    def list_voices(self) -> List[str]:
        ...

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        model_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        voice_settings: Optional[Dict[str, float]] = None,
        play_audio: bool = True,
    ) -> Path:
        ...


class ElevenLabsProvider:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set.")

    def list_voices(self) -> List[str]:
        headers = {"xi-api-key": self.api_key}
        response = requests.get("https://api.elevenlabs.io/v1/voices", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        voices = data.get("voices", [])
        return [v.get("voice_id") for v in voices if v.get("voice_id")]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        model_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        voice_settings: Optional[Dict[str, float]] = None,
        play_audio: bool = True,
    ) -> Path:
        if not text:
            raise ValueError("Text to speak must be non-empty.")
        model_id = model_id or os.getenv("ELEVENLABS_MODEL_ID", "eleven_v3")
        voice_settings = voice_settings or {
            "stability": 0.5,
            "similarity_boost": 0.5,
            "style": 0.0,
            "use_speaker_boost": True,
        }

        headers = {
            "xi-api-key": self.api_key,
            "Accept": "audio/wav",
            "Content-Type": "application/json",
        }
        payload = {"text": text, "model_id": model_id, "voice_settings": voice_settings}
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
        response.raise_for_status()

        if output_path:
            output_path = Path(output_path)
        output_dir = output_path.parent if output_path else DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = output_path.name if output_path else f"tts_{voice_id}_{uuid.uuid4().hex}.wav"
        file_path = output_dir / filename

        with open(file_path, "wb") as audio_file:
            for chunk in response.iter_content(chunk_size=4096):
                if chunk:
                    audio_file.write(chunk)
        if play_audio:
            _play_audio(file_path)
        return file_path


class InworldProvider:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("INWORLD_API_TOKEN")
        if not self.api_key:
            raise RuntimeError("INWORLD_API_TOKEN is not set.")
        self.base_url = "https://api.inworld.ai/tts/v1"

    def list_voices(self) -> List[str]:
        headers = {"Authorization": f"Basic {self.api_key}"}
        response = requests.get(f"{self.base_url}/voices", headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        voices = data.get("voices", [])
        return [v.get("voiceId") for v in voices if v.get("voiceId")]

    def synthesize(
        self,
        text: str,
        voice_id: str,
        *,
        model_id: Optional[str] = None,
        output_path: Optional[Path] = None,
        voice_settings: Optional[Dict[str, float]] = None,
        play_audio: bool = True,
    ) -> Path:
        if not text:
            raise ValueError("Text to speak must be non-empty.")
        model_id = model_id or "inworld-tts-1"
        sample_rate = 48000
        if voice_settings and "sample_rate_hz" in voice_settings:
            try:
                sample_rate = int(voice_settings["sample_rate_hz"])
            except Exception:
                pass

        headers = {
            "Authorization": f"Basic {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": text,
            "voiceId": voice_id,
            "modelId": model_id,
            "audio_config": {
                "audio_encoding": "LINEAR16",
                "sample_rate_hertz": sample_rate,
            },
        }
        url = f"{self.base_url}/voice:stream"
        response = requests.post(url, json=payload, headers=headers, stream=True, timeout=120)
        response.raise_for_status()

        if output_path:
            output_path = Path(output_path)
        output_dir = output_path.parent if output_path else DEFAULT_OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = output_path.name if output_path else f"tts_{voice_id}_{uuid.uuid4().hex}.wav"
        file_path = output_dir / filename

        import base64
        import io
        import json
        import wave

        raw_audio = io.BytesIO()
        for line in response.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            audio_chunk = base64.b64decode(chunk["result"]["audioContent"])
            if len(audio_chunk) > 44:
                raw_audio.write(audio_chunk[44:])

        with wave.open(str(file_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(raw_audio.getvalue())

        if play_audio:
            _play_audio(file_path)
        return file_path


def get_provider(name: str, **kwargs: Any) -> TTSProvider:
    name_l = (name or "").strip().lower()
    if name_l in {"elevenlabs", "eleven"}:
        return ElevenLabsProvider(**kwargs)
    if name_l in {"inworld"}:
        return InworldProvider(**kwargs)
    raise ValueError(f"Unknown TTS provider: {name}")


def list_voices(provider: str, **kwargs: Any) -> List[str]:
    return get_provider(provider, **kwargs).list_voices()


def speak(
    text: str,
    voice_id: str,
    *,
    provider: str = "elevenlabs",
    model_id: Optional[str] = None,
    output_path: Optional[Path] = None,
    voice_settings: Optional[Dict[str, float]] = None,
    play_audio: bool = True,
    **provider_kwargs: Any,
) -> Path:
    tts = get_provider(provider, **provider_kwargs)
    return tts.synthesize(
        text,
        voice_id,
        model_id=model_id,
        output_path=output_path,
        voice_settings=voice_settings,
        play_audio=play_audio,
    )


def _play_audio(file_path: Path) -> None:
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["afplay", str(file_path)], check=True)
    elif system == "Windows":
        command = [
            "powershell",
            "-Command",
            f"Start-Process -FilePath 'wmplayer' -ArgumentList '{file_path}' -Wait",
        ]
        subprocess.run(command, check=True)
    else:
        subprocess.run(["aplay", str(file_path)], check=True)


__all__ = [
    "list_voices",
    "speak",
    "get_provider",
    "ElevenLabsProvider",
    "InworldProvider",
]
