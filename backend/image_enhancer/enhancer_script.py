import os
import concurrent.futures
from typing import Any, cast
from pyvips import Image, Interpretation

MAX_PAGES_BASE = 100
MAX_PAGES_PREMIUM = 500
MAX_WORKERS = 4

# Private Function to this file
def enhance_page(input_pdf_path: str, page_num: int) -> Image:
    """Process a single page of the pdf by executing different operations to intensify wanted pixels and minimize unwanted ones"""
    img: Image = cast(Image, Image.new_from_file(input_pdf_path, dpi=400, page=page_num, access="sequential"))
    gray: Image = img.colourspace("b-w")  # type: ignore

    blur = gray.gaussblur(2) # type: ignore
    binary_clear = (gray < (blur - 15)).cast("uchar") * 255 # type: ignore

    mask_matrix = [[1, 1, 1], [1, 1, 1], [1, 1, 1]]
    return binary.morph(mask_matrix, "morph_min") # type: ignore

# Private Function to this file
def enhance_music_pdf(input_pdf_path: str, output_pdf_path: str):
    """Process an entire music pdf"""
    try:
        pdf = Image.pdf_load(input_pdf_path, page=0, n=1)
        n_pages: int = pdf.get("n-pages") # type: ignore
        if n_pages >= MAX_PAGES_BASE:
            return ValueError("Exceeded page limit")
        processed_pages = []
        for p in range(n_pages):
            page = enhance_page(input_pdf_path=input_pdf_path, page_num=p)
            processed_pages.append(page)
    except Exception as e:
        print(f"Error Occured during pdf processing: {e}")
    
    final_pdf = Image.arrayjoin(processed_pages, across=1) # type: ignore
    final_pdf.write_to_file(output_pdf_path, page_height=processed_pages[0].height) # type: ignore
    return 0
    
# Public function called by external code
# !! ONLY CALL THIS FUNCTION 
def process_list(pdf_list: list, output_dir: str):
    os.makedirs(output_dir, exist_ok=True) 
    with concurrent.futures.ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for pdf in pdf_list:
            out_name = os.path.basename(pdf)
            out_path = os.path.join(output_dir, out_name)
            
            # Dispatch the entire file execution path to a worker process
            f = executor.submit(enhance_music_pdf, pdf, out_path)
            futures[f] = pdf
            
        for future in concurrent.futures.as_completed(futures):
            pdf_orig = futures[future]
            print(f"Successfully optimized and written: {pdf_orig}")

    
    
