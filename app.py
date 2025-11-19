import streamlit as st
import fitz  # PyMuPDF
from PyPDF2 import PdfWriter, PdfReader
from io import BytesIO
import base64
import streamlit.components.v1 as components
import requests
import math


# ----------------------------------------------
# 🔑 OCR SPACE API KEY (FALLBACK)
# ----------------------------------------------
OCR_API_KEY = "K88121712188957"   # <-- REPLACE THIS IF NEEDED


# ----------------------------------------------
# STREAMLIT CONFIG
# ----------------------------------------------
st.set_page_config(page_title="Invoice Extractor", layout="wide")
st.title("📄 Invoice Page Extractor (HS + CO + Item + 6cm Rule)")
st.write(
    "• Filters PDFs by GIR number in the **filename**\n"
    "• Ignores PDFs whose name contains 'BOE'\n"
    "• On each page, requires **HS Code**, **Country of Origin**, and **Item Number**\n"
    "• Item Number must be within **6 cm** of the HS Code on that page\n"
    "• Highlights HS Code, Country, and Item Number\n"
    "• Merges all matching pages into one PDF\n"
    "• Download + Print Preview"
)


# ----------------------------------------------
# USER INPUTS
# ----------------------------------------------
gir_number = st.text_input("Enter GIR Number (required)")

hs_code = st.text_input("Enter HS Code (required)")
item_number = st.text_input("Enter Item Number (required)")
country_origin = st.text_input("Enter Country of Origin (required)")

uploaded_files = st.file_uploader(
    "Upload Invoice PDFs",
    type="pdf",
    accept_multiple_files=True
)


# ----------------------------------------------
# OCR FALLBACK FUNCTION
# ----------------------------------------------
def ocr_fallback(image_bytes):
    files = {"file": ("page.png", image_bytes)}
    data = {
        "apikey": OCR_API_KEY,
        "language": "eng",
        "OCREngine": 1,
        "scale": True,
        "detectOrientation": True
    }

    try:
        resp = requests.post(
            "https://api.ocr.space/parse/image",
            files=files,
            data=data
        ).json()

        if resp.get("IsErroredOnProcessing"):
            return ""

        return resp["ParsedResults"][0]["ParsedText"].lower()

    except:
        return ""


# ----------------------------------------------
# RECTANGLE DISTANCE (PyMuPDF rects)
# ----------------------------------------------
def rect_distance(r1, r2):
    """Returns minimum distance between two rectangles in PDF points."""
    # Horizontal gap
    if r1.x1 < r2.x0:
        dx = r2.x0 - r1.x1
    elif r2.x1 < r1.x0:
        dx = r1.x0 - r2.x1
    else:
        dx = 0  # overlapping horizontally

    # Vertical gap
    if r1.y1 < r2.y0:
        dy = r2.y0 - r1.y1
    elif r2.y1 < r1.y0:
        dy = r1.y0 - r2.y1
    else:
        dy = 0  # overlapping vertically

    return math.sqrt(dx * dx + dy * dy)


# ----------------------------------------------
# MAIN PROCESSING
# ----------------------------------------------
if uploaded_files and gir_number and hs_code and item_number and country_origin:

    st.info(
        "Processing… Using direct text extraction, OCR fallback, and a 6 cm "
        "proximity rule between HS Code and Item Number."
    )

    matched_pages = []

    hs_lower = hs_code.lower()
    item_lower = item_number.lower()
    country_lower = country_origin.lower()

    ONE_CM = 28.3465            # 1 cm in PDF points
    SIX_CM = ONE_CM * 6         # 6 cm in PDF points

    for uploaded in uploaded_files:
        file_name = uploaded.name

        # Ignore BOE files
        if "BOE" in file_name.upper():
            continue

        # Only process PDFs containing GIR number in the filename
        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Process each page
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            # 1) Direct text extraction first (fast)
            text = page.get_text().lower().strip()

            # If empty → OCR fallback
            if len(text) < 10:
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                text = ocr_fallback(img_bytes)

            # Must contain HS + Country + Item somewhere in text
            if hs_lower in text and country_lower in text and item_lower in text:

                # Obtain rectangles for HS, Country, and Item
                hs_rects = page.search_for(hs_code)
                country_rects = page.search_for(country_origin)
                item_rects = page.search_for(item_number)

                if not hs_rects or not country_rects or not item_rects:
                    continue

                # Check spatial proximity between HS Code and Item Number
                close_enough = False

                for hs_rect in hs_rects:
                    for item_rect in item_rects:
                        if rect_distance(hs_rect, item_rect) <= SIX_CM:
                            close_enough = True
                            break
                    if close_enough:
                        break

                if not close_enough:
                    # HS and Item exist but too far apart → not the same line/entry
                    continue

                # PAGE MATCHES — highlight HS, Country, and Item
                highlight_page = pdf_doc.load_page(page_num)

                for rect in hs_rects:
                    highlight_page.add_highlight_annot(rect)

                for rect in country_rects:
                    highlight_page.add_highlight_annot(rect)

                for rect in item_rects:
                    highlight_page.add_highlight_annot(rect)

                # Save modified single page
                temp_pdf = BytesIO(pdf_doc.write())
                temp_reader = PdfReader(temp_pdf)

                single_writer = PdfWriter()
                single_page_pdf = BytesIO()
                single_writer.add_page(temp_reader.pages[page_num])
                single_writer.write(single_page_pdf)

                # Low-res image preview
                preview_img = page.get_pixmap(dpi=150).tobytes("png")

                matched_pages.append({
                    "pdf_name": file_name,
                    "page_num": page_num + 1,
                    "pdf_bytes": single_page_pdf.getvalue(),
                    "image": preview_img
                })


    # ----------------------------------------------
    # RESULTS
    # ----------------------------------------------
    st.header("Matched Pages (HS + Country + Item + ≤ 6 cm HS–Item)")

    if not matched_pages:
        st.error(
            "❌ No pages met ALL conditions:\n"
            "• HS Code present\n"
            "• Country of Origin present\n"
            "• Item Number present\n"
            "• Item Number within 6 cm of HS Code"
        )
    else:
        final_writer = PdfWriter()

        for item in matched_pages:
            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            final_writer.add_page(reader.pages[0])

        final_pdf = BytesIO()
        final_writer.write(final_pdf)

        # Show previews
        for item in matched_pages:
            st.write(f"📄 {item['pdf_name']} — Page {item['page_num']}")
            st.image(item["image"], width=450)

        st.markdown("---")

        # Output file name
        file_out = f"CustomsPrint-{hs_code}-{country_origin}-{item_number}-{gir_number}.pdf"

        # Download button
        st.download_button(
            label=f"📥 Download {file_out}",
            data=final_pdf.getvalue(),
            file_name=file_out,
            mime="application/pdf"
        )

        # Print Preview (opens browser print dialog on the merged PDF)
        base64_pdf = base64.b64encode(final_pdf.getvalue()).decode("utf-8")

        html_code = f"""
            <iframe id="pdfFrame"
                src="data:application/pdf;base64,{base64_pdf}"
                style="display:none;"></iframe>

            <button onclick="printPDF()"
                style="
                    padding:12px 22px;
                    background-color:#4CAF50;
                    color:white;
                    border:none;
                    border-radius:6px;
                    cursor:pointer;
                    font-size:16px;">
                🖨️ Print Preview
            </button>

            <script>
                function printPDF() {{
                    var frame = document.getElementById('pdfFrame');
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                }}
            </script>
        """

        components.html(html_code, height=80)






















