import argparse
import base64
import os
from pathlib import Path


def _extract_first_image_bytes(response):
    # Works with google.genai response objects or dict-like payloads.
    candidates = getattr(response, "candidates", None)
    if candidates is None and isinstance(response, dict):
        candidates = response.get("candidates", [])
    if not candidates:
        return None, None

    for cand in candidates:
        content = getattr(cand, "content", None) if not isinstance(cand, dict) else cand.get("content")
        parts = getattr(content, "parts", None) if content is not None and not isinstance(content, dict) else (
            content.get("parts", []) if isinstance(content, dict) else []
        )
        for part in parts or []:
            inline = getattr(part, "inline_data", None) if not isinstance(part, dict) else part.get("inline_data")
            if inline is None and isinstance(part, dict):
                inline = part.get("inlineData")
            if inline:
                data = getattr(inline, "data", None) if not isinstance(inline, dict) else inline.get("data")
                mime = getattr(inline, "mime_type", None) if not isinstance(inline, dict) else inline.get("mime_type")
                if data:
                    if isinstance(data, str):
                        return base64.b64decode(data), mime
                    return data, mime
    return None, None


def generate_image_from_synopsis(*, synopsis: str, model_name: str, out_path: str) -> str:
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    client = genai.Client(api_key=api_key)
    cfg = genai_types.GenerateContentConfig(response_modalities=["Text", "Image"]) if genai_types else None

    prompt = (
        "Create one high-quality image illustrating this description. "
        "Do not include any words or text on the image. "
        "Use a single frame, no collage or split panels.\n"
        f"Description: {synopsis}"
    )
    response = client.models.generate_content(model=model_name, contents=prompt, config=cfg)
    image_bytes, mime = _extract_first_image_bytes(response)
    if not image_bytes:
        raise RuntimeError("No image returned by the model")

    out = Path(out_path)
    if out.suffix == "":
        ext = ".png" if not mime else (".jpg" if "jpeg" in mime else ".png")
        out = out.with_suffix(ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(image_bytes)
    return str(out)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a single image from a synopsis.")
    parser.add_argument("synopsis", help="Short synopsis text to illustrate.")
    parser.add_argument("--model", default="models/gemini-2.5-flash-image-preview", help="GenAI image model name.")
    parser.add_argument("--out", default="synopsis_image.png", help="Output image path.")
    args = parser.parse_args()

    out_path = generate_image_from_synopsis(
        synopsis=args.synopsis,
        model_name=args.model,
        out_path=args.out,
    )
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
