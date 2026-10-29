"""Opt-in real HTTP smoke test; every route uses an isolated synthetic store.

Run with WEALTH_APP_RUN_HTTP_SMOKE=1 to bind an ephemeral loopback port.
"""
import base64
import atexit
from copy import deepcopy
import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from unittest.mock import patch
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

_test_data = tempfile.TemporaryDirectory(prefix="wealth-app-http-import-")
os.environ["WEALTH_APP_DATA_DIR"] = _test_data.name

import main
from finance_core import FinanceStore


def _cleanup_import_store():
    try:
        main.STORE.close()
    except Exception:
        pass
    _test_data.cleanup()


atexit.register(_cleanup_import_store)


def synthetic_text_pdf(text):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_ref})
    })
    content = text.encode("ascii").replace(b"(", b"\\(").replace(b")", b"\\)")
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (" + content + b") Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@unittest.skipUnless(os.environ.get("WEALTH_APP_RUN_HTTP_SMOKE") == "1", "opt-in loopback HTTP smoke test")
class HttpSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_store = main.STORE
        cls.server = main.AppServer(("127.0.0.1", 0), main.Handler)
        cls.port = cls.server.server_address[1]
        cls.origin = "http://127.0.0.1:{}".format(cls.port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    def setUp(self):
        self.previous_store = main.STORE
        self.data = tempfile.TemporaryDirectory(prefix="wealth-app-http-smoke-case-")
        main.STORE = FinanceStore(os.path.join(self.data.name, "synthetic.sqlite3"))

    def tearDown(self):
        main.STORE.close()
        main.STORE = self.previous_store
        self.data.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        main.STORE = cls.previous_store

    def request(self, method, path, body=None, *, origin=None, host=None, raw_body=None):
        headers = {}
        headers["Host"] = "" if host is False else (host or "127.0.0.1:{}".format(self.port))
        if origin is not None:
            headers["Origin"] = origin
        encoded = raw_body if raw_body is not None else (json.dumps(body).encode() if body is not None else None)
        if body is not None or raw_body is not None:
            headers["Content-Type"] = "application/json"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        conn.request(method, path, body=encoded, headers=headers)
        response = conn.getresponse()
        payload = response.read()
        status = response.status
        content_type = response.getheader("Content-Type", "")
        conn.close()
        parsed = json.loads(payload) if "application/json" in content_type and payload else payload
        return status, parsed

    def test_synthetic_http_routes_and_guards(self):
        for route in ("/", "/app.css", "/app.js"):
            status, _ = self.request("GET", route)
            self.assertEqual(status, 200, route)
        for route in ("/api/health", "/api/bootstrap", "/api/reports", "/api/settings"):
            status, _ = self.request("GET", route)
            self.assertEqual(status, 200, route)

        wallet_data = {"name": "Synthetic HTTP wallet", "type": "cash", "currency": "EUR",
                       "opening_balance": "0", "opening_date": "2026-01-01"}
        status, wallet = self.request("POST", "/api/wallets", wallet_data, origin=self.origin)
        self.assertEqual(status, 201)
        self.assertIn("id", wallet)
        status, updated = self.request("PATCH", "/api/wallets/{}".format(wallet["id"]),
                                       {**wallet_data, "name": "Synthetic HTTP wallet updated"}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(updated["name"], "Synthetic HTTP wallet updated")

        status, category = self.request("POST", "/api/categories",
                                        {"name": "Synthetic HTTP category", "kind": "expense"}, origin=self.origin)
        self.assertEqual(status, 201)
        status, category = self.request("PATCH", "/api/categories/{}".format(category["id"]),
                                        {"name": "Synthetic HTTP category updated", "kind": "expense"}, origin=self.origin)
        self.assertEqual(status, 200)
        budget_data = {"name": "Synthetic HTTP budget", "period": "custom", "start_date": "2026-01-01",
                       "end_date": "2026-01-31", "amount": "100.00", "currency": "EUR",
                       "scope": "category", "category_id": category["id"]}
        status, budget = self.request("POST", "/api/budgets", budget_data, origin=self.origin)
        self.assertEqual(status, 201)
        status, _ = self.request("PATCH", "/api/budgets/{}".format(budget["id"]),
                                 {"name": "Updated synthetic budget"}, origin=self.origin)
        self.assertEqual(status, 200)
        transaction_data = {"wallet_id": wallet["id"], "category_id": category["id"],
                            "type": "expense", "amount": "12.34", "date": "2026-01-02",
                            "description": "Synthetic HTTP transaction"}
        status, transaction = self.request("POST", "/api/transactions", transaction_data,
                                           origin=self.origin, host="localhost:{}".format(self.port))
        self.assertEqual(status, 201)
        status, listed = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(listed["total"], 1)
        status, _ = self.request("PATCH", "/api/transactions/{}".format(transaction["id"]),
                                 {**transaction_data, "description": "Updated synthetic transaction"}, origin=self.origin)
        self.assertEqual(status, 200)

        status, second_wallet = self.request("POST", "/api/wallets",
            {**wallet_data, "name": "Synthetic destination"}, origin=self.origin)
        self.assertEqual(status, 201)
        status, transfer = self.request("POST", "/api/transfers", {
            "source_wallet_id": wallet["id"], "destination_wallet_id": second_wallet["id"],
            "amount": "2.00", "date": "2026-01-03"}, origin=self.origin)
        self.assertEqual(status, 201)
        status, _ = self.request("PATCH", "/api/transfers/{}".format(transfer["id"]), {
            "source_wallet_id": wallet["id"], "destination_wallet_id": second_wallet["id"],
            "amount": "2.50", "date": "2026-01-03"}, origin=self.origin)
        self.assertEqual(status, 200)
        status, _ = self.request("DELETE", "/api/transfers/{}".format(transfer["id"]), origin=self.origin)
        self.assertEqual(status, 200)

        csv_text = ("transaction_date,type,amount,currency,wallet,category,description,notes\n"
                    "2026-01-04,expense,3.25,EUR,Synthetic HTTP wallet updated,"
                    "Synthetic HTTP category updated,CSV smoke,synthetic\n")
        status, review = self.request("POST", "/api/imports/csv/preview", {"content": csv_text}, origin=self.origin)
        self.assertEqual(status, 201)
        status, committed = self.request("POST", "/api/imports/{}/commit".format(review["batch_id"]),
                                         {"rows": [{"id": review["rows"][0]["id"], "accepted": True}]}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(committed["accepted_count"], 1)
        status, cancelled_review = self.request("POST", "/api/imports/csv/preview", {"content": csv_text}, origin=self.origin)
        self.assertEqual(status, 201)
        status, cancelled = self.request("POST", "/api/imports/{}/cancel".format(cancelled_review["batch_id"]), {}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "cancelled")
        status, exported = self.request("GET", "/api/transactions/export.csv")
        self.assertEqual(status, 200)
        self.assertIn(b"Synthetic HTTP", exported)

        status, _ = self.request("POST", "/api/imports/pdf/preview",
                                 {"content_base64": "bm90LWEtcGRm"}, origin=self.origin)
        self.assertEqual(status, 400)
        with patch.object(main.STORE, "backup_payload",
                          return_value={"padding": "x" * main.MAX_BACKUP_PAYLOAD_BYTES}):
            status, oversized_backup = self.request("POST", "/api/backup/create",
                {"passphrase": "Synthetic smoke passphrase 42"}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("5 MiB limit", oversized_backup["error"])
        status, archive = self.request("POST", "/api/backup/create",
                                       {"passphrase": "Synthetic smoke passphrase 42"}, origin=self.origin)
        self.assertEqual(status, 200)
        encoded_archive = base64.b64encode(archive).decode("ascii")
        restore_body = {"content_base64": encoded_archive, "passphrase": "Synthetic smoke passphrase 42"}
        status, preview = self.request("POST", "/api/backup/preview", restore_body, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertGreater(preview["preview"]["total"], 0)
        self.assertEqual(set(preview), {"preview"})
        self.assertNotIn("payload", preview)
        self.assertNotIn("Updated synthetic transaction", json.dumps(preview))
        status, unchanged = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        transaction_count_before_cancel = unchanged["total"]
        # Preview is a read-only step; cancelling simply leaves the encrypted
        # archive unused and must not alter the synthetic ledger.
        status, still_unchanged = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(still_unchanged["total"], transaction_count_before_cancel)

        status, post_backup_wallet = self.request("POST", "/api/wallets",
            {**wallet_data, "name": "Synthetic post-backup wallet"}, origin=self.origin)
        self.assertEqual(status, 201)
        status, post_backup_transaction = self.request("POST", "/api/transactions", {
            "wallet_id": post_backup_wallet["id"], "type": "expense", "amount": "1.10",
            "date": "2026-01-05", "description": "Synthetic post-backup marker"}, origin=self.origin)
        self.assertEqual(status, 201)
        status, restored = self.request("POST", "/api/backup/restore", {**restore_body, "mode": "merge"}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(restored["mode"], "merge")
        self.assertEqual(restored["inserted"]["transactions"], 0)
        status, after_merge = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(after_merge["total"], transaction_count_before_cancel + 1)
        status, error = self.request("POST", "/api/backup/restore", {**restore_body, "mode": "replace"}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("REPLACE MY DATA", error["error"])
        status, after_wrong_confirmation = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(after_wrong_confirmation["total"], transaction_count_before_cancel + 1)
        status, replaced = self.request("POST", "/api/backup/restore",
            {**restore_body, "mode": "replace", "confirmation": "REPLACE MY DATA"}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(replaced["mode"], "replace")
        status, after_replace = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(after_replace["total"], transaction_count_before_cancel)
        self.assertNotIn(post_backup_transaction["id"], [item["id"] for item in after_replace["items"]])

        before_oversize = after_replace["total"]
        oversized_archive = base64.b64encode(b"x" * (main.MAX_BACKUP_ARCHIVE_BYTES + 1)).decode("ascii")
        oversized_restore = {"content_base64": oversized_archive,
                             "passphrase": "Synthetic smoke passphrase 42", "mode": "replace",
                             "confirmation": "REPLACE MY DATA"}
        status, oversized_preview_error = self.request("POST", "/api/backup/preview",
            {"content_base64": oversized_archive, "passphrase": "Synthetic smoke passphrase 42"}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("8 MiB limit", oversized_preview_error["error"])
        status, oversized_error = self.request("POST", "/api/backup/restore", oversized_restore, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("8 MiB limit", oversized_error["error"])
        status, after_oversize = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(after_oversize["total"], before_oversize)

        status, error = self.request("POST", "/api/wallets", {"name": "", "type": "cash", "currency": "EUR"}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("error", error)
        status, error = self.request("POST", "/api/wallets", wallet_data, origin="https://example.invalid")
        self.assertEqual(status, 400)
        self.assertIn("Cross-origin", error["error"])
        status, error = self.request("POST", "/api/wallets", wallet_data,
                                     origin=self.origin, host="example.invalid")
        self.assertEqual(status, 400)
        self.assertIn("loopback", error["error"])
        status, error = self.request("POST", "/api/wallets", raw_body=b"{")
        self.assertEqual(status, 400)
        status, error = self.request("GET", "/api/reports?from=not-a-date&to=also-invalid")
        self.assertEqual(status, 400)
        status, _ = self.request("OPTIONS", "/api/health")
        self.assertEqual(status, 405)
        status, _ = self.request("DELETE", "/api/transactions/{}".format(transaction["id"]), origin=self.origin)
        self.assertEqual(status, 200)

    def test_pdf_http_preview_stages_valid_file_and_rejects_oversize_without_staging(self):
        wallet = main.STORE.create_wallet({"name":"Synthetic PDF wallet","type":"cash","currency":"EUR","opening_balance":"0"})
        pdf = synthetic_text_pdf("2026-01-02 Synthetic PDF item 12.34 EUR")
        encoded = base64.b64encode(pdf).decode("ascii")
        before_batches = main.STORE.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        with patch.object(main, "MAX_PDF_BYTES", len(pdf) - 1):
            status, error = self.request("POST", "/api/imports/pdf/preview", {
                "content_base64": encoded, "wallet_id": wallet["id"], "currency":"EUR"
            }, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("too large", error["error"])
        self.assertEqual(main.STORE.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], before_batches)
        self.assertEqual(main.STORE.list_transactions()["total"], 0)
        status, malformed = self.request("POST", "/api/imports/pdf/preview", {
            "content_base64": base64.b64encode(b"%PDF-1.4\n%%EOF").decode("ascii"),
            "wallet_id": wallet["id"], "currency":"EUR"
        }, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("could not be extracted", malformed["error"])
        self.assertNotIn("Traceback", malformed["error"])
        self.assertEqual(main.STORE.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], before_batches)
        self.assertEqual(main.STORE.list_transactions()["total"], 0)

        status, review = self.request("POST", "/api/imports/pdf/preview", {
            "content_base64": encoded, "wallet_id": wallet["id"], "currency":"EUR"
        }, origin=self.origin)
        self.assertEqual(status, 201)
        self.assertEqual(review["accepted_count"], 1)
        self.assertEqual(main.STORE.list_transactions()["total"], 0)
        status, canceled = self.request("POST", "/api/imports/{}/cancel".format(review["batch_id"]), {}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(canceled["status"], "cancelled")
        self.assertEqual(main.STORE.list_transactions()["total"], 0)

    def test_csv_rejects_duplicate_headers_and_requires_type_and_category_correction(self):
        store = main.STORE
        wallet = store.create_wallet({"name":"Synthetic CSV resolution wallet","type":"cash","currency":"EUR","opening_balance":"0"})
        category = next(c for c in store.list_categories() if c["kind"] == "expense")
        batch_count = store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        transaction_count = store.list_transactions()["total"]

        for malformed in (
            "date,amount, Amount \n2026-01-02,1.00,2.00\n",
            "date,transaction_date,amount\n2026-01-02,2026-01-03,1.00\n",
        ):
            status, error = self.request("POST", "/api/imports/csv/preview", {"content":malformed}, origin=self.origin)
            self.assertEqual(status, 400)
            self.assertIn("duplicate header", error["error"])
            self.assertNotIn("Traceback", error["error"])
        self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0], batch_count)
        self.assertEqual(store.list_transactions()["total"], transaction_count)

        status, review = self.request("POST", "/api/imports/csv/preview", {"content":
            "description,amount,currency,wallet,date\nSynthetic income,4.25,EUR,Synthetic CSV resolution wallet,2026-01-02\n"
        }, origin=self.origin)
        self.assertEqual(status, 201)
        row = review["rows"][0]
        self.assertFalse(row["accepted"])
        self.assertIsNone(row["type"])
        self.assertIn("Transaction type is missing", row["warnings"][0])
        status, error = self.request("POST", "/api/imports/{}/commit".format(review["batch_id"]),
            {"rows":[{"id":row["id"],"accepted":True}]}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("Choose income or expense", error["error"])
        self.assertEqual(store.list_transactions()["total"], transaction_count)
        status, committed = self.request("POST", "/api/imports/{}/commit".format(review["batch_id"]),
            {"rows":[{"id":row["id"],"accepted":True,"type":"income","amount_minor":425,
                      "wallet_id":wallet["id"],"currency":"EUR","transaction_date":"2026-01-02",
                      "description":"Synthetic income","category_id":None}]}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(committed["accepted_count"], 1)
        saved = store.list_transactions()["items"][0]
        self.assertEqual((saved["type"], saved["description"], saved["amount_minor"]), ("income", "Synthetic income", 425))

        income_category = next(c for c in store.list_categories() if c["kind"] == "income")
        normalized_type = ("date,type,amount,currency,wallet,category,description\n"
                          "2026-01-02,  INCOME  ,1.25,EUR,Synthetic CSV resolution wallet,  {},Synthetic normalized type\n".format(income_category["name"].upper()))
        status, normalized_review = self.request("POST", "/api/imports/csv/preview", {"content":normalized_type}, origin=self.origin)
        self.assertEqual(status, 201)
        normalized_row = normalized_review["rows"][0]
        self.assertEqual(normalized_row["type"], "income")
        self.assertEqual(normalized_row["category_id"], income_category["id"])
        self.assertTrue(normalized_row["accepted"])
        status, _ = self.request("POST", "/api/imports/{}/cancel".format(normalized_review["batch_id"]), {}, origin=self.origin)
        self.assertEqual(status, 200)

        unsupported_content = "date,type,amount,currency,wallet\n2026-01-02,transfer,1.00,EUR,Synthetic CSV resolution wallet\n"
        status, unsupported_review = self.request("POST", "/api/imports/csv/preview", {"content":unsupported_content}, origin=self.origin)
        self.assertEqual(status, 201)
        unsupported = unsupported_review["rows"][0]
        self.assertFalse(unsupported["accepted"])
        self.assertIsNone(unsupported["type"])
        self.assertIn("Unsupported transaction type 'transfer'", unsupported["warnings"][0])
        status, error = self.request("POST", "/api/imports/{}/commit".format(unsupported_review["batch_id"]),
            {"rows":[{"id":unsupported["id"],"accepted":True,"type":"transfer","amount_minor":100,
                      "wallet_id":wallet["id"],"currency":"EUR","transaction_date":"2026-01-02"}]}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("Choose income or expense", error["error"])
        self.assertEqual(store.list_transactions()["total"], 1)
        status, _ = self.request("POST", "/api/imports/{}/cancel".format(unsupported_review["batch_id"]), {}, origin=self.origin)
        self.assertEqual(status, 200)

        unknown_content = ("date,type,amount,currency,wallet,category,description\n"
                           "2026-01-03,expense,2.10,EUR,Synthetic CSV resolution wallet,Unknown synthetic category,Synthetic expense\n")
        status, unknown_review = self.request("POST", "/api/imports/csv/preview", {"content":unknown_content}, origin=self.origin)
        self.assertEqual(status, 201)
        unknown = unknown_review["rows"][0]
        self.assertFalse(unknown["accepted"])
        self.assertIsNone(unknown["category_id"])
        self.assertIn("Category not found", unknown["warnings"][-1])
        status, error = self.request("POST", "/api/imports/{}/commit".format(unknown_review["batch_id"]),
            {"rows":[{"id":unknown["id"],"accepted":True,"type":"expense","amount_minor":210,
                      "wallet_id":wallet["id"],"currency":"EUR","transaction_date":"2026-01-03",
                      "description":"Synthetic expense","category_id":None}]}, origin=self.origin)
        self.assertEqual(status, 400)
        self.assertIn("Choose an existing category", error["error"])
        self.assertEqual(store.list_transactions()["total"], 1)
        status, committed = self.request("POST", "/api/imports/{}/commit".format(unknown_review["batch_id"]),
            {"rows":[{"id":unknown["id"],"accepted":True,"type":"expense","amount_minor":210,
                      "wallet_id":wallet["id"],"currency":"EUR","transaction_date":"2026-01-03",
                      "description":"Synthetic expense","category_id":category["id"]}]}, origin=self.origin)
        self.assertEqual(status, 200)
        saved = store.list_transactions()["items"][0]
        self.assertEqual(saved["category_id"], category["id"])
        self.assertEqual(saved["description"], "Synthetic expense")
        self.assertEqual(saved["amount_minor"], 210)

        empty_category = "date,type,amount,currency,wallet,description\n2026-01-04,expense,1.00,EUR,Synthetic CSV resolution wallet,Uncategorized synthetic\n"
        status, empty_review = self.request("POST", "/api/imports/csv/preview", {"content":empty_category}, origin=self.origin)
        self.assertEqual(status, 201)
        self.assertTrue(empty_review["rows"][0]["accepted"])
        status, cancelled = self.request("POST", "/api/imports/{}/cancel".format(empty_review["batch_id"]), {}, origin=self.origin)
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(store.list_transactions()["total"], 2)

    def test_csv_explicit_delimiters_stage_correctly_and_reject_mismatch_without_fallback(self):
        store=main.STORE
        store.create_wallet({"name":"Synthetic delimiter wallet","type":"cash","currency":"EUR","opening_balance":"0"})
        batches_before=store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0]
        tx_before=store.list_transactions()["total"]

        status,error=self.request("POST","/api/imports/csv/preview",{
            "delimiter":"\t","content":"date\tamount\n2026-01-02\t1.00\n"
        },origin=self.origin)
        self.assertEqual(status,400)
        self.assertIn("comma or semicolon",error["error"])
        self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0],batches_before)

        status,error=self.request("POST","/api/imports/csv/preview",{
            "delimiter":",","content":"date;amount\n2026-01-02;1.00\n"
        },origin=self.origin)
        self.assertEqual(status,400)
        self.assertIn("selected delimiter",error["error"])
        self.assertNotIn("Traceback",error["error"])
        self.assertEqual(store.conn.execute("SELECT COUNT(*) FROM import_batches").fetchone()[0],batches_before)

        semicolon=("date;type;amount;currency;wallet;description\n"
                   "2026-01-02;expense;1.25;EUR;Synthetic delimiter wallet;\"A; quoted \"\"memo\"\"\nand second line\"\n")
        status,review=self.request("POST","/api/imports/csv/preview",{"delimiter":";","content":semicolon},origin=self.origin)
        self.assertEqual(status,201)
        self.assertEqual(review["delimiter"],";")
        self.assertEqual(review["rows"][0]["description"],'A; quoted "memo"\nand second line')
        self.assertTrue(review["rows"][0]["accepted"])
        self.assertEqual(store.list_transactions()["total"],tx_before)
        status,cancelled=self.request("POST","/api/imports/{}/cancel".format(review["batch_id"]),{},origin=self.origin)
        self.assertEqual(status,200)
        self.assertEqual(cancelled["status"],"cancelled")

        comma="date,type,amount,currency,wallet,description\n2026-01-03,expense,1.25,EUR,Synthetic delimiter wallet,Default comma\n"
        status,default_review=self.request("POST","/api/imports/csv/preview",{"content":comma},origin=self.origin)
        self.assertEqual(status,201)
        self.assertEqual(default_review["delimiter"],",")
        self.assertEqual(default_review["accepted_count"],1)
        status,_=self.request("POST","/api/imports/{}/cancel".format(default_review["batch_id"]),{},origin=self.origin)
        self.assertEqual(status,200)

        localized="date;type;amount;currency;wallet\n2026-01-04;expense;12,34;EUR;Synthetic delimiter wallet\n"
        status,review=self.request("POST","/api/imports/csv/preview",{"delimiter":";","content":localized},origin=self.origin)
        self.assertEqual(status,201)
        self.assertFalse(review["rows"][0]["accepted"])
        self.assertIsNone(review["rows"][0]["amount_minor"])
        self.assertIn("Amount or currency needs review",review["rows"][0]["warnings"])
        self.assertEqual(store.list_transactions()["total"],tx_before)
        status,_=self.request("POST","/api/imports/{}/cancel".format(review["batch_id"]),{},origin=self.origin)
        self.assertEqual(status,200)

    def test_backup_create_rejects_bounded_snapshot_without_archive_or_data_changes(self):
        main.STORE.create_wallet({"name":"Synthetic bounded backup wallet","type":"cash","currency":"EUR","opening_balance":"4.50"})
        before=deepcopy(main.STORE.backup_payload()["data"])
        with patch.object(main,"MAX_BACKUP_PAYLOAD_BYTES",1):
            status,error=self.request("POST","/api/backup/create",
                {"passphrase":"Synthetic bounded backup passphrase 57"},origin=self.origin)
        self.assertEqual(status,400)
        self.assertEqual(set(error),{"error"})
        self.assertIn("5 MiB limit",error["error"])
        self.assertEqual(main.STORE.backup_payload()["data"],before)

    def test_restore_api_rejects_authenticated_invalid_payload_before_merge_or_replace(self):
        main.STORE.create_wallet({"name":"Synthetic API validation wallet","type":"cash","currency":"EUR",
                                  "opening_balance":"0","opening_date":"2026-01-01"})
        before=deepcopy(main.STORE.backup_payload()["data"])
        invalid=deepcopy(main.STORE.backup_payload())
        invalid["data"]["categories"][0]["color"]="url(javascript:alert(1))"
        with patch.object(main.STORE,"backup_payload",return_value=invalid):
            status,archive=self.request("POST","/api/backup/create",
                {"passphrase":"Synthetic API validation passphrase 91"},origin=self.origin)
        self.assertEqual(status,200)
        body={"content_base64":base64.b64encode(archive).decode("ascii"),
              "passphrase":"Synthetic API validation passphrase 91"}
        status,preview_error=self.request("POST","/api/backup/preview",body,origin=self.origin)
        self.assertEqual(status,400)
        self.assertIn("category color",preview_error["error"])
        for mode,extra in (("merge",{}),("replace",{"confirmation":"REPLACE MY DATA"})):
            with self.subTest(mode=mode):
                status,error=self.request("POST","/api/backup/restore",{**body,"mode":mode,**extra},origin=self.origin)
                self.assertEqual(status,400)
                self.assertIn("category color",error["error"])
                self.assertEqual(main.STORE.backup_payload()["data"],before)

    def test_api_routes_reject_unexpected_host_before_returning_data(self):
        wallet_data = {"name": "Synthetic Host wallet", "type": "cash", "currency": "EUR",
                       "opening_balance": "0", "opening_date": "2026-01-01"}
        status, wallet = self.request("POST", "/api/wallets", wallet_data,
                                      origin=self.origin, host="localhost:{}".format(self.port))
        self.assertEqual(status, 201)
        transaction_data = {"wallet_id": wallet["id"], "type": "expense", "amount": "3.21",
                            "date": "2026-01-02", "description": "Synthetic Host marker"}
        status, transaction = self.request("POST", "/api/transactions", transaction_data,
                                           origin=self.origin, host="127.0.0.1:{}".format(self.port))
        self.assertEqual(status, 201)

        api_routes = (
            "/api/health", "/api/bootstrap", "/api/transactions?limit=10",
            "/api/reports", "/api/transactions/export.csv", "/api/imports/template.csv",
            "/api/settings",
        )
        for route in api_routes:
            for host in ("127.0.0.1:{}".format(self.port), "localhost:{}".format(self.port),
                         "LOCALHOST:{}".format(self.port)):
                status, payload = self.request("GET", route, host=host)
                self.assertEqual(status, 200, (route, host))
                if route == "/api/transactions/export.csv":
                    self.assertIn(b"Synthetic Host marker", payload)

            for host in (
                "example.invalid", "localhost", "localhost:{}".format(self.port + 1),
                "127.0.0.1:{}".format(self.port + 1), "localhost:{}evil.invalid".format(self.port),
                "localhost:{},example.invalid".format(self.port),
            ):
                status, payload = self.request("GET", route, host=host)
                self.assertEqual(status, 400, (route, host))
                self.assertNotIn(b"Synthetic Host marker", payload if isinstance(payload, bytes) else
                                 json.dumps(payload).encode("utf-8"))

            status, payload = self.request("GET", route, host=False)
            self.assertEqual(status, 400, (route, "empty Host"))
            self.assertNotIn(b"Synthetic Host marker", payload if isinstance(payload, bytes) else
                             json.dumps(payload).encode("utf-8"))

        status, payload = self.request("GET", "/api/transactions/export.csv", host="example.invalid")
        self.assertEqual(status, 400)
        self.assertNotIn(b"Synthetic Host marker", payload)
        status, _ = self.request("OPTIONS", "/api/bootstrap", host="example.invalid")
        self.assertEqual(status, 400)
        status, _ = self.request("OPTIONS", "/api/bootstrap",
                                 host="127.0.0.1:{}".format(self.port))
        self.assertEqual(status, 405)

        invalid_wallet = {**wallet_data, "name": "Synthetic rejected Host wallet"}
        status, _ = self.request("POST", "/api/wallets", invalid_wallet,
                                 origin=self.origin, host="example.invalid")
        self.assertEqual(status, 400)
        status, _ = self.request("PATCH", "/api/wallets/{}".format(wallet["id"]),
                                 {"name": "Synthetic rejected Host edit"},
                                 origin=self.origin, host="localhost:{}".format(self.port + 1))
        self.assertEqual(status, 400)
        status, _ = self.request("DELETE", "/api/transactions/{}".format(transaction["id"]),
                                 origin=self.origin, host="attacker.invalid")
        self.assertEqual(status, 400)
        status, current = self.request("GET", "/api/transactions?limit=10")
        self.assertEqual(status, 200)
        self.assertEqual(current["total"], 1)
        status, current_wallets = self.request("GET", "/api/bootstrap")
        self.assertEqual(status, 200)
        self.assertEqual(len([w for w in current_wallets["wallets"]
                              if w["name"] == "Synthetic Host wallet"]), 1)


if __name__ == "__main__":
    unittest.main()
