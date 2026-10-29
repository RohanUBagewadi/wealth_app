"""Loopback-only HTTP application for the local-first personal finance app."""
from __future__ import annotations

import base64
import binascii
import csv
import io
import json
import os
import re
import secrets
import sys
import traceback
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from finance_core import CURRENCY_EXPONENTS, MAX_BACKUP_PAYLOAD_BYTES, FinanceError, FinanceStore, amount_to_minor, minor_to_decimal_string

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_JSON_BYTES = 12 * 1024 * 1024
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_PDF_TEXT_CHARS = 2_000_000
MAX_PDF_BASE64_CHARS = 4 * ((MAX_PDF_BYTES + 2) // 3)
# The encrypted .wbackup file is base64-wrapped in a JSON request. An 8 MiB
# archive expands to about 10.67 MiB, leaving room for JSON fields under the
# 12 MiB request-body limit. AES-GCM and the envelope add overhead, so the
# decrypted UTF-8 JSON payload has a separate, smaller 5 MiB limit.
MAX_BACKUP_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_BACKUP_BASE64_CHARS = 4 * ((MAX_BACKUP_ARCHIVE_BYTES + 2) // 3)


def data_directory() -> Path:
    configured = os.environ.get("WEALTH_APP_DATA_DIR")
    path = Path(configured).expanduser() if configured else ROOT / "instance"
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass
    return path


STORE = FinanceStore(str(data_directory() / "wealth_app.sqlite3"))


def parse_csv_text(text: str, delimiter: str = ",") -> list:
    if not isinstance(delimiter, str) or delimiter not in (",", ";"):
        raise FinanceError("Choose comma or semicolon as the CSV delimiter.")
    try:
        byte_length = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise FinanceError("CSV must use UTF-8 encoding.")
    if byte_length > MAX_CSV_BYTES:
        raise FinanceError("CSV file is too large. Limit is 2 MiB.")
    if text.startswith("\ufeff"):
        text = text[1:]
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        if not reader.fieldnames:
            raise FinanceError("CSV needs a header row.")
        normalized_headers = [str(h or "").strip().lower() for h in reader.fieldnames]
        semantic_headers = ["transaction_date" if h == "date" else h for h in normalized_headers]
        seen_headers = set()
        for header in semantic_headers:
            if header in seen_headers:
                label = "transaction_date" if header == "transaction_date" else (header or "(blank)")
                raise FinanceError("CSV contains a duplicate header: {}.".format(label))
            seen_headers.add(header)
        header_map = {normalized: original for normalized, original in zip(normalized_headers, reader.fieldnames)}
        if not ({"transaction_date", "date"} & set(header_map)) or "amount" not in header_map:
            raise FinanceError("Required date and amount columns were not found using the selected delimiter. Check the delimiter and include transaction_date (or date) and amount columns.")
        result = []
        for row in reader:
            if None in row:
                raise FinanceError("CSV structure could not be read.")
            normalized = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
            if not any((v or "").strip() for v in normalized.values()):
                continue
            result.append(normalized)
            if len(result) > 5000:
                raise FinanceError("CSV contains more than 5000 rows.")
        return result
    except UnicodeDecodeError:
        raise FinanceError("CSV must use UTF-8 encoding.")
    except csv.Error:
        raise FinanceError("CSV structure could not be read.")


class _PdfTextLimitExceeded(Exception):
    pass


def parse_pdf_candidates(encoded: str, default_wallet: Optional[str], default_currency: Optional[str]) -> list:
    if not isinstance(encoded, str) or len(encoded) > MAX_PDF_BASE64_CHARS:
        raise FinanceError("PDF file is too large. Limit is 8 MiB.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error, UnicodeEncodeError):
        raise FinanceError("PDF file could not be read.")
    if len(raw) > MAX_PDF_BYTES:
        raise FinanceError("PDF file is too large. Limit is 8 MiB.")
    if not raw.startswith(b"%PDF-"):
        raise FinanceError("Choose a valid PDF file.")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise FinanceError("PDF text extraction is unavailable. Install the listed pypdf dependency.")
    currency = str(default_currency or "").upper()
    if currency and currency not in CURRENCY_EXPONENTS:
        raise FinanceError("Choose a supported default currency.")
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            raise FinanceError("Password-protected PDFs are not supported.")
        # Reject an excessive declared page count before materializing the page
        # collection; verify the actual collection as well because PDFs can be
        # malformed or provide an inaccurate /Count value.
        declared_pages = reader.trailer["/Root"]["/Pages"].get("/Count")
        if isinstance(declared_pages, int) and declared_pages > MAX_PDF_PAGES:
            raise FinanceError("PDF contains too many pages. Limit is 100.")
        pages = reader.pages
        if len(pages) > MAX_PDF_PAGES:
            raise FinanceError("PDF contains too many pages. Limit is 100.")
    except FinanceError:
        raise
    except Exception:
        raise FinanceError("PDF text could not be extracted. Try CSV import or enter rows manually.")

    # Deliberately conservative candidate recognition. Statement-specific lines
    # remain only candidates; the review screen is the commit boundary.
    line_re = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s+(.+?)\s+([+-]?[0-9][0-9,]*(?:\.[0-9]{1,3})?)\s*([A-Z]{3})?\s*$")
    candidates = []
    extracted_chars = 0
    found_text = False
    try:
        for page in pages:
            page_chunks = []

            def collect_text(text, _cm, _tm, _font_dict, _font_size):
                nonlocal extracted_chars
                if not isinstance(text, str) or not text:
                    return
                extracted_chars += len(text)
                if extracted_chars > MAX_PDF_TEXT_CHARS:
                    raise _PdfTextLimitExceeded()
                page_chunks.append(text)

            page.extract_text(visitor_text=collect_text)
            page_text = "".join(page_chunks)
            if page_text.strip():
                found_text = True
            # Process and release each page's text before extracting the next.
            for line in page_text.splitlines():
                match = line_re.match(line)
                if not match:
                    continue
                raw_date, description, signed_amount, code = match.groups()
                code = (code or currency).upper()
                if not code or code not in CURRENCY_EXPONENTS:
                    continue
                try:
                    from datetime import date as _date
                    _date.fromisoformat(raw_date)
                    amount = amount_to_minor(signed_amount.lstrip("+-"), code)
                except (ValueError, FinanceError):
                    continue
                negative = signed_amount.startswith("-")
                candidates.append({"transaction_date":raw_date,"type":"expense" if negative else "income",
                                   "amount":minor_to_decimal_string(amount,code),"currency":code,
                                   "wallet_id":default_wallet,"description":description.strip()})
                if len(candidates) > 5000:
                    raise FinanceError("PDF contains more than 5000 candidate rows.")
    except _PdfTextLimitExceeded:
        raise FinanceError("PDF text exceeds the 2,000,000 character processing limit.")
    except FinanceError:
        raise
    except Exception:
        raise FinanceError("PDF text could not be extracted. Try CSV import or enter rows manually.")
    if not found_text:
        raise FinanceError("No selectable text was found. Scanned PDFs need OCR, which this app does not run.")
    if not candidates:
        raise FinanceError("No recognizable transaction rows were found. PDF layouts vary; try CSV import or enter rows manually.")
    return candidates


def encrypt_backup(passphrase: str) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 12 or len(passphrase) > 1024:
        raise FinanceError("Use a backup passphrase of 12 to 1024 characters.")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError:
        raise FinanceError("Encrypted backups are unavailable. Install the listed cryptography dependency.")
    payload = serialize_json_limited(STORE.backup_payload(
                                        max_bytes=MAX_BACKUP_PAYLOAD_BYTES,
                                        size_error="Backup data exceeds the 5 MiB limit."), MAX_BACKUP_PAYLOAD_BYTES,
                                     "Backup data exceeds the 5 MiB limit.")
    salt, nonce = os.urandom(16), os.urandom(12)
    aad = b"wealth-app-backup:v1"
    envelope = {"format":"wealth-app-encrypted-backup","version":1,"kdf":"scrypt","n":2**15,"r":8,"p":1,
                "salt":base64.b64encode(salt).decode("ascii"),"cipher":"AES-256-GCM",
                "nonce":base64.b64encode(nonce).decode("ascii"),"ciphertext":""}
    envelope_prefix = json.dumps(envelope,separators=(",",":" )).encode("utf-8")
    encoded_ciphertext_bytes = 4 * ((len(payload) + 16 + 2) // 3)
    if len(envelope_prefix) + encoded_ciphertext_bytes > MAX_BACKUP_ARCHIVE_BYTES:
        raise FinanceError("Encrypted backup exceeds the 8 MiB limit.")
    key = Scrypt(salt=salt,length=32,n=2**15,r=8,p=1).derive(passphrase.encode("utf-8"))
    ciphertext = AESGCM(key).encrypt(nonce,payload,aad)
    envelope["ciphertext"] = base64.b64encode(ciphertext).decode("ascii")
    raw = json.dumps(envelope,separators=(",",":" )).encode("utf-8")
    if len(raw) > MAX_BACKUP_ARCHIVE_BYTES:
        raise FinanceError("Encrypted backup exceeds the 8 MiB limit.")
    return raw


def serialize_json_limited(value: Any, max_bytes: int, message: str) -> bytes:
    """Serialize JSON incrementally without building an unbounded JSON string."""
    output = bytearray()
    encoder = json.JSONEncoder(separators=(",",":"), ensure_ascii=False)
    for chunk in encoder.iterencode(value):
        encoded = chunk.encode("utf-8")
        if len(output) + len(encoded) > max_bytes:
            raise FinanceError(message)
        output.extend(encoded)
    return bytes(output)


def decode_backup_content(encoded: Any) -> bytes:
    if not isinstance(encoded, str):
        raise FinanceError("Backup file is invalid.")
    if len(encoded) > MAX_BACKUP_BASE64_CHARS:
        raise FinanceError("Backup file exceeds the 8 MiB limit.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise FinanceError("Backup file could not be read.")
    if len(raw) > MAX_BACKUP_ARCHIVE_BYTES:
        raise FinanceError("Backup file exceeds the 8 MiB limit.")
    return raw


def decrypt_backup(raw: bytes, passphrase: str) -> Dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)):
        raise FinanceError("Backup file is invalid.")
    if len(raw) > MAX_BACKUP_ARCHIVE_BYTES:
        raise FinanceError("Backup file exceeds the 8 MiB limit.")
    try:
        envelope=json.loads(raw.decode("utf-8"))
        if envelope.get("format")!="wealth-app-encrypted-backup" or envelope.get("version")!=1 or envelope.get("cipher")!="AES-256-GCM" or envelope.get("kdf")!="scrypt":
            raise FinanceError("Backup format or version is unsupported.")
        n,r,p=int(envelope["n"]),int(envelope["r"]),int(envelope["p"])
        # Version 1 backups are generated with these fixed work factors. Do not
        # let an untrusted archive request much larger scrypt memory/CPU costs.
        if (n,r,p)!=(2**15,8,1):
            raise FinanceError("Backup encryption parameters are unsupported.")
        salt=base64.b64decode(envelope["salt"],validate=True)
        nonce=base64.b64decode(envelope["nonce"],validate=True)
        ciphertext_text=envelope["ciphertext"]
        max_ciphertext_chars=4*((MAX_BACKUP_PAYLOAD_BYTES+16+2)//3)
        if not isinstance(ciphertext_text,str) or len(ciphertext_text)>max_ciphertext_chars:
            raise FinanceError("Decrypted backup data exceeds the 5 MiB limit.")
        ciphertext=base64.b64decode(ciphertext_text,validate=True)
        if len(salt)!=16 or len(nonce)!=12 or len(ciphertext)<16:
            raise FinanceError("Backup structure is invalid.")
        if len(ciphertext)-16>MAX_BACKUP_PAYLOAD_BYTES:
            raise FinanceError("Decrypted backup data exceeds the 5 MiB limit.")
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        key=Scrypt(salt=salt,length=32,n=n,r=r,p=p).derive(passphrase.encode("utf-8"))
        payload=AESGCM(key).decrypt(nonce,ciphertext,b"wealth-app-backup:v1")
        if len(payload)>MAX_BACKUP_PAYLOAD_BYTES:
            raise FinanceError("Decrypted backup data exceeds the 5 MiB limit.")
        return json.loads(payload.decode("utf-8"))
    except FinanceError:
        raise
    except Exception:
        raise FinanceError("Could not decrypt backup. Check the passphrase and file.")


class AppServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "WealthApp/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:
        # Do not send URL query strings or request data to logs.
        return

    def _headers(self, content_type: str = "application/json; charset=utf-8", length: Optional[int] = None) -> None:
        self.send_header("Content-Type",content_type)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if length is not None:
            self.send_header("Content-Length",str(length))

    def _json(self, status: int, body: Any) -> None:
        raw=json.dumps(body,separators=(",",":"),ensure_ascii=False,default=str).encode("utf-8")
        self.send_response(status)
        self._headers(length=len(raw))
        self.end_headers()
        self.wfile.write(raw)

    def _bytes(self, status: int, raw: bytes, content_type: str, disposition: Optional[str] = None) -> None:
        self.send_response(status)
        self._headers(content_type,length=len(raw))
        if disposition:
            self.send_header("Content-Disposition",disposition)
        self.end_headers()
        self.wfile.write(raw)

    def _body(self) -> Dict[str, Any]:
        try:
            size=int(self.headers.get("Content-Length","0"))
        except ValueError:
            raise FinanceError("Request size is invalid.")
        if size<=0 or size>MAX_JSON_BYTES:
            raise FinanceError("Request is empty or too large.")
        if "application/json" not in self.headers.get("Content-Type","").lower():
            raise FinanceError("Request must use JSON content type.")
        try:
            obj=json.loads(self.rfile.read(size).decode("utf-8"))
        except (UnicodeDecodeError,json.JSONDecodeError):
            raise FinanceError("Request data is invalid.")
        if not isinstance(obj,dict):
            raise FinanceError("Request data is invalid.")
        return obj

    def _check_host(self) -> None:
        bind_host, bind_port = self.server.server_address[:2]
        if bind_host != "127.0.0.1":
            raise FinanceError("This local app accepts requests only through its loopback address.")
        allowed_hosts = {"127.0.0.1:{}".format(bind_port), "localhost:{}".format(bind_port)}
        get_all = getattr(self.headers, "get_all", None)
        host_values = get_all("Host") if get_all else None
        if host_values is not None and len(host_values) != 1:
            raise FinanceError("This local app accepts requests only through its loopback address.")
        host=self.headers.get("Host","")
        if not isinstance(host,str) or host.lower() not in allowed_hosts:
            raise FinanceError("This local app accepts requests only through its loopback address.")

    def _check_origin(self) -> None:
        self._check_host()
        _, bind_port = self.server.server_address[:2]
        origin=self.headers.get("Origin")
        loopback_origins = {"http://127.0.0.1:{}".format(bind_port), "http://localhost:{}".format(bind_port)}
        if origin and origin not in loopback_origins:
            raise FinanceError("Cross-origin requests are not allowed.")

    def do_GET(self) -> None:
        try:
            parsed=urlsplit(self.path)
            path=parsed.path
            qs=parse_qs(parsed.query,keep_blank_values=False)
            if path.startswith("/api/"):
                self._check_host()
            if path=="/":
                raw=(STATIC/"index.html").read_bytes()
                self._bytes(200,raw,"text/html; charset=utf-8")
                return
            if path in ("/app.css","/components.css","/app.js","/manifest.webmanifest","/service-worker.js"):
                file=STATIC/path.lstrip("/")
                if not file.is_file() or file.parent.resolve()!=STATIC.resolve():
                    self._json(404,{"error":"Not found."})
                    return
                kind={".css":"text/css; charset=utf-8",".js":"text/javascript; charset=utf-8",".webmanifest":"application/manifest+json; charset=utf-8"}.get(file.suffix,"text/plain; charset=utf-8")
                self._bytes(200,file.read_bytes(),kind)
                return
            if path=="/api/health":
                self._json(200,{"ok":True,"mode":"local_only"})
                return
            if path=="/api/bootstrap":
                today=date.today()
                start=today.replace(day=1).isoformat()
                self._json(200,{"dashboard":STORE.dashboard(start,today.isoformat()),"wallets":STORE.list_wallets(),
                                "categories":STORE.list_categories(),"budgets":STORE.list_budgets(),
                                "transactions":STORE.list_transactions({"limit":50}),
                                "currencies":[{"code":k,"exponent":v} for k,v in CURRENCY_EXPONENTS.items()]})
                return
            if path=="/api/transactions":
                self._json(200,STORE.list_transactions({k:v[0] for k,v in qs.items()}))
                return
            if path=="/api/reports":
                start=(qs.get("from") or [date.today().replace(day=1).isoformat()])[0]
                end=(qs.get("to") or [date.today().isoformat()])[0]
                self._json(200,STORE.report_data(start,end))
                return
            if path=="/api/imports/template.csv":
                text="transaction_date,type,amount,currency,wallet,category,description,notes\n2026-01-15,expense,12.50,EUR,Daily cash,Food & dining,Lunch,\n"
                self._bytes(200,text.encode("utf-8"),"text/csv; charset=utf-8",'attachment; filename="wealth-app-import-template.csv"')
                return
            if path=="/api/transactions/export.csv":
                start=(qs.get("from") or [None])[0]
                end=(qs.get("to") or [None])[0]
                text=STORE.export_csv(start,end)
                self._bytes(200,text.encode("utf-8"),"text/csv; charset=utf-8",'attachment; filename="wealth-app-transactions.csv"')
                return
            if path=="/api/settings":
                self._json(200,{"mode":"local_only","sync":{"configured":False,"label":"Remote sync not configured"},
                                "backup":{"manual_encrypted":True,"pcloud_oauth":False},
                                "data_dir":"local application data","currency_options":list(CURRENCY_EXPONENTS)})
                return
            self._json(404,{"error":"Not found."})
        except FinanceError as exc:
            self._json(400,{"error":str(exc)})
        except (BrokenPipeError,ConnectionResetError):
            return
        except Exception:
            self._json(500,{"error":"Something went wrong. Try again."})

    def do_POST(self) -> None:
        try:
            self._check_origin()
            path=urlsplit(self.path).path
            data=self._body()
            if path=="/api/wallets":
                self._json(201,STORE.create_wallet(data));return
            if path=="/api/categories":
                self._json(201,STORE.create_category(data));return
            if path=="/api/transactions":
                with STORE._write() as c:
                    result=STORE.idempotent_execute(c,self.headers.get("Idempotency-Key"),"transaction.create",data,
                        lambda conn:STORE.create_transaction(data,c=conn),lambda conn,rid:STORE.get_transaction(rid,conn))
                self._json(201,result);return
            if path=="/api/transfers":
                with STORE._write() as c:
                    result=STORE.idempotent_execute(c,self.headers.get("Idempotency-Key"),"transfer.create",data,
                        lambda conn:STORE.create_transfer(data,conn),lambda conn,rid:STORE._get_transfer_with(conn,rid))
                self._json(201,result);return
            if path=="/api/budgets":
                self._json(201,STORE.create_budget(data));return
            if path=="/api/imports/csv/preview":
                text=data.get("content")
                if not isinstance(text,str):raise FinanceError("CSV content is missing.")
                delimiter=data.get("delimiter",",")
                rows=parse_csv_text(text,delimiter)
                review=STORE.begin_import("csv_import",rows)
                review["delimiter"]=delimiter
                self._json(201,review);return
            if path=="/api/imports/pdf/preview":
                rows=parse_pdf_candidates(data.get("content_base64"),data.get("wallet_id"),data.get("currency"))
                self._json(201,STORE.begin_import("pdf_import",rows));return
            if path=="/api/backup/create":
                raw=encrypt_backup(data.get("passphrase"))
                self._bytes(200,raw,"application/vnd.wealth-app.backup+json",'attachment; filename="wealth-app-backup.wbackup"');return
            if path=="/api/backup/preview":
                raw=decode_backup_content(data.get("content_base64"))
                payload=decrypt_backup(raw,data.get("passphrase",""))
                preview=STORE.preview_restore(payload)
                self._json(200,{"preview":preview});return
            if path.startswith("/api/imports/") and path.endswith("/commit"):
                batch_id=unquote(path[len("/api/imports/"):-len("/commit")].strip("/"))
                self._json(200,STORE.commit_import(batch_id,data.get("rows") or []));return
            if path.startswith("/api/imports/") and path.endswith("/cancel"):
                batch_id=unquote(path[len("/api/imports/"):-len("/cancel")].strip("/"))
                STORE.cancel_import(batch_id);self._json(200,{"status":"cancelled"});return
            if path=="/api/backup/restore":
                raw=decode_backup_content(data.get("content_base64"))
                payload=decrypt_backup(raw,data.get("passphrase",""))
                mode=data.get("mode")
                if mode=="replace" and data.get("confirmation")!="REPLACE MY DATA":
                    raise FinanceError("Type REPLACE MY DATA to confirm replacement.")
                self._json(200,STORE.restore_payload(payload,mode));return
            self._json(404,{"error":"Not found."})
        except FinanceError as exc:
            self._json(400,{"error":str(exc)})
        except (ValueError,TypeError,binascii.Error):
            self._json(400,{"error":"Request data is invalid."})
        except Exception:
            self._json(500,{"error":"Something went wrong. Try again."})

    def do_PATCH(self) -> None:
        try:
            self._check_origin()
            path=urlsplit(self.path).path
            data=self._body()
            parts=path.strip("/").split("/")
            if len(parts)==3 and parts[0]=="api" and parts[1]=="wallets":
                self._json(200,STORE.update_wallet(unquote(parts[2]),data));return
            if len(parts)==3 and parts[0]=="api" and parts[1]=="categories":
                self._json(200,STORE.update_category(unquote(parts[2]),data));return
            if len(parts)==3 and parts[0]=="api" and parts[1]=="transactions":
                self._json(200,STORE.update_transaction(unquote(parts[2]),data));return
            if len(parts)==3 and parts[0]=="api" and parts[1]=="transfers":
                self._json(200,STORE.update_transfer(unquote(parts[2]),data));return
            if len(parts)==3 and parts[0]=="api" and parts[1]=="budgets":
                self._json(200,STORE.update_budget(unquote(parts[2]),data));return
            self._json(404,{"error":"Not found."})
        except FinanceError as exc:
            self._json(400,{"error":str(exc)})
        except Exception:
            self._json(500,{"error":"Something went wrong. Try again."})

    def do_DELETE(self) -> None:
        try:
            self._check_origin()
            parts=urlsplit(self.path).path.strip("/").split("/")
            if len(parts)==3 and parts[:2]==["api","transactions"]:
                STORE.delete_transaction(unquote(parts[2]));self._json(200,{"status":"deleted"});return
            if len(parts)==3 and parts[:2]==["api","transfers"]:
                transfer_id=unquote(parts[2])
                with STORE._write() as c:
                    if not c.execute("SELECT 1 FROM transfers WHERE id=? AND owner_id=?",(transfer_id,"local")).fetchone():
                        raise FinanceError("Transfer is unavailable.")
                    c.execute("DELETE FROM transfers WHERE id=?",(transfer_id,))
                self._json(200,{"status":"deleted"});return
            self._json(404,{"error":"Not found."})
        except FinanceError as exc:
            self._json(400,{"error":str(exc)})
        except Exception:
            self._json(500,{"error":"Something went wrong. Try again."})

    def do_OPTIONS(self) -> None:
        if urlsplit(self.path).path.startswith("/api/"):
            try:
                self._check_host()
            except FinanceError as exc:
                self._json(400,{"error":str(exc)})
                return
        self._json(405,{"error":"Method not allowed."})


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    if host not in ("127.0.0.1",):
        raise SystemExit("The app may only bind to 127.0.0.1 in this local mode.")
    server=AppServer((host,port),Handler)
    print("Wealth app ready at http://127.0.0.1:{}".format(port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        STORE.close()


if __name__=="__main__":
    serve()
