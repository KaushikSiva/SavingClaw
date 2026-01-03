"""SadTalker prompt-to-video helper (generic wrapper)."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


class SadTalkerError(RuntimeError):
    """Raised when SadTalker cannot run or there is a missing configuration."""


@dataclass
class SadTalkerResult:
    video_path: Path
    result_dir: Path


def _iterable_args(name: str, values: Optional[Iterable[int]]) -> List[str]:
    if not values:
        return []
    flattened = (str(int(value)) for value in values)
    return [f"--{name}", *flattened]


def _synthesize_text_to_wav(text: str, target: Path) -> None:
    try:
        import pyttsx3
    except ImportError as exc:
        raise SadTalkerError(
            "pyttsx3 is required to turn prompts into driving audio. Install it (e.g. `pip install pyttsx3`) and rerun."
        ) from exc

    engine = pyttsx3.init()
    engine.setProperty("rate", 150)
    engine.save_to_file(text, str(target))
    engine.runAndWait()


def generate_video_from_prompt(
    prompt: str,
    reference_image: Path,
    *,
    repo_path: Optional[Path] = None,
    result_dir: Optional[Path] = None,
    checkpoint_dir: Optional[Path] = None,
    pose_style: int = 0,
    size: int = 256,
    still_mode: bool = False,
    expression_scale: float = 1.0,
    preprocess: str = "crop",
    batch_size: int = 2,
    input_yaw: Optional[Iterable[int]] = None,
    input_pitch: Optional[Iterable[int]] = None,
    input_roll: Optional[Iterable[int]] = None,
    ref_pose: Optional[Path] = None,
    ref_eyeblink: Optional[Path] = None,
    enhancer: Optional[str] = None,
    background_enhancer: Optional[str] = None,
    old_version: bool = False,
    verbose: bool = False,
    cleanup_audio: bool = True,
    device: str = "cpu",
    driven_audio: Optional[Path] = None,
) -> SadTalkerResult:
    repo_path = Path(repo_path or os.getenv("SAD_TALKER_PATH", "")).expanduser().resolve()
    if not repo_path or not repo_path.exists():
        raise SadTalkerError("Set SAD_TALKER_PATH or pass repo_path to the SadTalker repo.")
    inference_script = repo_path / "inference.py"
    if not inference_script.exists():
        raise SadTalkerError(f"SadTalker repo missing at {repo_path!r}; clone it first.")

    reference_path = Path(reference_image)
    if not reference_path.is_file():
        raise SadTalkerError(f"Provided reference image {reference_path} does not exist.")

    if ref_pose is not None:
        ref_pose = Path(ref_pose)
        if not ref_pose.is_file():
            raise SadTalkerError(f"Ref pose video {ref_pose} does not exist.")
    if ref_eyeblink is not None:
        ref_eyeblink = Path(ref_eyeblink)
        if not ref_eyeblink.is_file():
            raise SadTalkerError(f"Ref eyeblink video {ref_eyeblink} does not exist.")

    working_result_dir = Path(result_dir or repo_path / "results")
    working_result_dir.mkdir(parents=True, exist_ok=True)

    before_videos = {path for path in working_result_dir.rglob("*.mp4")}
    parent_before = {path for path in working_result_dir.parent.rglob("*.mp4")}

    temp_audio_file: Optional[Path] = None

    if driven_audio:
        audio_file = Path(driven_audio).expanduser().resolve()
        if not audio_file.is_file():
            raise SadTalkerError(f"Driving audio {audio_file} does not exist.")
        cleanup_audio = False
    else:
        tmp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        audio_file = Path(tmp_audio.name)
        tmp_audio.close()
        temp_audio_file = audio_file
    try:
        if not prompt.strip():
            raise SadTalkerError("Prompt cannot be empty.")

        if not driven_audio:
            _synthesize_text_to_wav(prompt, audio_file)

        command: List[str] = [
            sys.executable,
            str(inference_script),
            "--driven_audio",
            str(audio_file),
            "--source_image",
            str(reference_path),
            "--result_dir",
            str(working_result_dir),
            "--pose_style",
            str(pose_style),
            "--batch_size",
            str(batch_size),
            "--size",
            str(size),
            "--expression_scale",
            str(expression_scale),
            "--preprocess",
            preprocess,
        ]

        if checkpoint_dir:
            command += ["--checkpoint_dir", str(checkpoint_dir)]
        else:
            default_checkpoint_dir = repo_path / "checkpoints"
            if default_checkpoint_dir.exists():
                command += ["--checkpoint_dir", str(default_checkpoint_dir)]

        if still_mode:
            command.append("--still")
        if ref_pose:
            command += ["--ref_pose", str(ref_pose)]
        if ref_eyeblink:
            command += ["--ref_eyeblink", str(ref_eyeblink)]
        if enhancer:
            command += ["--enhancer", enhancer]
        if background_enhancer:
            command += ["--background_enhancer", background_enhancer]
        if old_version:
            command.append("--old_version")
        if verbose:
            command.append("--verbose")
        command += _iterable_args("input_yaw", input_yaw)
        command += _iterable_args("input_pitch", input_pitch)
        command += _iterable_args("input_roll", input_roll)

        device_choice = device.lower()
        if device_choice == "cpu":
            command.append("--cpu")
        elif device_choice not in {"cuda", "gpu"}:
            raise SadTalkerError("`device` must be 'cpu', 'cuda', or 'gpu'.")

        env = os.environ.copy()
        project_root = Path(__file__).resolve().parent
        existing_path = env.get("PYTHONPATH")
        sad_repo_root = repo_path.resolve()
        env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(project_root), str(sad_repo_root), existing_path])
        )
        try:
            subprocess.run(command, cwd=repo_path, check=True, env=env)
        except subprocess.CalledProcessError as exc:
            raise SadTalkerError(f"SadTalker inference failed: {exc}") from exc

        folder_candidates = [
            path for path in working_result_dir.rglob("*.mp4") if path not in before_videos
        ]
        parent_candidates = [
            path
            for path in working_result_dir.parent.rglob("*.mp4")
            if path not in parent_before
        ]
        candidates = folder_candidates + parent_candidates
        if not candidates:
            candidates = list(working_result_dir.glob("*.mp4"))
            candidates += [
                path
                for path in working_result_dir.parent.glob("*.mp4")
                if path not in parent_before
            ]
        if not candidates:
            raise SadTalkerError("SadTalker did not produce any mp4 videos.")

        latest_video = max(candidates, key=lambda path: path.stat().st_mtime)
        return SadTalkerResult(video_path=latest_video, result_dir=working_result_dir)
    finally:
        if cleanup_audio and temp_audio_file and temp_audio_file.exists():
            audio_file.unlink(missing_ok=True)


__all__ = ["SadTalkerError", "SadTalkerResult", "generate_video_from_prompt"]
