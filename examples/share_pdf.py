"""Upload a PDF and get a tracked share link for one recipient.

    HELPRANGE_API_KEY=hr_test_... python examples/share_pdf.py proposal.pdf
"""
import sys

from helprange import HelpRange

path = sys.argv[1] if len(sys.argv) > 1 else "proposal.pdf"

with HelpRange() as hr:  # reads HELPRANGE_API_KEY
    result = hr.share(
        path,
        label="ACME - Anna",  # who the link is for – shown in the statistics, unique per document
        allow_download=False,
        watermark=True,
        require_email=True,
        expires_on="2026-12-31",
    )
    doc, link = result["document"], result["link"]
    print(f'Uploaded "{doc["name"]}" ({doc["pages"] or "?"} pages, id {doc["id"]})')
    print(f"Send this link: {link['url']}")
    if hr.test_mode:
        print("(test mode – this lives in your sandbox)")
