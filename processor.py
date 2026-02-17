"""
RAW Photo Processor for Canon CR3 files.
Optimized for landscape lighting photography.
"""

import rawpy
import numpy as np
from PIL import Image, ImageFilter, ImageEnhance
from io import BytesIO


# Landscape Lighting Preset - optimized for outdoor lighting photos
LANDSCAPE_LIGHTING_PRESET = {
    'exposure': 1.15,      # Slight lift for better visibility
    'warmth': 0.12,        # Warm golden tone
    'contrast': 1.20,      # Punchy contrast
    'shadows': 0.35,       # Recover shadow detail
    'highlights': 0.3,     # Pull back blown highlights on fixtures
    'clarity': 0.25,       # Local contrast for texture pop
    'vibrance': 0.20,      # Boost colors without oversaturation
    'vignette': 0.15,      # Subtle edge darkening
    'sharpness': 1.4,      # Crisp detail enhancement
}

DEFAULT_SETTINGS = {
    'exposure': 1.0,
    'warmth': 0.0,
    'contrast': 1.0,
    'shadows': 0.0,
    'highlights': 0.0,
    'clarity': 0.0,
    'vibrance': 0.0,
    'vignette': 0.0,
    'sharpness': 1.0,
}


def load_raw(path: str, preview: bool = True) -> np.ndarray:
    """
    Load a CR3 RAW file and return RGB array.

    Args:
        path: Path to CR3 file
        preview: If True, use half_size for faster processing

    Returns:
        numpy array (H, W, 3) as float32 in 0-1 range
    """
    with rawpy.imread(path) as raw:
        # Use camera white balance as baseline
        # half_size=True gives 4x speed boost for previews
        rgb = raw.postprocess(
            use_camera_wb=True,
            half_size=preview,
            output_bps=16,
            no_auto_bright=True,
        )

    # Convert to float32 in 0-1 range for processing
    return rgb.astype(np.float32) / 65535.0


def apply_exposure(img: np.ndarray, exposure: float) -> np.ndarray:
    """Apply exposure adjustment (0.5-2.0 range, 1.0 = no change)."""
    return np.clip(img * exposure, 0, 1)


def apply_warmth(img: np.ndarray, warmth: float) -> np.ndarray:
    """
    Apply white balance warmth shift.
    warmth > 0: warmer (boost red/yellow, reduce blue)
    warmth < 0: cooler (boost blue, reduce red)
    Range: -0.5 to 0.5
    """
    if warmth == 0:
        return img

    result = img.copy()
    # Warm: boost red, slightly boost green, reduce blue
    result[:, :, 0] = np.clip(result[:, :, 0] * (1 + warmth * 0.8), 0, 1)  # Red
    result[:, :, 1] = np.clip(result[:, :, 1] * (1 + warmth * 0.2), 0, 1)  # Green
    result[:, :, 2] = np.clip(result[:, :, 2] * (1 - warmth * 0.6), 0, 1)  # Blue

    return result


def apply_contrast(img: np.ndarray, contrast: float) -> np.ndarray:
    """
    Apply contrast adjustment using midpoint pivot.
    contrast > 1: more contrast
    contrast < 1: less contrast
    Range: 0.5-2.0, 1.0 = no change
    """
    if contrast == 1.0:
        return img

    # Pivot around middle gray (0.5)
    return np.clip((img - 0.5) * contrast + 0.5, 0, 1)


def apply_shadow_recovery(img: np.ndarray, amount: float) -> np.ndarray:
    """
    Lift shadows without affecting highlights.
    Uses a soft curve that only affects darker regions.
    amount: 0.0-1.0 (0 = no change, 1 = maximum lift)
    """
    if amount == 0:
        return img

    # Calculate luminance for masking
    luminance = 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]

    # Shadow mask: 1.0 for blacks, 0.0 for highlights
    # Smooth falloff around 0.3 luminance
    shadow_mask = np.clip(1.0 - luminance / 0.4, 0, 1) ** 2
    shadow_mask = shadow_mask[:, :, np.newaxis]

    # Lift shadows by blending toward lifted values
    lift = amount * 0.15  # Max lift amount
    lifted = img + lift * shadow_mask

    return np.clip(lifted, 0, 1)


