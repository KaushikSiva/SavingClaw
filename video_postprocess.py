from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional


def ensure_ffmpeg() -> Optional[str]:
    """Wire ffmpeg for MoviePy using imageio-ffmpeg if not on PATH."""
    try:
        import imageio_ffmpeg  # type: ignore

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        os.environ.setdefault("IMAGEIO_FFMPEG_EXE", exe)
        try:
            from moviepy.config import change_settings  # type: ignore

            change_settings({"FFMPEG_BINARY": exe})
        except Exception:
            pass
        logging.getLogger(__name__).info("video_postprocess: using ffmpeg exe=%s", exe)
        return exe
    except Exception:
        return None


def _import_moviepy_components():
    """Import MoviePy components compatibly across versions (>=2 preferred)."""
    try:
        from moviepy import (  # type: ignore
            VideoFileClip,
            ImageClip,
            ColorClip,
            concatenate_videoclips,
        )
        return VideoFileClip, ImageClip, ColorClip, concatenate_videoclips
    except Exception:
        from moviepy.editor import (  # type: ignore
            VideoFileClip,
            ImageClip,
            ColorClip,
            concatenate_videoclips,
        )
        return VideoFileClip, ImageClip, ColorClip, concatenate_videoclips


def append_image_and_endcard(
    *,
    video_path: Path,
    image_path: Optional[Path],
    out_path: Path,
    image_seconds: float = 2.0,
    endcard_seconds: float = 2.0,
    endcard_text: str = "Coming soon.",
) -> None:
    """Append a still image and a text end-card to an existing video."""
    ff = ensure_ffmpeg()
    logging.getLogger(__name__).info(
        "video_postprocess: start video=%s image=%s out=%s ffmpeg=%s",
        str(video_path),
        str(image_path) if image_path else None,
        str(out_path),
        ff,
    )

    from PIL import Image, ImageDraw, ImageFont  # type: ignore

    VideoFileClip, ImageClip, _ColorClip, concatenate_videoclips = _import_moviepy_components()

    base = VideoFileClip(str(video_path))
    w, h = base.w, base.h
    clips = [base]

    if image_path and image_path.exists():
        logging.getLogger(__name__).info("video_postprocess: appending image segment")
        image_clip = ImageClip(str(image_path))
        try:
            iw, ih = image_clip.w, image_clip.h
            scale = min(w / float(iw or 1), h / float(ih or 1))
            target_size = (max(1, int((iw or w) * scale)), max(1, int((ih or h) * scale)))
        except Exception:
            target_size = (w, h)

        if hasattr(image_clip, "with_size"):
            try:
                image_clip = image_clip.with_size(target_size)
            except Exception:
                try:
                    image_clip = image_clip.with_size(width=target_size[0])
                except Exception:
                    pass
        elif hasattr(image_clip, "resize"):
            try:
                image_clip = image_clip.resize(newsize=target_size)
            except Exception:
                image_clip = image_clip.resize(width=target_size[0])

        if hasattr(image_clip, "with_duration"):
            image_clip = image_clip.with_duration(image_seconds)
        else:
            image_clip = image_clip.set_duration(image_seconds)

        try:
            from moviepy import ColorClip as _ColorClip  # type: ignore
        except Exception:
            from moviepy.editor import ColorClip as _ColorClip  # type: ignore

        bg = _ColorClip((w, h), color=(0, 0, 0))
        if hasattr(bg, "with_duration"):
            bg = bg.with_duration(image_seconds)
        else:
            bg = bg.set_duration(image_seconds)

        if hasattr(image_clip, "with_position"):
            image_on_bg = image_clip.with_position("center")
        elif hasattr(image_clip, "set_position"):
            image_on_bg = image_clip.set_position("center")
        else:
            image_on_bg = image_clip

        try:
            from moviepy import CompositeVideoClip  # type: ignore
        except Exception:
            from moviepy.editor import CompositeVideoClip  # type: ignore

        comp = CompositeVideoClip([bg, image_on_bg])
        clips.append(comp)

    txt_img = Image.new("RGB", (w, h), (0, 0, 0))
    draw = ImageDraw.Draw(txt_img)
    font = None
    for name in ("Arial.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(name, size=max(16, int(h * 0.06)))
            break
        except Exception:
            continue
    if font is None:
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
    try:
        bbox = draw.textbbox((0, 0), endcard_text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    except Exception:
        try:
            tw, th = draw.textsize(endcard_text, font=font)
        except Exception:
            tw, th = (len(endcard_text) * 10, int(h * 0.06))
    x, y = max(0, (w - tw) // 2), max(0, int(h * 0.45))
    try:
        draw.text((x, y), endcard_text, font=font, fill=(255, 255, 255))
    except Exception:
        pass

    tmp_end = out_path.parent / "_endcard.png"
    try:
        txt_img.save(tmp_end)
    except Exception:
        tmp_end = None

    if tmp_end and tmp_end.exists():
        logging.getLogger(__name__).info("video_postprocess: appending end card")
        end_clip = ImageClip(str(tmp_end))
        if hasattr(end_clip, "with_duration"):
            end_clip = end_clip.with_duration(endcard_seconds)
        else:
            end_clip = end_clip.set_duration(endcard_seconds)
        clips.append(end_clip)

    final = concatenate_videoclips(clips, method="compose")
    tmp_out = out_path.parent / "_tmp_out.mp4"
    logging.getLogger(__name__).info("video_postprocess: writing final video to %s", str(tmp_out))

    try:
        import inspect

        sig = inspect.signature(final.write_videofile)  # type: ignore[attr-defined]
        params = sig.parameters
        if "verbose" in params or "logger" in params:
            final.write_videofile(
                str(tmp_out),
                codec="libx264",
                audio_codec="aac",
                fps=base.fps or 24,
                verbose=False,
                logger=None,
            )
        else:
            final.write_videofile(str(tmp_out), codec="libx264", audio_codec="aac", fps=base.fps or 24)
    except Exception:
        final.write_videofile(str(tmp_out), codec="libx264", audio_codec="aac", fps=base.fps or 24)
    try:
        if out_path.exists():
            out_path.unlink()
        tmp_out.rename(out_path)
    finally:
        try:
            base.close()
        except Exception:
            pass
        try:
            final.close()
        except Exception:
            pass
        try:
            if tmp_end:
                tmp_end.unlink(missing_ok=True)
        except Exception:
            pass


def concat_videos(input1: str | Path, input2: str | Path, out_path: Path) -> str:
    """Concatenate two videos back-to-back and write to out_path."""
    ensure_ffmpeg()
    VideoFileClip, _ImageClip, _ColorClip, concatenate_videoclips = _import_moviepy_components()
    c1 = None
    c2 = None
    try:
        c1 = VideoFileClip(str(input1))
        c2 = VideoFileClip(str(input2))
        final = concatenate_videoclips([c1, c2], method="compose")
        tmp_out = out_path.parent / "_tmp_concat.mp4"
        try:
            import inspect

            sig = inspect.signature(final.write_videofile)  # type: ignore[attr-defined]
            params = sig.parameters
            if "verbose" in params or "logger" in params:
                final.write_videofile(
                    str(tmp_out),
                    codec="libx264",
                    audio_codec="aac",
                    fps=c1.fps or 24,
                    verbose=False,
                    logger=None,
                )
            else:
                final.write_videofile(str(tmp_out), codec="libx264", audio_codec="aac", fps=c1.fps or 24)
        except Exception:
            final.write_videofile(str(tmp_out), codec="libx264", audio_codec="aac", fps=c1.fps or 24)
        try:
            if out_path.exists():
                out_path.unlink()
            tmp_out.rename(out_path)
        finally:
            try:
                final.close()
            except Exception:
                pass
        return str(out_path)
    finally:
        try:
            if c1:
                c1.close()
        except Exception:
            pass
        try:
            if c2:
                c2.close()
        except Exception:
            pass


def concat_videos_many(inputs: list[str | Path], out_path: Path) -> str:
    """Concatenate N videos in order and write to out_path."""
    ensure_ffmpeg()
    VideoFileClip, _ImageClip, _ColorClip, concatenate_videoclips = _import_moviepy_components()
    clips = []
    try:
        for p in inputs:
            clips.append(VideoFileClip(str(p)))
        if not clips:
            raise ValueError("No input videos provided")
        final = concatenate_videoclips(clips, method="compose")
        tmp_out = out_path.parent / "_tmp_concat_many.mp4"
        try:
            import inspect

            sig = inspect.signature(final.write_videofile)  # type: ignore[attr-defined]
            params = sig.parameters
            fps = getattr(clips[0], "fps", None) or 24
            if "verbose" in params or "logger" in params:
                final.write_videofile(
                    str(tmp_out),
                    codec="libx264",
                    audio_codec="aac",
                    fps=fps,
                    verbose=False,
                    logger=None,
                )
            else:
                final.write_videofile(str(tmp_out), codec="libx264", audio_codec="aac", fps=fps)
        except Exception:
            final.write_videofile(
                str(tmp_out),
                codec="libx264",
                audio_codec="aac",
                fps=getattr(clips[0], "fps", None) or 24,
            )
        try:
            if out_path.exists():
                out_path.unlink()
            tmp_out.rename(out_path)
        finally:
            try:
                final.close()
            except Exception:
                pass
        return str(out_path)
    finally:
        for c in clips:
            try:
                c.close()
            except Exception:
                pass
