import os
import math
import shutil
import time
from PIL import Image


# --- Main Pipeline Orchestrator ---

def run_image_pipeline(project_path: str, grid_rows: int = 4, grid_cols: int = 4, bg_color: str = 'black', spacing: int = 0, downscale_factor: int = 3):
    """
    Runs a complete image processing pipeline, including timing the execution.
    1. Crops and downsizes images from <project_path>/Print to <project_path>/Share.
    2. Creates grid images using the processed images from <project_path>/Share.
    3. Renames the images from <project_path>/Share and saves them to <project_path>/Forge.

    Args:
        project_path (str): The full path to the main project folder.
        grid_rows (int, optional): Number of rows for the image grid. Defaults to 4.
        grid_cols (int, optional): Number of columns for the image grid. Defaults to 4.
        bg_color (str, optional): Background color for the grid ('white' or 'black'). Defaults to 'black'.
        spacing (int, optional): Pixel spacing between images in the grid. Defaults to 0.
        downscale_factor (int, optional): The factor by which to downscale images. Defaults to 3.
    """
    # --- Start Timer ---
    start_time = time.monotonic()
    print("=== STARTING IMAGE PIPELINE ===\n")

    # Define standardized folder paths
    print_folder = os.path.join(project_path, 'Print')
    share_folder = os.path.join(project_path, 'Share')
    forge_folder = os.path.join(project_path, 'Forge')

    # --- Step 1: Crop and Downsize images for the 'Share' folder ---
    print("--- Starting Step 1: Cropping and Downsizing to 'Share' folder ---")
    crop_and_downsize_for_share(
        input_folder=print_folder,
        output_folder=share_folder,
        downscale_factor=downscale_factor
    )
    print("--- Step 1 Finished ---\n")

    # --- Step 2: Create Image Grids from the 'Share' folder ---
    print("--- Starting Step 2: Creating Image Grids ---")
    run_grid_maker(
        folder_path=share_folder,
        output_path=project_path,
        rows=grid_rows,
        cols=grid_cols,
        background_color=bg_color,
        spacer_pixels=spacing
    )
    print("--- Step 2 Finished ---\n")

    # --- Step 3: Rename files from 'Share' for the 'Forge' folder ---
    print("--- Starting Step 3: Renaming files for 'Forge' folder ---")
    rename_for_forge(
        source_folder=share_folder,
        destination_folder=forge_folder
    )
    print("--- Step 3 Finished ---")

    # --- End Timer and Print Duration ---
    end_time = time.monotonic()
    duration = end_time - start_time
    print("\n=== PIPELINE FINISHED ===")
    print(f"Total execution time: {duration:.2f} seconds.")


# --- Child Functions ---

def crop_and_downsize_for_share(input_folder: str, output_folder: str, downscale_factor: int):
    """
    Crops bleed based on a ratio, downsizes the image, and saves it to the output folder.
    Handles images of different resolutions, provided they have the correct aspect ratio.
    """
    if not os.path.isdir(input_folder):
        print(f"Error: Input folder for cropping not found at '{input_folder}'. Skipping step.")
        return

    os.makedirs(output_folder, exist_ok=True)

    # Ratios derived from the original bleed crop (2010x2814 from 2187x2975).
    # This defines the percentage of the original image to keep after cropping.
    CROP_WIDTH_RATIO = 2010 / 2187
    CROP_HEIGHT_RATIO = 2814 / 2975

    # Expected aspect ratio for validation, with a small tolerance.
    # Using the 2187x2975 dimensions as the reference.
    EXPECTED_ASPECT_RATIO = 2187 / 2975

    print(f"Scanning for images in: {input_folder}")
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename)
            try:
                with Image.open(input_path) as img:
                    img_width, img_height = img.size

                    # Validate aspect ratio instead of exact size.
                    # We use math.isclose to account for small floating point variations.
                    current_aspect_ratio = img_width / img_height
                    if not math.isclose(current_aspect_ratio, EXPECTED_ASPECT_RATIO, rel_tol=1e-3):
                        print(
                            f"Skipping '{filename}': incorrect aspect ratio {current_aspect_ratio:.4f}. Expected ~{EXPECTED_ASPECT_RATIO:.4f}.")
                        continue

                    # 1. Calculate the crop box dynamically for the current image
                    target_width = int(img_width * CROP_WIDTH_RATIO)
                    target_height = int(img_height * CROP_HEIGHT_RATIO)

                    left = (img_width - target_width) // 2
                    top = (img_height - target_height) // 2
                    right = left + target_width
                    bottom = top + target_height
                    crop_box = (left, top, right, bottom)

                    cropped_img = img.crop(crop_box)

                    # 2. Downsize the cropped image
                    new_width = cropped_img.width // downscale_factor
                    new_height = cropped_img.height // downscale_factor
                    resized_img = cropped_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                    # 3. Save the final result
                    resized_img.save(output_path)
                    print(f"Processed '{filename}' ({img_width}x{img_height}) and saved to '{output_folder}'.")
            except Exception as e:
                print(f"Could not process '{filename}'. Error: {e}")