def apply_highlights_recovery(img: np.ndarray, amount: float) -> np.ndarray:
    """
    Pull back blown highlights to recover detail.
    Uses a soft rolloff curve that compresses bright areas.
    amount: 0.0-1.0 (0 = no change, 1 = maximum recovery)
    """
    if amount == 0:
        return img

    # Calculate luminance
    luminance = 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]

    # Highlight mask: affects pixels above 0.6 luminance
    highlight_mask = np.clip((luminance - 0.6) / 0.4, 0, 1) ** 1.5
    highlight_mask = highlight_mask[:, :, np.newaxis]

    # Compress highlights using soft knee curve
    # This pulls down bright areas while preserving relative differences
    compression = 1.0 - (amount * 0.4 * highlight_mask)
    result = img * compression

    # Slight boost to midtones to compensate
    midtone_boost = amount * 0.05 * (1 - highlight_mask)
    result = result + midtone_boost

    return np.clip(result, 0, 1)


def apply_clarity(img: np.ndarray, amount: float) -> np.ndarray:
    """
    Apply local contrast enhancement (clarity).
    Enhances midtone contrast and texture without affecting shadows/highlights.
    amount: -1.0 to 1.0 (0 = no change, positive = more clarity)
    """
    if amount == 0:
        return img

    from scipy.ndimage import gaussian_filter

    # Create a blurred version for local contrast
    # Use larger radius for more "punch"
    radius = 30
    blurred = np.zeros_like(img)
    for c in range(3):
        blurred[:, :, c] = gaussian_filter(img[:, :, c], sigma=radius)

    # High-pass: difference between original and blurred
    high_pass = img - blurred

    # Calculate luminance for midtone targeting
    luminance = 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]

    # Midtone mask: peaks at 0.5, falls off toward shadows and highlights
    midtone_mask = 1.0 - 2.0 * np.abs(luminance - 0.5)
    midtone_mask = np.clip(midtone_mask, 0, 1) ** 0.7
    midtone_mask = midtone_mask[:, :, np.newaxis]

    # Apply clarity weighted by midtone mask
    result = img + high_pass * amount * midtone_mask * 0.8

    return np.clip(result, 0, 1)


def apply_vibrance(img: np.ndarray, amount: float) -> np.ndarray:
    """
    Intelligent saturation that boosts less-saturated colors more.
    Protects already-saturated colors and skin tones from oversaturation.
    amount: -1.0 to 1.0 (0 = no change, positive = more vibrant)
    """
    if amount == 0:
        return img

    # Convert to HSV-like representation for saturation analysis
    max_rgb = np.max(img, axis=2)
    min_rgb = np.min(img, axis=2)
    saturation = np.where(max_rgb > 0, (max_rgb - min_rgb) / (max_rgb + 0.001), 0)

    # Vibrance mask: boost low-saturation areas more than high-saturation
    # This prevents already-vivid colors from becoming garish
    vibrance_mask = 1.0 - saturation ** 0.5
    vibrance_mask = vibrance_mask[:, :, np.newaxis]

    # Calculate the "colorfulness" boost
    luminance = 0.299 * img[:, :, 0] + 0.587 * img[:, :, 1] + 0.114 * img[:, :, 2]
    luminance = luminance[:, :, np.newaxis]

    # Increase distance from gray (saturation boost)
    color_diff = img - luminance
    boost = amount * vibrance_mask * 0.5

    result = img + color_diff * boost

    return np.clip(result, 0, 1)


def apply_vignette(img: np.ndarray, amount: float) -> np.ndarray:
    """
    Apply vignette (edge darkening) effect.
    amount: 0.0-1.0 (0 = no vignette, 1 = strong vignette)
    """
    if amount == 0:
        return img

    h, w = img.shape[:2]

    # Create radial gradient from center
    y, x = np.ogrid[:h, :w]
    center_y, center_x = h / 2, w / 2

    # Normalize distances to 0-1 range (corners = 1)
    max_dist = np.sqrt(center_x**2 + center_y**2)
    dist = np.sqrt((x - center_x)**2 + (y - center_y)**2) / max_dist

    # Smooth falloff curve - keeps center bright, darkens edges
    # Using power curve for natural falloff
    vignette_mask = 1.0 - (dist ** 1.5) * amount * 0.7
    vignette_mask = np.clip(vignette_mask, 0.3, 1.0)  # Don't go too dark
    vignette_mask = vignette_mask[:, :, np.newaxis]

    return img * vignette_mask


