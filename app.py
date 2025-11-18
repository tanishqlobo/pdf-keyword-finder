import streamlit as st
import fitz  # PyMuPDF
from PyPDF2 import PdfWriter, PdfReader
from io import BytesIO
import base64
import streamlit.components.v1 as components
import requests


# ----------------------------------------------
# 🔑 OCR SPACE API KEY (FALLBACK)
# ----------------------------------------------
OCR_API_KEY = "K88121712188957"   # <-- REPLACE THIS


# ----------------------------------------------
# STREAMLIT CONFIG
# ----------------------------------------------
st.set_page_config(page_title="Invoice Extractor", layout="wide")
st.title("📄 Invoice Page Extractor (Hybrid: Direct Text + OCR Fallback)")
st.write(
    "• Filters PDFs by GIR number\n"
    "• Ignores BOE PDFs\n"
    "• Extracts pages ONLY if BOTH Item Number AND Country of Origin exist\n"
    "• Highlights both terms\n"
    "• Merges results into one PDF\n"
    "• Enables Download + Print Preview"
)


# ----------------------------------------------
# USER INPUTS
# ----------------------------------------------
gir_number = st.text_input("Enter GIR Number")

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
# MAIN PROCESSING
# ----------------------------------------------
if uploaded_files and gir_number and item_number and country_origin:

    st.info("Processing invoices… Fast text extraction with OCR fallback if needed.")

    matched_pages = []

    item_lower = item_number.lower()
    country_lower = country_origin.lower()

    # Loop through PDFs
    for uploaded in uploaded_files:
        file_name = uploaded.name

        # Skip BOE files
        if "BOE" in file_name.upper():
            continue

        # Only process PDFs containing GIR in filename
        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Process each page
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            # ------------------------------------------
            # 1) Direct text extraction (super fast)
            # ------------------------------------------
            text = page.get_text().lower().strip()

            # If empty, fallback to OCR
            if len(text) < 10:
                pix = page.get_pixmap(dpi=300)
                img_bytes = pix.tobytes("png")
                text = ocr_fallback(img_bytes)

            # ------------------------------------------
            # Must contain BOTH keywords
            # ------------------------------------------
            if item_lower in text and country_lower in text:

                # Modify the page for highlighting
                highlight_page = pdf_doc.load_page(page_num)

                # Highlight Item Number
                item_rects = highlight_page.search_for(item_number)
                for rect in item_rects:
                    highlight_page.add_highlight_annot(rect)

                # Highlight Country of Origin
                country_rects = highlight_page.search_for(country_origin)
                for rect in country_rects:
                    highlight_page.add_highlight_annot(rect)

                # Save highlighted single page PDF
                temp_pdf = BytesIO(pdf_doc.write())
                temp_reader = PdfReader(temp_pdf)

                single_writer = PdfWriter()
                single_page_pdf = BytesIO()
                single_writer.add_page(temp_reader.pages[page_num])
                single_writer.write(single_page_pdf)

                matched_pages.append({
                    "pdf_name": file_name,
                    "page_num": page_num + 1,
                    "pdf_bytes": single_page_pdf.getvalue(),
                    "image": page.get_pixmap(dpi=150).tobytes("png")
                })


    # ----------------------------------------------
    # RESULTS
    # ----------------------------------------------
    st.header("Matched Pages")

    if not matched_pages:
        st.error("❌ No pages found containing BOTH the Item Number AND the Country of Origin.")
    else:
        final_writer = PdfWriter()

        # Merge all matched pages
        for item in matched_pages:
            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            final_writer.add_page(reader.pages[0])

        final_pdf = BytesIO()
        final_writer.write(final_pdf)

        # Show results
        for item in matched_pages:
            st.write(f"📄 {item['pdf_name']} — Page {item['page_num']}")
            st.image(item["image"], width=450)

        st.markdown("---")

        file_out = f"CustomsPrint-{item_number}-{country_origin}-{gir_number}.pdf"

        # ----------------------------------------------
        # DOWNLOAD BUTTON
        # ----------------------------------------------
        st.download_button(
            label=f"📥 Download {file_out}",
            data=final_pdf.getvalue(),
            file_name=file_out,
            mime="application/pdf"
        )

        # ----------------------------------------------
        # PRINT PREVIEW BUTTON (Chrome-compatible)
        # ----------------------------------------------
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
