def run_grid_maker(folder_path: str, output_path: str, rows: int, cols: int, background_color: str, spacer_pixels: int):
    """
    Combines images from a folder into one or more grid images.
    """
    if not os.path.isdir(folder_path):
        print(f"Error: Source folder for grid maker not found at '{folder_path}'. Skipping step.")
        return

    valid_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff')
    try:
        image_files = sorted([f for f in os.listdir(folder_path) if f.lower().endswith(valid_extensions)])
    except FileNotFoundError:
        print(f"Error: Could not access the directory at '{folder_path}'. Skipping step.")
        return

    if not image_files:
        print(f"No images found in '{folder_path}' to create a grid.")
        return

    project_folder_name = os.path.basename(os.path.abspath(output_path))
    images_per_grid = rows * cols
    num_grids = math.ceil(len(image_files) / images_per_grid)

    print(f"Found {len(image_files)} images. Creating {num_grids} grid(s)...")

    with Image.open(os.path.join(folder_path, image_files[0])) as img:
        source_width, source_height = img.size
    print(f"Using source image dimensions for grid: {source_width}x{source_height}")

    for grid_index in range(num_grids):
        print(f"\nProcessing Grid #{grid_index + 1}...")
        start_index = grid_index * images_per_grid
        end_index = start_index + images_per_grid
        grid_image_files = image_files[start_index:end_index]

        total_width = (source_width * cols) + (spacer_pixels * (cols + 1))
        total_height = (source_height * rows) + (spacer_pixels * (rows + 1))

        grid_image = Image.new('RGB', (total_width, total_height), color=background_color)

        for i, filename in enumerate(grid_image_files):
            row = i // cols
            col = i % cols
            paste_x = (col * source_width) + (spacer_pixels * (col + 1))
            paste_y = (row * source_height) + (spacer_pixels * (row + 1))
            try:
                with Image.open(os.path.join(folder_path, filename)) as img:
                    grid_image.paste(img, (paste_x, paste_y))
            except IOError:
                print(f"Warning: Could not process {filename}. Skipping.")
                continue

        output_filename = f"{project_folder_name} {grid_index + 1}.jpg"
        final_output_path = os.path.join(output_path, output_filename)

        try:
            grid_image.save(final_output_path, format='JPEG', quality=95)
            print(f"✅ Success! Grid saved to: {final_output_path}")
        except IOError as e:
            print(f"Error: Could not save the final image. {e}")


def rename_for_forge(source_folder: str, destination_folder: str):
    """
    Copies and renames files from a source folder to a destination folder.
    """
    if not os.path.isdir(source_folder):
        print(f"Error: Source folder for Forge prep not found at '{source_folder}'. Skipping step.")
        return

    os.makedirs(destination_folder, exist_ok=True)

    print("Copying and renaming files for Forge...")
    for file_name in os.listdir(source_folder):
        # We process any image file type that might be in the Share folder
        if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            # Determine the base name by removing the extension
            base_name, extension = os.path.splitext(file_name)

            # Strips leading numbers, spaces, and underscores from the base name
            stripped_name = base_name.lstrip('0123456789_ ')

            # Perform final replacements and add the new extension
            new_file_name = stripped_name.replace('’', '\'') + '.fullborder.jpg'

            source_path = os.path.join(source_folder, file_name)
            destination_path = os.path.join(destination_folder, new_file_name)

            shutil.copy2(source_path, destination_path)
            print(f"Copied '{file_name}' to '{new_file_name}' in {destination_folder}")


# --- Example Usage ---
if __name__ == '__main__':

    # --- IMPORTANT ---
    # Define the main project path.
    # Use a raw string (r"...") on Windows to handle backslashes correctly.
    # There should already be a folder called Print inside of the filepath listed here
    project = r'C:\Users\kayss\Pictures\Magic\Commander\Test'

    # --- Optional Parameters ---
    GRID_ROWS = 4
    GRID_COLS = 4
    BACKGROUND_COLOR = 'black'
    SPACING_PIXELS = 0
    DOWNSCALE_FACTOR = 3

    # --- Run the full pipeline ---
    run_image_pipeline(
        project_path=project,
        grid_rows=GRID_ROWS,
        grid_cols=GRID_COLS,
        bg_color=BACKGROUND_COLOR,
        spacing=SPACING_PIXELS,
        downscale_factor=DOWNSCALE_FACTOR
    )