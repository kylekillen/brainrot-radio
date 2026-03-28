#!/usr/bin/env python3
"""
artwork.py — Generate per-episode podcast artwork for Killen Time.

Uses mflux (MLX-native FLUX) to generate images locally on Apple Silicon,
then composites episode title text and show branding via Pillow.

Usage:
    python3 artwork.py --title "AI Wars Heat Up" --topics "AI,Claude,OpenAI"
    python3 artwork.py --title "NBA Trade Deadline" --topics "NBA,trades" --seed 123
    python3 artwork.py --title "Market Chaos" --size 1400  # 1400x1400
    python3 artwork.py --fallback  # just copy static artwork

Output: assets/episode-artwork/artwork-YYYY-MM-DD[-NN].jpg
"""

import argparse
import shutil
import sys
import time
import traceback
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ── Paths ──────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent
ASSETS_DIR = PROJECT_DIR / "assets"
ARTWORK_DIR = ASSETS_DIR / "episode-artwork"
STATIC_ARTWORK = ASSETS_DIR / "artwork.jpg"

# ── Defaults ───────────────────────────────────────────────────────────
DEFAULT_GEN_SIZE = 1024  # diffusion model native resolution
DEFAULT_OUTPUT_SIZE = 3000  # podcast spec (Apple requires 1400-3000)
DEFAULT_STEPS = 4  # FLUX.2 Klein is step-distilled to 4
DEFAULT_QUANTIZE = 8  # 8-bit quantization for M1 16GB
JPEG_QUALITY = 95


# ── Topic-to-Visual Mapping ───────────────────────────────────────────
TOPIC_VISUALS = {
    "ai": "geometric eye shape, radiating concentric circles, angular circuit lines",
    "tech": "interlocking geometric gears, angular digital grid, bold arrow shapes",
    "prediction markets": "bold bar chart silhouettes, angular probability arrows, split geometric panels",
    "kalshi": "geometric scale balance, angular split composition, bold percentage shapes",
    "polymarket": "tessellated hexagonal grid, angular node connections, bold geometric chain",
    "nba": "bold basketball silhouette, angular court lines, geometric player figure",
    "sports": "bold athletic figure silhouette, angular motion lines, geometric trophy shape",
    "trading": "angular candlestick shapes, bold zigzag line, geometric chart silhouette",
    "crypto": "bold hexagonal coin shape, angular chain links, geometric block pattern",
    "politics": "bold capitol dome silhouette, angular columns, geometric eagle shape",
    "entertainment": "bold film strip shapes, angular spotlight beam, geometric screen frame",
    "screenwriting": "bold typewriter key silhouette, angular page shapes, geometric film slate",
    "science": "bold atomic orbital rings, angular molecular bonds, geometric flask silhouette",
    "health": "bold heartbeat zigzag, angular DNA helix, geometric cross shape",
    "economics": "bold currency symbol silhouettes, angular graph arrows, geometric globe shape",
    "music": "bold sound wave shapes, angular piano key pattern, geometric note silhouette",
    "gaming": "bold pixel grid, angular controller silhouette, geometric power symbol",
    "space": "bold planet silhouette, angular orbit rings, geometric star burst",
    "climate": "bold earth silhouette, angular wave patterns, geometric sun rays",
    "default": "bold geometric shapes, angular intersecting planes, stark abstract composition",
}


def build_prompt(title: str, topics: list[str]) -> str:
    """Build a diffusion model prompt from episode title and topics."""
    # Map topics to visual elements
    visuals = []
    for topic in topics:
        topic_lower = topic.strip().lower()
        for key, visual in TOPIC_VISUALS.items():
            if key in topic_lower or topic_lower in key:
                visuals.append(visual)
                break
        else:
            visuals.append(TOPIC_VISUALS["default"])

    # Deduplicate while preserving order
    seen = set()
    unique_visuals = []
    for v in visuals:
        if v not in seen:
            seen.add(v)
            unique_visuals.append(v)

    visual_str = ", ".join(unique_visuals[:3])  # max 3 visual elements

    prompt = (
        f"Podcast cover art inspired by the theme '{title}'. "
        f"Featuring {visual_str}. "
        "Saul Bass inspired graphic design. Bold flat geometric shapes, stark minimalist composition. "
        "Strong silhouettes against flat color planes. Limited color palette: deep black background "
        "with bold orange, vermillion red, and warm gold accent shapes. "
        "Mid-century modern poster aesthetic, high contrast, paper cut-out style, no gradients. "
        "No text, no words, no letters, no watermarks."
    )
    return prompt


