"""Generate the fictional sample files in samples/.

    python3 scripts/generate_samples.py

Every bank, business and amount is made up. The generator is seeded, so it
writes the same files every time. Each statement gets:
  - a 3-column CSV (Date, Description, Amount)
  - a 4-column CSV (Date, Description, Credit, Debit)
  - a .statement.json sidecar with the printed opening and closing balance
The rows always add up: opening + rows = closing.
Then samples/invalid/ gets one broken copy per upload rule, listed in
samples/invalid/expected.json with the rule each file must fail.
"""
import csv
import datetime as dt
import json
import os
import random
import shutil
from decimal import Decimal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "samples")

ACCOUNTS = [
    # slug, fictional bank, fictional business, type, last4, date format, opening
    ("harbor-point-checking", "Harbor Point Savings Bank", "Juniper Lane Bakery LLC", "checking", "4471", "MM/DD/YYYY", "8214.37"),
    ("cedar-valley-checking", "Cedar Valley Credit Union", "Okafor Family Dental PC", "checking", "0932", "MM/DD/YYYY", "23650.10"),
    ("northfield-savings", "Northfield National Bank", "Brightwater Landscaping Inc", "savings", "7718", "MM/DD/YYYY", "41000.00"),
    ("prairie-trust-checking", "Prairie Trust Bank", "Redline Freight Co", "checking", "2256", "MM/DD/YYYY", "15402.88"),
    ("lakeshore-checking", "Lakeshore Community Bank", "Marisol Vega CPA", "checking", "6603", "MM/DD/YYYY", "5120.45"),
    ("summit-card", "Summit Card Services", "Juniper Lane Bakery LLC", "credit_card", "9014", "MM/DD/YYYY", "1873.22"),
    ("granite-card", "Granite Bank Card", "Redline Freight Co", "credit_card", "3380", "MM/DD/YYYY", "6240.00"),
    ("thistle-current", "Thistle & Moor Bank (fictional, DD/MM/YYYY example)", "Fenwick Joinery Ltd", "checking", "5129", "DD/MM/YYYY", "3912.60"),
]

MONEY_IN = ["SQUARE DEPOSIT", "STRIPE TRANSFER", "MOBILE CHECK DEPOSIT", "ACH CREDIT CLIENT PAYMENT", "WIRE IN CUSTOMER", "SHOPIFY PAYOUT", "INTEREST PAID", "CASH DEPOSIT BRANCH"]
MONEY_OUT = ["GUSTO PAYROLL", "ADP PAYROLL TAX", "COSTCO WHSE #0412", "AMAZON MKTPLACE PMTS", "COMCAST BUSINESS", "PG&E ONLINE PAYMENT", "SHELL OIL 57443", "STAPLES 01182", "INTUIT QUICKBOOKS", "CHECK 1043", "CHECK 1044", "RENT ACH LANDLORD LLC", "VERIZON WIRELESS", "UPS STORE 4417", "HOME DEPOT 6630", "MONTHLY SERVICE FEE", "ZELLE TO CONTRACTOR", "STATE FARM INSURANCE"]
CARD_OUT = ["UBER TRIP", "DELTA AIR LINES", "GOOGLE WORKSPACE", "ADOBE CREATIVE CLD", "WHOLE FOODS MKT", "OFFICE DEPOT", "PILOT TRAVEL CENTER", "ZOOM.US", "MARRIOTT HOTEL", "CHEVRON 0091"]
CARD_IN = ["PAYMENT THANK YOU", "RETURN OFFICE DEPOT", "STATEMENT CREDIT"]
MONTHS = [(2026, 7), (2026, 8), (2026, 9)]


def month_end(y, m):
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def money(rng, lo, hi):
    return Decimal(rng.randint(int(lo * 100), int(hi * 100))) / 100


