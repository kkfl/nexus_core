"""Convert implementation_plan.md to PDF using fpdf2 + markdown->HTML."""

import re
import markdown
from fpdf import FPDF


class PlanPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "Nexus Server Administration Agent -- Implementation Plan", align="C")
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def main():
    md_path = r"C:\Users\randa\.gemini\antigravity\brain\13d4f979-8c02-4524-8ebf-42de3345f248\implementation_plan.md"
    pdf_path = r"C:\Users\randa\Desktop\Nexus_Server_Agent_Implementation_Plan.pdf"

    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )

    # Replace em-dashes for encoding safety
    html_body = html_body.replace("\u2014", "--")
    html_body = html_body.replace("\u2013", "-")
    html_body = html_body.replace("\u2018", "'").replace("\u2019", "'")
    html_body = html_body.replace("\u201c", '"').replace("\u201d", '"')
    html_body = html_body.replace("\u2192", "->")
    html_body = html_body.replace("\u2705", "[OK]")
    html_body = html_body.replace("\u274c", "[FAIL]")

    css = """
    body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; }
    h1 { font-size: 18pt; color: #0f3460; }
    h2 { font-size: 14pt; color: #0f3460; border-bottom: 1px solid #ccc; }
    h3 { font-size: 12pt; color: #533483; }
    h4 { font-size: 11pt; color: #e94560; }
    table { border-collapse: collapse; width: 100%; }
    th { background-color: #0f3460; color: #ffffff; padding: 4px 6px; }
    td { border: 1px solid #ddd; padding: 3px 6px; }
    tr:nth-child(even) { background-color: #f8f9fa; }
    code { font-family: Courier; font-size: 9pt; background-color: #f0f0f0; }
    pre { font-family: Courier; font-size: 8pt; background-color: #f0f0f0; padding: 8px; }
    hr { border: none; border-top: 1px solid #ccc; }
    """

    full_html = "<html><head><style>" + css + "</style></head><body>" + html_body + "</body></html>"

    pdf = PlanPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.write_html(full_html)
    pdf.output(pdf_path)
    print(f"PDF saved to: {pdf_path}")


if __name__ == "__main__":
    main()
