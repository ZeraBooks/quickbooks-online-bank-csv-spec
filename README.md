# QuickBooks Online bank CSV spec

QuickBooks Online takes a bank CSV in one of two layouts: 3 columns (Date, Description, Amount, with money out as a minus) or 4 columns (Date, Description, Credit, Debit). The file must be 350 KB or less with up to 1,000 lines, use one date format, and leave empty cells blank instead of 0. If you are starting from a PDF statement, [ZeraBooks](https://www.zerabooks.com/pdf-to-qbo-converter) reads it, proves every account against the printed opening and closing balances, and downloads a QuickBooks-ready CSV in the 3-column layout.

This repo is the long version of that answer: the two layouts as JSON Schema, every upload rule with its source, 48 fictional sample files that pass, 14 that fail on purpose, and a small Python checker you can run on your own file before you upload it.

- Spec and rules: [`schema/`](schema/), [`rules/upload-rules.csv`](rules/upload-rules.csv)
- Samples: [`samples/`](samples/) (all fictional)
- Checker: [`cli/qbo_csv_check.py`](cli/qbo_csv_check.py) (Python 3.8+, no installs)
- Download everything: [latest release zip](https://github.com/ZeraBooks/quickbooks-online-bank-csv-spec/releases/latest)

## The two layouts

**3-column.** One signed amount. Payments are negative, deposits positive.

```csv
Date,Description,Amount
07/02/2026,SQUARE DEPOSIT,1250.00
07/03/2026,COSTCO WHSE #0412,-612.30
07/31/2026,MONTHLY SERVICE FEE,-15.00
```

**4-column.** Two positive columns. Credit is money in, Debit is money out. Each row fills one of them and leaves the other blank.

```csv
Date,Description,Credit,Debit
07/02/2026,SQUARE DEPOSIT,1250.00,
07/03/2026,COSTCO WHSE #0412,,612.30
07/31/2026,MONTHLY SERVICE FEE,,15.00
```

Column order matters. A Balance, Reference or Account column on the end is the most common reason a file that looks fine won't map.

## The rules QuickBooks Online rejects files for

Each rule has an ID the checker prints. Rules marked Intuit come from Intuit's own help articles, read on November 5, 2026 (links in [`rules/upload-rules.csv`](rules/upload-rules.csv)). Rules marked spec are this spec's additions: QuickBooks would take the file, but your books would be wrong.

| ID | Rule | Source |
|---|---|---|
| QBO-001 | Exactly 3 or exactly 4 columns, in the order above | Intuit |
| QBO-002 | 4-column headers read `Credit` and `Debit`, not `Credit Amount` | Intuit |
| QBO-003 | No zeros. Leave the cell blank | Intuit |
| QBO-004 | One date format for the whole file | Intuit |
| QBO-005 | No weekday text in the date cell (`07/02/2026 THU`) | Intuit |
| QBO-006 | File is 350 KB or less | Intuit |
| QBO-007 | 1,000 transaction lines or fewer per upload | Intuit |
| QBO-008 | 3-column: money out negative, money in positive | Intuit |
| QBO-009 | Description is text, not only a number (warning) | Intuit |
| QBO-010 | Amounts are plain numbers: no `$`, no thousands commas, no `(12.00)`, no `CR` | spec |
| QBO-011 | 4-column: exactly one of Credit or Debit per row | spec |
| QBO-012 | Every date is real and inside the statement period | spec |
| QBO-013 | Opening balance + rows = printed closing balance | spec |
| QBO-014 | Same date, description and amount twice (warning) | spec |
| QBO-015 | No balance or total lines as transactions | spec |

QBO-013 is the one that matters most and the one QuickBooks can't check for you. It imports whatever rows you give it. A row dropped at a page break, or a card export with every sign flipped, goes in without complaint and shows up weeks later as a reconciliation that is off by an amount nobody can find.

## Check a file

```bash
python3 cli/qbo_csv_check.py my-statement.csv
```

Add the printed balances to prove the rows add up. Here is `samples/invalid/missing-row.csv`, a July statement with one $608.16 row dropped. Write a small JSON file like the ones in [`samples/statements/`](samples/statements/):

```json
{"bank": "Your bank", "account_last4": "1234", "account_type": "checking",
 "period_start": "2026-07-01", "period_end": "2026-07-31",
 "opening_balance": "8214.37", "closing_balance": "9771.44",
 "date_format": "MM/DD/YYYY", "csv_files": ["my-statement.csv"]}
```

```bash
python3 cli/qbo_csv_check.py my-statement.csv --statement my-statement.statement.json
```

```
ERROR   QBO-013 file: opening 8214.37 + rows 2165.23 = 10379.60, but the statement prints 9771.44 (off by -608.16)
```

`--fix cleaned.csv` writes a copy with `$`, thousands commas, parentheses, zeros, weekday text and balance lines taken out, then checks the copy. It never changes dates or guesses at a missing row. `--json` prints the result for scripts. The exit code is 0 when there are no errors, 1 when there are, and 2 when the file can't be read.

For credit card accounts, set `"account_type": "credit_card"`. The balances are amounts owed, so a charge (a negative row) raises the balance and a payment lowers it.

## Samples

All banks, businesses and amounts are made up. `scripts/generate_samples.py` writes them from a fixed seed, so you get the same files every time.

| Folder | Files | What they are |
|---|---|---|
| `samples/3-column/` | 24 | Three months (July to September 2026) for 8 fictional accounts: 5 checking (one in DD/MM/YYYY), 1 savings, 2 credit cards. |
| `samples/4-column/` | 24 | The same statements in the 4-column layout. |
| `samples/statements/` | 24 | The printed opening and closing balance for each. Each month's closing is the next month's opening. |
| `samples/invalid/` | 14 | One broken file per rule, plus `expected.json` naming the rule each must fail. |
| `samples/index.csv` | 1 | One row per statement. |

## Coming from a PDF statement

Most bank CSV trouble starts with a PDF. Copying rows out of a PDF loses minus signs, splits wrapped descriptions into two rows and picks up the balance line as a transaction.

[ZeraBooks Convert](https://www.zerabooks.com/pdf-to-qbo-converter) reads the PDF (up to 500 pages per file), checks each account against the opening, running and closing balances printed on it, and only marks a statement Proven when it ties to the cent. The **QuickBooks-ready** download writes this repo's 3-column layout with US dates (MM/DD/YYYY), which you then upload in QuickBooks Online's bank transactions screen. It writes CSV and Excel files, not .qbo files, and it doesn't connect to QuickBooks. Pricing is on [zerabooks.com/pricing](https://www.zerabooks.com/pricing): one plan with 1,000 pages a month, $79 a month billed annually or $149 month to month, with a 7-day trial.

Whatever tool makes your CSV, run the checker on it first. It takes a second.

## Run the tests

```bash
python3 scripts/generate_samples.py
python3 -m unittest discover -s tests -v
```

## Files

- `MANIFEST.json` lists every data file with its size, row count and SHA-256. `checksums.txt` has the same hashes in `sha256sum` format: `shasum -a 256 -c checksums.txt`.
- `scripts/build_manifest.py` and `scripts/package_release.py` rebuild those and the release zip.

## License and citation

Code is MIT ([`LICENSE`](LICENSE)). Samples, schemas, rules and docs are CC BY 4.0 ([`LICENSE-SAMPLES`](LICENSE-SAMPLES)). Cite it with [`CITATION.cff`](CITATION.cff) or as: ZeraBooks, *QuickBooks Online Bank CSV Spec*, v1.0.0, 2026, https://github.com/ZeraBooks/quickbooks-online-bank-csv-spec.

QuickBooks is a trademark of Intuit Inc. This project is not made by or affiliated with Intuit. Intuit can change its upload rules; each rule's check date is in the rules file.