def generate_image(prompt: str, seed: int, gen_size: int, steps: int) -> Image.Image:
    """Generate an image using mflux. Returns a PIL Image."""
    # Try FLUX.2 Klein 4B first (fastest, fits M1 16GB easily)
    try:
        from mflux.models.flux2 import Flux2Klein

        print(f"Loading FLUX.2 Klein 4B (q{DEFAULT_QUANTIZE})...")
        model = Flux2Klein(quantize=DEFAULT_QUANTIZE)
        print(f"Generating {gen_size}x{gen_size} image ({steps} steps, seed {seed})...")
        t0 = time.time()
        result = model.generate_image(
            prompt=prompt,
            seed=seed,
            num_inference_steps=steps,
            width=gen_size,
            height=gen_size,
        )
        elapsed = time.time() - t0
        print(f"Generated in {elapsed:.1f}s")
        # mflux returns an object with .save() — convert to PIL
        # Save to temp file and reload as PIL Image
        tmp_path = ARTWORK_DIR / ".tmp-gen.png"
        result.save(str(tmp_path))
        img = Image.open(tmp_path).convert("RGB")
        tmp_path.unlink(missing_ok=True)
        return img

    except (ImportError, Exception) as e:
        print(f"FLUX.2 Klein not available ({e}), trying FLUX.1 schnell...")

    # Fallback: FLUX.1 schnell (12B, needs 8-bit quantization on 16GB)
    try:
        from mflux import Flux1
        from mflux.config.model_config import ModelConfig

        # Use smaller resolution for FLUX.1 on M1 16GB to avoid swap
        if gen_size > 768:
            print(f"WARNING: FLUX.1 on M1 16GB — reducing to 768x768 to avoid swap thrashing")
            gen_size = 768

        print(f"Loading FLUX.1 schnell (q{DEFAULT_QUANTIZE})...")
        model = Flux1(
            model_config=ModelConfig.from_name("schnell"),
            quantize=DEFAULT_QUANTIZE,
        )
        print(f"Generating {gen_size}x{gen_size} image (2 steps, seed {seed})...")
        t0 = time.time()
        result = model.generate_image(
            prompt=prompt,
            seed=seed,
            num_inference_steps=2,  # schnell is designed for 1-4 steps
            width=gen_size,
            height=gen_size,
        )
        elapsed = time.time() - t0
        print(f"Generated in {elapsed:.1f}s")
        tmp_path = ARTWORK_DIR / ".tmp-gen.png"
        result.save(str(tmp_path))
        img = Image.open(tmp_path).convert("RGB")
        tmp_path.unlink(missing_ok=True)
        return img

    except (ImportError, Exception) as e:
        print(f"FLUX.1 schnell also failed ({e})")
        raise RuntimeError("No image generation model available. Run setup-image-model.sh first.")


def add_text_overlay(img: Image.Image, title: str, show_name: str = "KILLEN TIME") -> Image.Image:
    """Add episode title and show name text overlay to the image."""
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Try to use a good system font, fall back to default
    font_paths = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSDisplay.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ]

    title_font = None
    brand_font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                title_font = ImageFont.truetype(fp, size=int(width * 0.05))
                brand_font = ImageFont.truetype(fp, size=int(width * 0.08))
                break
            except Exception:
                continue

    if title_font is None:
        title_font = ImageFont.load_default()
        brand_font = ImageFont.load_default()

    # Semi-transparent dark gradient at bottom for text readability
    gradient = Image.new("RGBA", (width, int(height * 0.35)), (0, 0, 0, 0))
    gradient_draw = ImageDraw.Draw(gradient)
    for y in range(gradient.height):
        alpha = int(200 * (y / gradient.height))
        gradient_draw.rectangle([(0, y), (width, y + 1)], fill=(0, 0, 0, alpha))

    # Composite gradient onto image
    img_rgba = img.convert("RGBA")
    img_rgba.paste(gradient, (0, height - gradient.height), gradient)
    img = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Show name — bottom center, larger
    brand_y = height - int(height * 0.12)
    brand_bbox = draw.textbbox((0, 0), show_name, font=brand_font)
    brand_w = brand_bbox[2] - brand_bbox[0]
    brand_x = (width - brand_w) // 2
    # Shadow
    draw.text((brand_x + 2, brand_y + 2), show_name, fill=(0, 0, 0), font=brand_font)
    # Main text
    draw.text((brand_x, brand_y), show_name, fill=(255, 255, 255), font=brand_font)

    # Episode title — above show name, smaller, wrapped
    title_upper = title.upper()
    # Simple word wrap
    max_chars = max(20, int(width / (width * 0.03)))  # rough char limit
    words = title_upper.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        test_bbox = draw.textbbox((0, 0), test, font=title_font)
        if test_bbox[2] - test_bbox[0] > width * 0.85:
            if current_line:
                lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    # Draw title lines
    line_height = int(width * 0.06)
    title_start_y = brand_y - len(lines) * line_height - int(height * 0.02)
    for i, line in enumerate(lines):
        line_bbox = draw.textbbox((0, 0), line, font=title_font)
        line_w = line_bbox[2] - line_bbox[0]
        line_x = (width - line_w) // 2
        line_y = title_start_y + i * line_height
        draw.text((line_x + 2, line_y + 2), line, fill=(0, 0, 0), font=title_font)
        draw.text((line_x, line_y), line, fill=(230, 230, 230), font=title_font)

    return img


