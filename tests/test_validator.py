import csv
import glob
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "cli"))
import qbo_csv_check as q  # noqa: E402


def errors(issues):
    return [i for i in issues if i.severity == "error"]


class ValidSamples(unittest.TestCase):
    def test_every_valid_sample_passes_and_ties(self):
        sides = sorted(glob.glob(os.path.join(ROOT, "samples", "statements", "*.statement.json")))
        self.assertEqual(len(sides), 24)
        for side in sides:
            st = json.load(open(side, encoding="utf-8"))
            for rel in st["csv_files"]:
                issues, summary = q.check(os.path.join(ROOT, rel), st)
                self.assertEqual(errors(issues), [], rel)
                self.assertEqual(summary["computed_closing"], st["closing_balance"], rel)

    def test_statements_chain_month_to_month(self):
        rows = list(csv.DictReader(open(os.path.join(ROOT, "samples", "index.csv"), encoding="utf-8")))
        by_acct = {}
        for r in rows:
            by_acct.setdefault(r["sample"].rsplit("-", 2)[0], []).append(r)
        for acct, months in by_acct.items():
            for a, b in zip(months, months[1:]):
                self.assertEqual(a["closing_balance"], b["opening_balance"], acct)

    def test_three_and_four_column_files_agree(self):
        for f3 in glob.glob(os.path.join(ROOT, "samples", "3-column", "*.csv")):
            f4 = f3.replace("3-column", "4-column")
            _, s3 = q.check(f3)
            _, s4 = q.check(f4)
            self.assertEqual(s3["net_change"], s4["net_change"], f3)
            self.assertEqual(s3["rows"], s4["rows"])


class InvalidSamples(unittest.TestCase):
    def test_each_invalid_sample_fails_its_rule(self):
        cases = json.load(open(os.path.join(ROOT, "samples", "invalid", "expected.json"), encoding="utf-8"))
        self.assertGreaterEqual(len(cases), 14)
        for c in cases:
            st = json.load(open(os.path.join(ROOT, c["statement"]), encoding="utf-8")) if c["statement"] else None
            issues, _ = q.check(os.path.join(ROOT, c["file"]), st)
            self.assertIn(c["must_fail"], {i.rule for i in issues}, c["file"])

    def test_fix_repairs_symbols_and_still_ties(self):
        src = os.path.join(ROOT, "samples", "invalid", "currency-symbols-and-parentheses.csv")
        st = json.load(open(os.path.join(ROOT, "samples", "statements", "harbor-point-checking-2026-07.statement.json")))
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "fixed.csv")
            q.fix(src, out)
            issues, _ = q.check(out, st)
            self.assertEqual(errors(issues), [])

    def test_fix_blanks_zeros(self):
        src = os.path.join(ROOT, "samples", "invalid", "zeros-not-blank.csv")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "fixed.csv")
            q.fix(src, out)
            self.assertEqual(errors(q.check(out)[0]), [])


class Rules(unittest.TestCase):
    def test_rules_file_lists_every_rule_the_validator_uses(self):
        ids = {r["rule_id"] for r in csv.DictReader(open(os.path.join(ROOT, "rules", "upload-rules.csv"), encoding="utf-8"))}
        src = open(os.path.join(ROOT, "cli", "qbo_csv_check.py"), encoding="utf-8").read()
        used = {f"QBO-{n:03d}" for n in range(1, 30) if f'"QBO-{n:03d}"' in src}
        self.assertEqual(used - ids, set())

    def test_cli_exit_codes(self):
        good = os.path.join(ROOT, "samples", "3-column", "lakeshore-checking-2026-08.csv")
        bad = os.path.join(ROOT, "samples", "invalid", "weekday-in-date.csv")
        self.assertEqual(q.main([good]), 0)
        self.assertEqual(q.main([bad]), 1)


if __name__ == "__main__":
    unittest.main()
