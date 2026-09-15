"""
Parse bank and credit card statement files into normalized transaction rows.

Supports CSV (Chase, BofA, Capital One, Amex, generic) and PDF (Claude-powered extraction).
After parsing, normalize_categories() assigns generic spending categories via Claude Haiku.
"""

import base64
import csv
import io
import json
import re
import time
from datetime import datetime

from .base import LLMBase, DEFAULT_MODEL

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = DEFAULT_MODEL

_DEFAULT_TAXONOMY = [
    "Travel", "Dining", "Groceries", "Gas & Fuel", "Streaming",
    "Digital Subscriptions", "Fitness", "Shopping", "Home & Garden",
    "Auto", "Utilities", "Healthcare", "Childcare & Education",
    "Fees & Interest", "Payment", "Income", "Other",
]

_PDF_EXTRACT_PROMPT = """Extract all transactions from this bank or credit card statement.
Return a JSON array where each element is:
{
  "date": "YYYY-MM-DD",
  "description": "merchant or payee name",
  "amount": <absolute value, always positive>,
  "txn_type": "debit" or "credit",
  "account": "last 4 digits of account or card name if visible"
}

txn_type rules:
- "credit" = money flowing INTO the account: payroll, direct deposits, ACH credits, incoming Zelle/wire, refunds, interest, transfers in, credit card payments received
- "debit"  = money flowing OUT of the account: purchases, charges, withdrawals, outgoing Zelle/wire, loan payments, bill pay, credit card charges

Include all transactions. Skip running balances, summary rows, totals, and non-transaction lines.
Return only a valid JSON array — no prose, no markdown fences."""


def _build_normalize_prompt(taxonomy: list[str]) -> str:
    cats = ", ".join(taxonomy)
    return f"""Assign a spending category to each transaction.

Each item has a "description" and a "txn_type": "debit" (money out) or "credit" (money in).

Rules:
- Use BOTH description AND txn_type — never ignore either.
- txn_type="credit" is strong evidence of Income, Payment, or a merchant refund.
- txn_type="credit" + description contains "Payroll", "Direct Deposit", "ACH Credit", "Salary", "Employer", "Zelle From" → "Income".
- txn_type="credit" + description contains "Payment", "Autopay", "Balance Transfer" → "Payment".
- txn_type="credit" that is a merchant refund → same category as the merchant (e.g. "AMAZON REFUND" → "Shopping").
- txn_type="debit": identify the merchant type — "DELTA AIR LINES" → "Travel", "SOULCYCLE" → "Fitness", "NETFLIX" → "Streaming".
- Be specific: "Streaming" not "Entertainment", "Gas & Fuel" not "Auto", "Dining" not "Food".
- Use only categories from this list: {cats}

Input: a JSON array of {{"description": str, "txn_type": "debit"|"credit"}} objects.
Return: a JSON array of category strings — same length, same order, nothing else.
No markdown, no explanation, just the JSON array."""


