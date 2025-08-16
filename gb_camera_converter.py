import argparse
from PIL import Image, ImageOps
import numpy as np
import os
import sys
import random

# --- GB Camera Hardware Constants ---
GB_WIDTH = 128
GB_HEIGHT = 112

# --- Color and Dithering Constants ---
# A dictionary of preset palettes for convenience.
# Colors are specified from darkest to lightest.
PRESET_PALETTES = {
    "grayscale": ["#000000", "#555555", "#AAAAAA", "#FFFFFF"],
    "green":     ["#0f380f", "#306230", "#8bac0f", "#9bbc0f"],
    "berry":     ["#2c0020", "#6b1e53", "#c35064", "#ff9a74"],
    "frost":     ["#1a2a3a", "#2a5a7a", "#6a9ac4", "#e0f0ff"],

    # Crazy palettes for fun
    "crimson":   ["#210002", "#64000b", "#b51d2a", "#ffd8d6"],
    "vaporwave": ["#2c0e3a", "#aa2a8d", "#2de2e6", "#fff0f5"],

    # Thematic & Atmospheric
    "sunset":    ["#201033", "#7d2e38", "#eb8e44", "#fcdab5"],
    "midnight":  ["#0a0f26", "#213c54", "#5a6a8c", "#c4d1e2"],
    "desert":    ["#4a2e19", "#91642f", "#d4a96a", "#fff4c2"],
    "toxic":     ["#0f1c0d", "#2a572a", "#98e85a", "#fafaae"],
}

DITHER_MATRIX = np.array([
    [0, 2],
    [3, 1]
])

def hex_to_rgb(hex_code):
    """Converts a hex color string (e.g., '#RRGGBB') to an (R, G, B) tuple."""
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))

def parse_palette(palette_arg):
    """Parses user palette input into a flat list for Pillow."""
    if len(palette_arg) == 1 and palette_arg[0] in PRESET_PALETTES:
        hex_codes = PRESET_PALETTES[palette_arg[0]]
        print(f"Using preset palette: {palette_arg[0]}")
    elif len(palette_arg) == 4:
        hex_codes = palette_arg
        print(f"Using custom palette: {hex_codes}")
    else:
        print("Error: Palette must be a preset name or 4 hex codes.", file=sys.stderr)
        sys.exit(1)

    rgb_colors = [hex_to_rgb(code) for code in hex_codes]
    # Flatten the list of tuples into [R1, G1, B1, R2, G2, B2, ...]
    return [value for color in rgb_colors for value in color]


