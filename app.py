import os
import math
import base64
from io import BytesIO
import traceback

import gradio as gr
import fitz  # PyMuPDF
from PyPDF2 import PdfWriter, PdfReader
import requests


# -----------------------------
# OCR SPACE API KEY (fallback)
# -----------------------------
OCR_API_KEY = "K88121712188957"   # <-- replace if needed


# -----------------------------
# OCR FALLBACK
# -----------------------------
def ocr_fallback(image_bytes: bytes) -> str:
    try:
        files = {"file": ("page.png", image_bytes)}
        data = {
            "apikey": OCR_API_KEY,
            "language": "eng",
            "OCREngine": 1,
            "scale": True,
            "detectOrientation": True,
        }

        resp = requests.post(
            "https://api.ocr.space/parse/image",
            files=files,
            data=data,
            timeout=60,
        ).json()

        if resp.get("IsErroredOnProcessing"):
            return ""

        return resp["ParsedResults"][0]["ParsedText"].lower()
    except Exception:
        return ""


# -----------------------------
# RECTANGLE DISTANCE
# -----------------------------
def rect_distance(r1, r2) -> float:
    # Horizontal gap
    if r1.x1 < r2.x0:
        dx = r2.x0 - r1.x1
    elif r2.x1 < r1.x0:
        dx = r1.x0 - r2.x1
    else:
        dx = 0

    # Vertical gap
    if r1.y1 < r2.y0:
        dy = r2.y0 - r1.y1
    elif r2.y1 < r1.y0:
        dy = r1.y0 - r2.y1
    else:
        dy = 0

    return math.sqrt(dx * dx + dy * dy)


# -----------------------------
# MAIN LOGIC
# -----------------------------
def process_pdfs(files, gir_number, hs_code, country_origin, item_number):
    try:
        # Normalize inputs
        gir_number = (gir_number or "").strip()
        hs_code = (hs_code or "").strip()
        country_origin = (country_origin or "").strip()
        item_number = (item_number or "").strip()

        if not files:
            return "No files uploaded.", None, ""

        if not gir_number or not hs_code or not country_origin or not item_number:
            return "Please fill GIR, HS Code, Country of Origin, and Item Number.", None, ""

        # Gradio File(type="filepath") → files is str or list[str]
        if isinstance(files, str):
            files = [files]

        hs_lower = hs_code.lower()
        co_lower = country_origin.lower()
        item_lower = item_number.lower()

        ONE_CM = 28.3465          # 1 cm in PDF points
        SIX_CM = ONE_CM * 6       # 6 cm in PDF points

        matched_pages = []

        for path in files:
            file_path = path
            file_name = os.path.basename(path)

            # Ignore BOE PDFs
            if "BOE" in file_name.upper():
                continue

            # Only process PDFs whose filename contains the GIR
            if gir_number not in file_name:
                continue

            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]

                # Direct text extraction
                text = page.get_text().lower().strip()

                # OCR fallback if almost empty
                if len(text) < 10:
                    pix = page.get_pixmap(dpi=300)
                    img_bytes = pix.tobytes("png")
                    text = ocr_fallback(img_bytes)

                # Require HS + CO + Item in text
                if hs_lower in text and co_lower in text and item_lower in text:
                    hs_rects = page.search_for(hs_code)
                    co_rects = page.search_for(country_origin)
                    item_rects = page.search_for(item_number)

                    if not hs_rects or not co_rects or not item_rects:
                        continue

                    # Item must be within 6 cm of HS Code
                    close_enough = False
                    for hs_rect in hs_rects:
                        for item_rect in item_rects:
                            if rect_distance(hs_rect, item_rect) <= SIX_CM:
                                close_enough = True
                                break
                        if close_enough:
                            break

                    if not close_enough:
                        continue

                    # Highlight HS, CO, and Item
                    highlight_page = pdf_doc.load_page(page_num)
                    for r in hs_rects:
                        highlight_page.add_highlight_annot(r)
                    for r in co_rects:
                        highlight_page.add_highlight_annot(r)
                    for r in item_rects:
                        highlight_page.add_highlight_annot(r)

                    # Export just this page
                    temp_pdf = BytesIO(pdf_doc.write())
                    temp_reader = PdfReader(temp_pdf)

                    single_writer = PdfWriter()
                    single_page_buf = BytesIO()
                    single_writer.add_page(temp_reader.pages[page_num])
                    single_writer.write(single_page_buf)

                    matched_pages.append({
                        "pdf_name": file_name,
                        "page_num": page_num + 1,
                        "bytes": single_page_buf.getvalue(),
                    })

        if not matched_pages:
            return (
                "❌ No pages met ALL conditions:\n"
                "• HS Code present\n"
                "• Country of Origin present\n"
                "• Item Number present\n"
                "• Item Number within 6 cm of HS Code",
                None,
                "",
            )

        # Merge all matching pages
        final_writer = PdfWriter()
        for item in matched_pages:
            reader = PdfReader(BytesIO(item["bytes"]))
            final_writer.add_page(reader.pages[0])

        final_pdf_bytes = BytesIO()
        final_writer.write(final_pdf_bytes)

        out_name = f"CustomsPrint-{hs_code}-{country_origin}-{item_number}-{gir_number}.pdf"

        # Save to /tmp so Gradio can serve it
        os.makedirs("/tmp/customs_out", exist_ok=True)
        out_path = os.path.join("/tmp/customs_out", out_name)
        with open(out_path, "wb") as f:
            f.write(final_pdf_bytes.getvalue())

        # Build print-preview HTML using base64-embedded PDF
        b64_pdf = base64.b64encode(final_pdf_bytes.getvalue()).decode("utf-8")
        html_preview = f"""
        <div style="margin-top: 10px;">
            <iframe id="pdfFrame"
                src="data:application/pdf;base64,{b64_pdf}"
                style="width:0;height:0;border:none;display:none;"></iframe>
            <button onclick="printPDF()"
                style="
                    padding:10px 18px;
                    background-color:#4CAF50;
                    color:white;
                    border:none;
                    border-radius:6px;
                    cursor:pointer;
                    font-size:15px;">
                🖨️ Print Preview
            </button>
            <script>
                function printPDF() {{
                    var frame = document.getElementById('pdfFrame');
                    frame.style.display = 'block';
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                }}
            </script>
        </div>
        """

        status_msg = f"✅ Found {len(matched_pages)} matching page(s)."

        return status_msg, out_path, html_preview

    except Exception:
        err = traceback.format_exc()
        return f"⚠ ERROR OCCURRED:\n\n{err}", None, ""


