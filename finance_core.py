"""Local-first finance domain and SQLite persistence.

Money is stored and calculated as integer minor units. This module never logs
record content; callers are responsible for keeping API errors value-free.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timezone
from calendar import monthrange
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


class FinanceError(ValueError):
    """A safe, user-facing validation or domain error."""


CURRENCY_EXPONENTS = {
    "EUR": 2, "USD": 2, "GBP": 2, "CAD": 2, "AUD": 2, "CHF": 2,
    "NZD": 2, "INR": 2, "JPY": 0, "KRW": 0, "KWD": 3, "BHD": 3,
    "SEK": 2, "NOK": 2, "DKK": 2, "SGD": 2, "HKD": 2, "CNY": 2,
}
WALLET_TYPES = {"cash", "checking", "savings", "credit", "other"}
TRANSACTION_TYPES = {"expense", "income"}
MAX_MINOR = 10**15
LOCAL_OWNER = "local"
MAX_BACKUP_PAYLOAD_BYTES = 5 * 1024 * 1024


def formula_safe_csv_cell(value: Any) -> str:
    """Keep spreadsheet software from evaluating user-controlled CSV text."""
    text = "" if value is None else str(value)
    probe = text.lstrip(" \t\r\n")
    if text.startswith(("\t", "\r", "\n")) or probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def validate_date(value: Any, label: str = "Date") -> str:
    if not isinstance(value, str):
        raise FinanceError("Enter a valid date.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise FinanceError("Enter a valid date.")


def currency_exponent(currency: Any) -> int:
    code = str(currency or "").upper()
    if code not in CURRENCY_EXPONENTS:
        raise FinanceError("Choose a supported currency.")
    return CURRENCY_EXPONENTS[code]


def amount_to_minor(value: Any, currency: str, allow_negative: bool = False) -> int:
    exponent = currency_exponent(currency)
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, AttributeError):
        raise FinanceError("Enter a valid amount.")
    if not amount.is_finite():
        raise FinanceError("Enter a valid amount.")
    if not allow_negative and amount <= 0:
        raise FinanceError("Amount must be greater than zero.")
    if abs(amount) > Decimal(MAX_MINOR) / (Decimal(10) ** exponent):
        raise FinanceError("Amount is too large.")
    scaled = amount * (Decimal(10) ** exponent)
    if scaled != scaled.to_integral_value(rounding=ROUND_HALF_UP):
        raise FinanceError("Amount has too many decimal places for this currency.")
    return int(scaled)


def minor_to_decimal_string(value: int, currency: str) -> str:
    exponent = currency_exponent(currency)
    sign = "-" if value < 0 else ""
    n = abs(int(value))
    if exponent == 0:
        return sign + str(n)
    base = 10**exponent
    return "{}{}.{:0{}d}".format(sign, n // base, n % base, exponent)


def safe_text(value: Any, label: str, maximum: int, required: bool = False) -> Optional[str]:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise FinanceError("Enter valid text.")
    cleaned = value.strip()
    if required and not cleaned:
        raise FinanceError("{} is required.".format(label))
    if len(cleaned) > maximum:
        raise FinanceError("{} is too long.".format(label))
    return cleaned or None


def row_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


class FinanceStore:
    def __init__(self, db_path: str = "instance/wealth_app.sqlite3") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA busy_timeout = 10000")
        if self.db_path != ":memory:":
            self.conn.execute("PRAGMA journal_mode = WAL")
        self._initialize()
        if self.db_path != ":memory:":
            try:
                Path(self.db_path).chmod(0o600)
            except OSError:
                pass

    def close(self) -> None:
        with self._lock:
            self.conn.close()

    @contextmanager
    def _write(self):
        with self._lock:
            self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def _initialize(self) -> None:
        with self._write() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS wallets (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                    type TEXT NOT NULL, currency TEXT NOT NULL,
                    opening_balance_minor INTEGER NOT NULL DEFAULT 0,
                    opening_date TEXT NOT NULL, archived_at TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS categories (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                    kind TEXT NOT NULL, parent_id TEXT REFERENCES categories(id),
                    icon TEXT NOT NULL DEFAULT 'circle', color TEXT NOT NULL DEFAULT '#8b7cf6',
                    is_system INTEGER NOT NULL DEFAULT 0, archived_at TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS transfers (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    source_wallet_id TEXT NOT NULL REFERENCES wallets(id),
                    destination_wallet_id TEXT NOT NULL REFERENCES wallets(id),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL, transaction_date TEXT NOT NULL,
                    note TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    wallet_id TEXT NOT NULL REFERENCES wallets(id),
                    type TEXT NOT NULL CHECK(type IN ('expense','income','transfer')),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL, transaction_date TEXT NOT NULL,
                    category_id TEXT REFERENCES categories(id),
                    description TEXT, payee TEXT, notes TEXT, tags TEXT,
                    source TEXT NOT NULL DEFAULT 'manual', import_batch_id TEXT,
                    fingerprint TEXT, transfer_id TEXT REFERENCES transfers(id) ON DELETE CASCADE,
                    transfer_side TEXT CHECK(transfer_side IN ('out','in') OR transfer_side IS NULL),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    deleted_at TEXT, version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_wallet_date
                    ON transactions(owner_id, wallet_id, transaction_date DESC);
                CREATE INDEX IF NOT EXISTS idx_transactions_date_type
                    ON transactions(owner_id, transaction_date DESC, type);
                CREATE INDEX IF NOT EXISTS idx_transactions_category
                    ON transactions(owner_id, category_id, transaction_date DESC);
                CREATE INDEX IF NOT EXISTS idx_transactions_fingerprint
                    ON transactions(owner_id, fingerprint);
                CREATE TABLE IF NOT EXISTS budgets (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                    period TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL, scope TEXT NOT NULL,
                    category_id TEXT REFERENCES categories(id),
                    wallet_id TEXT REFERENCES wallets(id), rollover INTEGER NOT NULL DEFAULT 0,
                    archived_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS import_batches (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, source_type TEXT NOT NULL,
                    status TEXT NOT NULL, created_at TEXT NOT NULL,
                    completed_at TEXT, accepted_count INTEGER NOT NULL DEFAULT 0,
                    skipped_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS import_rows (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
                    row_number INTEGER NOT NULL, transaction_date TEXT, type TEXT,
                    amount_minor INTEGER, currency TEXT, wallet_id TEXT, category_id TEXT,
                    description TEXT, notes TEXT, warnings TEXT NOT NULL DEFAULT '[]',
                    accepted INTEGER NOT NULL DEFAULT 1, committed_transaction_id TEXT,
                    fingerprint TEXT
                );
                CREATE TABLE IF NOT EXISTS idempotency_keys (
                    key TEXT PRIMARY KEY, owner_id TEXT NOT NULL, operation TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, resource_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            version = c.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
            if version is None:
                c.execute("INSERT INTO schema_version(version) VALUES (1)")
            count = c.execute("SELECT COUNT(*) AS n FROM categories WHERE owner_id=?", (LOCAL_OWNER,)).fetchone()["n"]
            if count == 0:
                self._seed_categories(c)

    def _seed_categories(self, c: sqlite3.Connection) -> None:
        ts = now_iso()
        defaults = [
            ("Home", "expense", "home", "#5f8df7"),
            ("Food & dining", "expense", "utensils", "#f39a63"),
            ("Transport", "expense", "train", "#5bb8a6"),
            ("Shopping", "expense", "bag", "#df78a8"),
            ("Health", "expense", "heart", "#ef7777"),
            ("Entertainment", "expense", "sparkles", "#967df0"),
            ("Utilities", "expense", "bolt", "#56a4d7"),
            ("Travel", "expense", "plane", "#7b9b69"),
            ("Other expense", "expense", "circle", "#8b7cf6"),
            ("Salary", "income", "briefcase", "#34a886"),
            ("Other income", "income", "plus-circle", "#56a4d7"),
        ]
        for name, kind, icon, color in defaults:
            c.execute("INSERT INTO categories(id,owner_id,name,kind,icon,color,is_system,created_at,updated_at) VALUES(?,?,?,?,?,?,1,?,?)",
                      (new_id(), LOCAL_OWNER, name, kind, icon, color, ts, ts))

    def _wallet(self, c: sqlite3.Connection, wallet_id: str, include_archived: bool = False) -> sqlite3.Row:
        row = c.execute("SELECT * FROM wallets WHERE id=? AND owner_id=?", (wallet_id, LOCAL_OWNER)).fetchone()
        if row is None or (row["archived_at"] and not include_archived):
            raise FinanceError("Wallet is unavailable.")
        return row

    def _category(self, c: sqlite3.Connection, category_id: Optional[str], kind: Optional[str] = None) -> Optional[sqlite3.Row]:
        if not category_id:
            return None
        row = c.execute("SELECT * FROM categories WHERE id=? AND owner_id=?", (category_id, LOCAL_OWNER)).fetchone()
        if row is None or row["archived_at"]:
            raise FinanceError("Category is unavailable.")
        if kind and row["kind"] not in (kind, "both"):
            raise FinanceError("Choose a category that matches the transaction type.")
        return row

    def wallet_balance(self, wallet_id: str) -> int:
        with self._lock:
            row = self.conn.execute("""
                SELECT w.opening_balance_minor + COALESCE(SUM(
                    CASE WHEN t.type='income' THEN t.amount_minor
                         WHEN t.type='expense' THEN -t.amount_minor
                         WHEN t.type='transfer' AND t.transfer_side='in' THEN t.amount_minor
                         WHEN t.type='transfer' AND t.transfer_side='out' THEN -t.amount_minor
                         ELSE 0 END),0) AS balance
                FROM wallets w LEFT JOIN transactions t
                    ON t.wallet_id=w.id AND t.deleted_at IS NULL
                WHERE w.id=? AND w.owner_id=? GROUP BY w.id
            """, (wallet_id, LOCAL_OWNER)).fetchone()
        if row is None:
            raise FinanceError("Wallet is unavailable.")
        return int(row["balance"])

    def list_wallets(self, include_archived: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute("""
                SELECT w.*, w.opening_balance_minor + COALESCE(SUM(
                    CASE WHEN t.type='income' THEN t.amount_minor
                         WHEN t.type='expense' THEN -t.amount_minor
                         WHEN t.type='transfer' AND t.transfer_side='in' THEN t.amount_minor
                         WHEN t.type='transfer' AND t.transfer_side='out' THEN -t.amount_minor
                         ELSE 0 END),0) AS balance_minor
                FROM wallets w LEFT JOIN transactions t
                    ON t.wallet_id=w.id AND t.deleted_at IS NULL
                WHERE w.owner_id=? GROUP BY w.id ORDER BY w.archived_at IS NOT NULL, w.created_at
            """, (LOCAL_OWNER,)).fetchall()
        return [dict(r) for r in rows if include_archived or not r["archived_at"]]

    def create_wallet(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = safe_text(data.get("name"), "Wallet name", 80, True)
        wallet_type = str(data.get("type") or "").lower()
        if wallet_type not in WALLET_TYPES:
            raise FinanceError("Choose a wallet type.")
        currency = str(data.get("currency") or "").upper()
        opening = amount_to_minor(data.get("opening_balance", "0"), currency, allow_negative=True)
        opening_date = validate_date(data.get("opening_date") or date.today().isoformat())
        ts, wid = now_iso(), new_id()
        with self._write() as c:
            c.execute("INSERT INTO wallets(id,owner_id,name,type,currency,opening_balance_minor,opening_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (wid, LOCAL_OWNER, name, wallet_type, currency, opening, opening_date, ts, ts))
        return next(w for w in self.list_wallets() if w["id"] == wid)

    def update_wallet(self, wallet_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._write() as c:
            old = self._wallet(c, wallet_id, include_archived=True)
            name = safe_text(data.get("name", old["name"]), "Wallet name", 80, True)
            wallet_type = str(data.get("type", old["type"])).lower()
            if wallet_type not in WALLET_TYPES:
                raise FinanceError("Choose a wallet type.")
            currency = str(data.get("currency", old["currency"])).upper()
            currency_exponent(currency)
            if currency != old["currency"] and c.execute("SELECT 1 FROM transactions WHERE wallet_id=? LIMIT 1", (wallet_id,)).fetchone():
                raise FinanceError("Currency cannot change after a wallet has transactions.")
            opening = amount_to_minor(data.get("opening_balance", minor_to_decimal_string(old["opening_balance_minor"], old["currency"])), currency, allow_negative=True)
            opening_date = validate_date(data.get("opening_date", old["opening_date"]))
            archived = data.get("archived", bool(old["archived_at"]))
            archived_at = now_iso() if archived and not old["archived_at"] else (old["archived_at"] if archived else None)
            c.execute("UPDATE wallets SET name=?,type=?,currency=?,opening_balance_minor=?,opening_date=?,archived_at=?,updated_at=?,version=version+1 WHERE id=?",
                      (name, wallet_type, currency, opening, opening_date, archived_at, now_iso(), wallet_id))
        return next(w for w in self.list_wallets() if w["id"] == wallet_id)

    def list_categories(self, include_archived: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM categories WHERE owner_id=? ORDER BY kind,name", (LOCAL_OWNER,)).fetchall()
        return [dict(r) for r in rows if include_archived or not r["archived_at"]]

    def create_category(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = safe_text(data.get("name"), "Category name", 60, True)
        kind = data.get("kind")
        if kind not in ("expense", "income", "both"):
            raise FinanceError("Choose a category type.")
        parent_id = data.get("parent_id") or None
        icon = safe_text(data.get("icon", "circle"), "Icon", 32, True)
        color = str(data.get("color", "#8b7cf6"))
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise FinanceError("Choose a valid category color.")
        ts, cid = now_iso(), new_id()
        with self._write() as c:
            if parent_id:
                parent = self._category(c, parent_id)
                if parent["parent_id"]:
                    raise FinanceError("Subcategories can only be one level deep.")
                if parent["kind"] not in (kind, "both") and kind != "both":
                    raise FinanceError("Parent and subcategory types must be compatible.")
            duplicate = c.execute("SELECT 1 FROM categories WHERE owner_id=? AND lower(name)=lower(?) AND kind=? AND archived_at IS NULL",
                                  (LOCAL_OWNER, name, kind)).fetchone()
            if duplicate:
                raise FinanceError("A category with that name already exists.")
            c.execute("INSERT INTO categories(id,owner_id,name,kind,parent_id,icon,color,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                      (cid, LOCAL_OWNER, name, kind, parent_id, icon, color, ts, ts))
            row = c.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()
        return dict(row)

    def update_category(self, category_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._write() as c:
            old = self._category(c, category_id)
            name = safe_text(data.get("name", old["name"]), "Category name", 60, True)
            kind = data.get("kind", old["kind"])
            if kind not in ("expense", "income", "both"):
                raise FinanceError("Choose a category type.")
            parent_id = data.get("parent_id", old["parent_id"]) or None
            if parent_id:
                if parent_id == category_id:
                    raise FinanceError("A category cannot be its own parent.")
                parent = self._category(c, parent_id)
                if parent["parent_id"]:
                    raise FinanceError("Subcategories can only be one level deep.")
                if parent["kind"] not in (kind, "both") and kind != "both":
                    raise FinanceError("Parent and subcategory types must be compatible.")
            has_children = c.execute("SELECT 1 FROM categories WHERE parent_id=? LIMIT 1", (category_id,)).fetchone()
            if has_children and parent_id:
                raise FinanceError("A category with subcategories cannot become a subcategory.")
            if has_children:
                children = c.execute("SELECT kind FROM categories WHERE parent_id=?", (category_id,)).fetchall()
                incompatible = any(
                    kind not in (child["kind"], "both") and child["kind"] != "both"
                    for child in children
                )
                if incompatible:
                    raise FinanceError("Category type cannot change because it would make a subcategory incompatible.")
            icon = safe_text(data.get("icon", old["icon"]), "Icon", 32, True)
            color = str(data.get("color", old["color"]))
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise FinanceError("Choose a valid category color.")
            archived = data.get("archived", bool(old["archived_at"]))
            archived_at = now_iso() if archived and not old["archived_at"] else (old["archived_at"] if archived else None)
            c.execute("UPDATE categories SET name=?,kind=?,parent_id=?,icon=?,color=?,archived_at=?,updated_at=?,version=version+1 WHERE id=?",
                      (name, kind, parent_id, icon, color, archived_at, now_iso(), category_id))
            row = c.execute("SELECT * FROM categories WHERE id=?", (category_id,)).fetchone()
        return dict(row)

    def _transaction_fingerprint(self, d: Dict[str, Any]) -> str:
        canonical = "|".join(str(d.get(k) or "").strip().lower() for k in ("transaction_date", "amount_minor", "currency", "wallet_id", "type", "description"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def idempotent_execute(self, c: sqlite3.Connection, key: Optional[str], operation: str,
                           payload: Dict[str, Any], action, load_result) -> Dict[str, Any]:
        if not key:
            return action(c)
        if not re.fullmatch(r"[A-Za-z0-9._:-]{16,128}", key):
            raise FinanceError("A valid idempotency key is required for this save.")
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")).hexdigest()
        existing=c.execute("SELECT * FROM idempotency_keys WHERE key=? AND owner_id=?",(key,LOCAL_OWNER)).fetchone()
        if existing:
            if existing["operation"]!=operation or existing["payload_sha256"]!=digest:
                raise FinanceError("This save key was already used for different data. Close and reopen the form to start a new save.")
            return load_result(c,existing["resource_id"])
        result=action(c)
        resource_id=result.get("id") or result.get("transfer_id")
        if not resource_id:
            raise FinanceError("The save could not be confirmed.")
        # Persist only an opaque resource ID and payload digest, never submitted text.
        c.execute("INSERT INTO idempotency_keys(key,owner_id,operation,payload_sha256,resource_id,created_at) VALUES(?,?,?,?,?,?)",
                  (key,LOCAL_OWNER,operation,digest,resource_id,now_iso()))
        return result

    def create_transaction(self, data: Dict[str, Any], source: str = "manual", batch_id: Optional[str] = None,
                           c: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        own_tx = c is None
        if own_tx:
            with self._write() as conn:
                return self.create_transaction(data, source, batch_id, conn)
        wallet = self._wallet(c, str(data.get("wallet_id") or ""))
        tx_type = str(data.get("type") or "").lower()
        if tx_type not in TRANSACTION_TYPES:
            raise FinanceError("Choose income or expense.")
        currency = str(data.get("currency") or wallet["currency"]).upper()
        if currency != wallet["currency"]:
            raise FinanceError("Transaction currency must match the wallet.")
        amount_minor = data.get("amount_minor")
        if amount_minor is None:
            amount_minor = amount_to_minor(data.get("amount"), currency)
        amount_minor = int(amount_minor)
        if amount_minor <= 0 or amount_minor > MAX_MINOR:
            raise FinanceError("Enter a valid positive amount.")
        if data.get("amount") is not None and amount_minor != amount_to_minor(data["amount"], currency):
            raise FinanceError("Enter an amount with valid currency precision.")
        tx_date = validate_date(data.get("transaction_date") or data.get("date"))
        category = self._category(c, data.get("category_id"), tx_type)
        description = safe_text(data.get("description"), "Description", 180)
        payee = safe_text(data.get("payee"), "Payee", 120)
        notes = safe_text(data.get("notes"), "Notes", 1000)
        tags = data.get("tags") or []
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or len(t) > 40 for t in tags):
            raise FinanceError("Enter valid tags.")
        ts, tid = now_iso(), new_id()
        record = {"transaction_date": tx_date, "amount_minor": amount_minor, "currency": currency,
                  "wallet_id": wallet["id"], "type": tx_type, "description": description}
        fingerprint = data.get("fingerprint") or self._transaction_fingerprint(record)
        c.execute("""INSERT INTO transactions(id,owner_id,wallet_id,type,amount_minor,currency,transaction_date,
            category_id,description,payee,notes,tags,source,import_batch_id,fingerprint,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tid, LOCAL_OWNER, wallet["id"], tx_type, amount_minor, currency, tx_date,
             category["id"] if category else None, description, payee, notes, json.dumps(tags),
             source, batch_id, fingerprint, ts, ts))
        return self.get_transaction(tid, c)

    def get_transaction(self, transaction_id: str, c: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        conn = c or self.conn
        row = conn.execute("""SELECT t.*,w.name AS wallet_name,c.name AS category_name,tr.source_wallet_id,tr.destination_wallet_id
            FROM transactions t JOIN wallets w ON w.id=t.wallet_id
            LEFT JOIN categories c ON c.id=t.category_id LEFT JOIN transfers tr ON tr.id=t.transfer_id
            WHERE t.id=? AND t.owner_id=?""", (transaction_id, LOCAL_OWNER)).fetchone()
        if row is None:
            raise FinanceError("Transaction is unavailable.")
        d = dict(row)
        try:
            d["tags"] = json.loads(d.get("tags") or "[]")
        except ValueError:
            d["tags"] = []
        return d

    def update_transaction(self, transaction_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._write() as c:
            old = c.execute("SELECT * FROM transactions WHERE id=? AND owner_id=? AND deleted_at IS NULL", (transaction_id, LOCAL_OWNER)).fetchone()
            if old is None:
                raise FinanceError("Transaction is unavailable.")
            if old["type"] == "transfer":
                raise FinanceError("Edit this transfer from its transfer details.")
            merged = dict(old)
            merged.update(data)
            wallet = self._wallet(c, str(merged["wallet_id"]))
            currency = str(merged.get("currency") or wallet["currency"]).upper()
            if currency != wallet["currency"]:
                raise FinanceError("Transaction currency must match the wallet.")
            amount = amount_to_minor(merged.get("amount", minor_to_decimal_string(old["amount_minor"], old["currency"])), currency)
            tx_date = validate_date(merged.get("transaction_date") or merged.get("date"))
            tx_type = str(merged.get("type") or old["type"])
            if tx_type not in TRANSACTION_TYPES:
                raise FinanceError("Choose income or expense.")
            category = self._category(c, merged.get("category_id"), tx_type)
            description = safe_text(merged.get("description"), "Description", 180)
            payee = safe_text(merged.get("payee"), "Payee", 120)
            notes = safe_text(merged.get("notes"), "Notes", 1000)
            tags = merged.get("tags")
            if isinstance(tags, str):
                tags = json.loads(tags or "[]")
            if not isinstance(tags, list) or len(tags) > 20:
                raise FinanceError("Enter valid tags.")
            record = {"transaction_date": tx_date, "amount_minor": amount, "currency": currency,
                      "wallet_id": wallet["id"], "type": tx_type, "description": description}
            c.execute("""UPDATE transactions SET wallet_id=?,type=?,amount_minor=?,currency=?,transaction_date=?,category_id=?,
                description=?,payee=?,notes=?,tags=?,fingerprint=?,updated_at=?,version=version+1 WHERE id=?""",
                (wallet["id"], tx_type, amount, currency, tx_date, category["id"] if category else None,
                 description, payee, notes, json.dumps(tags), self._transaction_fingerprint(record), now_iso(), transaction_id))
        return self.get_transaction(transaction_id)

    def delete_transaction(self, transaction_id: str) -> None:
        with self._write() as c:
            row = c.execute("SELECT * FROM transactions WHERE id=? AND owner_id=? AND deleted_at IS NULL", (transaction_id, LOCAL_OWNER)).fetchone()
            if row is None:
                raise FinanceError("Transaction is unavailable.")
            if row["transfer_id"]:
                c.execute("DELETE FROM transfers WHERE id=?", (row["transfer_id"],))
            else:
                c.execute("UPDATE transactions SET deleted_at=?,updated_at=?,version=version+1 WHERE id=?", (now_iso(), now_iso(), transaction_id))

    def create_transfer(self, data: Dict[str, Any], c: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        if c is None:
            with self._write() as conn:
                return self.create_transfer(data,conn)
        else:
            source = self._wallet(c, str(data.get("source_wallet_id") or ""))
            destination = self._wallet(c, str(data.get("destination_wallet_id") or ""))
            if source["id"] == destination["id"]:
                raise FinanceError("Choose two different wallets.")
            if source["currency"] != destination["currency"]:
                raise FinanceError("Transfers require wallets with the same currency.")
            amount = amount_to_minor(data.get("amount"), source["currency"])
            tx_date = validate_date(data.get("transaction_date") or data.get("date"))
            note = safe_text(data.get("note"), "Note", 180)
            ts, transfer_id = now_iso(), new_id()
            c.execute("INSERT INTO transfers(id,owner_id,source_wallet_id,destination_wallet_id,amount_minor,currency,transaction_date,note,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                      (transfer_id, LOCAL_OWNER, source["id"], destination["id"], amount, source["currency"], tx_date, note, ts, ts))
            for wallet_id, side in ((source["id"], "out"), (destination["id"], "in")):
                c.execute("""INSERT INTO transactions(id,owner_id,wallet_id,type,amount_minor,currency,transaction_date,
                    description,source,transfer_id,transfer_side,created_at,updated_at)
                    VALUES(?,?,?,'transfer',?,?,?,?,?,?,?, ?,?)""",
                    (new_id(), LOCAL_OWNER, wallet_id, amount, source["currency"], tx_date, "Wallet transfer", "manual", transfer_id, side, ts, ts))
        return self.get_transfer(transfer_id) if c is self.conn else self._get_transfer_with(c,transfer_id)

    def get_transfer(self, transfer_id: str) -> Dict[str, Any]:
        with self._lock:
            row = self._get_transfer_row(self.conn,transfer_id)
        if row is None:
            raise FinanceError("Transfer is unavailable.")
        return dict(row)

    @staticmethod
    def _get_transfer_row(c: sqlite3.Connection, transfer_id: str) -> Optional[sqlite3.Row]:
        return c.execute("""SELECT tr.*,s.name AS source_wallet_name,d.name AS destination_wallet_name
            FROM transfers tr JOIN wallets s ON s.id=tr.source_wallet_id
            JOIN wallets d ON d.id=tr.destination_wallet_id WHERE tr.id=? AND tr.owner_id=?""",
            (transfer_id,LOCAL_OWNER)).fetchone()

    def _get_transfer_with(self,c: sqlite3.Connection,transfer_id: str) -> Dict[str, Any]:
        row=self._get_transfer_row(c,transfer_id)
        if row is None:raise FinanceError("Transfer is unavailable.")
        return dict(row)

    def update_transfer(self, transfer_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._write() as c:
            old = c.execute("SELECT * FROM transfers WHERE id=? AND owner_id=?", (transfer_id, LOCAL_OWNER)).fetchone()
            if old is None:
                raise FinanceError("Transfer is unavailable.")
            source = self._wallet(c, str(data.get("source_wallet_id", old["source_wallet_id"])))
            dest = self._wallet(c, str(data.get("destination_wallet_id", old["destination_wallet_id"])))
            if source["id"] == dest["id"] or source["currency"] != dest["currency"]:
                raise FinanceError("Choose different wallets that share a currency.")
            amount = amount_to_minor(data.get("amount", minor_to_decimal_string(old["amount_minor"], old["currency"])), source["currency"])
            tx_date = validate_date(data.get("transaction_date", old["transaction_date"]))
            note = safe_text(data.get("note", old["note"]), "Note", 180)
            ts = now_iso()
            c.execute("UPDATE transfers SET source_wallet_id=?,destination_wallet_id=?,amount_minor=?,currency=?,transaction_date=?,note=?,updated_at=?,version=version+1 WHERE id=?",
                      (source["id"], dest["id"], amount, source["currency"], tx_date, note, ts, transfer_id))
            c.execute("UPDATE transactions SET wallet_id=?,amount_minor=?,currency=?,transaction_date=?,updated_at=?,version=version+1 WHERE transfer_id=? AND transfer_side='out'",
                      (source["id"], amount, source["currency"], tx_date, ts, transfer_id))
            c.execute("UPDATE transactions SET wallet_id=?,amount_minor=?,currency=?,transaction_date=?,updated_at=?,version=version+1 WHERE transfer_id=? AND transfer_side='in'",
                      (dest["id"], amount, source["currency"], tx_date, ts, transfer_id))
        return self.get_transfer(transfer_id)

    def list_transactions(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        filters = filters or {}
        limit = max(1, min(int(filters.get("limit", 50)), 200))
        offset = max(0, int(filters.get("offset", 0)))
        where = ["t.owner_id=?", "t.deleted_at IS NULL"]
        params: List[Any] = [LOCAL_OWNER]
        for key, col in (("wallet_id", "t.wallet_id"), ("category_id", "t.category_id"), ("type", "t.type")):
            value = filters.get(key)
            if value:
                where.append(col + "=?")
                params.append(value)
        if filters.get("from"):
            where.append("t.transaction_date>=?")
            params.append(validate_date(filters["from"]))
        if filters.get("to"):
            where.append("t.transaction_date<=?")
            params.append(validate_date(filters["to"]))
        query = safe_text(filters.get("q"), "Search", 100)
        if query:
            where.append("(t.description LIKE ? ESCAPE '\\' OR t.payee LIKE ? ESCAPE '\\' OR t.notes LIKE ? ESCAPE '\\')")
            needle = "%" + query.replace("%", "\\%").replace("_", "\\_") + "%"
            params.extend([needle] * 3)
        clause = " AND ".join(where)
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) AS n FROM transactions t WHERE " + clause, params).fetchone()["n"]
            rows = self.conn.execute("""SELECT t.*,w.name AS wallet_name,c.name AS category_name,
                tr.source_wallet_id,tr.destination_wallet_id
                FROM transactions t JOIN wallets w ON w.id=t.wallet_id
                LEFT JOIN categories c ON c.id=t.category_id LEFT JOIN transfers tr ON tr.id=t.transfer_id
                WHERE """ + clause + " ORDER BY t.transaction_date DESC,t.created_at DESC LIMIT ? OFFSET ?",
                params + [limit, offset]).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d.get("tags") or "[]")
            except ValueError:
                d["tags"] = []
            result.append(d)
        return {"items": result, "total": int(total), "limit": limit, "offset": offset}

    def create_budget(self, data: Dict[str, Any]) -> Dict[str, Any]:
        name = safe_text(data.get("name"), "Budget name", 80, True)
        period = data.get("period", "monthly")
        if period not in ("monthly", "custom"):
            raise FinanceError("Choose a supported budget period.")
        start = validate_date(data.get("start_date") or date.today().replace(day=1).isoformat())
        end = validate_date(data.get("end_date") or self._month_end(start))
        if end < start:
            raise FinanceError("End date must be on or after the start date.")
        scope = data.get("scope", "overall")
        if scope not in ("overall", "category", "wallet"):
            raise FinanceError("Choose a supported budget scope.")
        currency = str(data.get("currency") or "").upper()
        amount = amount_to_minor(data.get("amount"), currency)
        category_id = data.get("category_id") if scope == "category" else None
        wallet_id = data.get("wallet_id") if scope == "wallet" else None
        with self._write() as c:
            if scope == "category":
                cat = self._category(c, category_id, "expense")
                if not cat:
                    raise FinanceError("Choose a category for this budget.")
            if scope == "wallet":
                wallet = self._wallet(c, str(wallet_id or ""))
                if wallet["currency"] != currency:
                    raise FinanceError("Budget currency must match the wallet.")
            ts, bid = now_iso(), new_id()
            c.execute("""INSERT INTO budgets(id,owner_id,name,period,start_date,end_date,amount_minor,currency,scope,
                category_id,wallet_id,rollover,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (bid, LOCAL_OWNER, name, period, start, end, amount, currency, scope, category_id, wallet_id,
                 1 if data.get("rollover") else 0, ts, ts))
        return next(b for b in self.list_budgets() if b["id"] == bid)

    @staticmethod
    def _month_end(start: str) -> str:
        d = date.fromisoformat(start)
        return date(d.year, d.month, monthrange(d.year, d.month)[1]).isoformat()

    def list_budgets(self, active_only: bool = True) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute("""SELECT b.*,c.name AS category_name,w.name AS wallet_name FROM budgets b
                LEFT JOIN categories c ON c.id=b.category_id LEFT JOIN wallets w ON w.id=b.wallet_id
                WHERE b.owner_id=? ORDER BY b.archived_at IS NOT NULL,b.start_date DESC""", (LOCAL_OWNER,)).fetchall()
            result = []
            for row in rows:
                d = dict(row)
                if active_only and d["archived_at"]:
                    continue
                where = ["owner_id=?", "type='expense'", "deleted_at IS NULL", "transaction_date>=?", "transaction_date<=?", "currency=?"]
                params: List[Any] = [LOCAL_OWNER, d["start_date"], d["end_date"], d["currency"]]
                if d["scope"] == "category":
                    where.append("category_id=?")
                    params.append(d["category_id"])
                elif d["scope"] == "wallet":
                    where.append("wallet_id=?")
                    params.append(d["wallet_id"])
                spent = self.conn.execute("SELECT COALESCE(SUM(amount_minor),0) AS n FROM transactions WHERE " + " AND ".join(where), params).fetchone()["n"]
                d["spent_minor"] = int(spent)
                d["remaining_minor"] = int(d["amount_minor"]) - int(spent)
                d["progress_percent"] = min(100, round(int(spent) * 100 / int(d["amount_minor"])))
                result.append(d)
        return result

    def update_budget(self, budget_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._write() as c:
            old = c.execute("SELECT * FROM budgets WHERE id=? AND owner_id=?", (budget_id, LOCAL_OWNER)).fetchone()
            if old is None:
                raise FinanceError("Budget is unavailable.")
            name = safe_text(data.get("name", old["name"]), "Budget name", 80, True)
            archived = data.get("archived", bool(old["archived_at"]))
            archived_at = now_iso() if archived and not old["archived_at"] else (old["archived_at"] if archived else None)
            c.execute("UPDATE budgets SET name=?,archived_at=?,updated_at=?,version=version+1 WHERE id=?", (name, archived_at, now_iso(), budget_id))
        return next(b for b in self.list_budgets(active_only=False) if b["id"] == budget_id)

    def dashboard(self, start: Optional[str] = None, end: Optional[str] = None) -> Dict[str, Any]:
        today = date.today()
        start = validate_date(start or today.replace(day=1).isoformat())
        end = validate_date(end or today.isoformat())
        if end < start:
            raise FinanceError("Date range is invalid.")
        wallets = self.list_wallets(include_archived=False)
        with self._lock:
            totals = self.conn.execute("""SELECT currency,
                COALESCE(SUM(CASE WHEN type='income' THEN amount_minor ELSE 0 END),0) income_minor,
                COALESCE(SUM(CASE WHEN type='expense' THEN amount_minor ELSE 0 END),0) expense_minor
                FROM transactions WHERE owner_id=? AND deleted_at IS NULL AND type IN ('income','expense')
                AND transaction_date>=? AND transaction_date<=? GROUP BY currency""", (LOCAL_OWNER, start, end)).fetchall()
        summary = [{"currency": r["currency"], "income_minor": int(r["income_minor"]),
                    "expense_minor": int(r["expense_minor"]), "net_minor": int(r["income_minor"]) - int(r["expense_minor"])} for r in totals]
        budgets = self.list_budgets()
        recent = self.list_transactions({"limit": 8})["items"]
        return {"range": {"from": start, "to": end}, "wallets": wallets, "summary": summary,
                "budgets": budgets[:4], "recent": recent, "sync": {"state": "local_only", "label": "Local only"}}

    def report_data(self, start: str, end: str) -> Dict[str, Any]:
        start, end = validate_date(start), validate_date(end)
        if end < start:
            raise FinanceError("Date range is invalid.")
        with self._lock:
            categories = self.conn.execute("""SELECT t.currency,t.category_id,COALESCE(c.name,'Uncategorized') name,
                SUM(t.amount_minor) amount_minor,COUNT(*) count FROM transactions t
                LEFT JOIN categories c ON c.id=t.category_id WHERE t.owner_id=? AND t.deleted_at IS NULL
                AND t.type='expense' AND t.transaction_date>=? AND t.transaction_date<=?
                GROUP BY t.currency,t.category_id,c.name ORDER BY amount_minor DESC""", (LOCAL_OWNER,start,end)).fetchall()
            monthly = self.conn.execute("""SELECT substr(transaction_date,1,7) month,currency,
                SUM(CASE WHEN type='income' THEN amount_minor ELSE 0 END) income_minor,
                SUM(CASE WHEN type='expense' THEN amount_minor ELSE 0 END) expense_minor
                FROM transactions WHERE owner_id=? AND deleted_at IS NULL AND type IN ('income','expense')
                AND transaction_date>=? AND transaction_date<=? GROUP BY month,currency ORDER BY month""",
                (LOCAL_OWNER,start,end)).fetchall()
            by_wallet = self.conn.execute("""SELECT w.id,w.name,w.currency,
                SUM(CASE WHEN t.type='expense' THEN t.amount_minor ELSE 0 END) expense_minor,
                SUM(CASE WHEN t.type='income' THEN t.amount_minor ELSE 0 END) income_minor
                FROM wallets w LEFT JOIN transactions t ON t.wallet_id=w.id AND t.owner_id=? AND t.deleted_at IS NULL
                AND t.transaction_date>=? AND t.transaction_date<=? AND t.type IN ('expense','income')
                WHERE w.owner_id=? AND w.archived_at IS NULL GROUP BY w.id ORDER BY expense_minor DESC""",
                (LOCAL_OWNER,start,end,LOCAL_OWNER)).fetchall()
        return {"range":{"from":start,"to":end},"categories":[dict(x) for x in categories],
                "monthly":[dict(x) for x in monthly],"wallets":[dict(x) for x in by_wallet]}

    def begin_import(self, source_type: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        if source_type not in ("csv_import", "pdf_import"):
            raise FinanceError("Unsupported import type.")
        if not rows or len(rows) > 5000:
            raise FinanceError("Import needs between 1 and 5000 candidate rows.")
        batch, ts = new_id(), now_iso()
        wallets = self.list_wallets(include_archived=False)
        categories = self.list_categories(include_archived=False)
        wallet_by_name = {w["name"].casefold(): w for w in wallets}
        category_by_name = {c["name"].casefold(): c for c in categories}
        staged = []
        with self._write() as c:
            c.execute("INSERT INTO import_batches(id,owner_id,source_type,status,created_at) VALUES(?,?,?,'review',?)",
                      (batch, LOCAL_OWNER, source_type, ts))
            for index, raw in enumerate(rows, 1):
                warnings: List[str] = []
                row_id = new_id()
                try:
                    tx_date = validate_date(raw.get("transaction_date") or raw.get("date"))
                except FinanceError:
                    tx_date = None
                    warnings.append("Date needs review")
                raw_type = str(raw.get("type") or "").strip().lower()
                if raw_type in TRANSACTION_TYPES:
                    tx_type = raw_type
                elif source_type == "csv_import":
                    tx_type = None
                    if raw_type:
                        shown_type = raw_type[:40]
                        warnings.append("Unsupported transaction type '{}'; choose income or expense".format(shown_type))
                    else:
                        warnings.append("Transaction type is missing; choose income or expense")
                else:
                    tx_type = "expense"
                    warnings.append("Type needs review")
                currency = str(raw.get("currency") or "").upper()
                try:
                    amount = amount_to_minor(raw.get("amount"), currency)
                except FinanceError:
                    amount = None
                    warnings.append("Amount or currency needs review")
                wallet_id = raw.get("wallet_id")
                wallet_name = str(raw.get("wallet") or raw.get("wallet_name") or "").strip()
                if wallet_id:
                    wallet = next((w for w in wallets if w["id"] == wallet_id), None)
                else:
                    wallet = wallet_by_name.get(wallet_name.casefold()) if wallet_name else None
                if wallet is None:
                    warnings.append("Choose a wallet")
                elif currency and currency != wallet["currency"]:
                    warnings.append("Currency does not match wallet")
                category_name = str(raw.get("category") or raw.get("category_name") or "").strip()
                category_id = raw.get("category_id")
                if not category_id and category_name:
                    cat = category_by_name.get(category_name.casefold())
                    category_id = cat["id"] if cat else None
                    if cat is None:
                        warnings.append("Category not found; choose an existing category")
                description = safe_text(raw.get("description"), "Description", 180)
                notes = safe_text(raw.get("notes"), "Notes", 1000)
                row = {"id": row_id, "row_number": index, "transaction_date": tx_date, "type": tx_type,
                       "amount_minor": amount, "currency": currency or (wallet["currency"] if wallet else None),
                       "wallet_id": wallet["id"] if wallet else None, "wallet_name": wallet["name"] if wallet else None,
                       "category_id": category_id, "category_name": category_name, "description": description,
                       "notes": notes, "warnings": warnings, "accepted": not warnings}
                if amount and tx_date and wallet and tx_type:
                    candidate = {"transaction_date":tx_date,"amount_minor":amount,"currency":row["currency"],
                                 "wallet_id":wallet["id"],"type":tx_type,"description":description}
                    row["fingerprint"] = self._transaction_fingerprint(candidate)
                    duplicate = c.execute("SELECT 1 FROM transactions WHERE owner_id=? AND fingerprint=? AND deleted_at IS NULL LIMIT 1",
                                          (LOCAL_OWNER,row["fingerprint"])).fetchone()
                    if duplicate:
                        row["warnings"].append("Possible duplicate")
                        row["accepted"] = False
                c.execute("""INSERT INTO import_rows(id,batch_id,row_number,transaction_date,type,amount_minor,currency,
                    wallet_id,category_id,description,notes,warnings,accepted,fingerprint)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (row_id,batch,index,tx_date,tx_type,amount,row["currency"],row["wallet_id"],category_id,
                     description,notes,json.dumps(row["warnings"]),1 if row["accepted"] else 0,row.get("fingerprint")))
                staged.append(row)
        return {"batch_id":batch,"source_type":source_type,"status":"review","rows":staged,
                "accepted_count":sum(1 for r in staged if r["accepted"]),"review_count":sum(1 for r in staged if not r["accepted"])}

    def get_import(self, batch_id: str) -> Dict[str, Any]:
        with self._lock:
            batch = self.conn.execute("SELECT * FROM import_batches WHERE id=? AND owner_id=?", (batch_id,LOCAL_OWNER)).fetchone()
            if not batch:
                raise FinanceError("Import review is unavailable.")
            rows = self.conn.execute("SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number", (batch_id,)).fetchall()
        result=[]
        for r in rows:
            d=dict(r)
            d["warnings"]=json.loads(d["warnings"] or "[]")
            d["accepted"]=bool(d["accepted"])
            result.append(d)
        return {"batch":dict(batch),"rows":result}

    def commit_import(self, batch_id: str, rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        updates={str(r.get("id")):r for r in rows}
        committed=0
        with self._write() as c:
            batch=c.execute("SELECT * FROM import_batches WHERE id=? AND owner_id=? AND status='review'", (batch_id,LOCAL_OWNER)).fetchone()
            if not batch:
                raise FinanceError("Import review is unavailable.")
            existing=c.execute("SELECT * FROM import_rows WHERE batch_id=? ORDER BY row_number",(batch_id,)).fetchall()
            for old in existing:
                patch=updates.get(old["id"],{})
                if not patch.get("accepted",bool(old["accepted"])):
                    continue
                warnings=json.loads(old["warnings"] or "[]")
                if batch["source_type"]=="csv_import":
                    if any(w.startswith(("Transaction type is missing", "Unsupported transaction type")) for w in warnings):
                        if patch.get("type") not in TRANSACTION_TYPES:
                            raise FinanceError("Choose income or expense for every accepted row with an unresolved type.")
                    if any(w.startswith("Category not found") for w in warnings):
                        if not patch.get("category_id"):
                            raise FinanceError("Choose an existing category for every accepted row with an unmapped category.")
                data={"transaction_date":patch.get("transaction_date",old["transaction_date"]),
                      "type":patch.get("type",old["type"]),"amount_minor":patch.get("amount_minor",old["amount_minor"]),
                      "currency":patch.get("currency",old["currency"]),"wallet_id":patch.get("wallet_id",old["wallet_id"]),
                      "category_id":patch.get("category_id",old["category_id"]),
                      "description":patch.get("description",old["description"]),"notes":patch.get("notes",old["notes"])}
                if data["amount_minor"] is None or not data["wallet_id"] or not data["transaction_date"]:
                    raise FinanceError("Complete the required fields for each accepted row.")
                wallet=self._wallet(c,data["wallet_id"])
                data["currency"]=str(data["currency"] or wallet["currency"]).upper()
                if data["currency"]!=wallet["currency"]:
                    raise FinanceError("Transaction currency must match its wallet.")
                data["fingerprint"]=old["fingerprint"]
                tx=self.create_transaction(data, batch["source_type"], batch_id, c)
                c.execute("UPDATE import_rows SET committed_transaction_id=?,accepted=1 WHERE id=?",(tx["id"],old["id"]))
                committed+=1
            c.execute("UPDATE import_batches SET status='committed',completed_at=?,accepted_count=?,skipped_count=? WHERE id=?",
                      (now_iso(),committed,len(existing)-committed,batch_id))
            c.execute("DELETE FROM import_rows WHERE batch_id=?",(batch_id,))
        return {"status":"committed","accepted_count":committed,"skipped_count":len(existing)-committed}

    def cancel_import(self, batch_id: str) -> None:
        with self._write() as c:
            batch=c.execute("SELECT id,status FROM import_batches WHERE id=? AND owner_id=?",(batch_id,LOCAL_OWNER)).fetchone()
            if not batch or batch["status"]!="review":
                raise FinanceError("Import review is unavailable.")
            c.execute("UPDATE import_batches SET status='cancelled',completed_at=? WHERE id=?",(now_iso(),batch_id))
            c.execute("DELETE FROM import_rows WHERE batch_id=?",(batch_id,))

    def export_csv(self, start: Optional[str] = None, end: Optional[str] = None) -> str:
        filters={"limit":200,"offset":0}
        if start: filters["from"]=start
        if end: filters["to"]=end
        first=self.list_transactions(filters)
        if first["total"]>50000:
            raise FinanceError("Select a narrower date range. CSV export is limited to 50000 records.")
        rows=list(first["items"])
        for offset in range(200,first["total"],200):
            filters["offset"]=offset
            rows.extend(self.list_transactions(filters)["items"])
        out=io.StringIO(newline="")
        writer=csv.writer(out)
        writer.writerow(["transaction_date","type","amount","currency","wallet","category","description","notes"])
        for t in rows:
            if t["type"]=="transfer":
                continue
            values=[t["transaction_date"],t["type"],minor_to_decimal_string(t["amount_minor"],t["currency"]),
                    t["currency"],t["wallet_name"],t["category_name"] or "",t["description"] or "",t["notes"] or ""]
            writer.writerow([formula_safe_csv_cell(value) for value in values])
        return out.getvalue()

    def backup_payload(self, max_bytes: Optional[int] = MAX_BACKUP_PAYLOAD_BYTES,
                       size_error: str = "Backup data exceeds the 5 MiB limit.") -> Dict[str, Any]:
        """Build the v1 snapshot incrementally, optionally bounding its JSON size.

        The bound is measured using the same compact UTF-8 JSON encoding used
        for backup serialization. Rows are appended only after they fit, so an
        oversized snapshot stops reading the result cursor immediately.
        """
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
            raise FinanceError("Backup size limit is invalid.")
        tables=("wallets","categories","transactions","transfers","budgets")
        data={table:[] for table in tables}
        payload={"format":"wealth-app-backup","version":1,"created_at":now_iso(),"data":data}
        encoder=json.JSONEncoder(separators=(",",":"),ensure_ascii=False)
        current_size=sum(len(chunk.encode("utf-8")) for chunk in encoder.iterencode(payload))
        if max_bytes is not None and current_size > max_bytes:
            raise FinanceError(size_error)
        with self._lock:
            for table in tables:
                rows=data[table]
                cursor=self.conn.execute("SELECT * FROM {} WHERE owner_id=?".format(table),(LOCAL_OWNER,))
                for row in cursor:
                    record=dict(row)
                    item_size=0
                    comma_size=1 if rows else 0
                    for chunk in encoder.iterencode(record):
                        item_size+=len(chunk.encode("utf-8"))
                        if max_bytes is not None and current_size+comma_size+item_size > max_bytes:
                            raise FinanceError(size_error)
                    rows.append(record)
                    current_size+=comma_size+item_size
        return payload

    def preview_restore(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tables=("wallets","categories","transactions","transfers","budgets")
        if (not isinstance(payload,dict) or set(payload)!={"format","version","created_at","data"}
                or payload.get("format")!="wealth-app-backup" or type(payload.get("version")) is not int
                or payload.get("version")!=1):
            raise FinanceError("Backup format or version is unsupported.")
        data=payload.get("data")
        if not isinstance(data,dict) or set(data)!=set(tables):
            raise FinanceError("Backup structure is invalid.")

        def record_error():
            raise FinanceError("Backup contains an invalid record.")

        def valid_id(value):
            if not isinstance(value,str) or not re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",value):
                record_error()
            try:
                if str(uuid.UUID(value))!=value:
                    record_error()
            except (ValueError,AttributeError):
                record_error()
            return value

        def valid_text(value,maximum,required=False):
            if not isinstance(value,str) or len(value)>maximum or value!=value.strip() or (required and not value):
                record_error()
            if not required and not value:
                record_error()
            return value

        def valid_nullable_text(value,maximum):
            if value is not None:
                valid_text(value,maximum)

        def valid_time(value,nullable=False):
            if value is None and nullable:
                return
            if not isinstance(value,str) or len(value)>40:
                record_error()
            try:
                parsed=datetime.fromisoformat(value)
            except (ValueError,TypeError):
                record_error()
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                record_error()

        def valid_date(value):
            if not isinstance(value,str):
                record_error()
            try:
                if date.fromisoformat(value).isoformat()!=value:
                    record_error()
            except ValueError:
                record_error()

        def valid_currency(value):
            if not isinstance(value,str) or value not in CURRENCY_EXPONENTS:
                record_error()

        def valid_integer(value,minimum=None,maximum=None):
            if type(value) is not int or (minimum is not None and value<minimum) or (maximum is not None and value>maximum):
                record_error()

        def valid_timestamp_field(row,key,nullable=False):
            valid_time(row[key],nullable)

        field_sets={
            "wallets":set("id owner_id name type currency opening_balance_minor opening_date archived_at created_at updated_at version".split()),
            "categories":set("id owner_id name kind parent_id icon color is_system archived_at created_at updated_at version".split()),
            "transactions":set("id owner_id wallet_id type amount_minor currency transaction_date category_id description payee notes tags source import_batch_id fingerprint transfer_id transfer_side created_at updated_at deleted_at version".split()),
            "transfers":set("id owner_id source_wallet_id destination_wallet_id amount_minor currency transaction_date note created_at updated_at version".split()),
            "budgets":set("id owner_id name period start_date end_date amount_minor currency scope category_id wallet_id rollover archived_at created_at updated_at version".split()),
        }
        validated={}
        for table in tables:
            rows=data[table]
            if not isinstance(rows,list) or len(rows)>100000:
                raise FinanceError("Backup contains too many records or has an invalid structure.")
            ids=set()
            for row in rows:
                if not isinstance(row,dict) or set(row)-field_sets[table] or field_sets[table]-set(row)-{"owner_id"}:
                    raise FinanceError("Backup record structure is invalid.")
                if "owner_id" in row and row["owner_id"] not in (None,LOCAL_OWNER):
                    raise FinanceError("Backup owner scope is invalid.")
                record_id=valid_id(row["id"])
                if record_id in ids:
                    raise FinanceError("Backup has duplicate record identifiers.")
                ids.add(record_id)
                valid_integer(row["version"],1,2**63-1)
                valid_timestamp_field(row,"created_at")
                valid_timestamp_field(row,"updated_at")
                if table=="wallets":
                    valid_text(row["name"],80,True)
                    if not isinstance(row["type"],str) or row["type"] not in WALLET_TYPES:
                        record_error()
                    valid_currency(row["currency"])
                    valid_integer(row["opening_balance_minor"],-MAX_MINOR,MAX_MINOR)
                    valid_date(row["opening_date"])
                    valid_timestamp_field(row,"archived_at",True)
                elif table=="categories":
                    valid_text(row["name"],60,True)
                    if row["kind"] not in ("expense","income","both"):
                        record_error()
                    if row["parent_id"] is not None:
                        valid_id(row["parent_id"])
                    valid_text(row["icon"],32,True)
                    if not isinstance(row["color"],str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",row["color"]):
                        raise FinanceError("Backup contains an invalid category color.")
                    valid_integer(row["is_system"],0,1)
                    valid_timestamp_field(row,"archived_at",True)
                elif table=="transfers":
                    valid_id(row["source_wallet_id"])
                    valid_id(row["destination_wallet_id"])
                    valid_integer(row["amount_minor"],1,MAX_MINOR)
                    valid_currency(row["currency"])
                    valid_date(row["transaction_date"])
                    valid_nullable_text(row["note"],180)
                elif table=="transactions":
                    valid_id(row["wallet_id"])
                    if row["type"] not in ("expense","income","transfer"):
                        record_error()
                    valid_integer(row["amount_minor"],1,MAX_MINOR)
                    valid_currency(row["currency"])
                    valid_date(row["transaction_date"])
                    if row["category_id"] is not None:
                        valid_id(row["category_id"])
                    valid_nullable_text(row["description"],180)
                    valid_nullable_text(row["payee"],120)
                    valid_nullable_text(row["notes"],1000)
                    if row["tags"] is None and row["type"]=="transfer":
                        pass  # Transfer legs are inserted without a tags value.
                    else:
                        if not isinstance(row["tags"],str):
                            record_error()
                        try:
                            tags=json.loads(row["tags"])
                        except (ValueError,TypeError):
                            record_error()
                        if (not isinstance(tags,list) or len(tags)>20 or
                                any(not isinstance(tag,str) or len(tag)>40 for tag in tags)):
                            record_error()
                    if row["source"] not in ("manual","csv_import","pdf_import"):
                        record_error()
                    if row["import_batch_id"] is not None:
                        valid_id(row["import_batch_id"])
                    if row["source"]=="manual" and row["import_batch_id"] is not None:
                        record_error()
                    if row["source"] in ("csv_import","pdf_import") and row["import_batch_id"] is None:
                        record_error()
                    fingerprint=row["fingerprint"]
                    if fingerprint is not None and (not isinstance(fingerprint,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",fingerprint)):
                        record_error()
                    if row["transfer_id"] is not None:
                        valid_id(row["transfer_id"])
                    if row["transfer_side"] not in (None,"in","out"):
                        record_error()
                    valid_timestamp_field(row,"deleted_at",True)
                elif table=="budgets":
                    valid_text(row["name"],80,True)
                    if row["period"] not in ("monthly","custom") or row["scope"] not in ("overall","category","wallet"):
                        record_error()
                    valid_date(row["start_date"])
                    valid_date(row["end_date"])
                    if row["end_date"]<row["start_date"]:
                        record_error()
                    valid_integer(row["amount_minor"],1,MAX_MINOR)
                    valid_currency(row["currency"])
                    for key in ("category_id","wallet_id"):
                        if row[key] is not None:
                            valid_id(row[key])
                    valid_integer(row["rollover"],0,1)
                    valid_timestamp_field(row,"archived_at",True)
            validated[table]=rows

        if not isinstance(payload["created_at"],str):
            raise FinanceError("Backup creation time is invalid.")
        valid_time(payload["created_at"])
        wallets={row["id"]:row for row in validated["wallets"]}
        categories={row["id"]:row for row in validated["categories"]}
        transfers={row["id"]:row for row in validated["transfers"]}
        for category in validated["categories"]:
            parent_id=category["parent_id"]
            if parent_id is None:
                continue
            parent=categories.get(parent_id)
            if parent is None or parent_id==category["id"] or parent["parent_id"] is not None:
                raise FinanceError("Backup contains an invalid category parent reference.")
            if parent["kind"] not in (category["kind"],"both") and category["kind"]!="both":
                raise FinanceError(
                    "Backup contains a category type that is incompatible with its parent. "
                    "Update the category hierarchy in the source app and create a new backup."
                )

        transfer_legs={transfer_id:[] for transfer_id in transfers}
        for transaction in validated["transactions"]:
            wallet=wallets.get(transaction["wallet_id"])
            if wallet is None or transaction["currency"]!=wallet["currency"]:
                raise FinanceError("Backup contains an invalid transaction wallet reference.")
            category_id=transaction["category_id"]
            category=categories.get(category_id) if category_id else None
            if category_id and category is None:
                raise FinanceError("Backup contains an invalid transaction category reference.")
            if transaction["type"]=="transfer":
                transfer_id=transaction["transfer_id"]
                if (category_id is not None or transfer_id not in transfers or
                        transaction["transfer_side"] not in ("in","out") or
                        transaction["source"]!="manual" or transaction["import_batch_id"] is not None or
                        transaction["deleted_at"] is not None):
                    raise FinanceError("Backup contains an invalid transfer transaction reference.")
                transfer_legs[transfer_id].append(transaction)
            else:
                if transaction["transfer_id"] is not None or transaction["transfer_side"] is not None:
                    raise FinanceError("Backup contains an invalid transaction transfer reference.")
                if category and category["kind"] not in (transaction["type"],"both"):
                    raise FinanceError("Backup transaction category type is incompatible.")

        for transfer in validated["transfers"]:
            source=wallets.get(transfer["source_wallet_id"])
            destination=wallets.get(transfer["destination_wallet_id"])
            legs=transfer_legs[transfer["id"]]
            if (source is None or destination is None or source["id"]==destination["id"] or
                    source["currency"]!=destination["currency"] or transfer["currency"]!=source["currency"]):
                raise FinanceError("Backup contains an invalid transfer wallet reference.")
            if len(legs)!=2 or {leg["transfer_side"] for leg in legs}!={"in","out"}:
                raise FinanceError("Backup transfer does not have exactly two linked transaction records.")
            for leg in legs:
                expected_wallet=source["id"] if leg["transfer_side"]=="out" else destination["id"]
                if (leg["wallet_id"]!=expected_wallet or leg["amount_minor"]!=transfer["amount_minor"] or
                        leg["currency"]!=transfer["currency"] or leg["transaction_date"]!=transfer["transaction_date"]):
                    raise FinanceError("Backup transfer records are inconsistent.")

        for budget in validated["budgets"]:
            category_id,wallet_id=budget["category_id"],budget["wallet_id"]
            if budget["scope"]=="overall":
                if category_id is not None or wallet_id is not None:
                    record_error()
            elif budget["scope"]=="category":
                category=categories.get(category_id)
                if category is None or category["kind"] not in ("expense","both") or wallet_id is not None:
                    raise FinanceError("Backup contains an invalid budget category reference.")
            else:
                wallet=wallets.get(wallet_id)
                if wallet is None or wallet["currency"]!=budget["currency"] or category_id is not None:
                    raise FinanceError("Backup contains an invalid budget wallet reference.")

        with self._lock:
            counts={}
            conflicts={}
            for table in tables:
                ids=[row["id"] for row in validated[table]]
                counts[table]=len(ids)
                conflicts[table]=0
                for offset in range(0,len(ids),500):
                    batch=ids[offset:offset+500]
                    placeholders=",".join("?" for _ in batch)
                    conflicts[table]+=self.conn.execute(
                        "SELECT COUNT(*) n FROM {} WHERE owner_id=? AND id IN ({})".format(table,placeholders),
                        [LOCAL_OWNER]+batch).fetchone()["n"]
            current_wallets={r["id"]:r["currency"] for r in self.conn.execute(
                "SELECT id,currency FROM wallets WHERE owner_id=?",(LOCAL_OWNER,)).fetchall()}
            for wallet_id,wallet in wallets.items():
                if wallet_id in current_wallets and current_wallets[wallet_id]!=wallet["currency"]:
                    raise FinanceError("A wallet ID in this backup has a different currency on this device. Resolve this conflict before merging.")
        return {"counts":counts,"conflicts":conflicts,"total":sum(counts.values())}

    def _validate_merge_relationships(self, data: Dict[str, Any]) -> None:
        """Validate references against values that merge will actually retain."""
        with self._lock:
            current={table:{row["id"]:dict(row) for row in self.conn.execute(
                "SELECT * FROM {} WHERE owner_id=?".format(table),(LOCAL_OWNER,)).fetchall()}
                for table in ("wallets","categories","transfers","transactions","budgets")}
        effective={table:dict(rows) for table,rows in current.items()}
        for table,rows in data.items():
            for row in rows:
                effective[table].setdefault(row["id"],row)
        wallets,categories=effective["wallets"],effective["categories"]
        for incoming in data["categories"]:
            category=categories[incoming["id"]]
            parent_id=category["parent_id"]
            if parent_id is None:
                continue
            parent=categories.get(parent_id)
            if (parent is None or parent_id==category["id"] or parent["parent_id"] is not None or
                    (parent["kind"] not in (category["kind"],"both") and category["kind"]!="both")):
                raise FinanceError("Backup category conflicts with an incompatible local category relationship.")

        touched_transfers=set()
        for incoming in data["transactions"]:
            if incoming["id"] in current["transactions"]:
                continue
            transaction=effective["transactions"][incoming["id"]]
            wallet=wallets.get(transaction["wallet_id"])
            if wallet is None or wallet["currency"]!=transaction["currency"]:
                raise FinanceError("Backup transaction conflicts with the local wallet currency.")
            category_id=transaction["category_id"]
            category=categories.get(category_id) if category_id else None
            if category_id and category is None:
                raise FinanceError("Backup transaction conflicts with a missing local category.")
            if category and category["kind"] not in (transaction["type"],"both"):
                raise FinanceError("Backup transaction conflicts with the local category type.")
            if transaction["type"]=="transfer":
                touched_transfers.add(transaction["transfer_id"])
        for incoming in data["transfers"]:
            if incoming["id"] not in current["transfers"]:
                touched_transfers.add(incoming["id"])
        for transfer_id in touched_transfers:
            transfer=effective["transfers"].get(transfer_id)
            if transfer is None:
                raise FinanceError("Backup contains a missing local transfer reference.")
            source=wallets.get(transfer["source_wallet_id"])
            destination=wallets.get(transfer["destination_wallet_id"])
            legs=[row for row in effective["transactions"].values() if row["transfer_id"]==transfer_id]
            if (source is None or destination is None or source["id"]==destination["id"] or
                    source["currency"]!=destination["currency"] or source["currency"]!=transfer["currency"] or
                    len(legs)!=2 or {row["transfer_side"] for row in legs}!={"in","out"}):
                raise FinanceError("Backup conflicts with an incomplete local transfer relationship.")
            for leg in legs:
                expected=source["id"] if leg["transfer_side"]=="out" else destination["id"]
                if (leg["wallet_id"]!=expected or leg["currency"]!=transfer["currency"] or
                        leg["amount_minor"]!=transfer["amount_minor"] or
                        leg["transaction_date"]!=transfer["transaction_date"]):
                    raise FinanceError("Backup conflicts with inconsistent local transfer records.")

        for incoming in data["budgets"]:
            if incoming["id"] in current["budgets"]:
                continue
            budget=effective["budgets"][incoming["id"]]
            category_id,wallet_id=budget["category_id"],budget["wallet_id"]
            if budget["scope"]=="category":
                category=categories.get(category_id)
                if category is None or category["kind"] not in ("expense","both"):
                    raise FinanceError("Backup budget conflicts with the local category type.")
            elif budget["scope"]=="wallet":
                wallet=wallets.get(wallet_id)
                if wallet is None or wallet["currency"]!=budget["currency"]:
                    raise FinanceError("Backup budget conflicts with the local wallet currency.")

    def restore_payload(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        preview=self.preview_restore(payload)
        if mode not in ("merge","replace"):
            raise FinanceError("Choose merge or replace.")
        data=payload["data"]
        if mode=="merge":
            self._validate_merge_relationships(data)
        order=("wallets","categories","transfers","transactions","budgets")
        inserted={}
        with self._write() as c:
            if mode=="replace":
                c.execute("DELETE FROM import_rows")
                c.execute("DELETE FROM import_batches")
                c.execute("DELETE FROM transactions")
                c.execute("DELETE FROM transfers")
                c.execute("DELETE FROM budgets")
                c.execute("DELETE FROM categories")
                c.execute("DELETE FROM wallets")
            for table in order:
                inserted[table]=0
                columns=[r[1] for r in c.execute("PRAGMA table_info({})".format(table)).fetchall() if r[1]!="rowid"]
                allowed=set(columns)
                rows=data.get(table,[])
                if table=="categories":
                    # Backup list order is not a dependency guarantee. The
                    # schema permits one parent level, so insert roots first.
                    rows=sorted(rows,key=lambda row:row["parent_id"] is not None)
                for row in rows:
                    values={k:v for k,v in row.items() if k in allowed}
                    if values.get("owner_id") not in (None,LOCAL_OWNER):
                        raise FinanceError("Backup owner scope is invalid.")
                    values["owner_id"]=LOCAL_OWNER
                    if c.execute("SELECT 1 FROM {} WHERE id=?".format(table),(values["id"],)).fetchone():
                        if mode=="merge":
                            continue
                        raise FinanceError("Backup contains duplicate records.")
                    if table=="transactions" and values.get("import_batch_id") is not None:
                        # Import batches are transient review/idempotency records and
                        # are intentionally omitted from v1 archives. Preserve the
                        # transaction's source label, but sever this non-FK link so
                        # restored rows cannot point at a missing or unrelated batch.
                        values["import_batch_id"]=None
                    names=list(values)
                    c.execute("INSERT INTO {}({}) VALUES({})".format(table,",".join(names),",".join("?" for _ in names)),[values[n] for n in names])
                    inserted[table]+=1
        return {"mode":mode,"inserted":inserted,"preview":preview}
