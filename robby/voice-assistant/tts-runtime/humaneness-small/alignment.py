"""Reuse the old demo's word alignment and fades, with Small edge-cue protection."""
import logging
import os
import re
import sys
import numpy as np

import settings

if str(settings.PARENT) not in sys.path:
    sys.path.append(str(settings.PARENT))
import align_engine
import timed_script

log = logging.getLogger("small.alignment")
_TAG = re.compile(r"\([^)]*\)|\[[^]]*\]")


def edge_cues(tagged):
    """Only tags outside the spoken words protect the leading/trailing edges.

    Unlike the legacy heuristic, this works without duration tags and does not
    mistake a mid-sentence burst for a leading or closing sound. Explicit edge
    trailing silence is also intentional. Leading silence needs no exception:
    the legacy fade silences the lead without removing samples or its duration.
    """
    tagged = str(tagged or "")
    masked = _TAG.sub(lambda m: " " * len(m[0]), tagged)
    speech = list(re.finditer(r"\S+", masked))
    if not speech:
        return True, ""

    def protects(tag):
        if tag.startswith("["):
            return "pause" in tag.lower()
        body = tag[1:-1]
        return bool(re.search(r",\s*[0-9.]+\s*seconds?", body, re.I)
                    or timed_script._is_burst_label(body))

    prefix = tagged[:speech[0].start()]
    suffix = tagged[speech[-1].end():]
    allow_lead = not any(m[0].startswith("(") and protects(m[0]) for m in _TAG.finditer(prefix))
    closing = []
    for m in _TAG.finditer(suffix):
        tag = m[0]
        if not protects(tag):
            continue
        number = re.search(r"([0-9.]+)\s*seconds?", tag, re.I)
        seconds = float(number[1]) if number else (0.5 if tag.startswith("[") else 0.28)
        # Legacy trim's tail rule retains twice the requested length plus air.
        closing.append(f"(requested edge sound or silence, {seconds} seconds)")
    return allow_lead, "[0 seconds duration] speech " + " ".join(closing)


class AudioFinisher:
    def __init__(self):
        # Deliberately choose the same Apache-2.0 Qwen backend, not the old
        # optional non-commercial MMS fallback.
        self.aligner = align_engine.QwenAligner(device=settings.ALIGN_DEVICE)

    @property
    def available(self):
        return self.aligner is not None and self.aligner.ok

    def finish(self, waves, spec, enabled=True):
        allow_lead, edges = edge_cues(spec.get("edge_script", spec.get("tagged", "")))
        output, reports = [], []
        for wave in waves:
            raw_seconds = len(wave) / 48000
            if not enabled:
                report = {"applied": False, "note": "disabled", "spans": []}
                edited = wave
            else:
                try:
                    edited, report = align_engine.trim(wave, 48000, edges,
                        spec["text"], self.aligner, allow_lead=allow_lead)
                except Exception:
                    log.exception("Alignment failed; leaving this take unchanged")
                    edited, report = wave, {"applied": False, "note": "alignment failed", "spans": []}
            report.update(enabled=enabled, available=self.available,
                          raw_seconds=round(raw_seconds, 3), seconds=round(len(edited) / 48000, 3),
                          lead_ramp_s=align_engine.config.ALIGN_LEAD_RAMP_S,
                          tail_ramp_s=align_engine.config.ALIGN_TAIL_RAMP_S,
                          score_kind="structural plausibility, not model confidence")
            output.append(edited)
            reports.append(report)
        return output, reports


from streaming_boundaries import SpeechBoundaryGate


class LiveCutoff(SpeechBoundaryGate):
    """Strict target-word gate shared by classic and continuous streaming."""
    def __init__(self, spec, enabled=True):
        allow_lead, edges = edge_cues(spec.get('edge_script', spec.get('tagged', '')))
        closing = align_engine.closing_burst_s(edges)
        tail_allow = closing * align_engine.config.ALIGN_BURST_SLACK if closing else 0.
        super().__init__(spec['text'], enabled, preserve_lead=not allow_lead, tail_allow=tail_allow)
