import streamlit as st
import requests
import fitz  # PyMuPDF
from io import BytesIO
from PyPDF2 import PdfWriter, PdfReader

OCR_API_KEY = "YOUR_OCR_KEY_HERE"  # replace with real OCR.Space key

st.set_page_config(page_title="PDF Keyword Finder", layout="wide")

st.title("🔎 PDF Page Keyword Finder & Smart Printer")
st.write("Upload PDFs → Enter GIR → Enter Keyword → Extract Only Matching Pages → Print.")

uploaded_files = st.file_uploader("Upload PDF files", type="pdf", accept_multiple_files=True)
gir_number = st.text_input("Enter GIR Number")
keyword = st.text_input("Enter Keyword to Search")

if uploaded_files and gir_number and keyword:
    st.info("Processing... please wait.")

    matched_pages = []

    for uploaded_file in uploaded_files:
        file_name = uploaded_file.name

        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded_file.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            pix = page.get_pixmap(dpi=150)
            img_bytes = BytesIO(pix.tobytes("png"))

            # OCR
            files = {"file": ("page.png", img_bytes.getvalue())}
            data = {"apikey": OCR_API_KEY, "language": "eng", "OCREngine": 2}

            try:
                response = requests.post("https://api.ocr.space/parse/image",
                                         files=files, data=data)
                result = response.json()
                parsed_text = result["ParsedResults"][0]["ParsedText"].lower()
            except:
                parsed_text = ""

            if keyword.lower() in parsed_text:
                matched_pages.append({
                    "pdf_name": file_name,
                    "page_num": page_num + 1,
                    "image": pix.tobytes("png"),
                    "pdf_bytes": pdf_bytes
                })

    st.subheader("Matched Pages")

    if not matched_pages:
        st.warning("No matching pages found.")
    else:
        writer = PdfWriter()

        for item in matched_pages:
            st.write(f"📄 **{item['pdf_name']} — Page {item['page_num']}**")
            st.image(item["image"], width=400)

            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            writer.add_page(reader.pages[item["page_num"] - 1])

        out = BytesIO()
        writer.write(out)

        st.download_button(
            label="📥 Download PDF of Matching Pages",
            data=out.getvalue(),
            file_name="matched_pages.pdf",
            mime="application/pdf"
        )
