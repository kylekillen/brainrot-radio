#!/bin/bash
# setup-image-model.sh — Install mflux for local image generation on Apple Silicon
# Run this once. After setup, use artwork.py to generate episode artwork.

set -euo pipefail

VENV_DIR="$HOME/brainrot-radio/venv"
ARTWORK_DIR="$HOME/brainrot-radio/assets/episode-artwork"

echo "=== Killen Time — Image Model Setup ==="
echo ""
echo "Hardware check:"
sysctl -n machdep.cpu.brand_string
echo "RAM: $(sysctl -n hw.memsize | awk '{printf "%.0f GB", $0/1024/1024/1024}')"
echo ""

# ── Step 1: Activate existing venv ──────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    echo "ERROR: Expected venv at $VENV_DIR (created by brainrot-radio setup)"
    echo "Create it first: python3 -m venv $VENV_DIR"
    exit 1
fi

echo "Activating venv at $VENV_DIR..."
source "$VENV_DIR/bin/activate"

# ── Step 2: Install mflux ──────────────────────────────────────────
echo ""
echo "Installing mflux (MLX-native image generation)..."
pip install --upgrade mflux

echo ""
echo "Verifying installation..."
python3 -c "
import mflux
print('mflux installed successfully')
print(f'  Location: {mflux.__file__}')
"

# ── Step 3: Verify Pillow (needed for upscaling + text overlay) ────
echo ""
echo "Checking Pillow..."
python3 -c "
from PIL import Image, ImageDraw, ImageFont
print('Pillow OK — Image, ImageDraw, ImageFont all available')
"

# ── Step 4: Create output directory ────────────────────────────────
mkdir -p "$ARTWORK_DIR"
echo ""
echo "Episode artwork directory: $ARTWORK_DIR"

# ── Step 5: Pre-download model weights ─────────────────────────────
echo ""
echo "Pre-downloading FLUX.2 Klein 4B model weights (8-bit quantized)..."
echo "This will download ~2-4GB on first run. Subsequent runs use cached weights."
echo ""

# Generate a small test image to trigger model download
python3 -c "
from mflux.models.flux2 import Flux2Klein

print('Loading FLUX.2 Klein 4B (8-bit quantized)...')
model = Flux2Klein(quantize=8)

print('Generating test image (256x256, 1 step)...')
image = model.generate_image(
    prompt='test',
    seed=42,
    num_inference_steps=1,
    width=256,
    height=256,
)
image.save('$ARTWORK_DIR/test-setup.png')
print('Test image saved to $ARTWORK_DIR/test-setup.png')
print('')
print('Setup complete! Model weights are cached for future use.')
" 2>&1

# If FLUX.2 Klein isn't available yet, fall back to FLUX.1 schnell
if [ $? -ne 0 ]; then
    echo ""
    echo "FLUX.2 Klein not available in this mflux version. Trying FLUX.1 schnell..."
    python3 -c "
from mflux import Flux1

print('Loading FLUX.1 schnell (8-bit quantized)...')
model = Flux1(
    model_config=Flux1.ModelConfig.from_name('schnell'),
    quantize=8,
)

print('Generating test image (256x256, 2 steps)...')
image = model.generate_image(
    prompt='test',
    seed=42,
    num_inference_steps=2,
    width=256,
    height=256,
)
image.save('$ARTWORK_DIR/test-setup.png')
print('Test image saved to $ARTWORK_DIR/test-setup.png')
print('')
print('Setup complete! Model weights are cached for future use.')
print('NOTE: Using FLUX.1 schnell — heavier on memory. Generate at 512x512 max and upscale.')
"
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Usage:"
echo "  source $VENV_DIR/bin/activate"
echo "  python3 ~/brainrot-radio/artwork.py --title 'Episode Title' --topics 'AI,prediction markets,NBA'"
echo ""
echo "The first real generation (1024x1024) will take 30-120 seconds on M1."
echo "Subsequent generations use cached model weights and are faster to start."