# -----------------------------
# GRADIO UI
# -----------------------------
with gr.Blocks(title="Customs Invoice Extractor (HS + CO + Item + 6cm Rule)") as demo:
    gr.Markdown(
        """
    # 📄 Customs Invoice Extractor  
    **Logic:**  
    1. Filter PDFs by **GIR number in the filename**  
    2. Ignore any PDF whose name contains **"BOE"**  
    3. On each page, require **HS Code**, **Country of Origin**, and **Item Number**  
    4. Require **Item Number** to be within **6 cm** of the **HS Code**  
    5. Highlight HS, Country, and Item on matched pages  
    6. Merge all matching pages into one PDF for download/printing  
    """
    )

    with gr.Row():
        gir_number = gr.Textbox(label="GIR Number", placeholder="e.g., 5399")
        hs_code = gr.Textbox(label="HS Code", placeholder="e.g., 853690100000")

    with gr.Row():
        country_origin = gr.Textbox(label="Country of Origin", placeholder="e.g., GERMANY")
        item_number = gr.Textbox(label="Item Number", placeholder="e.g., 12345678")

    files = gr.File(
        label="Upload Invoice PDFs",
        file_count="multiple",
        type="filepath",      # Render: returns list[str] of paths
        file_types=[".pdf"],
    )

    submit = gr.Button("Process")

    status_box = gr.Textbox(label="Status", lines=6)
    result_file = gr.File(label="Download Extracted Pages")
    preview_html = gr.HTML(label="Print Preview")

    submit.click(
        process_pdfs,
        inputs=[files, gir_number, hs_code, country_origin, item_number],
        outputs=[status_box, result_file, preview_html],
    )


if __name__ == "__main__":
    # Render sets PORT env var; Gradio listens on that
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)























