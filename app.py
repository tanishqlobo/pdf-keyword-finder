import streamlit as st
import requests
import fitz  # PyMuPDF
from io import BytesIO
from PyPDF2 import PdfWriter, PdfReader
import base64
import streamlit.components.v1 as components


# -----------------------------
# 🔑 OCR SPACE API KEY
# -----------------------------
OCR_API_KEY = "K88121712188957"


# -----------------------------
# STREAMLIT PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="Customs Page Extractor", layout="wide")
st.title("📄 Customs BOE Page Extractor with Print Preview + Highlighting")
st.write("Upload PDFs → Enter GIR → Enter up to 10 Item Numbers → Get highlighted pages per item.")


# -----------------------------
# USER INPUTS
# -----------------------------
gir_number = st.text_input("Enter GIR Number (e.g., 5399)")

st.subheader("Enter Item Numbers (optional)")
keyword_inputs = []
for i in range(1, 11):
    keyword_inputs.append(
        st.text_input(f"Enter Item Number {i} from BOE")
    )

# Keep only non-empty keywords
keywords = [k.strip() for k in keyword_inputs if k.strip()]

uploaded_files = st.file_uploader(
    "Upload PDF files",
    type="pdf",
    accept_multiple_files=True
)


# -----------------------------
# MAIN PROCESSING
# -----------------------------
if uploaded_files and gir_number and keywords:

    st.info("Processing files… This may take some time depending on the number of pages.")

    results = {kw: [] for kw in keywords}  # store matches for each keyword

    for uploaded in uploaded_files:
        file_name = uploaded.name

        # Ignore BOE PDFs
        if "BOE" in file_name.upper():
            continue

        # Process only PDFs with GIR in filename
        if gir_number not in file_name:
            continue

        pdf_bytes = uploaded.read()
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]

            # Render page at 300 DPI
            pix = page.get_pixmap(dpi=300)
            img_bytes = BytesIO(pix.tobytes("png"))

            # OCR SPACE REQUEST
            files = {"file": ("page.png", img_bytes.getvalue())}
            data = {
                "apikey": OCR_API_KEY,
                "language": "eng",
                "OCREngine": 1,
                "scale": True,
                "detectOrientation": True
            }

            try:
                response = requests.post(
                    "https://api.ocr.space/parse/image",
                    files=files,
                    data=data
                )
                result = response.json()
            except Exception as e:
                st.error(f"Error sending OCR request: {e}")
                continue

            # Parse OCR text
            if result.get("IsErroredOnProcessing"):
                parsed_text = ""
            else:
                parsed_text = result["ParsedResults"][0]["ParsedText"].lower()

            # Debug expander
            with st.expander(f"OCR Text for {file_name} — Page {page_num+1}"):
                st.text(parsed_text)

            # Check each keyword
            for kw in keywords:
                if kw.lower() in parsed_text:

                    # -----------------------------
                    # HIGHLIGHT KEYWORD ON PDF PAGE
                    # -----------------------------
                    highlight_page = fitz.open(stream=pdf_bytes, filetype="pdf")[page_num]
                    rects = highlight_page.search_for(kw)

                    for rect in rects:
                        highlight_page.add_highlight_annot(rect)

                    # Save modified page to memory
                    writer = PdfWriter()
                    single_page_pdf = BytesIO()
                    writer.add_page(PdfReader(BytesIO(highlight_page.parent.write())).pages[0])
                    writer.write(single_page_pdf)

                    results[kw].append({
                        "pdf_name": file_name,
                        "page_num": page_num + 1,
                        "image": pix.tobytes("png"),
                        "pdf_bytes": single_page_pdf.getvalue()
                    })


    # -----------------------------
    # OUTPUT FOR EACH KEYWORD
    # -----------------------------
    st.subheader("Matched Results Per Keyword")

    for kw in keywords:
        st.markdown(f"## 🔍 Results for Item: **{kw}**")

        pages = results[kw]
        if not pages:
            st.warning(f"No pages found for keyword: {kw}")
            continue

        # Merge pages for this keyword
        writer = PdfWriter()
        for item in pages:
            reader = PdfReader(BytesIO(item["pdf_bytes"]))
            writer.add_page(reader.pages[0])

        final_pdf = BytesIO()
        writer.write(final_pdf)

        # Preview thumbnails
        for item in pages:
            st.write(f"📄 {item['pdf_name']} — Page {item['page_num']}")
            st.image(item["image"], width=450)

        # -----------------------------
        # DOWNLOAD BUTTON
        # -----------------------------
        st.download_button(
            label=f"📥 Download: CustomsPrint-{kw}-{gir_number}.pdf",
            data=final_pdf.getvalue(),
            file_name=f"CustomsPrint-{kw}-{gir_number}.pdf",
            mime="application/pdf"
        )

        # -----------------------------
        # PRINT PREVIEW BUTTON (Chrome)
        # -----------------------------
        base64_pdf = base64.b64encode(final_pdf.getvalue()).decode("utf-8")
        html_code = f"""
            <iframe id="pdfFrame_{kw}"
                src="data:application/pdf;base64,{base64_pdf}"
                style="display:none;"></iframe>

            <button onclick="printPDF_{kw}()"
                style="
                    padding:12px 22px;
                    background-color:#4CAF50;
                    color:white;
                    border:none;
                    border-radius:6px;
                    cursor:pointer;
                    font-size:16px;">
                🖨️ Print Preview for {kw}
            </button>

            <script>
                function printPDF_{kw}() {{
                    var frame = document.getElementById('pdfFrame_{kw}');
                    frame.contentWindow.focus();
                    frame.contentWindow.print();
                }}
            </script>
        """
        components.html(html_code, height=80)

        st.markdown("---")











