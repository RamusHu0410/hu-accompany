import queue
import sys
from pathlib import Path

import cv2
import fitz  # PyMuPDF
import numpy as np
from PIL import Image

# Some of these source PDFs embed a page geometry that already matches a
# high-res scan 1:1 in point-space (the same issue that crashed a fixed-DPI
# render elsewhere in this pipeline with FzErrorLimit: Overly large image) --
# rendering at a flat DPI is meaningless for them, since "DPI" is relative to
# the PDF's own (possibly bogus) page size, not the image's actual detail.
# Normalizing every page to the same long-edge pixel count instead makes
# rendering resolution consistent across PDFs regardless of page geometry,
# and keeps ADAPTIVE_BLOCK_SIZE below meaningful relative to a notehead's
# size no matter which PDF this runs on.
#
# 5000px lands around a 450-500 DPI-equivalent on a typical letter/A4 page
# (11in long edge) -- the low end of the 450-600 DPI range that actually
# resolves fine accidentals/staccato dots, rather than the top of it, since
# every extra pixel here is paid for on every page of every queued PDF and
# this same value already caused a 15+ minute stall through Ghostscript at
# 600 DPI before this pipeline moved off ImageMagick (see enhance_music_pdf's
# docstring). At this resolution cv2.adaptiveThreshold/morphologyEx still run
# in a small fraction of a second per page, so raising it is a one-line
# change if a queued batch's output still looks under-resolved.
TARGET_LONG_EDGE_PX = 5000

# Local adaptive threshold: binarize each pixel against its own neighborhood's
# mean brightness (minus a bias), rather than one global cutoff -- this is
# what actually preserves tiny loops in sharps/flats under uneven scan
# lighting instead of blowing them out or merging them with background noise.
# Scaled proportionally to TARGET_LONG_EDGE_PX (tuned by eye at the original
# 2200px long edge) so the neighborhood stays the same size relative to a
# notehead if that resolution ever changes again.
ADAPTIVE_BLOCK_SIZE = round(25 * TARGET_LONG_EDGE_PX / 2200) | 1  # must stay odd
ADAPTIVE_BIAS = round(0.10 * 255)  # ~10% of the full brightness range

# Small round-ish structuring element for the morphological smoothing pass
# below (open then close) -- clears jagged edges/stray noise around
# accidentals without eating the small loops adaptive thresholding preserved.
# Deliberately left as a fixed pixel size rather than scaled with
# TARGET_LONG_EDGE_PX: staccato dots and accidental strokes get proportionally
# more pixels at a higher render resolution, so keeping this kernel small in
# absolute terms only gets safer (less likely for MORPH_OPEN to erase a dot
# outright) as resolution goes up -- scaling it up with resolution would
# undo that.
_MORPH_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


def enhance_music_pdf(input_pdf_path, output_pdf_path):
    """
    Cleans up scan noise in a music PDF: local adaptive thresholding to binarize
    ink from background, then a morphological open+close pass to smooth jagged
    edges, writing the result back out as a new PDF of the same page count.

    Originally shelled out to ImageMagick (rasterizing via Ghostscript at 600
    DPI) plus a per-page ImageMagick subprocess for thresholding/morphology.
    That was never actually viable: 600 DPI through Ghostscript took 15+
    minutes on a 16-page PDF and never finished a test run, and once DPI was
    dropped to 300 the per-page step turned out to reference an ImageMagick
    morphology method ("intermediate") and kernel ("hexagon") that don't
    exist on this ImageMagick version at all, so it never actually completed
    once either. Doing the same operations in-process with PyMuPDF (already
    used for rasterizing elsewhere in this codebase, far faster than
    Ghostscript) and OpenCV (already a dependency) instead of spawning a
    subprocess per page removes both problems and the ImageMagick/Ghostscript
    dependency entirely -- a page that took ~25-30s via ImageMagick's -lat
    takes a small fraction of a second via cv2.adaptiveThreshold.
    """
    input_path = Path(input_pdf_path)
    output_path = Path(output_pdf_path)

    if not input_path.exists():
        print(f"ERROR: Input file '{input_pdf_path}' does not exist.")
        return

    print(f"Step 1: Rendering PDF pages to images ({TARGET_LONG_EDGE_PX}px long edge)...")
    doc = fitz.open(str(input_path))

    print("Step 2: Cleaning pages with local adaptive thresholding & morphology...")
    cleaned_pages = []
    for i, page in enumerate(doc):
        zoom = TARGET_LONG_EDGE_PX / max(page.rect.width, page.rect.height)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY, alpha=False)
        gray = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)

        binarized = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY,
            ADAPTIVE_BLOCK_SIZE, ADAPTIVE_BIAS,
        )
        opened = cv2.morphologyEx(binarized, cv2.MORPH_OPEN, _MORPH_KERNEL)
        smoothed = cv2.morphologyEx(opened, cv2.MORPH_CLOSE, _MORPH_KERNEL)

        cleaned_pages.append(Image.fromarray(smoothed))
        print(f"Processed page {i + 1}/{doc.page_count}")

    doc.close()

    if not cleaned_pages:
        print("ERROR: Failed to extract pages from PDF.")
        return

    print("Step 3: Compiling enhanced images back into a unified PDF...")
    cleaned_pages[0].save(str(output_path), save_all=True, append_images=cleaned_pages[1:])
    print(f"SUCCESS: Enhanced music sheet generated successfully at: {output_path}")


class IMSLPEnhancementQueue:
    """
    FIFO queue of PDF paths freshly downloaded from IMSLP, awaiting
    enhancement. Holds queued paths only for the life of this object (no
    disk staging of its own -- IMSLP downloads already land in permanent
    storage, see imslp_downloader.storage) so a batch of downloads can be
    enqueued as they arrive and enhanced one at a time in order, without the
    caller having to track per-file output paths itself.
    """

    def __init__(self, collected_dir):
        self.collected_dir = Path(collected_dir)
        self.collected_dir.mkdir(parents=True, exist_ok=True)
        self._pending = queue.Queue()

    def enqueue(self, pdf_path):
        """Adds a downloaded PDF's path to the back of the queue."""
        self._pending.put(Path(pdf_path))

    def process_all(self):
        """
        Runs every currently queued PDF through enhance_music_pdf in FIFO
        order, writing each result into collected_dir, and returns the list
        of collected output paths.
        """
        collected = []
        while not self._pending.empty():
            pdf_path = self._pending.get()
            output_path = self.collected_dir / f"{pdf_path.stem}_enhanced.pdf"
            enhance_music_pdf(str(pdf_path), str(output_path))
            collected.append(output_path)
            self._pending.task_done()
        return collected


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--batch":
        # Batch mode: enhance a whole run of freshly downloaded IMSLP PDFs
        # through the queue, collecting every result into one directory.
        if len(sys.argv) < 4:
            print("Usage: python enhancer_script.py --batch <collected_dir> <pdf1> [pdf2 ...]")
            sys.exit(1)

        collected_dir, *pdf_paths = sys.argv[2:]

        print("--- OMR Sheet Music Visual Enhancer Queue ---")
        print(f"Queuing {len(pdf_paths)} PDF(s), collecting into: {collected_dir}\n")

        enhancement_queue = IMSLPEnhancementQueue(collected_dir)
        for pdf_path in pdf_paths:
            enhancement_queue.enqueue(pdf_path)
        collected = enhancement_queue.process_all()

        print(f"SUCCESS: Enhanced {len(collected)} PDF(s) into {collected_dir}")
    else:
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
