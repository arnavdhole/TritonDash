import pdfplumber


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from a PDF, joining pages with double newlines."""
    pages: list[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
    return "\n\n".join(pages)
