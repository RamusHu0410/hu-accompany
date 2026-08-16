import os
import subprocess
import glob
import sys
from pathlib import Path

def check_imagemagick():
    """Checks if ImageMagick is installed and accessible in the system PATH."""
    try:
        # Check for modern ImageMagick v7+ syntax
        subprocess.run(["magick", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return "magick"
    except (subprocess.CalledProcessError, FileNotFoundError):
        try:
            # Check for older ImageMagick v6 syntax
            subprocess.run(["convert", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return "convert"
        except (subprocess.CalledProcessError, FileNotFoundError):
            print("ERROR: ImageMagick is not installed or not found in your system PATH.")
            print("Please download and install it from https://imagemagick.org")
            sys.exit(1)

def enhance_music_pdf(input_pdf_path, output_pdf_path):
    cmd_base = check_imagemagick()
    
    input_path = Path(input_pdf_path)
    output_path = Path(output_pdf_path)
    
    if not input_path.exists():
        print(f"ERROR: Input file '{input_pdf_path}' does not exist.")
        return

    # Create a temporary workplace directory
    temp_dir = Path("omr_cleanup_temp")
    temp_dir.mkdir(exist_ok=True)
    
    print("Step 1: Extracting PDF pages to high-resolution images (400 DPI)...")
    # %03d handles page numbering sequentially (page-000.png, page-001.png, etc.)
    extract_pattern = temp_dir / "page-%03d.png"
    
    if cmd_base == "magick":
        extract_cmd = ["magick", "-density", "600", str(input_path), str(extract_pattern)]
    else:
        extract_cmd = ["convert", "-density", "600", str(input_path), str(extract_pattern)]
        
    subprocess.run(extract_cmd, check=True)
    
    # Get all extracted pages
    extracted_pages = sorted(glob.glob(str(temp_dir / "page-*.png")))
    if not extracted_pages:
        print("ERROR: Failed to extract pages from PDF.")
        return
        
    print(f"Found {len(extracted_pages)} pages to process.")
    cleaned_pages = []
    
    print("Step 2: Processing pages with Local Adaptive Thresholding & Morphology filters...")
    for page in extracted_pages:
        page_path = Path(page)
        clean_page_path = temp_dir / f"clean-{page_path.name}"
        
        # Adaptive thresholding preserves tiny loops in sharps/flats. 
        # Morphology eliminates jagged edges and clears visual noise around accidentals.
        if cmd_base == "magick":
            process_cmd = [
                "magick", str(page_path),
                "-colorspace", "gray",
                "-negate",
                "-lat", "25x25+10%",
                "-negate",
                "-morphology", "intermediate", "hexagon:1",
                str(clean_page_path)
            ]
        else:
            process_cmd = [
                "convert", str(page_path),
                "-colorspace", "gray",
                "-negate",
                "-lat", "25x25+10%",
                "-negate",
                "-morphology", "intermediate", "hexagon:1",
                str(clean_page_path)
            ]
            
        subprocess.run(process_cmd, check=True)
        cleaned_pages.append(str(clean_page_path))
        print(f"Processed: {page_path.name}")

    print("Step 3: Compiling enhanced images back into a unified PDF...")
    # Grab all clean files using glob sorted naturally
    clean_pattern = sorted(glob.glob(str(temp_dir / "clean-page-*.png")))
    
    if cmd_base == "magick":
        compile_cmd = ["magick"] + clean_pattern + [str(output_path)]
    else:
        compile_cmd = ["convert"] + clean_pattern + [str(output_path)]
        
    subprocess.run(compile_cmd, check=True)
    print(f"SUCCESS: Enhanced music sheet generated successfully at: {output_path}")
    
    # Cleanup temporary images
    print("Cleaning up intermediate workspace files...")
    for f in glob.glob(str(temp_dir / "*")):
        os.remove(f)
    os.rmdir(temp_dir)

if __name__ == "__main__":
    # Example usage configuration
    # Change these filenames to match your local file names
    INPUT_FILE = "input_sheet_music.pdf"
    OUTPUT_FILE = "enhanced_sheet_music.pdf"
    
    print("--- OMR Sheet Music Visual Enhancer Script ---")
    print(f"Targeting input file: {INPUT_FILE}")
    print(f"Targeting output file: {OUTPUT_FILE}\n")
    
    # Check if user passed arguments via terminal command
    if len(sys.argv) > 2:
        INPUT_FILE = sys.argv[1]
        OUTPUT_FILE = sys.argv[2]
    elif len(sys.argv) == 2:
        INPUT_FILE = sys.argv[1]
        OUTPUT_FILE = "enhanced_" + INPUT_FILE
        
    enhance_music_pdf(INPUT_FILE, OUTPUT_FILE)
