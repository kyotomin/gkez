import os
import tempfile
from fpdf import FPDF


FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


class RuPDF(FPDF):
    def __init__(self, orientation="L"):
        super().__init__(orientation=orientation)
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
        self.set_text_color(0, 0, 0)


def _group_rows_by_phone(rows: list[dict]) -> tuple[dict, list[str]]:
    categories = sorted(set(r.get("category_name", "") for r in rows))
    accounts = {}
    for r in rows:
        phone = r.get("phone", "—")
        if phone not in accounts:
            accounts[phone] = {"cats": {}, "password": r.get("password", "")}
        cat = r.get("category_name", "")
        sold = int(r.get("sold_count", 0) or 0)
        eff_max = int(r.get("effective_max", 0) or 0)
        used = int(r.get("used_signatures", 0) or 0)
        remaining = eff_max - used
        revenue = float(r.get("revenue", 0) or 0)
        accounts[phone]["cats"][cat] = {
            "sold": sold,
            "remaining": remaining,
            "max": eff_max,
            "revenue": revenue,
        }
    return accounts, categories


def generate_operator_stats_pdf(
    operator_name: str,
    period_label: str,
    summary: dict,
    rows: list[dict],
) -> str:
    pdf = RuPDF(orientation="L")
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
        accounts, categories = _group_rows_by_phone(rows)

        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 8, "Детализация по аккаунтам", ln=True)
        pdf.ln(2)

        num_w = 10
        phone_w = 35
        cat_w = max(30, int((pdf.w - pdf.l_margin - pdf.r_margin - num_w - phone_w - 30) / max(len(categories), 1)))
        sum_w = 30
        col_w = [num_w, phone_w] + [cat_w] * len(categories) + [sum_w]
        headers = ["#", "Телефон"] + categories + ["Сумма"]

        pdf.set_font("DejaVu", "B", 7)
        pdf.set_fill_color(230, 230, 230)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("DejaVu", "", 7)
        grand_total = 0.0
        for idx, phone in enumerate(sorted(accounts.keys()), 1):
            acc = accounts[phone]
            row_total = 0.0
            pdf.cell(col_w[0], 6, str(idx), border=1, align="C")
            pdf.cell(col_w[1], 6, phone, border=1)
            for ci, cat in enumerate(categories):
                d = acc["cats"].get(cat, {"sold": 0, "remaining": 0, "max": 0, "revenue": 0})
                rev = d["revenue"]
                row_total += rev
                txt = f"{d['remaining']}/{d['max']} {d['sold']}шт ${rev:.0f}"
                pdf.cell(col_w[2 + ci], 6, txt, border=1, align="C")
            grand_total += row_total
            pdf.cell(col_w[-1], 6, f"${row_total:.2f}", border=1, align="R")
            pdf.ln()

        pdf.set_font("DejaVu", "B", 8)
        total_w = sum(col_w[:-1])
        pdf.cell(total_w, 7, "ИТОГО:", border=1, align="R")
        pdf.cell(col_w[-1], 7, f"${grand_total:.2f}", border=1, align="R")
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
    pdf = RuPDF(orientation="L")
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Наличие: {operator_name}", ln=True, align="C")
    pdf.ln(5)

    if not rows:
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(0, 8, "Нет данных.", ln=True)
    else:
        categories = sorted(set(r.get("category_name", "") for r in rows))
        accounts = {}
        for r in rows:
            phone = r.get("phone", "—")
            if phone not in accounts:
                accounts[phone] = {}
            cat = r.get("category_name", "")
            used = int(r.get("used_signatures", 0) or 0)
            eff_max = int(r.get("effective_max", 0) or 0)
            remaining = eff_max - used
            accounts[phone][cat] = {"remaining": remaining, "max": eff_max}

        num_w = 10
        phone_w = 40
        cat_w = max(35, int((pdf.w - pdf.l_margin - pdf.r_margin - num_w - phone_w) / max(len(categories), 1)))
        col_w = [num_w, phone_w] + [cat_w] * len(categories)
        headers = ["#", "Телефон"] + categories

        pdf.set_font("DejaVu", "B", 8)
        pdf.set_fill_color(230, 230, 230)
        for i, h in enumerate(headers):
            pdf.cell(col_w[i], 7, h, border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("DejaVu", "", 8)
        for idx, phone in enumerate(sorted(accounts.keys()), 1):
            pdf.cell(col_w[0], 6, str(idx), border=1, align="C")
            pdf.cell(col_w[1], 6, phone, border=1)
            for ci, cat in enumerate(categories):
                d = accounts[phone].get(cat, {"remaining": 0, "max": 0})
                txt = f"{d['remaining']}/{d['max']}"
                pdf.cell(col_w[2 + ci], 6, txt, border=1, align="C")
            pdf.ln()

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path


def generate_admin_stats_pdf(
    admin_id: int,
    stats_today: dict,
    stats_week: dict,
    stats_month: dict,
    stats_all: dict,
) -> str:
    pdf = RuPDF(orientation="P")
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("DejaVu", "B", 14)
    pdf.cell(0, 10, f"Статистика админа: {admin_id}", ln=True, align="C")
    pdf.ln(5)

    periods = [
        ("Сегодня", stats_today),
        ("За неделю", stats_week),
        ("За месяц", stats_month),
        ("За всё время", stats_all),
    ]

    col_w = [60, 35, 35, 35]
    headers = ["Период", "Аккаунтов", "Подписей", "Выручка"]

    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    for i, h in enumerate(headers):
        pdf.cell(col_w[i], 8, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("DejaVu", "", 10)
    for label, st in periods:
        pdf.cell(col_w[0], 7, label, border=1)
        pdf.cell(col_w[1], 7, str(st.get("accounts_added", 0)), border=1, align="C")
        pdf.cell(col_w[2], 7, str(st.get("signatures_sold", 0)), border=1, align="C")
        pdf.cell(col_w[3], 7, f"${st.get('revenue', 0):.2f}", border=1, align="R")
        pdf.ln()

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    pdf.output(path)
    return path