def build_rows(rng, acct_type, y, m, opening):
    start, end = dt.date(y, m, 1), month_end(y, m)
    span = (end - start).days
    rows = []
    n = rng.randint(14, 30)
    if acct_type == "credit_card":
        # Pay the last statement in full around the 20th, plus a return now and then.
        rows.append((start + dt.timedelta(days=19), "PAYMENT THANK YOU", Decimal(opening)))
        for _ in range(n):
            day = start + dt.timedelta(days=rng.randint(0, span))
            if rng.random() < 0.06:
                rows.append((day, rng.choice(CARD_IN[1:]), money(rng, 10, 180)))
            else:
                rows.append((day, rng.choice(CARD_OUT), -money(rng, 4, 600)))
    elif acct_type == "savings":
        for _ in range(rng.randint(3, 7)):
            day = start + dt.timedelta(days=rng.randint(0, span))
            if rng.random() < 0.6:
                rows.append((day, "ONLINE TRANSFER FROM CHK 2256", money(rng, 500, 5000)))
            else:
                rows.append((day, "ONLINE TRANSFER TO CHK 2256", -money(rng, 500, 4000)))
        rows.append((end, "INTEREST PAID", (Decimal(opening) * Decimal("0.0025")).quantize(Decimal("0.01"))))
    else:
        for _ in range(n):
            day = start + dt.timedelta(days=rng.randint(0, span))
            if rng.random() < 0.35:
                rows.append((day, rng.choice(MONEY_IN), money(rng, 300, 6000)))
            else:
                rows.append((day, rng.choice(MONEY_OUT), -money(rng, 6, 2400)))
        closing = Decimal(opening) + sum(r[2] for r in rows)
        if closing < 2000:
            top_up = (Decimal(rng.randint(3000, 6000)) - closing).quantize(Decimal("1"))
            rows.append((start + dt.timedelta(days=14), "ONLINE TRANSFER FROM SAVINGS", top_up))
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows, start, end


def fmt_date(d, style):
    return d.strftime("%m/%d/%Y") if style == "MM/DD/YYYY" else d.strftime("%d/%m/%Y")


