import unittest
from datetime import date

from finance_core import FinanceError, FinanceStore, amount_to_minor, minor_to_decimal_string


class FinanceCoreTests(unittest.TestCase):
    def setUp(self):
        self.store = FinanceStore(":memory:")
        self.wallet = self.store.create_wallet({
            "name": "Daily cash", "type": "cash", "currency": "EUR",
            "opening_balance": "100.00", "opening_date": "2026-01-01",
        })
        self.other = self.store.create_wallet({
            "name": "Reserve", "type": "savings", "currency": "EUR",
            "opening_balance": "0", "opening_date": "2026-01-01",
        })
        self.expense_category = next(c for c in self.store.list_categories() if c["name"] == "Food & dining")
        self.income_category = next(c for c in self.store.list_categories() if c["name"] == "Salary")

    def tearDown(self):
        self.store.close()

    def test_money_uses_currency_minor_units(self):
        self.assertEqual(amount_to_minor("19.23", "EUR"), 1923)
        self.assertEqual(amount_to_minor("19", "JPY"), 19)
        self.assertEqual(minor_to_decimal_string(1999, "EUR"), "19.99")
        with self.assertRaises(FinanceError):
            amount_to_minor("1.001", "EUR")
        with self.assertRaises(FinanceError):
            amount_to_minor("0", "EUR")
        with self.assertRaises(FinanceError):
            amount_to_minor("1", "XYZ")

    def test_opening_balance_and_income_expense_balance(self):
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"income","amount":"30.00",
            "transaction_date":"2026-01-15","category_id":self.income_category["id"]})
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"12.50",
            "transaction_date":"2026-01-16","category_id":self.expense_category["id"]})
        self.assertEqual(self.store.wallet_balance(self.wallet["id"]),11750)
        data=self.store.dashboard("2026-01-01","2026-01-31")
        summary=next(x for x in data["summary"] if x["currency"]=="EUR")
        self.assertEqual(summary["income_minor"],3000)
        self.assertEqual(summary["expense_minor"],1250)
        self.assertEqual(summary["net_minor"],1750)

    def test_transfer_has_atomic_linked_legs_and_is_excluded_from_net(self):
        transfer=self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.other["id"],
            "amount":"22.00","transaction_date":"2026-01-20"})
        self.assertEqual(self.store.wallet_balance(self.wallet["id"]),7800)
        self.assertEqual(self.store.wallet_balance(self.other["id"]),2200)
        tx=self.store.list_transactions({"type":"transfer"})["items"]
        self.assertEqual(len(tx),2)
        self.assertEqual(len({x["transfer_id"] for x in tx}),1)
        self.assertEqual(self.store.dashboard("2026-01-01","2026-01-31")["summary"],[])
        self.store.update_transfer(transfer["id"],{"amount":"25.00","transaction_date":"2026-01-21"})
        self.assertEqual(self.store.wallet_balance(self.wallet["id"]),7500)
        self.store.delete_transaction(tx[0]["id"])
        self.assertEqual(self.store.wallet_balance(self.wallet["id"]),10000)
        self.assertEqual(self.store.wallet_balance(self.other["id"]),0)

    def test_transfer_rejects_same_wallet_and_currency_mismatch(self):
        usd=self.store.create_wallet({"name":"US","type":"checking","currency":"USD","opening_balance":"0"})
        with self.assertRaises(FinanceError):
            self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.wallet["id"],"amount":"1","date":"2026-01-01"})
        with self.assertRaises(FinanceError):
            self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":usd["id"],"amount":"1","date":"2026-01-01"})

    def test_currency_change_blocked_after_ledger_entry(self):
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"1.00",
            "date":"2026-01-10","category_id":self.expense_category["id"]})
        with self.assertRaises(FinanceError):
            self.store.update_wallet(self.wallet["id"],{"name":"Daily cash","type":"cash","currency":"USD","opening_balance":"100","opening_date":"2026-01-01"})

    def test_category_archive_preserves_historical_assignment(self):
        tx=self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"4.00",
            "date":"2026-01-10","category_id":self.expense_category["id"]})
        self.store.update_category(self.expense_category["id"],{"name":self.expense_category["name"],"kind":"expense","archived":True})
        self.assertEqual(self.store.get_transaction(tx["id"])["category_id"],self.expense_category["id"])
        with self.assertRaises(FinanceError):
            self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"1.00",
                "date":"2026-01-11","category_id":self.expense_category["id"]})

    def test_budget_uses_inclusive_dates_expenses_only_and_currency(self):
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"10.00",
            "date":"2026-01-01","category_id":self.expense_category["id"]})
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"income","amount":"50.00",
            "date":"2026-01-31","category_id":self.income_category["id"]})
        self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.other["id"],
            "amount":"7.00","date":"2026-01-31"})
        budget=self.store.create_budget({"name":"January food","period":"monthly","start_date":"2026-01-01",
            "end_date":"2026-01-31","amount":"25.00","currency":"EUR","scope":"category","category_id":self.expense_category["id"]})
        self.assertEqual(budget["spent_minor"],1000)
        self.assertEqual(budget["remaining_minor"],1500)

    def test_monthly_budget_default_end_is_month_end(self):
        budget=self.store.create_budget({"name":"Monthly","start_date":"2026-02-01","amount":"100.00","currency":"EUR"})
        self.assertEqual(budget["end_date"],"2026-02-28")

    def test_soft_delete_keeps_transaction_row_and_updates_balance(self):
        tx=self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"3.00","date":"2026-01-10"})
        self.store.delete_transaction(tx["id"])
        self.assertEqual(self.store.wallet_balance(self.wallet["id"]),10000)
        self.assertEqual(self.store.list_transactions()["total"],0)
        self.assertIsNotNone(self.store.conn.execute("SELECT deleted_at FROM transactions WHERE id=?",(tx["id"],)).fetchone()["deleted_at"])

    def test_import_stays_staged_until_confirmed_and_cancel_clears_rows(self):
        staged=self.store.begin_import("csv_import",[{
            "date":"2026-03-04","type":"expense","amount":"8.20","currency":"EUR",
            "wallet_id":self.wallet["id"],"category_id":self.expense_category["id"],"description":"Synthetic fixture"
        }])
        self.assertEqual(self.store.list_transactions()["total"],0)
        self.assertEqual(staged["accepted_count"],1)
        result=self.store.commit_import(staged["batch_id"],[{"id":staged["rows"][0]["id"],"accepted":True}])
        self.assertEqual(result["accepted_count"],1)
        self.assertEqual(self.store.list_transactions()["total"],1)
        cancelled=self.store.begin_import("csv_import",[{"date":"bad","amount":"x","currency":"EUR"}])
        self.store.cancel_import(cancelled["batch_id"])
        self.assertEqual(self.store.get_import(cancelled["batch_id"])["rows"],[])

    def test_restore_preview_and_atomic_merge(self):
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"5.00","date":"2026-01-10"})
        payload=self.store.backup_payload()
        other=FinanceStore(":memory:")
        try:
            preview=other.preview_restore(payload)
            self.assertGreater(preview["total"],0)
            result=other.restore_payload(payload,"merge")
            self.assertEqual(result["inserted"]["transactions"],1)
            again=other.restore_payload(payload,"merge")
            self.assertEqual(again["inserted"]["transactions"],0)
            self.assertEqual(other.wallet_balance(self.wallet["id"]),9500)
        finally:
            other.close()

    def test_idempotency_key_replays_one_transaction_and_rejects_changed_payload(self):
        data={"wallet_id":self.wallet["id"],"type":"expense","amount":"4.50",
              "transaction_date":"2026-04-02","category_id":self.expense_category["id"]}
        def save():
            with self.store._write() as c:
                return self.store.idempotent_execute(c,"test-idempotency-key-001","transaction.create",data,
                    lambda conn:self.store.create_transaction(data,c=conn),
                    lambda conn,rid:self.store.get_transaction(rid,conn))
        first=save();second=save()
        self.assertEqual(first["id"],second["id"])
        self.assertEqual(self.store.list_transactions()["total"],1)
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) n FROM transactions WHERE deleted_at IS NULL").fetchone()["n"],1)
        changed=dict(data,amount="5.00")
        with self.store._write() as c:
            with self.assertRaises(FinanceError):
                self.store.idempotent_execute(c,"test-idempotency-key-001","transaction.create",changed,
                    lambda conn:self.store.create_transaction(changed,c=conn),
                    lambda conn,rid:self.store.get_transaction(rid,conn))

    def test_category_parent_is_one_level_and_kind_compatible(self):
        parent=self.store.create_category({"name":"Household","kind":"expense"})
        child=self.store.create_category({"name":"Supplies","kind":"expense","parent_id":parent["id"]})
        self.assertEqual(child["parent_id"],parent["id"])
        with self.assertRaises(FinanceError):
            self.store.create_category({"name":"Nested","kind":"expense","parent_id":child["id"]})
        income=self.store.create_category({"name":"Bonus","kind":"income"})
        with self.assertRaises(FinanceError):
            self.store.create_category({"name":"Wrong parent kind","kind":"expense","parent_id":income["id"]})


if __name__=="__main__":
    unittest.main()
