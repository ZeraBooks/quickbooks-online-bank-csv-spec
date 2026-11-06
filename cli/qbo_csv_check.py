#!/usr/bin/env python3
"""Check a bank CSV before you upload it to QuickBooks Online.

    python3 cli/qbo_csv_check.py file.csv
    python3 cli/qbo_csv_check.py file.csv --statement file.statement.json
    python3 cli/qbo_csv_check.py file.csv --fix cleaned.csv

Rules are in rules/upload-rules.csv. Exit code 0 means no errors (warnings
may still be printed), 1 means at least one error, 2 means the file could
not be read. Python 3.8+, standard library only.

Part of https://github.com/ZeraBooks/quickbooks-online-bank-csv-spec
(ZeraBooks, https://www.zerabooks.com/pdf-to-qbo-converter).
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

MAX_BYTES = 350 * 1024
MAX_LINES = 1000
LAYOUT_3 = ["Date", "Description", "Amount"]
LAYOUT_4 = ["Date", "Description", "Credit", "Debit"]
AMOUNT_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]{1,2})?$")
WEEKDAY_RE = re.compile(r"\b(MON|TUE|WED|THU|FRI|SAT|SUN)[A-Z]*\b", re.I)
SUMMARY_RE = re.compile(r"^(opening|closing|beginning|ending|previous|new)\s+balance|^balance\s+(forward|brought|carried)|^total\b|^subtotal\b", re.I)
DATE_FORMATS = {"MM/DD/YYYY": "%m/%d/%Y", "DD/MM/YYYY": "%d/%m/%Y", "YYYY-MM-DD": "%Y-%m-%d"}


class Issue:
    def __init__(self, rule, severity, line, message):
        self.rule, self.severity, self.line, self.message = rule, severity, line, message

    def __repr__(self):
        where = f"line {self.line}" if self.line else "file"
        return f"{self.severity.upper():7} {self.rule} {where}: {self.message}"


def date_style(value):
    """Return the set of formats a date string could be in."""
    value = value.strip()
    fits = set()
    for name, fmt in DATE_FORMATS.items():
        try:
            dt.datetime.strptime(value, fmt)
            fits.add(name)
        except ValueError:
            pass
    return fits


def parse_amount(text):
    text = text.strip()
    if not AMOUNT_RE.match(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def check(path, statement=None):
    """Return (issues, summary) for one CSV file."""
    issues = []
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        issues.append(Issue("QBO-006", "error", 0, f"file is {size} bytes; the limit is {MAX_BYTES} (350 KB)"))
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [Issue("QBO-001", "error", 0, "file is empty")], {}
    header = [h.strip() for h in rows[0]]
    if header == LAYOUT_3:
        layout = 3
    elif header == LAYOUT_4:
        layout = 4
    else:
        lowered = [h.lower() for h in header]
        if len(header) == 4 and "credit" in lowered[2] and "debit" in lowered[3]:
            issues.append(Issue("QBO-002", "error", 1, f"headers {header[2:]}: name them Credit and Debit, without 'amount'"))
            layout = 4
        else:
            issues.append(Issue("QBO-001", "error", 1, f"header {header} is not Date,Description,Amount or Date,Description,Credit,Debit"))
            return issues, {"layout": None, "rows": len(rows) - 1}
    body = [r for r in rows[1:] if any(c.strip() for c in r)]
    if len(body) > MAX_LINES:
        issues.append(Issue("QBO-007", "error", 0, f"{len(body)} transaction lines; the limit is {MAX_LINES} per upload"))

    styles_possible = None
    parsed_dates = []
    total = Decimal("0")
    seen = {}
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) != layout:
            issues.append(Issue("QBO-001", "error", n, f"row has {len(r)} cells, expected {layout}"))
            continue
        date, desc = r[0].strip(), r[1].strip()
        if WEEKDAY_RE.search(date):
            issues.append(Issue("QBO-005", "error", n, f"date '{date}' has weekday text"))
            date = WEEKDAY_RE.sub("", date).strip()
        fits = date_style(date)
        if not fits:
            issues.append(Issue("QBO-012", "error", n, f"'{date}' is not a real date in MM/DD/YYYY, DD/MM/YYYY or YYYY-MM-DD"))
        else:
            styles_possible = fits if styles_possible is None else styles_possible & fits
            if styles_possible == set():
                issues.append(Issue("QBO-004", "error", n, f"date '{date}' is in a different format from earlier rows"))
                styles_possible = fits
            parsed_dates.append((n, date))
        if SUMMARY_RE.search(desc):
            issues.append(Issue("QBO-015", "error", n, f"'{desc}' is a balance or total line, not a transaction"))
        if not desc:
            issues.append(Issue("QBO-009", "warning", n, "description is blank"))
        elif re.fullmatch(r"[0-9 .,-]+", desc):
            issues.append(Issue("QBO-009", "warning", n, f"description '{desc}' is only a number"))

        if layout == 3:
            raw = r[2].strip()
            amt = parse_amount(raw)
            if amt is None:
                issues.append(Issue("QBO-010", "error", n, f"amount '{raw}' must be digits, an optional minus and a decimal point"))
                continue
            if amt == 0:
                issues.append(Issue("QBO-003", "error", n, "amount is zero; remove the row or the value"))
            signed = amt
        else:
            cr_raw, db_raw = r[2].strip(), r[3].strip()
            for label, raw in (("Credit", cr_raw), ("Debit", db_raw)):
                if raw and parse_amount(raw) is None:
                    issues.append(Issue("QBO-010", "error", n, f"{label} '{raw}' must be digits and a decimal point"))
                elif raw and parse_amount(raw) == 0:
                    issues.append(Issue("QBO-003", "error", n, f"{label} is {raw}; leave the cell blank instead"))
                elif raw.startswith("-"):
                    issues.append(Issue("QBO-010", "error", n, f"{label} '{raw}' is negative; Credit and Debit are both positive"))
            cr = parse_amount(cr_raw) if cr_raw else None
            db = parse_amount(db_raw) if db_raw else None
            cr = cr if cr else None
            db = db if db else None
            if (cr is None) == (db is None):
                if not any(i.line == n and i.rule in ("QBO-003", "QBO-010") for i in issues):
                    issues.append(Issue("QBO-011", "error", n, "fill exactly one of Credit or Debit"))
                continue
            signed = cr if cr is not None else -db
        total += signed
        key = (date, desc.lower(), signed)
        if key in seen:
            issues.append(Issue("QBO-014", "warning", n, f"same date, description and amount as line {seen[key]}"))
        else:
            seen[key] = n

    style = None
    if styles_possible:
        style = sorted(styles_possible)[0] if len(styles_possible) == 1 else "ambiguous:" + "|".join(sorted(styles_possible))

    summary = {"layout": layout, "rows": len(body), "net_change": str(total), "date_style": style}
    if statement:
        opening = Decimal(statement["opening_balance"])
        closing = Decimal(statement["closing_balance"])
        sign = Decimal("-1") if statement.get("account_type") == "credit_card" else Decimal("1")
        # Card statements print a balance owed; money out (a charge) raises it.
        expected = opening + total * sign if sign == 1 else opening - total
        summary["computed_closing"] = str(expected)
        if expected != closing:
            issues.append(Issue("QBO-013", "error", 0, f"opening {opening} + rows {total} = {expected}, but the statement prints {closing} (off by {closing - expected})"))
        fmt = statement.get("date_format")
        start = dt.date.fromisoformat(statement["period_start"])
        end = dt.date.fromisoformat(statement["period_end"])
        if fmt in DATE_FORMATS:
            for n, d in parsed_dates:
                try:
                    day = dt.datetime.strptime(d, DATE_FORMATS[fmt]).date()
                except ValueError:
                    issues.append(Issue("QBO-004", "error", n, f"'{d}' is not {fmt}"))
                    continue
                if not start <= day <= end:
                    issues.append(Issue("QBO-012", "error", n, f"{d} is outside the statement period {start} to {end}"))
    return issues, summary


def fix(path, out_path):
    """Write a cleaned copy: strip $ and thousands commas, turn (12.00) into -12.00,
    blank out zeros, drop weekday text and summary rows. Dates are left as they are."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    header = [h.strip() for h in rows[0]]
    if len(header) == 4:
        header = LAYOUT_4
    elif len(header) == 3:
        header = LAYOUT_3

    def clean_amount(v):
        v = v.strip().replace("$", "").replace(",", "").replace(" ", "")
        neg = v.startswith("(") and v.endswith(")")
        v = v.strip("()")
        if v.upper().endswith("CR") or v.upper().endswith("DR"):
            v = v[:-2]
        if v in ("", "0", "0.0", "0.00", "-0.00"):
            return ""
        try:
            d = Decimal(v)
        except InvalidOperation:
            return v
        if neg:
            d = -d
        return f"{d:.2f}"

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(header)
    for r in rows[1:]:
        if not any(c.strip() for c in r):
            continue
        if len(r) > 1 and SUMMARY_RE.search(r[1].strip()):
            continue
        r = [c.strip() for c in r]
        r[0] = WEEKDAY_RE.sub("", r[0]).strip()
        for i in range(2, len(r)):
            r[i] = clean_amount(r[i])
        if len(r) == 4:
            for i in (2, 3):
                if r[i].startswith("-"):
                    r[i] = r[i][1:]
        w.writerow(r)
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out.getvalue())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a bank CSV against the QuickBooks Online upload rules.")
    ap.add_argument("csv")
    ap.add_argument("--statement", help="statement header JSON with printed opening and closing balances")
    ap.add_argument("--fix", metavar="OUT", help="write a cleaned copy to OUT, then check it")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    a = ap.parse_args(argv)
    target = a.csv
    try:
        if a.fix:
            fix(a.csv, a.fix)
            target = a.fix
        statement = None
        if a.statement:
            with open(a.statement, encoding="utf-8") as fh:
                statement = json.load(fh)
        issues, summary = check(target, statement)
    except (OSError, UnicodeDecodeError, csv.Error, KeyError, ValueError) as exc:
        print(f"could not read {target}: {exc}", file=sys.stderr)
        return 2
    errors = [i for i in issues if i.severity == "error"]
    if a.json:
        print(json.dumps({"file": target, "summary": summary, "ok": not errors,
                          "issues": [vars(i) for i in issues]}, indent=2))
    else:
        for i in issues:
            print(i)
        verdict = "OK, ready to upload" if not errors else f"{len(errors)} error(s), fix before uploading"
        print(f"{target}: {summary.get('rows', 0)} rows, {summary.get('layout')}-column layout, net {summary.get('net_change')}. {verdict}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
