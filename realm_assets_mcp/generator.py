"""
Image generation via fal.ai Flux + transparent background post-processing.
"""
from __future__ import annotations

import io
from pathlib import Path

import fal_client
import httpx
from PIL import Image

from config import FAL_GUIDANCE, FAL_MODEL, FAL_STEPS, STYLE_BASE, load_env


def build_prompt(subject: str, size: int) -> str:
    """Combine style base with subject description."""
    return f"{STYLE_BASE}, {size}x{size} icon, {subject}"


def build_negative_prompt() -> str:
    return (
        "text, letters, watermark, border, frame, shadow, background color, "
        "blurry, low quality, ugly, deformed, multiple objects, busy composition"
    )


async def generate_asset(
    subject_prompt: str,
    output_path: Path,
    size: int = 64,
    num_images: int = 1,
) -> list[Path]:
    """
    Generate one or more variants of an asset and save to output_path.
    If num_images > 1, saves as output_path, output_path_v2.png, etc.
    Returns list of saved paths.
    """
    load_env()
    if not __import__("os").environ.get("FAL_KEY"):
        raise RuntimeError(
            "FAL_KEY is not set. Export FAL_KEY=... or add it to the repo .env file."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    prompt = build_prompt(subject_prompt, size)
    neg = build_negative_prompt()

    result = await fal_client.run_async(
        FAL_MODEL,
        arguments={
            "prompt": prompt,
            "negative_prompt": neg,
            "image_size": {"width": size, "height": size},
            "num_inference_steps": FAL_STEPS,
            "guidance_scale": FAL_GUIDANCE,
            "num_images": num_images,
            "enable_safety_checker": False,
            "output_format": "png",
        },
    )

    saved: list[Path] = []
    images = result.get("images", [])

    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, img_data in enumerate(images):
            url = img_data.get("url", "")
            if not url:
                continue
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.content
            img = Image.open(io.BytesIO(raw)).convert("RGBA")
            img = _remove_white_background(img)
            img = img.resize((size, size), Image.LANCZOS)
            if i == 0:
                dest = output_path
            else:
                dest = output_path.with_stem(output_path.stem + f"_v{i + 1}")
            img.save(dest, "PNG", optimize=True)
            saved.append(dest)

    return saved


def _remove_white_background(img: Image.Image) -> Image.Image:
    """
    Convert near-white backgrounds to transparency.
    Works well for icon-style art that Flux generates on light backgrounds.
    """
    img = img.convert("RGBA")
    data = img.getdata()
    new_data: list[tuple[int, int, int, int]] = []
    for r, g, b, a in data:
        if r > 240 and g > 240 and b > 240:
            new_data.append((r, g, b, 0))
        else:
            new_data.append((r, g, b, a))
    img.putdata(new_data)
    return img
