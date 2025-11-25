import os
import base64
import traceback
from io import BytesIO

import gradio as gr
import fitz  # PyMuPDF
from PyPDF2 import PdfWriter, PdfReader
import requests



# --------------------------------------------------------
# OCR FALLBACK (OCR.Space)
# --------------------------------------------------------
OCR_API_KEY = "K88121712188957"

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



# --------------------------------------------------------
# MAIN LOGIC (GIR + MULTIPLE ITEMS)
# --------------------------------------------------------
def process_pdfs(files, gir_number, item_list):
    try:
        gir = (gir_number or "").strip()
        item_numbers = [i.strip() for i in item_list if i and i.strip()]
        item_numbers_lower = [i.lower() for i in item_numbers]

        if not files:
            return "No files uploaded.", None, ""

        if not gir:
            return "Please enter GIR Number.", None, ""

        if not item_numbers:
            return "Please enter at least one Item Number.", None, ""

        if isinstance(files, str):
            files = [files]

        matched_pages = []

        # --------------------------------------------------------
        # PROCESS FILES
        # --------------------------------------------------------
        for path in files:
            file_path = path
            file_name = os.path.basename(path)

            # Ignore BOE files
            if "BOE" in file_name.upper():
                continue

            # Filter by GIR inside filename
            if gir not in file_name:
                continue

            with open(file_path, "rb") as f:
                pdf_bytes = f.read()

            pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            # --------------------------------------------------------
            # PROCESS PAGES
            # --------------------------------------------------------
            for page_num in range(len(pdf_doc)):
                page = pdf_doc[page_num]

                text = page.get_text().lower().strip()

                if len(text) < 10:
                    pix = page.get_pixmap(dpi=300)
                    img_bytes = pix.tobytes("png")
                    text = ocr_fallback(img_bytes)

                matched_this_page = False
                matched_rects = []

                for item in item_numbers_lower:
                    if item in text:
                        rects = page.search_for(item)
                        if rects:
                            matched_this_page = True
                            matched_rects.extend(rects)

                if not matched_this_page:
                    continue

                # Highlight matched items
                highlight_page = pdf_doc.load_page(page_num)
                for rect in matched_rects:
                    highlight_page.add_highlight_annot(rect)

                # Export page
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
            return "❌ No pages contained the entered Item Numbers.", None, ""

        # --------------------------------------------------------
        # MERGE ALL MATCHES
        # --------------------------------------------------------
        final_writer = PdfWriter()
        for item in matched_pages:
            reader = PdfReader(BytesIO(item["bytes"]))
            final_writer.add_page(reader.pages[0])

        final_pdf_bytes = BytesIO()
        final_writer.write(final_pdf_bytes)

        out_name = f"CustomsPrint-{gir}.pdf"
        os.makedirs("/tmp/customs_out", exist_ok=True)
        out_path = os.path.join("/tmp/customs_out", out_name)
        with open(out_path, "wb") as f:
            f.write(final_pdf_bytes.getvalue())

        # --------------------------------------------------------
        # PRINT PREVIEW HTML
        # --------------------------------------------------------
        b64_pdf = base64.b64encode(final_pdf_bytes.getvalue()).decode("utf-8")
        html_preview = f"""
        <div style="margin-top: 10px;">
            <iframe id="pdfFrame"
                src="data:application/pdf;base64,{b64_pdf}"
                style="width:0;height:0;border:none;display:none;"></iframe>

            <button onclick="printPDF()"
                style="padding:10px 18px;background-color:#4CAF50;color:white;border:none;border-radius:6px;cursor:pointer;font-size:15px;">
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


# --------------------------------------------------------
# ADD ITEM NUMBER FIELD (DYNAMIC)
# --------------------------------------------------------
def add_item_field(existing_items):
    existing_items.append("")  # add empty input
    return gr.update(visible=True), existing_items


# --------------------------------------------------------
# GRADIO UI
# --------------------------------------------------------
with gr.Blocks(title="Customs Invoice Extractor (Dynamic Item Numbers)") as demo:

    gr.Markdown("# 📄 Customs Invoice Extractor (Dynamic Item Numbers)")

    gir_input = gr.Textbox(label="GIR Number", placeholder="e.g., 5399")

    gr.Markdown("### Enter Item Numbers")

    item_list_state = gr.State([])

    # Container for dynamic item fields
    item_fields = gr.Column()

    with item_fields:
        first_item = gr.Textbox(label="Item Number 1", placeholder="e.g. 12345678")
    item_list_state.value = [""]

    add_button = gr.Button("➕ Add another Item Number")

    def update_items(*inputs):
        # inputs = list of textbox values
        return list(inputs)

    add_button.click(
        add_item_field,
        inputs=[item_list_state],
        outputs=[item_fields, item_list_state]
    )

    files_in = gr.File(
        label="Upload PDFs",
        file_count="multiple",
        type="filepath",
        file_types=[".pdf"],
    )

    submit = gr.Button("Process")

    status_box = gr.Textbox(label="Status", lines=6)
    result_file = gr.File(label="Download Extracted PDF")
    preview_html = gr.HTML(label="Print Preview")

    submit.click(
        process_pdfs,
        inputs=[files_in, gir_input, item_list_state],
        outputs=[status_box, result_file, preview_html],
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port)





























