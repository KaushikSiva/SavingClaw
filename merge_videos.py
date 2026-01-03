from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional


def _import_moviepy_components():
    try:
        from moviepy import VideoFileClip, concatenate_videoclips  # type: ignore
        return VideoFileClip, concatenate_videoclips
    except Exception:
        from moviepy.editor import VideoFileClip, concatenate_videoclips  # type: ignore
        return VideoFileClip, concatenate_videoclips


def _parse_timestamp(value: str) -> float:
    if ":" not in value:
        return float(value)
    parts = [float(p) for p in value.split(":")]
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = 0.0, parts[0], parts[1]
    else:
        raise ValueError("Timestamp must be seconds or HH:MM:SS or MM:SS")
    return h * 3600 + m * 60 + s


def insert_video(
    *,
    video1_path: str,
    video2_path: str,
    timestamp: float,
    out_path: str,
) -> str:
    VideoFileClip, concatenate_videoclips = _import_moviepy_components()
    v1 = VideoFileClip(video1_path)
    v2 = VideoFileClip(video2_path)
    try:
        if timestamp < 0 or timestamp > (v1.duration or 0):
            raise ValueError("Timestamp must be within video1 duration.")
        try:
            pre = v1.subclip(0, timestamp)
            post = v1.subclip(timestamp)
        except AttributeError:
            try:
                pre = v1.subclipped(0, timestamp)
                post = v1.subclipped(timestamp)
            except AttributeError as exc:
                raise AttributeError(
                    "VideoFileClip has no subclip/subclipped method"
                ) from exc
        final = concatenate_videoclips([pre, v2, post], method="compose")
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            import inspect

            sig = inspect.signature(final.write_videofile)  # type: ignore[attr-defined]
            params = sig.parameters
            if "verbose" in params or "logger" in params:
                final.write_videofile(
                    str(out),
                    codec="libx264",
                    audio_codec="aac",
                    fps=v1.fps or 24,
                    verbose=False,
                    logger=None,
                )
            else:
                final.write_videofile(
                    str(out),
                    codec="libx264",
                    audio_codec="aac",
                    fps=v1.fps or 24,
                )
        except Exception:
            final.write_videofile(
                str(out),
                codec="libx264",
                audio_codec="aac",
                fps=v1.fps or 24,
            )
        return str(out)
    finally:
        try:
            v1.close()
        except Exception:
            pass
        try:
            v2.close()
        except Exception:
            pass
        try:
            final.close()  # type: ignore[has-type]
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Insert video2 into video1 at the given timestamp."
    )
    parser.add_argument("video1", help="Path to the main video.")
    parser.add_argument("video2", help="Path to the inserted video.")
    parser.add_argument("timestamp", help="Insert time (seconds or HH:MM:SS).")
    parser.add_argument(
        "--out",
        default="merged.mp4",
        help="Output path (default: merged.mp4).",
    )
    args = parser.parse_args()

    ts = _parse_timestamp(args.timestamp)
    out = insert_video(
        video1_path=args.video1,
        video2_path=args.video2,
        timestamp=ts,
        out_path=args.out,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
