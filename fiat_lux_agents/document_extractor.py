"""
DocumentExtractor — extract a structured document model from raw text.
"""

from .base import LLMBase

_HAIKU = "claude-haiku-4-5-20251001"

_SYSTEM = """You are a document analysis assistant. Extract structured information from the provided document text and return it as JSON."""

_PROMPT = """Analyze the following document text and extract a structured model.

Return exactly this JSON structure (no markdown, no extra text):
{
  "document_type": "short descriptive label (1-3 words, lowercase)",
  "metadata": {
    "key": "value"
  },
  "records": [
    {"col1": "val1", "col2": "val2"}
  ],
  "summary": {
    "key": "value"
  }
}

Field guidance:
- "document_type": short label like "medical bill", "class schedule", "bank statement"
- "metadata": non-tabular header/footer fields — names, IDs, addresses, dates, reference numbers, provider info, patient info. Use snake_case keys.
- "records": tabular rows with consistent columns. Use snake_case keys from column headers. Empty array [] if no tabular data.
- "summary": totals, counts, date ranges, aggregate values stated in the document. Empty object {} if none.

All four keys must be present. Use null values only if a field genuinely cannot be extracted.

Document text:
"""

_TYPE_HINT_SUFFIX = "\n\nDocument type hint: {hint}"


class DocumentExtractor(LLMBase):
    """Extract a structured document model from raw text."""

    def __init__(self):
        super().__init__(model=_HAIKU, max_tokens=4096)

    def extract(self, text: str, document_type_hint: str = None) -> dict:
        """
        Extract a structured document model from raw text.

        Returns:
            {
                "document_type": str,
                "metadata": {key: value},
                "records": [{...}, ...],
                "summary": {key: value}
            }
        """
        prompt = _PROMPT + text
        if document_type_hint:
            prompt += _TYPE_HINT_SUFFIX.format(hint=document_type_hint)

        raw = self.call_api(_SYSTEM, [{"role": "user", "content": prompt}])
        try:
            result = self.parse_json_response(raw)
        except ValueError:
            # Fallback: return minimal valid structure
            return {
                "document_type": document_type_hint or "unknown",
                "metadata": {},
                "records": [],
                "summary": {},
            }

        return {
            "document_type": (result.get("document_type") or document_type_hint or "unknown").strip().lower(),
            "metadata":      result.get("metadata") or {},
            "records":       result.get("records") if isinstance(result.get("records"), list) else [],
            "summary":       result.get("summary") or {},
        }