def convert_to_gb_camera(image_path, output_path, contrast, use_autocontrast, dither_intensity, palette, orientation='auto'):
    """
    Converts an image to a hardware-accurate Game Boy Camera picture.
    """
    try:
        img = Image.open(image_path)
    except FileNotFoundError:
        print(f"Error: The file '{image_path}' was not found.", file=sys.stderr)
        return

    # Determine target dimensions based on orientation
    original_width, original_height = img.size
    if orientation == 'auto':
        if original_height > original_width:
            target_width = GB_HEIGHT  # 112 (portrait)
            target_height = GB_WIDTH   # 128
        else:
            target_width = GB_WIDTH    # 128 (landscape)
            target_height = GB_HEIGHT  # 112
    elif orientation == 'portrait':
        target_width = GB_HEIGHT
        target_height = GB_WIDTH
    elif orientation == 'landscape':
        target_width = GB_WIDTH
        target_height = GB_HEIGHT
    else:
        print("Error: Invalid orientation specified. Use 'auto', 'portrait', or 'landscape'.", file=sys.stderr)
        return

    # 1. Prepare the palette first
    final_palette = parse_palette(palette)

    # 2. Convert to grayscale and apply contrast
    img_gray = ImageOps.grayscale(img)
    if use_autocontrast:
        img_gray = ImageOps.autocontrast(img_gray, cutoff=1)
    if contrast != 1.0:
        img_array = np.array(img_gray, dtype=np.float32)
        img_array = (img_array - 128) * contrast + 128
        img_array = np.clip(img_array, 0, 255)
        img_gray = Image.fromarray(img_array.astype(np.uint8))

    # 3. Crop to aspect ratio and resize
    # ImageOps.fit crops the image to the specified aspect ratio and then resizes.
    # This avoids distortion by taking the center slice of the image.
    print(f"Cropping to {target_width}x{target_height} aspect ratio and resizing...")
    img_fit = ImageOps.fit(img_gray, (target_width, target_height), Image.Resampling.LANCZOS)

    # 4. Apply ordered dithering
    pixels = np.array(img_fit, dtype=np.float32)
    threshold_map = (np.tile(DITHER_MATRIX, (target_height // 2, target_width // 2)) / 4.0 - 0.5) * (64 * dither_intensity)
    dithered_pixels = np.clip(pixels + threshold_map, 0, 255)
    palette_indices = np.round(dithered_pixels / 85).astype(np.uint8)
    palette_indices = np.clip(palette_indices, 0, 3)

    # 5. Create final paletted image
    final_img = Image.new('P', (target_width, target_height))
    final_img.putpalette(final_palette)
    final_img.putdata(palette_indices.flatten())

    # 6. Save the upscaled final image
    final_img_upscaled = final_img.resize((target_width * 4, target_height * 4), Image.Resampling.NEAREST)

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)

    final_img_upscaled.save(output_path)
    print(f"Successfully converted image saved to: {output_path}")

def convert_folder_to_gb_camera(input_folder, output_folder, contrast=1.0, use_autocontrast=False, dither_intensity=1.0, palette=["grayscale"], use_random_palette=False, orientation='auto'):
    """
    Converts all images in a folder to Game Boy Camera style pictures.

    Args:
        input_folder: Path to the folder containing input images
        output_folder: Path to the folder where processed images will be saved
        contrast: Contrast adjustment factor
        use_autocontrast: Whether to apply auto-contrast
        dither_intensity: Strength of dithering effect
        palette: Color palette to use
        use_random_palette: Whether to use a random palette for each image
        orientation: Orientation mode ('auto', 'portrait', or 'landscape')
    """
    # Create the output folder if it doesn't exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
        print(f"Created output directory: {output_folder}")

    # Supported image file extensions
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff']

    # Counter for processed images
    processed_count = 0

    # Process each file in the input folder
    for filename in os.listdir(input_folder):
        file_path = os.path.join(input_folder, filename)

        # Skip directories and non-image files
        if os.path.isdir(file_path):
            continue

        file_ext = os.path.splitext(filename)[1].lower()
        if file_ext not in image_extensions:
            continue

        # Generate output path
        output_filename = os.path.splitext(filename)[0] + ".png"
        output_path = os.path.join(output_folder, output_filename)

        # Select a random palette if requested
        current_palette = palette
        if use_random_palette:
            palette_name = random.choice(list(PRESET_PALETTES.keys()))
            current_palette = [palette_name]
            print(f"Using random palette for {filename}: {palette_name}")

        # Convert the image
        print(f"Processing {filename}...")
        convert_to_gb_camera(
            file_path,
            output_path,
            contrast,
            use_autocontrast,
            dither_intensity,
            current_palette,
            orientation
        )

        processed_count += 1

    print(f"Batch processing complete. Converted {processed_count} images to Game Boy Camera style.")

def main():
    parser = argparse.ArgumentParser(
        description="Convert an image into a Game Boy Camera style picture.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("input_image", help="Path to the input image file.")
    parser.add_argument("-o", "--output", default="gb_output.png", help="Path for the output image file.")
    parser.add_argument("-c", "--contrast", type=float, default=1.0, help="Manual contrast factor.")
    parser.add_argument("--autocontrast", action="store_true", help="Apply auto-contrast. Recommended.")
    parser.add_argument("--dither-intensity", type=float, default=1.0, help="Dithering strength. 0=posterize.")
    parser.add_argument(
        "--palette",
        nargs='+',
        default=["grayscale"],
        help="Choose a color palette. Either a preset name (green, berry, frost, grayscale) or 4 custom hex colors (e.g., '#RRGGBB' ...)."
    )
    parser.add_argument(
        "--orientation",
        choices=['auto', 'landscape', 'portrait'],
        default='auto',
        help="Orientation mode: 'auto' detects based on aspect ratio, 'landscape' forces 128x112, 'portrait' forces 112x128."
    )

    args = parser.parse_args()

    convert_to_gb_camera(
        args.input_image,
        args.output,
        args.contrast,
        args.autocontrast,
        args.dither_intensity,
        args.palette,
        args.orientation
    )

if __name__ == "__main__":
    main()
