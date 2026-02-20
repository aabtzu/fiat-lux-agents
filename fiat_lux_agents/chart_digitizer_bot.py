"""
Self-correcting scientific chart digitizer agent.

Multi-pass loop:
  1. Send chart image to Claude → initial JSON
  2. Generate a comparison chart overlay (matplotlib)
  3. Send original + comparison to Claude → "where did I go wrong? fix it"
  4. Repeat until max_passes or point count stabilizes

Completely generic — no assumptions about what the chart contains.
The caller provides a free-text chart_description and a list of data_keys
to extract. Each data point is expected to have at minimum an x field and
optionally a "value" field plus a "confidence" score.
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Callable

from .base import LLMBaseAgent, DEFAULT_MODEL


class ChartDigitizerBot(LLMBaseAgent):
    """
    Self-correcting scientific chart digitizer.

    Usage::

        agent = ChartDigitizerBot()
        result = agent.digitize(
            image_bytes=png_bytes,          # PNG of the chart panel
            chart_description=\"\"\"
                X-axis: Days post-infection (0–600)
                Left Y-axis: Platelet count x1000/uL (linear, 0–350)
                Right Y-axis: Viral RNA copies/mL (log10, 1E0–1E5)
                Platelet: continuous solid black line, left axis
                VL detected: 'x' markers, right log axis — return actual copies/mL
                VL not-detected: open diamond markers at bottom
            \"\"\",
            data_keys=["platelets", "vl", "vl_not_detected"],
            x_field="dpi",
            max_passes=4,
        )
        # result["platelets"] = [{"dpi": 0, "value": 197, "confidence": 0.9}, ...]
        # result["_passes"]   = 3  (how many iterations were used)
    """

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 16000):
        super().__init__(model=model, max_tokens=max_tokens)

    # ── Public API ────────────────────────────────────────────────────────────

    def digitize(
        self,
        image_bytes: bytes,
        chart_description: str,
        data_keys: list[str],
        x_field: str = "x",
        max_passes: int = 4,
        min_new_points: int = 5,
        on_pass: Callable | None = None,
    ) -> dict:
        """
        Digitize a chart with iterative self-correction.

        Args:
            image_bytes:       PNG bytes of the chart panel to digitize.
            chart_description: Free-text description of axes, scales, and marker types.
            data_keys:         Data series to extract, e.g. ["platelets", "vl", "vl_not_detected"].
            x_field:           Name of the x-axis field in returned JSON (default "x").
            max_passes:        Hard upper limit on refinement iterations (default 4).
            min_new_points:    Stop early if fewer than this many total points are added
                               compared to the previous pass (default 5).
            on_pass:           Optional callback(pass_num: int, result: dict) called after
                               each pass. Useful for progress reporting.

        Returns:
            dict with data_keys as arrays of data points, plus:
              "_passes"      — number of passes actually performed
              "_stop_reason" — "stabilized" | "max_passes" | "error"
        """
        result = None
        prev_count = 0

        for pass_num in range(1, max_passes + 1):
            is_first = pass_num == 1

            if is_first:
                prompt = self._initial_prompt(chart_description, data_keys, x_field)
                images = [image_bytes]
            else:
                comparison_bytes = self._make_comparison_chart(result, data_keys, x_field)
                prompt = self._refinement_prompt(
                    chart_description, data_keys, x_field, pass_num, prev_count
                )
                images = [image_bytes, comparison_bytes]

            raw = self._call_with_images(prompt, images)
            raw = _fix_sci_notation(raw)
            raw = _strip_fences(raw)

            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                repaired = _repair_truncated_json(raw)
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    if result is not None:
                        # keep last good result
                        break
                    result = {k: [] for k in data_keys}
                    result["_passes"] = pass_num
                    result["_stop_reason"] = "error"
                    return result

            result = parsed
            curr_count = sum(len(result.get(k, [])) for k in data_keys)
            delta = abs(curr_count - prev_count)

            if on_pass:
                on_pass(pass_num, result)

            if pass_num > 1 and delta < min_new_points:
                result["_passes"] = pass_num
                result["_stop_reason"] = "stabilized"
                return result

            prev_count = curr_count

        if result is None:
            result = {k: [] for k in data_keys}

        result["_passes"] = max_passes
        result["_stop_reason"] = "max_passes"
        return result

    # ── Prompts ───────────────────────────────────────────────────────────────

    def _initial_prompt(
        self, chart_description: str, data_keys: list[str], x_field: str
    ) -> str:
        example = {}
        for k in data_keys:
            example[k] = [{x_field: 0.0, "value": 123.0, "confidence": 0.90}]
        example_json = json.dumps(example, indent=2)

        return f"""You are a precise scientific chart digitizer. Extract all numerical \
data series from the chart image.

CHART DESCRIPTION:
{chart_description}

DATA SERIES TO EXTRACT: {', '.join(data_keys)}

RULES:
1. Record EVERY visible data point — every peak, trough, and direction change.
2. The curves may be highly oscillatory. Do NOT smooth or average — transcribe the actual jagged shape.
3. Confidence scores (0.0–1.0):
   - 0.95: clear and unambiguous
   - 0.80: minor uncertainty (near tick, slight overlap)
   - 0.60: crowded or unclear — include with caution
   - Below 0.60: omit the point
