# Local Image Generation for Killen Time — Research

## Hardware

- Apple M1, 16GB unified memory
- macOS Darwin 24.6.0
- Existing venv at `~/brainrot-radio/venv/` with MLX 0.31.0, Pillow 12.1.1, torch 2.10.0

## Options Evaluated

### 1. mflux (RECOMMENDED)

**What:** MLX-native port of FLUX and other diffusion models. Pure Python, pip-installable, designed specifically for Apple Silicon.

**Models available (as of v0.16.7, March 2026):**
- **FLUX.2 Klein 4B** — Fastest option, 4 inference steps, ~7-8GB quantized. Best fit for M1 16GB.
- **FLUX.2 Klein 9B** — Higher quality, but tight on 16GB even quantized.
- **FLUX.1 Schnell 12B** — Legacy, 2-4 steps. 8-bit quantized fits in 16GB but uses swap (~22GB total). ~3 min generation on M1 Pro 16GB.
- **Z-Image Turbo 6B** — Good quality, fast. Should fit in 16GB with 8-bit quantization.
- **FIBO 8B** — JSON-based prompting, interesting but overkill for artwork.

**Why it wins:**
- Already has MLX installed in the venv (0.31.0) — same framework as mlx-whisper
- Python API: `from mflux.models.flux2 import Flux2Klein; model.generate_image(prompt=..., seed=...)`
- 8-bit quantization cuts memory ~50%, critical for M1 16GB
- `uv` already installed on this system
- Active development (v0.16.7 released today, March 2, 2026)
- FLUX.2 Klein 4B at 8-bit quantization should be ~4-5GB, comfortable on 16GB

**Risks:**
- FLUX.1 12B at full precision needs ~22GB (swap required, locks up machine)
- FLUX.2 Klein 4B is newer, less battle-tested
- First run downloads model weights (~2-4GB for 4B quantized)
- Generation at 3000x3000 may be slow — generate at 1024x1024 and upscale with Pillow

**Install:** `pip install mflux` or `uv pip install mflux`

### 2. mlx-examples stable_diffusion

**What:** Apple's official MLX examples repo includes a Stable Diffusion implementation.

**Models:** SDXL Turbo, SD 2.1 only. No FLUX support.

**Why not:** Older models (SD 2.1 is from 2022, SDXL Turbo from late 2023). FLUX produces significantly better results. Would need to clone the repo and install separately — not pip-packaged.

### 3. DiffusionKit (argmaxinc)

**What:** On-device image generation package for Apple Silicon with SD 3.5 Large/Medium support.

**Why not:** Focused on SD 3 family, not FLUX. Requires conda environment with Python 3.11 (venv uses 3.13). Less active than mflux.

### 4. HuggingFace diffusers + MPS

**What:** Standard diffusers library with Apple Metal Performance Shaders backend.

**Why not:** PyTorch MPS backend is slower than native MLX on Apple Silicon. Higher memory overhead. Not optimized for the hardware the way mflux is. Would work but is the worst-performing option on this specific hardware.

### 5. ComfyUI

**What:** Node-based GUI for Stable Diffusion workflows.

**Why not:** GUI-focused, not designed for scripted/headless operation. Heavy install (node.js, custom environments). Overkill for generating podcast artwork from a script.

### 6. Pinocchio / Pinokio

**What:** One-click GUI launcher for local AI models. App Store app and/or Electron-based browser.

**Why not:** GUI wrapper, not scriptable. Installs its own Python/environments. No Python API for automation. Good for experimentation but not for an automated pipeline.

## Recommendation: mflux with FLUX.2 Klein 4B (8-bit quantized)

**Model:** FLUX.2 Klein 4B, quantized to 8-bit
**Generation resolution:** 1024x1024 (then upscale to 3000x3000 or 1400x1400 via Pillow LANCZOS)
**Expected performance:** 30-90 seconds per image on M1 16GB (estimate based on 4B params, 4 steps, 8-bit)
**Memory usage:** ~4-5GB (comfortable headroom on 16GB)

### Why not generate at 3000x3000 directly?

Diffusion models produce their best output at their training resolution (typically 1024x1024 for FLUX). Generating at 3000x3000 would:
1. Use 9x the memory (likely crash or require massive swap)
2. Take 9x longer
3. Not necessarily produce better results

High-quality LANCZOS upscaling from 1024x1024 to 3000x3000 is standard practice for podcast artwork.

## Prompt Strategy

For podcast episode artwork, the prompt should create visually striking, recognizable images that work at small sizes (podcast app thumbnails). Strategy:

```
Base prompt template:
"Podcast cover art for '{title}', featuring {visual_elements}.
Bold modern design, high contrast, clean composition,
dark background with vibrant accent colors.
Professional podcast artwork style, no text."
```

Text overlay (episode title, show name) should be added via Pillow after generation — diffusion models are poor at text rendering.

## File Locations

- Setup script: `~/brainrot-radio/setup-image-model.sh`
- Artwork generator: `~/brainrot-radio/artwork.py`
- Episode artwork output: `~/brainrot-radio/assets/episode-artwork/`
- Static fallback: `~/brainrot-radio/assets/artwork.jpg`
