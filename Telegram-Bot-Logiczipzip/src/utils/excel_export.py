import os
import tempfile
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side


CATEGORY_COLORS = {
    "МТС Физ": "FF6600",
    "МТС Е.": "CC0000",
    "МЕГАФОН": "006633",
    "ТЕЛЕ2": "1A1A2E",
    "БИЛАЙН": "FFD700",
    "YOTA": "0066CC",
    "М/СТ/Т": "993399",
}

DEFAULT_CAT_COLOR = "4472C4"


def _get_cat_header_fill(cat_name: str) -> PatternFill:
    color = CATEGORY_COLORS.get(cat_name, DEFAULT_CAT_COLOR)
    return PatternFill(start_color=color, end_color=color, fill_type="solid")


def generate_availability_excel(rows: list[dict], title: str = "Наличие") -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    categories = sorted(set(r["category_name"] for r in rows))

    headers = ["Логин", "Пароль"]
    header_fills = [header_fill, header_fill]
    for cat in categories:
        headers.append(cat)
        header_fills.append(_get_cat_header_fill(cat))

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fills[col_idx - 1]
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    accounts = {}
    account_passwords = {}
    for r in rows:
        phone = r["phone"]
        if phone not in accounts:
            accounts[phone] = {}
            account_passwords[phone] = r.get("password", "")
        remaining = r["effective_max"] - r["used_signatures"]
        price = r.get("category_price", 0) or 0
        accounts[phone][r["category_name"]] = {
            "remaining": remaining,
            "max": r["effective_max"],
            "price": price,
        }

    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")

    row_idx = 2
    for phone in sorted(accounts.keys()):
        cell_phone = ws.cell(row=row_idx, column=1, value=phone)
        cell_phone.border = thin_border
        cell_phone.alignment = Alignment(horizontal="left")

        cell_pass = ws.cell(row=row_idx, column=2, value=account_passwords.get(phone, ""))
        cell_pass.border = thin_border
        cell_pass.alignment = Alignment(horizontal="left")

        for cat_idx, cat in enumerate(categories):
            col = 3 + cat_idx
            data = accounts[phone].get(cat, {"remaining": 0, "max": 0, "price": 0})
            price_int = int(data["price"]) if data["price"] == int(data["price"]) else data["price"]
            cell_val = f"{data['remaining']}-{data['max']}${price_int}"
            cell = ws.cell(row=row_idx, column=col, value=cell_val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
            cell.fill = green_fill if data["remaining"] > 0 else red_fill

        row_idx += 1

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 16
    for col_idx in range(3, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 14

    fd, path = tempfile.mkstemp(suffix=".xlsx", prefix="availability_")
    os.close(fd)
    wb.save(path)
    return path


def generate_sales_excel(rows: list[dict], title: str = "Продажи") -> str:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]

    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )
    green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")

    categories = sorted(set(r["category_name"] for r in rows))

    headers = ["Логин", "Пароль"]
    header_fills = [header_fill, header_fill]
    for cat in categories:
        headers.append(cat)
        header_fills.append(_get_cat_header_fill(cat))
    headers.append("Продано")
    header_fills.append(header_fill)
    headers.append("Выручка $")
    header_fills.append(header_fill)

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fills[col_idx - 1]
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    accounts = {}
    account_passwords = {}
    for r in rows:
        phone = r["phone"]
        if phone not in accounts:
            accounts[phone] = {"cats": {}, "total_sold": 0, "total_revenue": 0}
            account_passwords[phone] = r.get("password", "")
        remaining = r["effective_max"] - r["used_signatures"]
        price = r.get("category_price", 0) or 0
        sold = r.get("sold_count", 0) or 0
        revenue = round(r.get("revenue", 0) or 0, 2)
        accounts[phone]["cats"][r["category_name"]] = {
            "remaining": remaining,
            "max": r["effective_max"],
            "price": price,
            "sold": sold,
            "revenue": revenue,
        }
        accounts[phone]["total_sold"] += sold
        accounts[phone]["total_revenue"] += revenue

    row_idx = 2
    total_revenue_all = 0
    total_sold_all = 0
    for phone in sorted(accounts.keys()):
        cell_phone = ws.cell(row=row_idx, column=1, value=phone)
        cell_phone.border = thin_border
        cell_phone.alignment = Alignment(horizontal="left")

        cell_pass = ws.cell(row=row_idx, column=2, value=account_passwords.get(phone, ""))
        cell_pass.border = thin_border
        cell_pass.alignment = Alignment(horizontal="left")

        for cat_idx, cat in enumerate(categories):
            col = 3 + cat_idx
            data = accounts[phone]["cats"].get(cat, {"remaining": 0, "max": 0, "price": 0, "sold": 0})
            price_int = int(data["price"]) if data["price"] == int(data["price"]) else data["price"]
            cell_val = f"{data['remaining']}-{data['max']}${price_int}"
            cell = ws.cell(row=row_idx, column=col, value=cell_val)
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
            if data.get("sold", 0) > 0:
                cell.fill = yellow_fill
            elif data["remaining"] > 0:
                cell.fill = green_fill
            else:
                cell.fill = red_fill

        sold_col = 3 + len(categories)
        rev_col = sold_col + 1

        cell_sold = ws.cell(row=row_idx, column=sold_col, value=accounts[phone]["total_sold"])
        cell_sold.border = thin_border
        cell_sold.alignment = Alignment(horizontal="center")
        cell_sold.font = Font(bold=True)

        cell_rev = ws.cell(row=row_idx, column=rev_col, value=round(accounts[phone]["total_revenue"], 2))
        cell_rev.border = thin_border
        cell_rev.alignment = Alignment(horizontal="center")
        cell_rev.font = Font(bold=True)
        cell_rev.number_format = '#,##0.00'

        total_sold_all += accounts[phone]["total_sold"]
        total_revenue_all += accounts[phone]["total_revenue"]
        row_idx += 1

    row_idx += 1
    total_font = Font(bold=True, size=12)
    sold_col = 3 + len(categories)
    rev_col = sold_col + 1

    cell_label = ws.cell(row=row_idx, column=sold_col - 1, value="ИТОГО:")
    cell_label.font = total_font
    cell_label.alignment = Alignment(horizontal="right")

    cell_total_sold = ws.cell(row=row_idx, column=sold_col, value=total_sold_all)
    cell_total_sold.font = total_font
    cell_total_sold.border = thin_border
    cell_total_sold.alignment = Alignment(horizontal="center")

    cell_total_rev = ws.cell(row=row_idx, column=rev_col, value=round(total_revenue_all, 2))
    cell_total_rev.font = total_font
    cell_total_rev.number_format = '#,##0.00'
    cell_total_rev.alignment = Alignment(horizontal="center")
    cell_total_rev.border = thin_border

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 16
    for col_idx in range(3, len(headers) + 1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = 14

    fd, path = tempfile.mkstemp(suffix=".xlsx", prefix="sales_")
    os.close(fd)
    wb.save(path)
    return path