def apply_adjustments(img: np.ndarray, settings: dict) -> np.ndarray:
    """
    Apply all adjustments in correct order.

    Args:
        img: Input image as float32 array (0-1 range)
        settings: Dict with all adjustment parameters

    Returns:
        Adjusted image as float32 array
    """
    # Apply in optimal order for best results:
    # 1. Exposure (base brightness)
    # 2. Highlights recovery (before other tonal adjustments)
    # 3. Shadows (lift dark areas)
    # 4. Contrast (global tonal adjustment)
    # 5. Clarity (local contrast - after global)
    # 6. Warmth (color adjustment)
    # 7. Vibrance (color boost)
    # 8. Vignette (final touch)
    # (sharpness applied later via PIL)

    result = img.copy()

    result = apply_exposure(result, settings.get('exposure', 1.0))
    result = apply_highlights_recovery(result, settings.get('highlights', 0.0))
    result = apply_shadow_recovery(result, settings.get('shadows', 0.0))
    result = apply_contrast(result, settings.get('contrast', 1.0))
    result = apply_clarity(result, settings.get('clarity', 0.0))
    result = apply_warmth(result, settings.get('warmth', 0.0))
    result = apply_vibrance(result, settings.get('vibrance', 0.0))
    result = apply_vignette(result, settings.get('vignette', 0.0))

    return result


def apply_sharpness(pil_img: Image.Image, amount: float) -> Image.Image:
    """
    Apply sharpening using unsharp mask.
    amount: 0.5-3.0 (1.0 = no change)
    """
    if amount == 1.0:
        return pil_img

    enhancer = ImageEnhance.Sharpness(pil_img)
    return enhancer.enhance(amount)


def numpy_to_pil(img: np.ndarray) -> Image.Image:
    """Convert float32 numpy array (0-1) to PIL Image."""
    img_8bit = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(img_8bit, mode='RGB')


def pil_to_numpy(pil_img: Image.Image) -> np.ndarray:
    """Convert PIL Image to float32 numpy array (0-1)."""
    return np.array(pil_img).astype(np.float32) / 255.0


def resize_image(pil_img: Image.Image, max_width: int) -> Image.Image:
    """Resize image to max_width while maintaining aspect ratio."""
    if pil_img.width <= max_width:
        return pil_img

    ratio = max_width / pil_img.width
    new_height = int(pil_img.height * ratio)
    return pil_img.resize((max_width, new_height), Image.Resampling.LANCZOS)


def process_raw(
    path: str,
    settings: dict,
    preview: bool = True,
    max_width: int = 1200
) -> Image.Image:
    """
    Full processing pipeline: load RAW -> apply adjustments -> return PIL Image.

    Args:
        path: Path to CR3 file
        settings: Adjustment settings dict
        preview: Use half_size for faster preview
        max_width: Maximum output width

    Returns:
        Processed PIL Image
    """
    # Load RAW
    img = load_raw(path, preview=preview)

    # Apply color/exposure adjustments
    img = apply_adjustments(img, settings)

    # Convert to PIL
    pil_img = numpy_to_pil(img)

    # Resize
    pil_img = resize_image(pil_img, max_width)

    # Apply sharpening (works better in PIL)
    pil_img = apply_sharpness(pil_img, settings.get('sharpness', 1.0))

    return pil_img


def export_jpg(
    pil_img: Image.Image,
    output_path: str = None,
    quality: int = 85
) -> bytes:
    """
    Export image as optimized JPG.

    Args:
        pil_img: PIL Image to export
        output_path: If provided, save to file
        quality: JPG quality (1-100)

    Returns:
        JPG bytes
    """
    # Convert to RGB if necessary (in case of RGBA)
    if pil_img.mode != 'RGB':
        pil_img = pil_img.convert('RGB')

    buffer = BytesIO()
    pil_img.save(
        buffer,
        format='JPEG',
        quality=quality,
        optimize=True,
        progressive=True
    )
    jpg_bytes = buffer.getvalue()

    if output_path:
        with open(output_path, 'wb') as f:
            f.write(jpg_bytes)

    return jpg_bytes


def get_landscape_lighting_preset() -> dict:
    """Return the landscape lighting preset settings."""
    return LANDSCAPE_LIGHTING_PRESET.copy()


def get_default_settings() -> dict:
    """Return default neutral settings."""
    return DEFAULT_SETTINGS.copy()
