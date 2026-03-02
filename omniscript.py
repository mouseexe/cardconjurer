import os
import math
import shutil
import time
from PIL import Image
import json
from datetime import date
import unicodedata
import re
import zipfile


def run_image_pipeline(project_path: str, grid_rows: int = 4, grid_cols: int = 4, bg_color: str = 'black', spacing: int = 0, downscale_factor: int = 3):
    start_time = time.monotonic()
    print("=== STARTING IMAGE PIPELINE ===\n")

    print_folder = os.path.join(project_path, 'Print')
    share_folder = os.path.join(project_path, 'Share')
    forge_folder = os.path.join(project_path, 'Forge')

    source_folders = [print_folder]
    backsides_folder = os.path.join(print_folder, 'Backsides')
    if os.path.isdir(backsides_folder):
        print(f"Found 'Backsides' folder at: {backsides_folder}")
        source_folders.append(backsides_folder)

    print("--- Starting Step 1: Cropping and Downsizing to 'Share' folder ---")
    crop_and_downsize_for_share(
        input_folders=source_folders,
        output_folder=share_folder,
        downscale_factor=downscale_factor
    )
    print("--- Step 1 Finished ---\n")

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

    print("--- Starting Step 3: Renaming files for 'Forge' folder ---")
    rename_for_forge(
        source_folder=share_folder,
        destination_folder=forge_folder
    )
    print("--- Step 3 Finished ---\n")

    print("--- Starting Step 4: Creating metadata .txt file ---")
    create_metadata_file(project_path=project_path)
    print("--- Step 4 Finished ---")

    end_time = time.monotonic()
    duration = end_time - start_time
    print("\n=== PIPELINE FINISHED ===")
    print(f"Total execution time: {duration:.2f} seconds.")