def _parse_amount(value: str) -> float | None:
    if not value or not value.strip():
        return None
    cleaned = value.strip().replace("$", "").replace(",", "").replace(" ", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_date(value: str) -> str | None:
    if not value or not value.strip():
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


def _detect_csv_columns(headers: list[str]) -> dict:
    h_lower = [x.strip().lower() for x in headers]
    orig = {x.strip().lower(): x.strip() for x in headers}

    def find(*candidates):
        for c in candidates:
            if c in h_lower:
                return orig[c]
        return None

    date_col = find("transaction date", "date", "posted date", "post date")
    desc_col = find("description", "merchant", "name", "payee", "memo")
    cat_col = find("category", "type")
    account_col = find("account", "card no.", "card number")
    debit_col = find("debit", "withdrawal", "debit amount")
    credit_col = find("credit", "deposit", "credit amount", "payment")
    amount_col = find("amount", "amount (usd)", "transaction amount")

    # Amex: positive = spending. Detect by "Extended Details" (older) or "Card Member" (newer).
    is_amex = "extended details" in h_lower or "card member" in h_lower
    amount_sign = 1 if is_amex else -1

    # Derive a human-readable source label from the column layout.
    if is_amex:
        detected_source = "Amex"
    elif debit_col and credit_col:
        # Separate debit/credit columns = BofA style checking
        detected_source = "BofA Checking"
    else:
        # Single signed amount column = Chase style
        detected_source = "Chase"

    return {
        "date_col": date_col,
        "desc_col": desc_col,
        "cat_col": cat_col,
        "account_col": account_col,
        "debit_col": debit_col,
        "credit_col": credit_col,
        "amount_col": amount_col,
        "amount_sign": amount_sign,
        "detected_source": detected_source,
    }


def _normalize_csv_row(row: dict, cols: dict, source_file: str) -> dict | None:
    date_str = row.get(cols["date_col"], "").strip() if cols["date_col"] else ""
    parsed_date = _parse_date(date_str)
    if not parsed_date:
        return None

    desc = row.get(cols["desc_col"], "").strip() if cols["desc_col"] else ""
    if not desc:
        return None

    if cols["debit_col"] and cols["credit_col"]:
        debit = _parse_amount(row.get(cols["debit_col"], ""))
        credit = _parse_amount(row.get(cols["credit_col"], ""))
        if debit is not None and debit > 0:
            amount, txn_type = debit, "debit"
        elif credit is not None and credit > 0:
            amount, txn_type = credit, "credit"
        else:
            return None
    else:
        raw = _parse_amount(row.get(cols["amount_col"], "")) if cols["amount_col"] else None
        if raw is None:
            return None
        signed = raw * cols["amount_sign"]
        txn_type = "debit" if signed > 0 else "credit"
        amount = abs(signed)

    cat = row.get(cols["cat_col"], "").strip() if cols["cat_col"] else ""
    category = cat or "Other"
    account = row.get(cols["account_col"], "").strip() if cols["account_col"] else ""
    dt = datetime.strptime(parsed_date, "%Y-%m-%d")

    return {
        "txn_date": parsed_date,
        "year": dt.year,
        "month": dt.month,
        "description": desc,
        "category": category,
        "amount": round(amount, 2),
        "txn_type": txn_type,
        "account": account,
        "source": cols.get("detected_source", ""),
        "source_file": source_file,
    }


def _claude_rows_to_transactions(raw: list[dict], source_file: str) -> list[dict]:
    result = []
    for item in raw:
        parsed_date = _parse_date(str(item.get("date", "")))
        if not parsed_date:
            continue
        try:
            amount = abs(float(item.get("amount") or 0))
        except (ValueError, TypeError):
            continue
        if amount == 0:
            continue
        dt = datetime.strptime(parsed_date, "%Y-%m-%d")
        desc = str(item.get("description", "")).strip()
        # Use txn_type if Claude returned it; fall back to sign convention for old prompts.
        raw_type = str(item.get("txn_type") or "").strip().lower()
        if raw_type in ("credit", "debit"):
            txn_type = raw_type
        else:
            # Legacy fallback: negative signed amount = credit.
            try:
                signed = float(item.get("amount") or 0)
            except (ValueError, TypeError):
                signed = amount
            txn_type = "credit" if signed < 0 else "debit"
        result.append({
            "txn_date": parsed_date,
            "year": dt.year,
            "month": dt.month,
            "description": desc,
            "category": str(item.get("category") or "Other").strip() or "Other",
            "amount": round(amount, 2),
            "txn_type": txn_type,
            "account": str(item.get("account") or ""),
            "source_file": source_file,
        })
    return result


class StatementParser(LLMBase):
    """
    Parse bank and credit card statements (CSV or PDF) into normalized transaction rows.

    Usage:
        parser = StatementParser()
        rows = parser.parse_and_normalize(file_bytes, filename)

    Each row is a dict with keys:
        txn_date, year, month, description, category, amount, account, source_file
    """

    def __init__(self, model: str = _SONNET, category_model: str = _HAIKU, max_tokens: int = 8192):
        super().__init__(model=model, max_tokens=max_tokens)
        self.category_model = category_model

    def parse_csv(self, file_bytes: bytes, filename: str) -> list[dict]:
        """Parse a CSV bank/CC statement into normalized transaction rows (no API call)."""
        text = file_bytes.decode("utf-8", errors="replace").lstrip("﻿")
        reader = csv.DictReader(io.StringIO(text))
        headers = list(reader.fieldnames or [])
        if not headers:
            return []

        cols = _detect_csv_columns(headers)
        if not cols["date_col"]:
            return []
        if not cols["amount_col"] and not (cols["debit_col"] and cols["credit_col"]):
            return []

        rows = []
        for row in reader:
            normalized = _normalize_csv_row(row, cols, filename)
            if normalized:
                rows.append(normalized)
        return rows

    def extract_from_pdf(self, file_bytes: bytes, filename: str) -> list[dict]:
        """Use Claude to extract transactions from a PDF statement."""
        b64 = base64.standard_b64encode(file_bytes).decode()
        try:
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": [
                    {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}},
                    {"type": "text", "text": _PDF_EXTRACT_PROMPT},
                ]}],
            )
            raw_text = resp.content[0].text
            m = re.search(r"\[[\s\S]*\]", raw_text.strip())
            if not m:
                return []
            raw = json.loads(m.group(0))
            return _claude_rows_to_transactions(raw if isinstance(raw, list) else [], filename)
        except Exception as exc:
            print(f"[StatementParser] PDF extraction failed: {exc!r}")
            return []

    def parse(self, file_bytes: bytes, filename: str) -> list[dict]:
        """Dispatch to CSV or PDF parser based on file extension."""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if ext == "csv":
            return self.parse_csv(file_bytes, filename)
        if ext == "pdf":
            return self.extract_from_pdf(file_bytes, filename)
        return []

    def normalize_categories(self, rows: list[dict], taxonomy: list[str] | None = None) -> list[dict]:
        """
        Use Claude Haiku to assign generic categories from transaction descriptions.

        Passes descriptions only (not raw bank categories, which are often merchant codes).
        Applies category assignments in-place and returns the rows.
        Falls back gracefully if the API call fails.
        """
        if not rows:
            return rows

        taxonomy = taxonomy or _DEFAULT_TAXONOMY
        prompt = _build_normalize_prompt(taxonomy)
        items = [{"description": r["description"], "txn_type": r.get("txn_type", "debit")} for r in rows]

        t0 = time.time()
        print(f"[StatementParser] Normalizing {len(rows)} rows with {self.category_model}...")
        try:
            resp = self.client.messages.create(
                model=self.category_model,
                max_tokens=4096,
                messages=[{"role": "user", "content": f"{prompt}\n\n{json.dumps(items)}"}],
            )
            elapsed = time.time() - t0
            raw_text = resp.content[0].text.strip()
            print(f"[StatementParser] Haiku responded in {elapsed:.1f}s, stop_reason={resp.stop_reason!r}")

            if raw_text.startswith("```"):
                raw_text = re.sub(r"```[^\n]*\n?", "", raw_text).strip()

            normalized = json.loads(raw_text)
            if isinstance(normalized, list) and len(normalized) > 0:
                applied = 0
                for row, cat in zip(rows, normalized):
                    if isinstance(cat, str) and cat.strip():
                        row["category"] = cat.strip()
                        applied += 1
                print(f"[StatementParser] Categories applied to {applied}/{len(rows)} rows.")
                if len(normalized) != len(rows):
                    print(f"[StatementParser] Note: got {len(normalized)} categories for {len(rows)} rows — used first {min(len(normalized), len(rows))}")
            else:
                print(f"[StatementParser] Unexpected response type: {type(normalized)}")
        except Exception as exc:
            elapsed = time.time() - t0
            print(f"[StatementParser] Category normalization failed after {elapsed:.1f}s: {exc!r}")

        return rows

    def parse_and_normalize(
        self,
        file_bytes: bytes,
        filename: str,
        taxonomy: list[str] | None = None,
    ) -> list[dict]:
        """Parse a statement file and normalize categories in one call."""
        rows = self.parse(file_bytes, filename)
        return self.normalize_categories(rows, taxonomy=taxonomy)