4. Aim for maximum fidelity. If a 600-unit x-range has many oscillations, you should have 80–120+ points.
   Fewer than 40 points for an oscillatory curve almost always means missed peaks and troughs.
5. For marker-only series (e.g. "not detected" flags with no y-value), return \
{{"{ x_field }": x, "confidence": c}} with no "value" key.

Return ONLY valid JSON (no markdown fences, no prose, no comments):
{example_json}

If a series is absent from this chart, return [].
"""

    def _refinement_prompt(
        self,
        chart_description: str,
        data_keys: list[str],
        x_field: str,
        pass_num: int,
        prev_count: int,
    ) -> str:
        return f"""You are refining a scientific chart digitization. You have been given \
TWO images:
- Image 1: The ORIGINAL chart to digitize
- Image 2: Your PREVIOUS digitization attempt, plotted as colored lines/points

CHART DESCRIPTION:
{chart_description}

YOUR TASK:
1. Carefully compare Image 1 (original) against Image 2 (your previous attempt).
2. Find regions where Image 2 looks SMOOTHER than Image 1 — those are missing peaks/troughs.
3. Find regions where Image 2 is MISSING data entirely.
4. Return a COMPLETE corrected dataset — not just the differences, but ALL points.

Your previous attempt had {prev_count} total points across all series.
If the original chart has oscillations that Image 2 doesn't capture, your new count should be HIGHER.

Return ONLY valid JSON with the same structure (keys: {', '.join(data_keys)}).
No markdown fences, no prose.
"""

    # ── API call with images ──────────────────────────────────────────────────

    def _call_with_images(self, prompt: str, images: list[bytes]) -> str:
        content = []
        for img_bytes in images:
            b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": b64,
                },
            })
        content.append({"type": "text", "text": prompt})

        message = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[{"role": "user", "content": content}],
        )
        return message.content[0].text.strip()

    # ── Comparison chart ──────────────────────────────────────────────────────

    def _make_comparison_chart(
        self, result: dict, data_keys: list[str], x_field: str
    ) -> bytes:
        """
        Render the current digitized data as a matplotlib figure and return PNG bytes.
        One subplot per data series that has "value" fields.
        Marker-only series (no "value") are shown as tick marks on the bottom of the first subplot.
        """
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            import matplotlib.gridspec as gridspec
        except ImportError:
            raise ImportError(
                "matplotlib is required for comparison charts. "
                "Install it: pip install matplotlib"
            )

        # Split keys into value series and marker-only series
        value_keys = [
            k for k in data_keys
            if any("value" in pt for pt in result.get(k, []))
        ]
        marker_keys = [
            k for k in data_keys
            if k not in value_keys and result.get(k)
        ]

        n_panels = max(len(value_keys), 1)
        fig = plt.figure(figsize=(12, 4 * n_panels))
        fig.suptitle("Previous digitization (pass comparison)", fontsize=10, color="#555")
        gs = gridspec.GridSpec(n_panels, 1, hspace=0.5)

        for i, key in enumerate(value_keys):
            ax = fig.add_subplot(gs[i])
            pts = [p for p in result.get(key, []) if x_field in p and "value" in p]

            if pts:
                xs = [p[x_field] for p in pts]
                ys = [p["value"] for p in pts]
                confs = [p.get("confidence", 0.8) for p in pts]
                colors = [
                    "#d32f2f" if c < 0.65 else "#ff9800" if c < 0.80 else "#2196F3"
                    for c in confs
                ]
                ax.plot(xs, ys, "-", color="#2196F3", linewidth=1, alpha=0.4, zorder=1)
                ax.scatter(xs, ys, c=colors, s=15, zorder=2)

            # Overlay marker-only series at y=0
            for mk in marker_keys:
                mk_xs = [
                    p[x_field] for p in result.get(mk, []) if x_field in p
                ]
                if mk_xs:
                    ax.scatter(
                        mk_xs, [0] * len(mk_xs),
                        marker="v", color="#9c27b0", s=20, alpha=0.6,
                        label=mk, zorder=3,
                    )

            ax.set_title(key, fontsize=9)
            ax.set_xlabel(x_field, fontsize=8)
            ax.grid(True, alpha=0.3)
            if i == 0 and marker_keys:
                ax.legend(fontsize=7, loc="upper right")

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()


# ── Module-level helpers ──────────────────────────────────────────────────────

def _strip_fences(text: str) -> str:
    """Remove markdown code fences if Claude added them."""
    if text.startswith("```"):
        lines = text.split("\n")
        end = -1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end])
    return text.strip()


def _fix_sci_notation(text: str) -> str:
    """Replace non-standard '1.E+04' with valid JSON '1.0E+04'."""
    return re.sub(r"(\d+\.)E([+-]\d+)", r"\g<1>0E\2", text)


def _repair_truncated_json(text: str) -> str:
    """
    Attempt to repair JSON truncated mid-stream (e.g. stop_reason='refusal').
    Truncates at the last complete '}' and closes any unclosed brackets.
    """
    last_brace = text.rfind("}")
    if last_brace < 0:
        return text
    text = text[: last_brace + 1]

    stack: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            i += 1
            while i < len(text):
                if text[i] == "\\":
                    i += 2
                elif text[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
        i += 1

    close_map = {"[": "]", "{": "}"}
    closing = "".join(close_map[c] for c in reversed(stack))
    return text + "\n" + closing if closing else text
