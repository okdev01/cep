import sys
from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFileDialog, QGridLayout,
    QHBoxLayout, QLineEdit, QProgressBar, QTableWidgetItem)

from desktop import Shell, button, label, metric, card, table, run
from engine import Ledger, CATEGORIES, money


class Window(Shell):
    def __init__(self,folder):
        super().__init__("Cep","Paran nereye gidiyor?\nBir bakışta gör.","Ayın resmi, elinin altında.",
                         "Gelir ve giderlerini kaydet. Bütçeni takip et. Her şey bu bilgisayarda.","Gelir & gider")
        self.folder=folder
        self.ledger=Ledger(folder/"cep.db")
        self.last_deleted=None
        self.rows=[]
        self.resize(1200,850)
        self.setMinimumSize(1080,790)
        metrics=QHBoxLayout()
        a,self.income=metric("GELİR","0,00 ₺")
        b,self.expense=metric("GİDER","0,00 ₺")
        c,self.balance=metric("AYLIK FARK","0,00 ₺")
        for item in (a,b,c): metrics.addWidget(item)
        self.body.addLayout(metrics)
        filters=QHBoxLayout()
        filters.addWidget(label("Görüntülenen ay","muted"))
        self.month=QDateEdit(QDate.currentDate())
        self.month.setDisplayFormat("MMMM yyyy")
        self.month.setCalendarPopup(True)
        self.month.dateChanged.connect(self.refresh)
        filters.addWidget(self.month)
        filters.addStretch()
        filters.addWidget(button("CSV dışa aktar",self.export_csv))
        filters.addWidget(button("Yedek al",self.backup))
        self.body.addLayout(filters)
        entry_card,entry_layout=card()
        fields=QGridLayout()
        self.day=QDateEdit(QDate.currentDate())
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat("dd.MM.yyyy")
        self.kind=QComboBox()
        self.kind.addItems(["Gider","Gelir"])
        self.category=QComboBox()
        self.category.addItems(CATEGORIES)
        self.category.setCurrentText("Market")
        self.amount=QLineEdit()
        self.amount.setPlaceholderText("1250,50")
        self.amount.setMaximumWidth(150)
        self.amount.setMaxLength(12)
        self.note=QLineEdit()
        self.note.setPlaceholderText("Kısa bir not (isteğe bağlı)")
        self.note.setMaxLength(300)
        for col,(name,field) in enumerate([("Tarih",self.day),("Tür",self.kind),("Kategori",self.category),("Tutar · TL",self.amount)]):
            fields.addWidget(label(name,"muted"),0,col)
            fields.addWidget(field,1,col)
        fields.addWidget(self.note,2,0,1,3)
        self.add_button=button("Kaydı ekle",self.add_entry,True)
        fields.addWidget(self.add_button,2,3)
        entry_layout.addLayout(fields)
        self.body.addWidget(entry_card)
        budget_row=QHBoxLayout()
        budget_row.addWidget(label("Aylık gider bütçesi","muted"))
        self.budget=QLineEdit()
        self.budget.setPlaceholderText("Örn. 20000")
        self.budget.setMaximumWidth(145)
        budget_row.addWidget(self.budget)
        budget_row.addWidget(button("Kaydet",self.save_budget))
        self.budget_bar=QProgressBar()
        self.budget_bar.setRange(0,100)
        self.budget_bar.setTextVisible(False)
        budget_row.addWidget(self.budget_bar,1)
        self.budget_text=label("Bütçe belirlenmedi","muted")
        budget_row.addWidget(self.budget_text)
        self.body.addLayout(budget_row)
        self.grid=table(["Tarih","Tür","Kategori","Tutar","Not"])
        self.body.addWidget(self.grid,1)
        actions=QHBoxLayout()
        actions.addWidget(button("Seçili kaydı kaldır",self.delete_entry))
        self.undo_button=button("Geri al",self.restore_entry)
        self.undo_button.setEnabled(False)
        actions.addWidget(self.undo_button)
        actions.addStretch()
        self.category_summary=label("Henüz kayıt yok","muted",True)
        actions.addWidget(self.category_summary)
        self.body.addLayout(actions)
        self.finish_layout()
        self.refresh()
        self.status.setText("Tutarı binlik ayırıcı olmadan yazın. Örnek: 1250,50")

    def selected_month(self):
        return self.month.date().toString("yyyy-MM")

    def refresh(self,*args):
        month=self.selected_month()
        self.rows=self.ledger.entries(month)
        summary=self.ledger.summary(month)
        self.income.setText(money(summary["income"]))
        self.expense.setText(money(summary["expense"]))
        self.balance.setText(money(summary["balance"]))
        self.grid.setRowCount(len(self.rows))
        for row,item in enumerate(self.rows):
            for col,text in enumerate([item["day"],item["kind"],item["category"],money(item["cents"]),item["note"]]):
                cell=QTableWidgetItem(text)
                cell.setToolTip(text)
                self.grid.setItem(row,col,cell)
        limit=summary["budget"]
        self.budget.setText(f"{limit//100},{limit%100:02d}" if limit else "")
        if limit:
            percentage=round(100*summary["expense"]/limit)
            self.budget_bar.setValue(min(100,percentage))
            self.budget_text.setText(f"%{percentage} kullanıldı")
        else:
            self.budget_bar.setValue(0)
            self.budget_text.setText("Bütçe belirlenmedi")
        categories=sorted(summary["categories"].items(),key=lambda item:item[1],reverse=True)
        self.category_summary.setText("En çok: " + " · ".join(k for k,v in categories[:2]) if categories else "Henüz gider yok")

    def add_entry(self):
        try:
            day=self.day.date().toString("yyyy-MM-dd")
            self.ledger.add(day,self.kind.currentText(),self.category.currentText(),self.amount.text(),self.note.text())
            self.month.setDate(self.day.date())
            self.amount.clear()
            self.note.clear()
            self.refresh()
            self.status.setText("Kayıt eklendi ve bilgisayarına kaydedildi.")
        except Exception as exc:
            self.status.setText("Kayıt eklenemedi: " + str(exc))

    def save_budget(self):
        try:
            self.ledger.set_budget(self.selected_month(),self.budget.text())
            self.refresh()
            self.status.setText("Aylık bütçe kaydedildi.")
        except Exception as exc:
            self.status.setText(str(exc))

    def delete_entry(self):
        row=self.grid.currentRow()
        if 0<=row<len(self.rows):
            self.last_deleted=self.rows[row]["id"]
            self.ledger.delete(self.last_deleted)
            self.undo_button.setEnabled(True)
            self.refresh()
            self.status.setText("Kayıt kaldırıldı. Geri al düğmesiyle geri getirebilirsin.")

    def restore_entry(self):
        if self.last_deleted is not None:
            self.ledger.restore(self.last_deleted)
            self.last_deleted=None
            self.undo_button.setEnabled(False)
            self.refresh()
            self.status.setText("Kayıt geri getirildi.")

    def export_csv(self):
        month=self.selected_month()
        path,_=QFileDialog.getSaveFileName(self,"CSV kaydet",f"Cep-{month}.csv","CSV (*.csv)")
        if path:
            try:
                self.ledger.export_csv(month,path)
                self.status.setText("CSV kaydedildi: " + path)
            except Exception as exc: self.show_error(str(exc))

    def backup(self):
        path,_=QFileDialog.getSaveFileName(self,"Yedek kaydet","Cep-yedek.db","Veritabanı (*.db)")
        if path:
            try:
                self.ledger.backup(path)
                self.status.setText("Yedek kaydedildi: " + path)
            except Exception as exc: self.show_error(str(exc))

    def seed_demo(self):
        today=date.today().isoformat()
        for kind,category,amount,note in [("Gelir","Maaş","45000","Aylık gelir"),("Gider","Ev","12000","Kira"),
            ("Gider","Market","1840,50","Haftalık alışveriş"),("Gider","Ulaşım","420","Ulaşım kartı"),
            ("Gider","Yemek","285","Öğle yemeği")]:
            self.ledger.add(today,kind,category,amount,note)
        self.ledger.set_budget(self.selected_month(),"25000")
        self.refresh()
        self.status.setText("Örnek görünüm · Tutarlar uygulama testi için oluşturulmuştur.")

    def smoke(self):
        before=len(self.rows)
        self.amount.setText("42,50")
        self.note.setText("Arayüz testi")
        self.add_button.click()
        assert len(self.rows)==before+1
        self.grid.selectRow(0)
        self.delete_entry()
        assert len(self.rows)==before
        self.restore_entry()
        assert len(self.rows)==before+1
        self.ledger.export_csv(self.selected_month(),self.folder/"smoke.csv")
        assert (self.folder/"smoke.csv").exists()
        return ["add ledger entry", "soft delete and undo", "monthly totals", "CSV export"]


if __name__=="__main__":
    sys.exit(run(Window,"Cep"))
