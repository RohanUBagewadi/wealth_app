import unittest
import csv
import io
import json
import sqlite3
import os
import tempfile
from copy import deepcopy
from unittest.mock import patch
from datetime import date

from finance_core import FinanceError, FinanceStore, amount_to_minor, formula_safe_csv_cell, minor_to_decimal_string


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

    def test_wallet_opening_balance_allows_zero_and_negative_values(self):
        zero = self.store.create_wallet({
            "name": "Synthetic zero opening wallet", "type": "cash", "currency": "EUR",
            "opening_balance": "0", "opening_date": "2026-01-01",
        })
        negative = self.store.create_wallet({
            "name": "Synthetic credit opening wallet", "type": "credit", "currency": "EUR",
            "opening_balance": "-12.34", "opening_date": "2026-01-01",
        })
        self.assertEqual(zero["opening_balance_minor"], 0)
        self.assertEqual(negative["opening_balance_minor"], -1234)

    def test_csv_formula_protection_covers_user_controlled_columns(self):
        wallet=self.store.create_wallet({"name":"=HYPERLINK(\"x\")","type":"cash","currency":"EUR","opening_balance":"0"})
        category=self.store.create_category({"name":"@SUM(1,1)","kind":"expense"})
        self.store.create_transaction({"wallet_id":wallet["id"],"type":"expense","amount":"1.00",
            "date":"2026-01-02","category_id":category["id"],"description":"  +cmd","notes":"=1+1"})
        self.store.create_transaction({"wallet_id":wallet["id"],"type":"expense","amount":"1.00",
            "date":"2026-01-03","category_id":category["id"],"description":"ordinary, \"quoted\"\nsecond line"})
        exported=self.store.export_csv()
        rows=list(csv.reader(io.StringIO(exported,newline="")))
        by_date={row[0]:row for row in rows[1:]}
        self.assertEqual(by_date["2026-01-02"][4],"'=HYPERLINK(\"x\")")
        self.assertEqual(by_date["2026-01-02"][5],"'@SUM(1,1)")
        self.assertEqual(by_date["2026-01-02"][6],"'+cmd")
        self.assertEqual(by_date["2026-01-02"][7],"'=1+1")
        self.assertEqual(by_date["2026-01-03"][6],"ordinary, \"quoted\"\nsecond line")
        self.assertEqual(formula_safe_csv_cell(None),"")
        self.assertEqual(formula_safe_csv_cell("ordinary text"),"ordinary text")
        self.assertEqual(formula_safe_csv_cell(" \t=1+1"),"' \t=1+1")

    def test_csv_export_applies_formula_protection_to_every_column(self):
        row={"transaction_date":"@date","type":"=income","amount_minor":1250,"currency":"EUR",
             "wallet_name":"+wallet","category_name":"-category","description":"=description","notes":"@notes"}
        with patch.object(self.store,"list_transactions",return_value={"total":1,"items":[row]}):
            output=self.store.export_csv()
        reader=csv.reader(io.StringIO(output,newline=""))
        cells=next(reader)
        self.assertEqual(cells,["transaction_date","type","amount","currency","wallet","category","description","notes"])
        values=next(reader)
        self.assertEqual(values,["'@date","'=income","12.50","EUR","'+wallet","'-category","'=description","'@notes"])

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

    def test_backup_snapshot_json_size_boundary(self):
        payload=self.store.backup_payload()
        encoded=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.store.backup_payload(max_bytes=len(encoded)),payload)
        with self.assertRaisesRegex(FinanceError,"snapshot test limit"):
            self.store.backup_payload(max_bytes=len(encoded)-1,size_error="Backup exceeds the snapshot test limit.")

    def test_backup_snapshot_stops_fetching_rows_after_bound_is_exceeded(self):
        for index in range(30):
            self.store.create_wallet({"name":"Synthetic bounded wallet {}".format(index),"type":"cash",
                "currency":"EUR","opening_balance":"0"})
        full=self.store.backup_payload()
        partial=deepcopy(full)
        partial["data"]["wallets"]=partial["data"]["wallets"][:1]
        limit=len(json.dumps(partial,separators=(",",":"),ensure_ascii=False).encode("utf-8"))
        original=self.store.conn

        fetched_by_table={}

        class CountingCursor:
            def __init__(self,cursor,table):
                self.cursor=cursor
                self.table=table
            def __iter__(self):
                return self
            def __next__(self):
                row=next(self.cursor)
                fetched_by_table[self.table]=fetched_by_table.get(self.table,0)+1
                return row

        class CountingConnection:
            def execute(self,*args,**kwargs):
                table=args[0].split("FROM ",1)[1].split()[0]
                return CountingCursor(original.execute(*args,**kwargs),table)
            def __getattr__(self,name):
                return getattr(original,name)

        try:
            self.store.conn=CountingConnection()
            with self.assertRaisesRegex(FinanceError,"snapshot test limit"):
                self.store.backup_payload(max_bytes=limit,size_error="Backup exceeds the snapshot test limit.")
        finally:
            self.store.conn=original
        wallet_total=original.execute("SELECT COUNT(*) FROM wallets WHERE owner_id='local'").fetchone()[0]
        self.assertGreater(fetched_by_table.get("wallets",0),1)
        self.assertLess(fetched_by_table.get("wallets",0),wallet_total)
        self.assertEqual(sum(fetched_by_table.values()),fetched_by_table["wallets"])

    def test_failed_replace_restore_keeps_existing_data(self):
        payload=self.store.backup_payload()
        before=self.store.list_wallets()
        self.store.conn.execute("""CREATE TRIGGER synthetic_restore_failure BEFORE INSERT ON wallets
            BEGIN SELECT RAISE(ABORT,'synthetic failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.restore_payload(payload,"replace")
        self.assertEqual(self.store.list_wallets(),before)

    def test_restore_preview_rejects_missing_required_fields(self):
        payload=self.store.backup_payload()
        payload["data"]["wallets"][0]["name"]=None
        before=self.store.list_wallets()
        with self.assertRaisesRegex(FinanceError,"invalid record"):
            self.store.restore_payload(payload,"replace")
        self.assertEqual(self.store.list_wallets(),before)

    def _restore_snapshot(self):
        return deepcopy(self.store.backup_payload()["data"])

    def test_restore_rejects_malformed_record_fields_without_writes(self):
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"5.00",
            "date":"2026-01-10","category_id":self.expense_category["id"]})
        self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.other["id"],
            "amount":"2.00","date":"2026-01-11"})
        self.store.create_budget({"name":"Synthetic food budget","period":"monthly","start_date":"2026-01-01",
            "end_date":"2026-01-31","amount":"50.00","currency":"EUR","scope":"category",
            "category_id":self.expense_category["id"]})
        base=self.store.backup_payload()
        bad_payloads=[]

        def bad(label,mutate):
            value=deepcopy(base);mutate(value);bad_payloads.append((label,value))

        bad("wrong record type",lambda p:p["data"]["wallets"].__setitem__(0,[]))
        bad("missing required field",lambda p:p["data"]["wallets"][0].pop("name"))
        bad("unexpected field",lambda p:p["data"]["wallets"][0].__setitem__("unexpected",1))
        bad("malformed id",lambda p:p["data"]["wallets"][0].__setitem__("id","not-a-uuid"))
        bad("duplicate id",lambda p:p["data"]["wallets"].append(deepcopy(p["data"]["wallets"][0])))
        bad("invalid enum",lambda p:p["data"]["wallets"][0].__setitem__("type","crypto"))
        bad("invalid numeric type",lambda p:p["data"]["transactions"][0].__setitem__("amount_minor",True))
        bad("amount outside domain range",lambda p:p["data"]["transactions"][0].__setitem__("amount_minor",10**15+1))
        bad("opening balance outside domain range",lambda p:p["data"]["wallets"][0].__setitem__("opening_balance_minor",10**15+1))
        bad("invalid date",lambda p:p["data"]["transactions"][0].__setitem__("transaction_date","2026-02-30"))
        bad("invalid tag structure",lambda p:p["data"]["transactions"][0].__setitem__("tags",'{"unexpected":true}'))
        bad("invalid budget amount",lambda p:p["data"]["budgets"][0].__setitem__("amount_minor",0))
        bad("invalid timestamp",lambda p:p["data"]["wallets"][0].__setitem__("created_at","not-a-timestamp"))
        bad("invalid currency",lambda p:p["data"]["wallets"][0].__setitem__("currency","EUR;"))
        bad("invalid CSS color",lambda p:p["data"]["categories"][0].__setitem__("color","url(javascript:alert(1))"))
        bad("invalid parent id",lambda p:p["data"]["categories"][0].__setitem__("parent_id","missing-parent"))

        for label,payload in bad_payloads:
            for mode in ("merge","replace"):
                with self.subTest(case=label,mode=mode):
                    before=self._restore_snapshot()
                    with self.assertRaises(FinanceError):
                        self.store.restore_payload(payload,mode)
                    self.assertEqual(self._restore_snapshot(),before)

    def test_restore_rejects_incompatible_dangling_and_transfer_references(self):
        parent=self.store.create_category({"name":"Synthetic parent category","kind":"expense"})
        child=self.store.create_category({"name":"Synthetic child category","kind":"expense","parent_id":parent["id"]})
        income_parent=self.store.create_category({"name":"Synthetic income parent","kind":"income"})
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"5.00",
            "date":"2026-01-10","category_id":self.expense_category["id"]})
        self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.other["id"],
            "amount":"2.00","date":"2026-01-11"})
        self.store.create_budget({"name":"Synthetic category budget","period":"custom","start_date":"2026-01-01",
            "end_date":"2026-01-31","amount":"50.00","currency":"EUR","scope":"category",
            "category_id":self.expense_category["id"]})
        base=self.store.backup_payload()
        income_category=next(c for c in base["data"]["categories"] if c["kind"]=="income")
        bad_payloads=[]
        bad_parent=deepcopy(base)
        next(c for c in bad_parent["data"]["categories"] if c["id"]==child["id"])["parent_id"]=child["id"]
        bad_payloads.append(("nested or self parent",bad_parent))
        bad_kind=deepcopy(base)
        next(c for c in bad_kind["data"]["categories"] if c["id"]==child["id"])["parent_id"]=income_parent["id"]
        bad_payloads.append(("incompatible parent kind",bad_kind))
        for label,table,index,key,value in (
            ("dangling wallet","transactions",0,"wallet_id","00000000-0000-4000-8000-000000000001"),
            ("category kind mismatch","transactions",0,"category_id",income_category["id"]),
            ("dangling budget wallet","budgets",0,"wallet_id","00000000-0000-4000-8000-000000000001"),
            ("budget category kind mismatch","budgets",0,"category_id",income_category["id"]),
            ("transfer source and destination same","transfers",0,"destination_wallet_id",self.wallet["id"]),
            ("transfer currency mismatch","transfers",0,"currency","USD"),
        ):
            value_payload=deepcopy(base);value_payload["data"][table][index][key]=value;bad_payloads.append((label,value_payload))
        bad_legs=deepcopy(base);bad_legs["data"]["transactions"]=[t for t in bad_legs["data"]["transactions"] if t["transfer_id"] is None or t["transfer_side"]!="in"]
        bad_payloads.append(("missing transfer leg",bad_legs))
        for label,payload in bad_payloads:
            with self.subTest(case=label):
                before=self._restore_snapshot()
                with self.assertRaises(FinanceError):
                    self.store.restore_payload(payload,"replace")
                self.assertEqual(self._restore_snapshot(),before)

    def test_restore_handles_child_before_parent_and_signed_opening_balances(self):
        parent=self.store.create_category({"name":"Synthetic parent","kind":"expense"})
        child=self.store.create_category({"name":"Synthetic child","kind":"expense","parent_id":parent["id"]})
        zero=self.store.create_wallet({"name":"Synthetic zero balance","type":"cash","currency":"EUR","opening_balance":"0"})
        negative=self.store.create_wallet({"name":"Synthetic negative balance","type":"credit","currency":"EUR","opening_balance":"-12.34"})
        payload=self.store.backup_payload()
        category_rows=payload["data"]["categories"]
        child_row=next(row for row in category_rows if row["id"]==child["id"])
        parent_row=next(row for row in category_rows if row["id"]==parent["id"])
        category_rows.remove(child_row);category_rows.remove(parent_row)
        category_rows.extend((child_row,parent_row))
        other=FinanceStore(":memory:")
        try:
            other.restore_payload(payload,"replace")
            restored_child=next(c for c in other.list_categories() if c["id"]==child["id"])
            self.assertEqual(restored_child["parent_id"],parent["id"])
            self.assertEqual(next(w for w in other.list_wallets() if w["id"]==zero["id"])["opening_balance_minor"],0)
            self.assertEqual(next(w for w in other.list_wallets() if w["id"]==negative["id"])["opening_balance_minor"],-1234)
        finally:
            other.close()

    def test_valid_backup_replace_restores_all_relationship_types(self):
        parent=self.store.create_category({"name":"Synthetic valid parent","kind":"expense"})
        child=self.store.create_category({"name":"Synthetic valid child","kind":"expense","parent_id":parent["id"]})
        self.store.create_transaction({"wallet_id":self.wallet["id"],"type":"expense","amount":"3.50",
            "date":"2026-01-10","category_id":child["id"],"tags":["synthetic"]})
        transfer=self.store.create_transfer({"source_wallet_id":self.wallet["id"],"destination_wallet_id":self.other["id"],
            "amount":"2.00","date":"2026-01-11"})
        self.store.create_budget({"name":"Synthetic category budget","period":"monthly","start_date":"2026-01-01",
            "end_date":"2026-01-31","amount":"50.00","currency":"EUR","scope":"category","category_id":child["id"]})
        self.store.create_budget({"name":"Synthetic wallet budget","period":"custom","start_date":"2026-01-01",
            "end_date":"2026-01-31","amount":"60.00","currency":"EUR","scope":"wallet","wallet_id":self.wallet["id"]})
        payload=self.store.backup_payload()
        target=FinanceStore(":memory:")
        try:
            preview=target.preview_restore(payload)
            result=target.restore_payload(payload,"replace")
            self.assertEqual(result["mode"],"replace")
            self.assertEqual(result["preview"],preview)
            self.assertEqual(target.conn.execute("PRAGMA foreign_key_check").fetchall(),[])
            self.assertEqual(target.conn.execute("SELECT COUNT(*) FROM transfers WHERE id=?",(transfer["id"],)).fetchone()[0],1)
            self.assertEqual(target.conn.execute("SELECT COUNT(*) FROM transactions WHERE transfer_id=?",(transfer["id"],)).fetchone()[0],2)
            self.assertEqual(target.conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0],2)
            restored_child=next(c for c in target.list_categories() if c["id"]==child["id"])
            self.assertEqual(restored_child["parent_id"],parent["id"])
        finally:
            target.close()

    def test_failed_merge_and_replace_roll_back_all_inserted_records(self):
        source=FinanceStore(":memory:")
        try:
            source_wallet=source.create_wallet({"name":"Synthetic donor wallet","type":"cash","currency":"EUR","opening_balance":"0"})
            source.create_transaction({"wallet_id":source_wallet["id"],"type":"expense","amount":"1.00","date":"2026-01-02"})
            payload=source.backup_payload()
        finally:
            source.close()
        self.store.conn.execute("""CREATE TRIGGER synthetic_transaction_restore_failure BEFORE INSERT ON transactions
            BEGIN SELECT RAISE(ABORT,'synthetic restore failure'); END""")
        for mode in ("merge","replace"):
            with self.subTest(mode=mode):
                before=self._restore_snapshot()
                with self.assertRaises(sqlite3.IntegrityError):
                    self.store.restore_payload(payload,mode)
                self.assertEqual(self._restore_snapshot(),before)

    def test_merge_keeps_conflicting_id_values_and_inserts_new_ids(self):
        payload=self.store.backup_payload()
        target=FinanceStore(":memory:")
        try:
            target.restore_payload(payload,"merge")
            target.update_wallet(self.wallet["id"],{"name":"Synthetic local conflict value"})
            new_wallet=self.store.create_wallet({"name":"Synthetic additional wallet","type":"cash","currency":"EUR","opening_balance":"0"})
            updated_payload=self.store.backup_payload()
            result=target.restore_payload(updated_payload,"merge")
            self.assertEqual(result["inserted"]["wallets"],1)
            self.assertEqual(next(w for w in target.list_wallets() if w["id"]==self.wallet["id"])["name"],"Synthetic local conflict value")
            self.assertTrue(any(w["id"]==new_wallet["id"] for w in target.list_wallets()))
        finally:
            target.close()

    def test_merge_rejects_new_transaction_incompatible_with_conflicting_local_category(self):
        source=FinanceStore(":memory:")
        target=FinanceStore(":memory:")
        try:
            category=next(c for c in source.list_categories() if c["kind"]=="expense")
            wallet=source.create_wallet({"name":"Synthetic merge source","type":"cash","currency":"EUR","opening_balance":"0"})
            seed=source.backup_payload()
            target.restore_payload(seed,"merge")
            target.update_category(category["id"],{"kind":"income"})
            source.create_transaction({"wallet_id":wallet["id"],"type":"expense","amount":"1.00",
                "date":"2026-01-02","category_id":category["id"]})
            incoming=source.backup_payload()
            before=target.backup_payload()["data"]
            with self.assertRaisesRegex(FinanceError,"local category type"):
                target.restore_payload(incoming,"merge")
            self.assertEqual(target.backup_payload()["data"],before)
        finally:
            source.close()
            target.close()

    def test_synthetic_data_persists_after_store_reopen(self):
        with tempfile.TemporaryDirectory(prefix="wealth-app-persistence-test-") as folder:
            path=os.path.join(folder,"synthetic.sqlite3")
            first=FinanceStore(path)
            wallet=first.create_wallet({"name":"Restart fixture","type":"cash","currency":"EUR","opening_balance":"12.34"})
            first.close()
            second=FinanceStore(path)
            try:
                saved=next(w for w in second.list_wallets() if w["id"]==wallet["id"])
                self.assertEqual(saved["name"],"Restart fixture")
                self.assertEqual(saved["balance_minor"],1234)
            finally:
                second.close()

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

    def test_category_parent_kind_update_cannot_break_existing_children(self):
        parent=self.store.create_category({"name":"Synthetic hierarchy parent","kind":"expense"})
        child=self.store.create_category({"name":"Synthetic hierarchy child","kind":"expense","parent_id":parent["id"]})
        with self.assertRaisesRegex(FinanceError,"make a subcategory incompatible"):
            self.store.update_category(parent["id"],{"kind":"income"})
        saved_parent=next(row for row in self.store.list_categories() if row["id"]==parent["id"])
        saved_child=next(row for row in self.store.list_categories() if row["id"]==child["id"])
        self.assertEqual(saved_parent["kind"],"expense")
        self.assertEqual(saved_child["kind"],"expense")
        self.assertEqual(self.store.update_category(parent["id"],{"kind":"both"})["kind"],"both")

    def test_legacy_v1_backup_with_parent_kind_changed_is_rejected_clearly(self):
        parent=self.store.create_category({"name":"Synthetic legacy parent","kind":"expense"})
        child=self.store.create_category({"name":"Synthetic legacy child","kind":"expense","parent_id":parent["id"]})
        # Simulate a v1 archive produced after the older update path changed only
        # the parent's kind, leaving the child unchanged.
        self.store.conn.execute("UPDATE categories SET kind='income' WHERE id=?",(parent["id"],))
        legacy_payload=self.store.backup_payload()
        target=FinanceStore(":memory:")
        try:
            baseline=target.backup_payload()["data"]
            message="incompatible with its parent"
            with self.assertRaisesRegex(FinanceError,message):
                target.preview_restore(legacy_payload)
            for mode in ("merge","replace"):
                with self.subTest(mode=mode):
                    with self.assertRaisesRegex(FinanceError,message):
                        target.restore_payload(legacy_payload,mode)
                    self.assertEqual(target.backup_payload()["data"],baseline)
            self.assertEqual(next(row for row in legacy_payload["data"]["categories"] if row["id"]==child["id"])["parent_id"],parent["id"])
        finally:
            target.close()

    def test_restore_clears_import_batch_references_omitted_from_v1_archives(self):
        staged=self.store.begin_import("csv_import",[{
            "date":"2026-03-04","type":"expense","amount":"8.20","currency":"EUR",
            "wallet_id":self.wallet["id"],"description":"Synthetic imported transaction"
        }])
        batch_id=staged["batch_id"]
        self.store.commit_import(batch_id,[{"id":staged["rows"][0]["id"],"accepted":True}])
        payload=self.store.backup_payload()
        archived_tx=payload["data"]["transactions"][0]
        self.assertEqual(archived_tx["source"],"csv_import")
        self.assertEqual(archived_tx["import_batch_id"],batch_id)
        self.assertNotIn("import_batches",payload["data"])

        for mode,matching_batch in (("merge",False),("merge",True),("replace",True)):
            target=FinanceStore(":memory:")
            try:
                target_wallet=target.create_wallet({"name":"Synthetic pre-restore wallet","type":"cash",
                    "currency":"EUR","opening_balance":"0"})
                if matching_batch:
                    # A matching UUID alone does not make this transient batch
                    # part of the archive or prove it represents the same review.
                    target.conn.execute("""INSERT INTO import_batches
                        (id,owner_id,source_type,status,created_at) VALUES(?,?,?,'committed',?)""",
                        (batch_id,"local","csv_import","2026-01-01T00:00:00+00:00"))
                    target.conn.commit()
                with self.subTest(mode=mode,matching_batch=matching_batch):
                    result=target.restore_payload(payload,mode)
                    self.assertEqual(result["inserted"]["transactions"],1)
                    restored=target.get_transaction(archived_tx["id"])
                    self.assertEqual(restored["source"],"csv_import")
                    self.assertIsNone(restored["import_batch_id"])
                    self.assertEqual(target.conn.execute("PRAGMA foreign_key_check").fetchall(),[])
                    dangling=target.conn.execute("""SELECT COUNT(*) FROM transactions t
                        LEFT JOIN import_batches b ON b.id=t.import_batch_id
                        WHERE t.import_batch_id IS NOT NULL AND b.id IS NULL""").fetchone()[0]
                    self.assertEqual(dangling,0)
                    if mode=="merge":
                        repeated=target.restore_payload(payload,"merge")
                        self.assertEqual(repeated["inserted"]["transactions"],0)
                        self.assertIsNone(target.get_transaction(archived_tx["id"])["import_batch_id"])
                        self.assertTrue(any(w["id"]==target_wallet["id"] for w in target.list_wallets()))
                    else:
                        self.assertEqual(target.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0],0)
                        self.assertFalse(any(w["id"]==target_wallet["id"] for w in target.list_wallets()))
            finally:
                target.close()


if __name__=="__main__":
    unittest.main()