def create_metadata_file(project_path: str):
    try:
        conjurer_filename = next(f for f in os.listdir(project_path) if f.lower().endswith('.cardconjurer'))
        conjurer_path = os.path.join(project_path, conjurer_filename)
    except StopIteration:
        print("Error: No .cardconjurer file found. Skipping metadata file creation.")
        return

    try:
        with open(conjurer_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: Could not parse '{conjurer_path}'. It may be malformed.")
        return
    except Exception as e:
        print(f"Error: Could not read the .cardconjurer file. {e}")
        return

    card_data_map = {
        card['key'].replace("’", "'"): card['data']
        for card in json_data
    }

    print_folder = os.path.join(project_path, 'Print')
    if not os.path.isdir(print_folder):
        print(f"Error: 'Print' folder not found. Skipping metadata file creation.")
        return

    image_filenames = [
        f for f in os.listdir(print_folder)
        if os.path.isfile(os.path.join(print_folder, f)) and f.lower().endswith(('.png', '.jpg', '.jpeg'))
    ]

    processed_cards = []
    for filename in image_filenames:
        base_name = os.path.splitext(filename)[0]
        stripped_name = base_name.lstrip('0123456789_ ')
        normalized_name = stripped_name.replace("’", "'")

        if normalized_name in card_data_map:
            rarity = card_data_map[normalized_name].get('infoRarity', 'C')
            processed_cards.append({'name': stripped_name, 'rarity': rarity})
        else:
            print(f"Warning: No data found for '{stripped_name}' in .cardconjurer file. Skipping.")

    if not processed_cards:
        print("No matching cards found to create metadata file.")
        return

    sorted_cards = sorted(processed_cards, key=lambda x: x['name'])

    set_code = os.path.splitext(conjurer_filename)[0]
    project_name = os.path.basename(project_path)
    today_str = date.today().strftime('%Y-%m-%d')
    output_lines = [
        "[metadata]",
        f"Code={set_code}",
        f"Date={today_str}",
        f"Name={project_name}",
        "Type=Other",
        "",
        "[cards]"
    ]

    total_cards = len(sorted_cards)
    pad_width = len(str(total_cards)) + 1

    for i, card in enumerate(sorted_cards, 1):
        number = str(i).zfill(pad_width)
        line = f"{number} {card['rarity']} {card['name']}".replace('’', '\'').replace('%', '//')
        output_lines.append(line)

    output_filename = f"{project_name}.txt"
    output_path = os.path.join(project_path, output_filename)
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        print(f"✅ Success! Metadata file saved to: {output_path}")
    except Exception as e:
        print(f"Error: Could not write the metadata file. {e}")


def crop_and_downsize_for_share(input_folders: list, output_folder: str, downscale_factor: int):
    if not os.path.isdir(input_folders[0]):
        print(f"Error: Main input folder for cropping not found at '{input_folders[0]}'. Skipping step.")
        return

    os.makedirs(output_folder, exist_ok=True)

    CROP_WIDTH_RATIO = 2010 / 2187
    CROP_HEIGHT_RATIO = 2814 / 2975

    EXPECTED_ASPECT_RATIO = 2187 / 2975

    for input_folder in input_folders:
        if not os.path.isdir(input_folder):
            print(f"Warning: Could not find source folder '{input_folder}'. Skipping.")
            continue

        print(f"Scanning for images in: {input_folder}")
        for filename in os.listdir(input_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.tiff')):
                input_path = os.path.join(input_folder, filename)
                output_path = os.path.join(output_folder, filename)
                try:
                    with Image.open(input_path) as img:
                        img_width, img_height = img.size

                        current_aspect_ratio = img_width / img_height
                        if not math.isclose(current_aspect_ratio, EXPECTED_ASPECT_RATIO, rel_tol=1e-3):
                            print(
                                f"Skipping '{filename}': incorrect aspect ratio {current_aspect_ratio:.4f}. Expected ~{EXPECTED_ASPECT_RATIO:.4f}.")
                            continue

                        target_width = int(img_width * CROP_WIDTH_RATIO)
                        target_height = int(img_height * CROP_HEIGHT_RATIO)

                        left = (img_width - target_width) // 2
                        top = (img_height - target_height) // 2
                        right = left + target_width
                        bottom = top + target_height
                        crop_box = (left, top, right, bottom)

                        cropped_img = img.crop(crop_box)

                        new_width = cropped_img.width // downscale_factor
                        new_height = cropped_img.height // downscale_factor
                        resized_img = cropped_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                        resized_img.save(output_path)
                        print(f"Processed '{filename}' ({img_width}x{img_height}) and saved to '{output_folder}'.")
                except Exception as e:
                    print(f"Could not process '{filename}'. Error: {e}")


def run_grid_maker(folder_path: str, output_path: str, rows: int, cols: int, background_color: str, spacer_pixels: int):
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
    if not os.path.isdir(source_folder):
        print(f"Error: Source folder for Forge prep not found at '{source_folder}'. Skipping step.")
        return

    os.makedirs(destination_folder, exist_ok=True)

    print("Copying and renaming files for Forge...")
    for file_name in os.listdir(source_folder):
        if file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
            base_name, extension = os.path.splitext(file_name)
            stripped_name = base_name.lstrip('0123456789_ ')
            replaced_name = stripped_name.replace('’', '\'').replace(' % ', '')
            cleaned_name = remove_accents(replaced_name)
            new_file_name = cleaned_name + '.fullborder.jpg'
            source_path = os.path.join(source_folder, file_name)
            destination_path = os.path.join(destination_folder, new_file_name)

            shutil.copy2(source_path, destination_path)
            print(f"Copied '{file_name}' to '{new_file_name}' in {destination_folder}")

    print("\n--- Starting Step 4: Creating Zip Archive ---")

    project_path = os.path.dirname(destination_folder)
    conjurer_filename = next(f for f in os.listdir(project_path) if f.lower().endswith('.cardconjurer'))
    set_code = os.path.splitext(conjurer_filename)[0]
    zip_file_path = os.path.join(project_path, f"{set_code}.zip")

    print(f"Creating zip archive at: {zip_file_path}")

    try:
        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            for file_name in os.listdir(destination_folder):
                if file_name.endswith('.fullborder.jpg'):
                    file_path = os.path.join(destination_folder, file_name)
                    zipf.write(file_path, arcname=file_name)

        print(f"✅ Success! Zip file created with {len(os.listdir(destination_folder))} files.")
    except Exception as e:
        print(f"Error: Could not create the zip file. {e}")

    print("--- Step 4 Finished ---")


def remove_accents(input_str: str) -> str:
    nfkd_form = unicodedata.normalize('NFD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])


if __name__ == '__main__':
    project = r'C:\Users\kayss\Pictures\Magic\Reserved List'

    GRID_ROWS = 6
    GRID_COLS = 6
    BACKGROUND_COLOR = 'black'
    SPACING_PIXELS = 0
    DOWNSCALE_FACTOR = 5

    run_image_pipeline(
        project_path=project,
        grid_rows=GRID_ROWS,
        grid_cols=GRID_COLS,
        bg_color=BACKGROUND_COLOR,
        spacing=SPACING_PIXELS,
        downscale_factor=DOWNSCALE_FACTOR
    )