def get_output_path(output_size: int) -> Path:
    """Generate output filename: artwork-YYYY-MM-DD[-NN].jpg"""
    today = date.today().isoformat()
    base = ARTWORK_DIR / f"artwork-{today}.jpg"
    if not base.exists():
        return base
    # Find next available suffix
    for n in range(2, 100):
        candidate = ARTWORK_DIR / f"artwork-{today}-{n:02d}.jpg"
        if not candidate.exists():
            return candidate
    return ARTWORK_DIR / f"artwork-{today}-99.jpg"


def use_fallback(output_path: Path) -> Path:
    """Copy static artwork as fallback."""
    if not STATIC_ARTWORK.exists():
        print(f"ERROR: Static artwork not found at {STATIC_ARTWORK}")
        sys.exit(1)
    shutil.copy2(STATIC_ARTWORK, output_path)
    print(f"Fallback: copied static artwork to {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate Killen Time episode artwork")
    parser.add_argument("--title", type=str, help="Episode title")
    parser.add_argument("--topics", type=str, default="", help="Comma-separated topic keywords")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (default: date-based)")
    parser.add_argument("--size", type=int, default=DEFAULT_OUTPUT_SIZE, help=f"Output size in px (default: {DEFAULT_OUTPUT_SIZE})")
    parser.add_argument("--gen-size", type=int, default=DEFAULT_GEN_SIZE, help=f"Generation size (default: {DEFAULT_GEN_SIZE})")
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS, help=f"Inference steps (default: {DEFAULT_STEPS})")
    parser.add_argument("--no-text", action="store_true", help="Skip text overlay")
    parser.add_argument("--fallback", action="store_true", help="Use static artwork (skip generation)")
    parser.add_argument("--output", type=str, default=None, help="Override output path")
    args = parser.parse_args()

    # Create output directory
    ARTWORK_DIR.mkdir(parents=True, exist_ok=True)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = get_output_path(args.size)

    # Fallback mode
    if args.fallback:
        use_fallback(output_path)
        return

    # Require title for generation
    if not args.title:
        parser.error("--title is required (or use --fallback)")

    # Parse topics
    topics = [t.strip() for t in args.topics.split(",") if t.strip()] if args.topics else ["default"]

    # Seed: date-based by default for reproducibility
    if args.seed is None:
        today = date.today()
        args.seed = today.year * 10000 + today.month * 100 + today.day

    # Build prompt
    prompt = build_prompt(args.title, topics)
    print(f"Prompt: {prompt[:120]}...")
    print(f"Seed: {args.seed}")
    print()

    # Generate
    try:
        img = generate_image(prompt, args.seed, args.gen_size, args.steps)

        # Upscale to target size
        if img.size[0] != args.size:
            print(f"Upscaling {img.size[0]}x{img.size[1]} -> {args.size}x{args.size}...")
            img = img.resize((args.size, args.size), Image.LANCZOS)

        # Add text overlay
        if not args.no_text:
            print("Adding text overlay...")
            img = add_text_overlay(img, args.title)

        # Save as JPEG
        img.save(output_path, "JPEG", quality=JPEG_QUALITY)
        print(f"Saved: {output_path} ({output_path.stat().st_size / 1024:.0f} KB)")

    except Exception as e:
        print(f"Generation failed: {e}")
        traceback.print_exc()
        print()
        print("Falling back to static artwork...")
        use_fallback(output_path)


if __name__ == "__main__":
    main()
