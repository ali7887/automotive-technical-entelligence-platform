"""Build minimal real PDFs with extractable text for pipeline tests.

pypdf can only write blank pages, so pages are assembled as raw PDF objects with
Helvetica text streams that pypdf's extractor reads back line by line.
"""


def pdf_with_text(pages: list[str]) -> bytes:
    font_obj_num = 3 + 2 * len(pages)
    objects: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for i, page_text in enumerate(pages):
        content_num = 3 + 2 * i + 1
        objects.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
                f"/Contents {content_num} 0 R >>"
            ).encode()
        )
        parts = ["BT /F1 10 Tf 12 TL 40 760 Td"]
        for j, line in enumerate(page_text.splitlines()):
            escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
            parts.append(("T* " if j else "") + f"({escaped}) Tj")
        parts.append("ET")
        stream = "\n".join(parts).encode("latin-1", errors="replace")
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for num, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    count = len(objects) + 1
    out += f"xref\n0 {count}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF".encode()
    return bytes(out)
