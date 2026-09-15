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
  "source": "institution and account type, e.g. Chase Checking, Chase Savings, Amex, BofA Checking, Citi Card",
  "account": "last 4 digits of account or card if visible, else empty string"
}

txn_type rules:
- "credit" = money flowing INTO the account: payroll, direct deposits, ACH credits, incoming Zelle/wire, refunds, interest, transfers in, credit card payments received
- "debit"  = money flowing OUT of the account: purchases, charges, withdrawals, outgoing Zelle/wire, loan payments, bill pay, credit card charges

source: read the institution name and account type from the statement header (e.g. "Chase Premier Plus Checking" → "Chase Checking", "American Express" → "Amex", "Bank of America Checking" → "BofA Checking"). Use the same source value for every row in the file.

Include all transactions. Skip running balances, summary rows, totals, and non-transaction lines.
Return only a valid JSON array — no prose, no markdown fences."""


def _extract_cat_conf(item) -> tuple[str, float]:
    """Extract (category, confidence) from a Haiku response item.

    Handles both new dict format {"category": str, "confidence": float}
    and legacy str format for backward compatibility.
    """
    if isinstance(item, dict):
        cat = str(item.get("category", "")).strip()
        try:
            conf = float(item.get("confidence", 1.0))
        except (ValueError, TypeError):
            conf = 1.0
        return cat, max(0.0, min(1.0, conf))
    if isinstance(item, str) and item.strip():
        return item.strip(), 1.0
    return "", 1.0


def _build_normalize_prompt(taxonomy: list[str]) -> str:
    cats = ", ".join(taxonomy)
    return f"""Assign a spending category to each transaction description.

Each item has a "description" (from a bank statement) and a "txn_type": "debit" (money out) or "credit" (money in).

## CRITICAL: Bank description format
Bank statement descriptions often append the merchant's physical location as a suffix, e.g.:
  "JACKS AUTOMOTIVE LARCHMONT INC - LARCHMONT NY"
  "BARNES & NOBLE #3304 - SCARSDALE NY"
  "NEW YORK STATE DMV - ALBANY NY"
  "LENSCRAFTERS - SCARSDALE NY"

A city/state suffix is the store's address — it does NOT mean the transaction is Travel.
Identify the merchant name BEFORE the last " - CITY STATE" portion.

Also ignore payment method and POS system prefixes when identifying the merchant:
- "AplPay" = Apple Pay, "GglPay" = Google Pay, "GOOGLE*" = Google billing
- "SQ *" or "SP " = Square point-of-sale terminal (look at the merchant name after the prefix)
- "TST*" = Toast point-of-sale terminal used exclusively by restaurants → always Dining
- "GF*" = GoFundMe or similar service

## Category rules (debit = money out)

### Travel
Only use Travel for: airlines (Delta, United, American, Southwest, JetBlue, Amtrak), hotels (Marriott, Hilton, Hyatt, IHG, Crowne Plaza, Bereshit Hotel, hotel chains), car rentals (Hertz, Avis, Enterprise, Budget, Kesher), airport parking, Airbnb (pattern: "AIRBNB *"), Expedia, booking.com, CLEAR (airport security), travel insurance premiums (Baggage Insurance, Travel Delay Insurance), Uber/Lyft ride-shares, taxi services, tours and tour operators.
Do NOT use Travel for restaurants, cafes, bakeries, or any food establishment — even if they are in a travel destination city.

### Streaming
Netflix, Hulu, HBO Max, Disney Plus, Disney+, Peacock, Apple TV+, YouTube, YouTube TV, YouTube Premium, YouTube Music, Spotify, Pandora, Tidal, Apple Music, Sling, Paramount+, Discovery+, ESPN+, Fubo.
"GOOGLE*YOUTUBE", "GOOGLE*YT PRIMETIME", "GOOGLE*YOUTUBETV" → Streaming
"PEACOCK" → Streaming
"DISNEY PLUS" or "DISNEY+" → Streaming

