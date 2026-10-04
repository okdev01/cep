"""Personal ledger: integer cents, explicit dates, CSV-safe exports."""
from contextlib import contextmanager
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import sqlite3

CATEGORIES = ["Maaş", "Ek gelir", "Market", "Yemek", "Ulaşım", "Ev", "Faturalar", "Sağlık", "Eğlence", "Diğer"]


def parse_amount(value):
    text = str(value).strip()
    if not re.fullmatch(r"\d{1,9}(?:[,.]\d{1,2})?", text):
        raise ValueError("Tutarı binlik ayırıcı olmadan yazın: 1250,50")
    try:
        amount = Decimal(text.replace(",", "."))
        if not amount.is_finite() or amount <= 0:
            raise ValueError("Tutar sıfırdan büyük olmalı")
        return int(amount * 100)
    except InvalidOperation:
        raise ValueError("Geçersiz tutar") from None


def money(cents):
    sign = "−" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{whole:,}".replace(",", ".") + f",{fraction:02d} ₺"


def csv_safe(text):
    value = str(text)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else value


class Ledger:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS entries (
                    id INTEGER PRIMARY KEY,day TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('Gelir','Gider')),
                    category TEXT NOT NULL,cents INTEGER NOT NULL CHECK(cents>0),note TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS entries_day ON entries(day,deleted);
                CREATE TABLE IF NOT EXISTS budgets (month TEXT PRIMARY KEY,cents INTEGER NOT NULL CHECK(cents>=0));
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, day, kind, category, amount, note=""):
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day or kind not in ("Gelir", "Gider") or category not in CATEGORIES:
            raise ValueError("Geçersiz tarih, tür veya kategori")
        if len(note) > 300:
            raise ValueError("Not en fazla 300 karakter olabilir")
        cents = parse_amount(amount)
        with self.db() as db:
            return db.execute("INSERT INTO entries(day,kind,category,cents,note) VALUES (?,?,?,?,?)",
                              (day, kind, category, cents, note.strip())).lastrowid

    @staticmethod
    def month_bounds(month):
        start = date.fromisoformat(month + "-01")
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        return start.isoformat(), end.isoformat()

    def entries(self, month):
        start, end = self.month_bounds(month)
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM entries WHERE day>=? AND day<? AND deleted=0 ORDER BY day DESC,id DESC", (start, end))]

    def delete(self, identifier):
        with self.db() as db:
            db.execute("UPDATE entries SET deleted=1 WHERE id=?", (identifier,))

    def restore(self, identifier):
        with self.db() as db:
            db.execute("UPDATE entries SET deleted=0 WHERE id=?", (identifier,))

    def set_budget(self, month, amount):
        self.month_bounds(month)
        cents = 0 if str(amount).strip() in ("", "0", "0,00", "0.00") else parse_amount(amount)
        with self.db() as db:
            db.execute("INSERT INTO budgets VALUES (?,?) ON CONFLICT(month) DO UPDATE SET cents=excluded.cents", (month, cents))

    def summary(self, month):
        rows = self.entries(month)
        income = sum(r["cents"] for r in rows if r["kind"] == "Gelir")
        expense = sum(r["cents"] for r in rows if r["kind"] == "Gider")
        categories = {}
        for row in rows:
            if row["kind"] == "Gider":
                categories[row["category"]] = categories.get(row["category"], 0) + row["cents"]
        with self.db() as db:
            row = db.execute("SELECT cents FROM budgets WHERE month=?", (month,)).fetchone()
        return {"income": income, "expense": expense, "balance": income-expense,
                "budget": row[0] if row else 0, "categories": categories}

    def export_csv(self, month, destination):
        if Path(destination).exists():
            raise FileExistsError("Dosya zaten var; farklı bir ad seçin")
        with open(destination, "x", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Tarih", "Tür", "Kategori", "Tutar (TL)", "Not"])
            for row in self.entries(month):
                writer.writerow([row["day"], row["kind"], row["category"],
                                 f'{row["cents"]//100},{row["cents"]%100:02d}', csv_safe(row["note"])])

    def backup(self, destination):
        if Path(destination).resolve() == Path(self.path).resolve() or Path(destination).exists():
            raise ValueError("Yedek için yeni bir dosya adı seçin")
        with self.db() as source:
            target = sqlite3.connect(str(destination))
            try:
                source.backup(target)
            finally:
                target.close()
