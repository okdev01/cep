import csv
from pathlib import Path
import tempfile
import unittest
from engine import Ledger, parse_amount, money


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.ledger=Ledger(self.root/"cep.db")

    def test_decimal_input_is_exact(self):
        self.assertEqual(parse_amount("0,29"),29)
        self.assertEqual(parse_amount("1250.50"),125050)
        self.assertEqual(money(-123456),"−1.234,56 ₺")

    def test_invalid_amounts(self):
        for value in ("0","-1","nan","inf","1e6","1.234,56","1,234","12.345","+10",""):
            with self.assertRaises(ValueError,msg=value): parse_amount(value)

    def test_month_boundaries_and_totals(self):
        self.ledger.add("2026-12-31","Gelir","Maaş","100,29")
        self.ledger.add("2026-12-31","Gider","Market","10,10")
        self.ledger.add("2027-01-01","Gider","Market","999")
        summary=self.ledger.summary("2026-12")
        self.assertEqual(summary["balance"],9019)
        self.assertEqual(summary["expense"],1010)

    def test_soft_delete_and_restore(self):
        identifier=self.ledger.add("2026-10-04","Gider","Ev","100")
        self.ledger.delete(identifier)
        self.assertEqual(self.ledger.entries("2026-10"),[])
        self.ledger.restore(identifier)
        self.assertEqual(len(self.ledger.entries("2026-10")),1)

    def test_budget_survives_restart(self):
        self.ledger.set_budget("2026-10","2000,50")
        self.assertEqual(Ledger(self.root/"cep.db").summary("2026-10")["budget"],200050)
        self.ledger.set_budget("2026-10","0")
        self.assertEqual(self.ledger.summary("2026-10")["budget"],0)

    def test_csv_formula_injection_and_precision(self):
        self.ledger.add("2026-10-04","Gider","Diğer","0,29","=HYPERLINK(\"bad\")")
        output=self.root/"export.csv"
        self.ledger.export_csv("2026-10",output)
        with output.open(encoding="utf-8-sig",newline="") as stream:
            rows=list(csv.reader(stream,delimiter=";"))
        self.assertEqual(rows[1][3],"0,29")
        self.assertTrue(rows[1][4].startswith("'="))
        with self.assertRaises(FileExistsError): self.ledger.export_csv("2026-10",output)

    def test_backup_reopens(self):
        self.ledger.add("2026-10-04","Gelir","Maaş","100")
        self.ledger.backup(self.root/"backup.db")
        self.assertEqual(Ledger(self.root/"backup.db").summary("2026-10")["income"],10000)

    def test_invalid_date_and_category(self):
        for day,cat in [("2026-02-30","Ev"),("2026-10-04","unknown")]:
            with self.assertRaises(ValueError): self.ledger.add(day,"Gider",cat,"10")


if __name__=="__main__": unittest.main()