### Digital Subscriptions
Software, SaaS, developer tools, productivity apps: Adobe, Microsoft 365, Dropbox, iCloud (APPLE.COM/BILL), GitHub, LinkedIn Premium, Anthropic, Cursor, OpenAI, Notion, Slack, DakBoard, Concur, Splitwise, Medium.
"APPLE.COM/BILL" → Digital Subscriptions (Apple's subscription billing)
NOT Streaming services (those go above).

### Fitness
Gyms and fitness studios: SoulCycle, Equinox, Planet Fitness, CrossFit, Peloton, Snap Fitness, LA Fitness, 24 Hour Fitness, YMCA.
Sports equipment stores (Pure Hockey, REI, Dick's Sporting Goods) → Shopping, NOT Fitness.

### Shopping
Retail: Amazon, Target, Walmart, Barnes & Noble, sporting goods stores, sports equipment shops (Pure Hockey, Hockey Town), department stores, clothing, electronics.

### Groceries
Grocery stores: Whole Foods, Trader Joe's, Stop & Shop, Fairway, Costco, BJ's, Wegmans, ShopRite, Key Food.

### Gas & Fuel
Gas stations AND convenience stores with gas: Shell, Mobil, BP, Sunoco, Exxon, Chevron, Gulf, Cumberland Farms, Wawa, Sheetz, Speedway.
E-ZPass, tolls, EZPass → Gas & Fuel.

### Auto
Auto repair shops, mechanics, car washes, automotive parts: Jiffy Lube, Midas, AutoZone, O'Reilly, Garagiste.
Car loan payments → Auto.
DMV fees, vehicle registration → Fees & Interest (government fee, NOT Auto).

### Healthcare
Doctors, dentists, hospitals, pharmacies, opticians: CVS Pharmacy, Walgreens, LensCrafters (optical/eyewear), vision centers, dental offices.
"LENSCRAFTERS" → Healthcare (it's an eyewear/vision store).

### Utilities
Electric, gas, water, internet, phone service: Con Edison, Con Ed, National Grid, Verizon (phone bill), AT&T, T-Mobile, Google Fi, water utilities, Vermont Gas.
NOT APPLE.COM/BILL (that is Digital Subscriptions).

### Home & Garden
Home improvement, hardware, locksmiths, furniture, appliances: Home Depot, Lowe's, IKEA, hardware stores, locksmith services (ABCO Lock).

### Fees & Interest
Bank fees, interest charges, ATM fees, government fees, vehicle registration, DMV fees, insurance premiums NOT related to travel, late fees.

### Dining
Restaurants, cafes, fast food, food delivery: DoorDash, Grubhub, Uber Eats, Seamless, and any restaurant.

### Income (credits only)
Payroll, direct deposits, ACH credits, salary, employer payments, rental income, freelance payments, interest earned.
"Zelle From" → Income. "Fidelity" transfer in → Income.

### Payment (credits only, or outgoing bill payments)
Credit card payments, loan payments, Amex autopay, Chase autopay. Outgoing Venmo/Zelle → Payment.

## Final rules
- Use only categories from this list: {cats}
- "Other" is a last resort — try hard to match a specific category first
- Return EXACTLY one object per input item, same count and same order

## Confidence scoring
Assign a confidence score (0.0–1.0) reflecting how certain you are of the category:
- 0.9–1.0: Clear match — well-known merchant, explicit pattern (TST*, APPLE.COM/BILL, airline name)
- 0.7–0.89: Reasonable guess — familiar merchant type, partial pattern match
- 0.5–0.69: Ambiguous — unfamiliar merchant name, could fit multiple categories
- 0.3–0.49: Very uncertain — generic or cryptic description, no recognizable pattern
Use confidence < 0.7 when: merchant name is a single word or abbreviation with no context, the name sounds like one thing but could be another (e.g. "Garagiste" sounds like auto but is wine), or the transaction is from a foreign city with unfamiliar merchants.

Input: a JSON array of {{"description": str, "txn_type": "debit"|"credit"}} objects.
Return: a JSON array of {{"category": str, "confidence": float}} objects — same length, same order, nothing else.
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


def _recover_partial_json_array(text: str) -> list:
    """Extract complete objects from a truncated JSON array (stop_reason=max_tokens)."""
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    in_string = False
    escape_next = False
    last_complete = -1
    for i, ch in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                last_complete = i
    if last_complete == -1:
        return []
    try:
        return json.loads(text[start : last_complete + 1] + "]")
    except json.JSONDecodeError:
        return []


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
            "source": str(item.get("source") or "").strip(),
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
            if resp.stop_reason == "max_tokens":
                print(f"[StatementParser] WARNING: PDF response truncated ({len(raw_text)} chars) — recovering partial results")
                raw = _recover_partial_json_array(raw_text)
                print(f"[StatementParser] Recovered {len(raw)} complete objects from truncated response")
                return _claude_rows_to_transactions(raw, filename)
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
                for row, item in zip(rows, normalized):
                    cat, conf = _extract_cat_conf(item)
                    if cat:
                        row["category"] = cat
                        row["confidence"] = conf
                        applied += 1
                print(f"[StatementParser] Categories applied to {applied}/{len(rows)} rows.")
                if len(normalized) < len(rows):
                    missed = rows[len(normalized):]
                    print(f"[StatementParser] {len(missed)} rows uncategorized — retrying")
                    retry_items = [{"description": r["description"], "txn_type": r.get("txn_type", "debit")} for r in missed]
                    retry_resp = self.client.messages.create(
                        model=self.category_model,
                        max_tokens=4096,
                        messages=[{"role": "user", "content": f"{prompt}\n\n{json.dumps(retry_items)}"}],
                    )
                    retry_text = retry_resp.content[0].text.strip()
                    if retry_text.startswith("```"):
                        retry_text = re.sub(r"```[^\n]*\n?", "", retry_text).strip()
                    retry_cats = json.loads(retry_text)
                    if isinstance(retry_cats, list):
                        for row, item in zip(missed, retry_cats):
                            cat, conf = _extract_cat_conf(item)
                            if cat:
                                row["category"] = cat
                                row["confidence"] = conf
                        print(f"[StatementParser] Retry categorized {min(len(retry_cats), len(missed))} missed rows.")
                elif len(normalized) > len(rows):
                    print(f"[StatementParser] Got {len(normalized)} categories for {len(rows)} rows — used first {len(rows)}")
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
