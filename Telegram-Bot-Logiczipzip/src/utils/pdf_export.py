import os
import tempfile
from fpdf import FPDF


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class RuPDF(FPDF):
    def __init__(self):
        super().__init__()
        self.add_font("DejaVu", "", FONT_PATH, uni=True)
        self.add_font("DejaVu", "B", FONT_BOLD_PATH, uni=True)
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("DejaVu", "", 7)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Стр. {self.page_no()}/{{nb}}", align="C")


def generate_operator_stats_pdf(
    operator_name: str,
    period_label: str,
    summary: dict,
    rows: list[dict],
) -> str:
    pdf = RuPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Статистика: {operator_name}", ln=True, align="C")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 7, f"Период: {period_label}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("DejaVu", "B", 11)
    pdf.cell(0, 8, "Сводка", ln=True)
    pdf.set_font("DejaVu", "", 10)
    info = [
        ("Всего аккаунтов", str(summary.get("total_accounts", 0))),
        ("Заказов", str(summary.get("total_orders", 0))),
        ("Завершено", str(summary.get("completed_orders", 0))),
        ("Подписей продано", str(summary.get("total_signatures", 0))),
        ("Выручка", f"${summary.get('total_revenue', 0):.2f}"),
        ("Аккаунтов задействовано", str(summary.get("accounts_used", 0))),
    ]
    for label, value in info:
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(70, 6, label + ":", border=0)
        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(0, 6, value, ln=True, border=0)

    pdf.ln(6)

    if rows:
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 8, "Детализация по аккаунтам", ln=True)
        pdf.ln(2)

        col_w = [15, 40, 45, 25, 25, 40]
        headers = ["#", "Телефон", "Категория", "Продано", "Макс.", "Выручка"]

        pdf.set_font("DejaVu", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("DejaVu", "", 8)
        total_revenue = 0.0
        for idx, r in enumerate(rows, 1):
            phone = r.get("phone", "—")
            cat = r.get("category_name", "—")
            sold = int(r.get("sold_count", 0))
            eff_max = int(r.get("effective_max", 0))
            revenue = float(r.get("revenue", 0))
            total_revenue += revenue

            pdf.cell(col_w[0], 6, str(idx), border=1, align="C")
            pdf.cell(col_w[1], 6, phone, border=1)
            pdf.cell(col_w[2], 6, cat, border=1)
            pdf.cell(col_w[3], 6, str(sold), border=1, align="C")
            pdf.cell(col_w[4], 6, str(eff_max), border=1, align="C")
            pdf.cell(col_w[5], 6, f"${revenue:.2f}", border=1, align="R")
            pdf.ln()

        pdf.set_font("DejaVu", "B", 9)
        total_w = sum(col_w[:5])
        pdf.cell(total_w, 7, "ИТОГО:", border=1, align="R")
        pdf.cell(col_w[5], 7, f"${total_revenue:.2f}", border=1, align="R")
        pdf.ln()
    else:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(0, 8, "Нет данных о продажах за выбранный период.", ln=True)

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path


def generate_operator_availability_pdf(
    operator_name: str,
    rows: list[dict],
) -> str:
    pdf = RuPDF()
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Наличие: {operator_name}", ln=True, align="C")
    pdf.ln(5)

    if not rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(0, 8, "Нет данных.", ln=True)
    else:
        col_w = [15, 45, 50, 35, 35]
        headers = ["#", "Телефон", "Категория", "Остаток", "Макс."]

        pdf.set_font("DejaVu", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("DejaVu", "", 8)
        for idx, r in enumerate(rows, 1):
            phone = r.get("phone", "—")
            cat = r.get("category_name", "—")
            used = int(r.get("used_signatures", 0))
            eff_max = int(r.get("effective_max", 0))
            remaining = eff_max - used

            pdf.cell(col_w[0], 6, str(idx), border=1, align="C")
            pdf.cell(col_w[1], 6, phone, border=1)
            pdf.cell(col_w[2], 6, cat, border=1)
            pdf.cell(col_w[3], 6, str(remaining), border=1, align="C")
            pdf.cell(col_w[4], 6, str(eff_max), border=1, align="C")
            pdf.ln()

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path