def write_csv(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\r\n")
        w.writerow(header)
        w.writerows(rows)


def main():
    rng = random.Random(20261105)
    for sub in ("3-column", "4-column", "statements", "invalid"):
        shutil.rmtree(os.path.join(OUT, sub), ignore_errors=True)
        os.makedirs(os.path.join(OUT, sub))
    index = []
    for slug, bank, biz, acct_type, last4, style, opening in ACCOUNTS:
        balance = Decimal(opening)
        for y, m in MONTHS:
            rows, start, end = build_rows(rng, acct_type, y, m, balance)
            net = sum(r[2] for r in rows)
            # Card balances are amounts owed: a charge (negative row) raises it.
            closing = balance - net if acct_type == "credit_card" else balance + net
            name = f"{slug}-{y}-{m:02d}"
            three = [[fmt_date(d, style), desc, f"{amt:.2f}"] for d, desc, amt in rows]
            four = [[fmt_date(d, style), desc, f"{amt:.2f}" if amt > 0 else "", f"{-amt:.2f}" if amt < 0 else ""] for d, desc, amt in rows]
            write_csv(os.path.join(OUT, "3-column", name + ".csv"), ["Date", "Description", "Amount"], three)
            write_csv(os.path.join(OUT, "4-column", name + ".csv"), ["Date", "Description", "Credit", "Debit"], four)
            side = {
                "bank": bank, "business": biz, "account_last4": last4, "account_type": acct_type,
                "period_start": start.isoformat(), "period_end": end.isoformat(),
                "opening_balance": f"{balance:.2f}", "closing_balance": f"{closing:.2f}",
                "transactions": len(rows), "date_format": style,
                "csv_files": [f"samples/3-column/{name}.csv", f"samples/4-column/{name}.csv"],
                "fictional": True,
            }
            with open(os.path.join(OUT, "statements", name + ".statement.json"), "w", encoding="utf-8") as fh:
                json.dump(side, fh, indent=2)
                fh.write("\n")
            index.append([name, bank, biz, acct_type, last4, start.isoformat(), end.isoformat(), f"{balance:.2f}", f"{closing:.2f}", len(rows), style])
            balance = closing
    write_csv(os.path.join(OUT, "index.csv"), ["sample", "bank", "business", "account_type", "account_last4", "period_start", "period_end", "opening_balance", "closing_balance", "transactions", "date_format"], index)
    make_invalid()
    print(f"{len(index)} statements, {len(index) * 2} valid CSVs")


def read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def make_invalid():
    base3 = read(os.path.join(OUT, "3-column", "harbor-point-checking-2026-07.csv"))
    base4 = read(os.path.join(OUT, "4-column", "harbor-point-checking-2026-07.csv"))
    cases = []

    def add(name, rows, rule, why, statement=None):
        write_csv(os.path.join(OUT, "invalid", name), rows[0], rows[1:])
        cases.append({"file": f"samples/invalid/{name}", "must_fail": rule, "what_is_wrong": why, "statement": statement})

    r = [row + ["4471"] for row in base3]; r[0][-1] = "Account"
    add("extra-balance-column.csv", r, "QBO-001", "a fourth Account column on a 3-column file")
    r = [list(x) for x in base4]; r[0] = ["Date", "Description", "Credit Amount", "Debit Amount"]
    add("amount-in-headers.csv", r, "QBO-002", "headers say Credit Amount and Debit Amount")
    r = [list(x) for x in base4]
    for row in r[1:]:
        row[2] = row[2] or "0.00"; row[3] = row[3] or "0.00"
    add("zeros-not-blank.csv", r, "QBO-003", "0.00 in the empty Credit or Debit cell")
    r = [list(x) for x in base3]
    d = dt.datetime.strptime(r[5][0], "%m/%d/%Y"); r[5][0] = d.strftime("%Y-%m-%d")
    add("mixed-date-formats.csv", r, "QBO-004", "one row in YYYY-MM-DD, the rest MM/DD/YYYY")
    r = [list(x) for x in base3]
    for row in r[1:]:
        row[0] = row[0] + " " + dt.datetime.strptime(row[0], "%m/%d/%Y").strftime("%a").upper()
    add("weekday-in-date.csv", r, "QBO-005", "dates like 07/02/2026 THU")
    big = [["Date", "Description", "Amount"]]
    rng = random.Random(7)
    for i in range(1200):
        big.append([f"07/{(i % 28) + 1:02d}/2026", f"POS PURCHASE STORE {i:04d} " + "X" * 260, f"-{rng.randint(100, 99999) / 100:.2f}"])
    add("too-big-and-too-long.csv", big, "QBO-006", "over 350 KB and over 1,000 lines (also fails QBO-007)")
    r = [list(x) for x in base3]
    for row in r[1:]:
        v = float(row[2]); row[2] = f"${abs(v):,.2f}" if v > 0 else f"(${abs(v):,.2f})"
    add("currency-symbols-and-parentheses.csv", r, "QBO-010", "amounts like $1,250.00 and ($612.30)")
    r = [list(x) for x in base4]
    r[3][2], r[3][3] = "10.00", r[3][3] or "10.00"
    add("both-credit-and-debit.csv", r, "QBO-011", "a row with both Credit and Debit filled")
    r = [list(x) for x in base3]; r[4][0] = "02/30/2026"
    add("impossible-date.csv", r, "QBO-012", "02/30/2026 does not exist")
    r = [list(x) for x in base3]; del r[6]
    add("missing-row.csv", r, "QBO-013", "one transaction dropped; rows no longer reach the printed closing balance",
        "samples/statements/harbor-point-checking-2026-07.statement.json")
    r = [list(x) for x in base3]; r.insert(1, ["07/01/2026", "Opening balance", "8214.37"])
    add("balance-line-as-transaction.csv", r, "QBO-015", "the opening balance line imported as a deposit")
    r = [list(x) for x in base3]; r[2][1] = "100432"
    add("number-as-description.csv", r, "QBO-009", "a description that is only a reference number (warning)")
    r = [list(x) for x in base3]; r.insert(3, list(r[2]))
    add("row-read-twice.csv", r, "QBO-014", "a row repeated, as when a page break is read twice (warning)")
    r = [list(x) for x in base3]
    for row in r[1:]:
        row[2] = f"{-float(row[2]):.2f}"
    add("signs-reversed.csv", r, "QBO-013", "every sign flipped, as some card exports do; balance proof catches it",
        "samples/statements/harbor-point-checking-2026-07.statement.json")
    with open(os.path.join(OUT, "invalid", "expected.json"), "w", encoding="utf-8") as fh:
        json.dump(cases, fh, indent=2)
        fh.write("\n")


if __name__ == "__main__":
    main()
