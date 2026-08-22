import os
import concurrent.futures
from typing import Any, cast
import pyvips
from pyvips import Image
import multiprocessing
import traceback
import img2pdf


# Private Function to this file
def enhance_page(input_pdf_path: str, page_num: int) -> Image:
    """Process a single page of the pdf by executing different operations to intensify wanted pixels and minimize unwanted ones"""
    img: Image = cast(Image, Image.pdfload(input_pdf_path, dpi=400, page=page_num, access="sequential"))
    gray: Image = img.colourspace("b-w")  # type: ignore
    
    blur = gray.gaussblur(2) # type: ignore
    binary_clear = (gray < (blur - 15)).cast("uchar") * 255 # type: ignore

    # FIX 1: Wrap the Python list inside an explicit pyvips Image array
    mask_structure = [[255, 255, 255], [255, 255, 255], [255, 255, 255]]
    mask_matrix = Image.new_from_array(mask_structure)
    
    return binary_clear.morph(mask_matrix, "erode") # type: ignore

# Private Function to this file
def enhance_music_pdf(input_pdf_path: str, output_pdf_path: str):
    """Process an entire music pdf"""
    try:
        pdf = Image.pdfload(input_pdf_path, page=0, n=1)
        n_pages: int = pdf.get("n-pages") # type: ignore
        base_name = os.path.splitext(os.path.basename(input_pdf_path))[0]
        # Get the directory where you want to save the output
        output_dir = os.path.dirname(output_pdf_path)
        
        if n_pages >= MAX_PAGES_BASE:
            raise ValueError("Exceeded page limit") # Use 'raise' instead of 'return' to halt processing
            
        for p in range(n_pages):
            page = enhance_page(input_pdf_path=input_pdf_path, page_num=p)
            page_output_path = os.path.join(output_dir, f"{base_name}_page_{p+1}.png")
            page.write_to_file(page_output_path, page_height=pdf[0].height) 
        return True
        
    except Exception as e:
        print(f"❌ Error Occured during pdf processing of {input_pdf_path}:")
        traceback.print_exc() # Correct usage to output the actual full traceback trace
        return False
    
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
            # Check the actual True/False result returned by enhance_music_pdf
            if future.result(): 
                print(f"Successfully optimized and written: {pdf_orig}")
            else:
                print(f"⚠️ Worker completed with errors for: {pdf_orig}")

# This Statement will be removed if code successfully runs 
if __name__ == "__main__":
    multiprocessing.freeze_support() # For future self: NEED THIS STATEMENT FOR CONCURRENT OPERATIONS EVERYTIME
    process_list(["/Users/kingsleyleon/Downloads/ysaye.pdf"], "test/")
