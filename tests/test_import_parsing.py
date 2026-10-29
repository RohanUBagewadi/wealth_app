import atexit
import base64
import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

_test_data = tempfile.TemporaryDirectory(prefix="wealth-app-import-tests-")
os.environ["WEALTH_APP_DATA_DIR"] = _test_data.name

import main
from finance_core import FinanceError


def _close_test_store():
    main.STORE.close()
    _test_data.cleanup()


atexit.register(_close_test_store)


def synthetic_text_pdf(text, *, page_count=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(page_count):
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
        content = text if isinstance(text, bytes) else text.encode("ascii")
        content = content.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 12 Tf 72 720 Td (" + content + b") Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-only")
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


class ImportParsingTests(unittest.TestCase):
    def test_csv_accepts_utf8_bom_header(self):
        rows = main.parse_csv_text("\ufefftransaction_date,amount\n2026-01-02,1.25\n")
        self.assertEqual(rows, [{"transaction_date": "2026-01-02", "amount": "1.25"}])

    def test_csv_rejects_duplicate_normalized_headers_and_date_aliases(self):
        for content, field in (
            ("date,amount, Amount \n2026-01-02,1.00,2.00\n", "amount"),
            ("date,transaction_date,amount\n2026-01-02,2026-01-03,1.00\n", "transaction_date"),
            ("transaction_date, DATE ,amount\n2026-01-02,2026-01-03,1.00\n", "transaction_date"),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(FinanceError, "duplicate header: {}".format(field)):
                main.parse_csv_text(content)

    def test_csv_accepts_reordered_whitespace_and_case_normalized_headers(self):
        rows = main.parse_csv_text(" Description , AMOUNT , Date , Type \nSynthetic note,1.25,2026-01-02,INCOME\n")
        self.assertEqual(rows, [{
            "description": "Synthetic note", "amount": "1.25", "date": "2026-01-02", "type": "INCOME"
        }])

    def test_csv_comma_and_semicolon_modes_parse_quoted_delimiters_quotes_and_multiline_fields(self):
        comma = 'date,amount,description\n2026-01-02,1.25,"comma, escaped ""quote""\nsecond line"\n'
        semicolon = 'date;amount;description\n2026-01-02;1.25;"semicolon; escaped ""quote""\nsecond line"\n'
        expected = 'comma, escaped "quote"\nsecond line'
        self.assertEqual(main.parse_csv_text(comma)[0]["description"], expected)
        self.assertEqual(main.parse_csv_text(semicolon, ";")[0]["description"],
                         'semicolon; escaped "quote"\nsecond line')
        self.assertEqual(main.parse_csv_text("\ufeffdate;amount;description\n2026-01-02;1;Café\n", ";")[0]["description"], "Café")

    def test_csv_rejects_unsupported_and_mismatched_delimiters_without_fallback(self):
        with self.assertRaisesRegex(FinanceError, "comma or semicolon"):
            main.parse_csv_text("date\tamount\n2026-01-02\t1.25\n", "\t")
        for content, selected in (("date;amount\n2026-01-02;1.25\n", ","),
                                  ("date,amount\n2026-01-02,1.25\n", ";")):
            with self.subTest(delimiter=selected), self.assertRaisesRegex(FinanceError, "selected delimiter"):
                main.parse_csv_text(content, selected)

    def test_csv_size_and_row_limits_apply_to_both_delimiters(self):
        for delimiter in (",", ";"):
            content = "date{}amount\n2026-01-02{}1.25\n".format(delimiter, delimiter)
            size = len(content.encode("utf-8"))
            with self.subTest(delimiter=delimiter), patch.object(main, "MAX_CSV_BYTES", size):
                self.assertEqual(len(main.parse_csv_text(content, delimiter)), 1)
            with self.subTest(delimiter=delimiter, case="oversize"), patch.object(main, "MAX_CSV_BYTES", size - 1):
                with self.assertRaisesRegex(FinanceError, "too large"):
                    main.parse_csv_text(content, delimiter)
            header = "date{}amount\n".format(delimiter)
            row = "2026-01-02{}1\n".format(delimiter)
            with self.subTest(delimiter=delimiter, case="row-limit"), self.assertRaisesRegex(FinanceError, "5000 rows"):
                main.parse_csv_text(header + row * 5001, delimiter)

    def test_csv_rejects_oversize_and_more_than_5000_rows(self):
        with self.assertRaisesRegex(FinanceError, "too large"):
            main.parse_csv_text("x" * (main.MAX_CSV_BYTES + 1))
        content = "transaction_date,amount\n" + "2026-01-02,1\n" * 5001
        with self.assertRaisesRegex(FinanceError, "5000 rows"):
            main.parse_csv_text(content)

    def test_csv_rejects_unterminated_quoted_field(self):
        with self.assertRaisesRegex(FinanceError, "structure"):
            main.parse_csv_text('transaction_date,amount,description\n2026-01-02,1,"unfinished\n')
        with self.assertRaisesRegex(FinanceError, "structure"):
            main.parse_csv_text("transaction_date,amount\n2026-01-02,1,unexpected\n")

    def test_csv_rejects_invalid_unicode_cleanly(self):
        with self.assertRaisesRegex(FinanceError, "UTF-8"):
            main.parse_csv_text("transaction_date,amount\n2026-01-02,\ud800\n")

    def test_pdf_rejects_invalid_and_oversized_inputs(self):
        with self.assertRaisesRegex(FinanceError, "could not be read"):
            main.parse_pdf_candidates("not-base64", None, None)
        with self.assertRaisesRegex(FinanceError, "valid PDF"):
            main.parse_pdf_candidates(base64.b64encode(b"not a pdf").decode("ascii"), None, None)
        too_large = base64.b64encode(b"%PDF-" + b"x" * main.MAX_PDF_BYTES).decode("ascii")
        with self.assertRaisesRegex(FinanceError, "too large"):
            main.parse_pdf_candidates(too_large, None, None)

    def test_pdf_decoded_size_boundary_accepts_below_and_at_rejects_above(self):
        pdf = synthetic_text_pdf("2026-01-02 Synthetic item 12.34 EUR")
        limit = len(pdf) + 32
        with patch.object(main, "MAX_PDF_BYTES", limit):
            for raw in (pdf + b" " * 31, pdf + b" " * 32):
                with self.subTest(size=len(raw)):
                    encoded = base64.b64encode(raw).decode("ascii")
                    self.assertEqual(len(main.parse_pdf_candidates(encoded, None, None)), 1)
            too_large = base64.b64encode(pdf + b" " * 33).decode("ascii")
            with self.assertRaisesRegex(FinanceError, "too large"):
                main.parse_pdf_candidates(too_large, None, None)

    def test_pdf_rejects_malformed_truncated_and_encrypted_files(self):
        for raw in (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog", b"%PDF-1.4\n%%EOF"):
            with self.subTest(malformed=raw[:12]):
                with self.assertRaisesRegex(FinanceError, "could not be extracted"):
                    main.parse_pdf_candidates(base64.b64encode(raw).decode("ascii"), None, None)
        encrypted = synthetic_text_pdf("2026-01-02 Synthetic item 12.34 EUR", encrypted=True)
        with self.assertRaisesRegex(FinanceError, "Password-protected"):
            main.parse_pdf_candidates(base64.b64encode(encrypted).decode("ascii"), None, None)

    def test_pdf_page_and_incremental_text_limits(self):
        text = "2026-01-02 Synthetic item 12.34 EUR"
        many_pages = synthetic_text_pdf(text, page_count=2)
        with patch.object(main, "MAX_PDF_PAGES", 1):
            with self.assertRaisesRegex(FinanceError, "too many pages"):
                main.parse_pdf_candidates(base64.b64encode(many_pages).decode("ascii"), None, None)

        text_pdf = synthetic_text_pdf(text)
        with patch.object(main, "MAX_PDF_TEXT_CHARS", len(text)):
            self.assertEqual(len(main.parse_pdf_candidates(base64.b64encode(text_pdf).decode("ascii"), None, None)), 1)
        with patch.object(main, "MAX_PDF_TEXT_CHARS", len(text) - 1):
            with self.assertRaisesRegex(FinanceError, "character processing limit"):
                main.parse_pdf_candidates(base64.b64encode(text_pdf).decode("ascii"), None, None)

    def test_pdf_without_selectable_text_is_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        stream = io.BytesIO()
        writer.write(stream)
        encoded = base64.b64encode(stream.getvalue()).decode("ascii")
        with self.assertRaisesRegex(FinanceError, "No selectable text"):
            main.parse_pdf_candidates(encoded, None, None)

    def test_encrypted_backup_roundtrip_tamper_and_kdf_limits(self):
        passphrase = "Synthetic test passphrase 23"
        encrypted = main.encrypt_backup(passphrase)
        payload = main.decrypt_backup(encrypted, passphrase)
        self.assertEqual(payload["format"], "wealth-app-backup")
        with self.assertRaisesRegex(FinanceError, "Could not decrypt"):
            main.decrypt_backup(encrypted, "Different synthetic passphrase")

        envelope = json.loads(encrypted.decode("utf-8"))
        ciphertext = bytearray(base64.b64decode(envelope["ciphertext"]))
        ciphertext[-1] ^= 1
        envelope["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
        with self.assertRaisesRegex(FinanceError, "Could not decrypt"):
            main.decrypt_backup(json.dumps(envelope).encode("utf-8"), passphrase)

        envelope["n"], envelope["r"], envelope["p"] = 2**18, 16, 8
        with self.assertRaisesRegex(FinanceError, "parameters are unsupported"):
            main.decrypt_backup(json.dumps(envelope).encode("utf-8"), passphrase)

    def test_backup_payload_size_boundary_and_encrypted_archive_limit(self):
        passphrase = "Synthetic size boundary passphrase"
        empty = {"padding": ""}
        empty_size = len(main.serialize_json_limited(empty, main.MAX_BACKUP_PAYLOAD_BYTES, "too large"))
        exact_value = {"padding": "x" * (main.MAX_BACKUP_PAYLOAD_BYTES - empty_size)}
        with patch.object(main.STORE, "backup_payload", return_value=exact_value):
            exact_archive = main.encrypt_backup(passphrase)
        self.assertLessEqual(len(exact_archive), main.MAX_BACKUP_ARCHIVE_BYTES)
        self.assertEqual(main.decrypt_backup(exact_archive, passphrase), exact_value)

        oversized_value = {"padding": "x" * (main.MAX_BACKUP_PAYLOAD_BYTES - empty_size + 1)}
        with patch.object(main.STORE, "backup_payload", return_value=oversized_value):
            with self.assertRaisesRegex(FinanceError, "5 MiB limit"):
                main.encrypt_backup(passphrase)

        exact_archive_limit = exact_archive + (b" " * (main.MAX_BACKUP_ARCHIVE_BYTES - len(exact_archive)))
        self.assertEqual(len(main.decode_backup_content(base64.b64encode(exact_archive_limit).decode("ascii"))),
                         main.MAX_BACKUP_ARCHIVE_BYTES)
        with self.assertRaisesRegex(FinanceError, "8 MiB limit"):
            main.decode_backup_content(base64.b64encode(exact_archive_limit + b" ").decode("ascii"))
        with self.assertRaisesRegex(FinanceError, "8 MiB limit"):
            main.decrypt_backup(exact_archive_limit + b" ", passphrase)

    def test_decrypted_backup_payload_limit_is_checked_before_json_parse(self):
        passphrase = "Synthetic decrypted boundary passphrase"
        with patch.object(main.STORE, "backup_payload", return_value={"padding": "safe"}):
            encrypted = main.encrypt_backup(passphrase)
        original_limit = main.MAX_BACKUP_PAYLOAD_BYTES
        try:
            main.MAX_BACKUP_PAYLOAD_BYTES = 1
            with self.assertRaisesRegex(FinanceError, "5 MiB limit"):
                main.decrypt_backup(encrypted, passphrase)
        finally:
            main.MAX_BACKUP_PAYLOAD_BYTES = original_limit


class RequestOriginTests(unittest.TestCase):
    class FakeRequest:
        def __init__(self, headers):
            self.headers = headers
            self.server = SimpleNamespace(server_address=("127.0.0.1", 8000))

        def _check_host(self):
            main.Handler._check_host(self)

    def test_origin_guard_accepts_loopback_and_rejects_other_origins(self):
        main.Handler._check_origin(self.FakeRequest({"Host": "127.0.0.1:8000"}))
        with self.assertRaisesRegex(FinanceError, "Cross-origin"):
            main.Handler._check_origin(self.FakeRequest({
                "Host": "127.0.0.1:8000", "Origin": "https://example.invalid"
            }))
        with self.assertRaisesRegex(FinanceError, "loopback"):
            main.Handler._check_origin(self.FakeRequest({"Host": "192.168.1.2:8000"}))

    def test_host_guard_accepts_only_allowlisted_loopback_hosts_and_port(self):
        for host in ("127.0.0.1:8000", "localhost:8000", "LOCALHOST:8000"):
            main.Handler._check_host(self.FakeRequest({"Host": host}))
        for host in (
            "example.invalid", "localhost", "localhost:8001", "127.0.0.1:8001",
            "localhost:08000", "localhost:8000.evil.invalid", " localhost:8000",
            "localhost:8000,example.invalid", "[::1]:8000", "",
        ):
            with self.subTest(host=host), self.assertRaisesRegex(FinanceError, "loopback"):
                main.Handler._check_host(self.FakeRequest({"Host": host}))
        with self.assertRaisesRegex(FinanceError, "loopback"):
            main.Handler._check_host(self.FakeRequest({}))

        class DuplicateHostHeaders(dict):
            def get_all(self, name):
                return ["127.0.0.1:8000", "localhost:8000"] if name == "Host" else None

        with self.assertRaisesRegex(FinanceError, "loopback"):
            main.Handler._check_host(self.FakeRequest(DuplicateHostHeaders()))

    def test_json_request_body_validation(self):
        def read(content, content_type="application/json", length=None):
            raw = content.encode("utf-8")
            headers = {"Content-Type": content_type, "Content-Length": str(len(raw) if length is None else length)}
            request = SimpleNamespace(headers=headers, rfile=io.BytesIO(raw))
            return main.Handler._body(request)

        self.assertEqual(read('{"synthetic":true}'), {"synthetic": True})
        with self.assertRaisesRegex(FinanceError, "content type"):
            read("{}", "text/plain")
        with self.assertRaisesRegex(FinanceError, "Request data is invalid"):
            read("{")
        with self.assertRaisesRegex(FinanceError, "Request data is invalid"):
            read("[]")
        with self.assertRaisesRegex(FinanceError, "empty or too large"):
            read("", length=0)
        with self.assertRaisesRegex(FinanceError, "empty or too large"):
            read("{}", length=main.MAX_JSON_BYTES + 1)


class ServeBindingTests(unittest.TestCase):
    def test_serve_refuses_non_loopback_bind(self):
        with self.assertRaisesRegex(SystemExit, "only bind to 127.0.0.1"):
            main.serve("0.0.0.0", 0)


if __name__ == "__main__":
    unittest.main()
