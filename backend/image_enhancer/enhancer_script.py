import concurrent.futures
import os
import multiprocessing
from pyvips import Image
from typing import cast
import traceback

# CONSTANTS
MAX_WORKERS: int = 8
MAX_PAGES_BASE: int = 50


# Private Function to this file
def enhance_page(input_pdf_path: str, page_num: int, output_pdf_path: str) -> bool:
    """Process a single page of the pdf by executing different operations to intensify wanted pixels and minimize unwanted ones"""
    try:
        piece_name = os.path.splitext(os.path.basename(input_pdf_path))[0]

        img: Image = cast(
            Image,
            Image.pdfload(input_pdf_path, dpi=400, page=page_num, access="sequential"),
        )
        gray: Image = img.colourspace("b-w").cast("uchar")  # type: ignore

        blur: Image = gray.gaussblur(10)  # type: ignore
        binary_clear = (gray < (blur - 7.5)).cast("uchar") * 255  # type: ignore

        # FIX 1: Wrap the Python list inside an explicit pyvips Image array
        mask_structure = [[255, 255, 255], [255, 255, 255], [255, 255, 255]]
        mask_matrix = Image.new_from_array(mask_structure)

        dilated = binary_clear.morph(mask_matrix, "dilate")
        dilated2 = dilated.morph(mask_matrix, "dilate")
        eroded = dilated2.morph(mask_matrix, "erode")
        eroded2 = eroded.morph(mask_matrix, "erode")

        finished_pg = eroded2.invert()

        page_output_path = os.path.join(output_pdf_path, f"{piece_name}-{page_num}.png")
        finished_pg.write_to_file(page_output_path)
        return True
    except Exception as e:
        print(f"❌ Error processing page {page_num}: {e}")
        return False


# Private Function to this file
def enhance_music_pdf(input_pdf_path: str, output_pdf_path: str):
    """Process an entire music pdf"""
    try:
        meta = Image.pdfload(input_pdf_path, page=0, n=1)
        n_pages: int = meta.get("n-pages")  # type: ignore

        if n_pages >= MAX_PAGES_BASE:
            raise ValueError(
                "Exceeded page limit"
            )  # Use 'raise' instead of 'return' to halt processing

        output_dir = os.path.dirname(output_pdf_path)

        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as exec:
            futures = []
            for p in range(n_pages):
                f = exec.submit(
                    enhance_page,
                    input_pdf_path=input_pdf_path,
                    page_num=p,
                    output_pdf_path=output_dir,
                )
                futures.append(f)
            concurrent.futures.wait(futures)
        print("All pages are processed!")
        return True

    except Exception as e:
        print(f"❌ Error Occured during pdf processing of {input_pdf_path}:")
        traceback.print_exc()  # Correct usage to output the actual full traceback trace
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
    multiprocessing.freeze_support()  # For future self: NEED THIS STATEMENT FOR CONCURRENT OPERATIONS EVERYTIME
    enhance_music_pdf("/Users/kingsleyleon/Downloads/ysaye.pdf", "test/")
