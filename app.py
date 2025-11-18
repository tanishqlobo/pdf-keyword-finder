import streamlit as st
import requests
import fitz  # PyMuPDF
from io import BytesIO
from PyPDF2 import PdfWriter, PdfReader

# 🔑 Replace this with your OCR.Space API key
OCR_API_KEY = K88121712188957

st.set_page_config(page_title="PDF Keyword Finder", layout="wide")

st.title("🔎 PDF Page Keyword Finder & Smart Printer")
st.write("Upload PDFs → Enter GIR → Enter Keyword → Extract Only Matching Pages → Print.")

# ----------------------
# USER INPUTS
# ----------------------

uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)
gir_number = st.text_input("Enter GIR Number (e.g., 5433)")
keyword = st.text_input("Enter keyword to search")

if uploaded_files and gir_number and keyword:

    st.info("Processing PDFs… please wait (OCR may take some time).")

    matched_pages = []   # Final results

    # ----------------------
    # PROCESS EACH PDF
    # ----------------------
    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name

        # Only include PDFs whose filenames contain the GIR number
        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded_file.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # ----------------------
        # PROCESS EACH PAGE
        # ----------------------
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            # Render page at 300 DPI for much better OCR quality
            pix = page.get_pixmap(dpi=300)
            img_bytes = BytesIO(pix.tobytes("png"))

            # ----------------------
            # SEND TO OCR.SPACE
            # ----------------------
            files = {"file": ("page.png", img_bytes.getvalue())}
            data = {
                "apikey": OCR_API_KEY,
                "language": "eng",
                "OCREngine": 1,         # More stable for scanned docs
                "scale": True,
                "detectOrientation": True
            }

            try:
                response = requests.post("https://api.ocr.space/parse/image",
                                         files=files, data=data)
                result = response.json()
                parsed_text = result["ParsedResults"][0]["ParsedText"].lower().strip()
            except Exception as e:
                st.warning(f"⚠️ OCR failed on {file_name} — Page {page_num+1}: {e}")
                parsed_text = ""

            # DEBUGGING — LET YOU SEE OCR RESULTS
            with st.expander(f"OCR Text for {file_name} — Page {page_num+1}"):
                st.text(parsed_text)

            # ----------------------
            # KEYWORD MATCH (FUZZY)
            # ----------------------
            clean_text = parsed_text.replace("\n", " ")

            if keyword.lower() in clean_text:
                matched_pages.append({
                    "pdf_name": file_name,
                    "page_num": page_num + 1,
                    "image": pix.tobytes("png"),
                    "pdf_bytes": pdf_bytes
                })

    # ----------------------
    # DISPLAY RESULTS
    # ----------------------
    st.subheader("📄 Matched Pages")

    if not matched_pages:
        st.error("❌ No matching pages found. Check OCR text above to see what OCR captured.")
    else:

        writer = PdfWriter()

        for item in matched_pages:
            st.write(f"### 📌 {item['pdf_name']} — Page {item['page_num']}")
            st.image(item["image"], width=450)

            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            writer.add_page(reader.pages[item["page_num"] - 1])

        out_pdf = BytesIO()
        writer.write(out_pdf)
        writer.close()

        st.success("Matching pages found! Scroll above to preview them.")

        # ----------------------
        # DOWNLOAD MATCHED PAGES PDF
        # ----------------------
        st.download_button(
            label="📥 Download PDF of Matching Pages",
            data=out_pdf.getvalue(),
            file_name="matched_pages.pdf",
            mime="application/pdf"
        )


