import streamlit as st
import requests
import fitz  # PyMuPDF
from io import BytesIO
from PyPDF2 import PdfReader, PdfWriter
import base64
import streamlit.components.v1 as components


# -------------------------
# 🔑 OCR.Space API KEY
# Replace with your key (inside quotes)
# -------------------------
OCR_API_KEY = "YOUR_OCR_KEY_HERE"


# -------------------------
# Streamlit UI
# -------------------------
st.set_page_config(page_title="PDF Page Finder", layout="wide")

st.title("🔎 PDF Page Extractor with Print Preview")
st.write("Upload PDFs → Enter GIR → Enter Keyword → Get Relevant Pages → Print.")


uploaded_files = st.file_uploader(
    "Upload PDF files",
    type="pdf",
    accept_multiple_files=True
)

gir_number = st.text_input("Enter GIR Number (e.g., 5433)")
keyword = st.text_input("Enter keyword to search for (English or Arabic)")


# -------------------------
# MAIN LOGIC
# -------------------------
if uploaded_files and gir_number and keyword:

    st.info("Processing PDFs… please wait. OCR may take a few seconds per page.")

    matched_pages = []

    for uploaded in uploaded_files:
        file_name = uploaded.name

        # Filter PDFs by GIR number in the filename
        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Process pages
        for page_num in range(len(pdf_doc)):

            page = pdf_doc[page_num]

            # Render page at higher DPI for better OCR accuracy
            pix = page.get_pixmap(dpi=300)
            img_bytes = BytesIO(pix.tobytes("png"))

            # OCR.Space request
            files = {"file": ("page.png", img_bytes.getvalue())}
            data = {
                "apikey": OCR_API_KEY,
                "language": "eng",
                "OCREngine": 1,
                "detectOrientation": True,
                "scale": True
            }

            # Send to OCR API
            try:
                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    files=files,
                    data=data
                )
                result = response.json()
            except Exception as e:
                st.error(f"OCR request failed on {file_name}, Page {page_num+1}: {e}")
                continue

            # Handle OCR errors
            if result.get("IsErroredOnProcessing"):
                err = result.get("ErrorMessage", "Unknown OCR error")
                st.warning(f"OCR error on {file_name}, Page {page_num+1}: {err}")
                parsed_text = ""
            else:
                parsed_text = result["ParsedResults"][0]["ParsedText"].lower().strip()

            # Debug text viewer
            with st.expander(f"OCR Text for {file_name} — Page {page_num+1}"):
                st.text(parsed_text)

            # Keyword match
            if keyword.lower() in parsed_text.replace("\n", " "):
                matched_pages.append({
                    "pdf_name": file_name,
                    "page_num": page_num + 1,
                    "image": pix.tobytes("png"),
                    "pdf_bytes": pdf_bytes
                })


    # -------------------------
    # RESULTS DISPLAY
    # -------------------------
    st.subheader("Matched Pages")

    if not matched_pages:
        st.error("❌ No matching pages found. Check OCR output above.")
    else:
        writer = PdfWriter()

        for item in matched_pages:
            st.write(f"### 📄 {item['pdf_name']} — Page {item['page_num']}")
            st.image(item["image"], width=450)

            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            writer.add_page(reader.pages[item["page_num"] - 1])

        out_pdf = BytesIO()
        writer.write(out_pdf)
        writer.close()

        # -------------------------
        # PRINT PREVIEW BUTTON
        # -------------------------
        base64_pdf = base64.b64encode(out_pdf.getvalue()).decode("utf-8")

        html_code = f"""
            <iframe id="pdfFrame"
                src="data:application/pdf;base64,{base64_pdf}"
                style="width:0; height:0; border:none;"></iframe>

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

        st.success("Matched pages ready! Scroll up to review them before printing.")







