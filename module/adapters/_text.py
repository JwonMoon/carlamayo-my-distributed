"""Shared decoding helpers for pulling CoT/CoC and VQA text out of ``extra`` dicts."""

import re

import numpy as np

SPECIAL_TOKEN_RE = re.compile(r"<\|[^>]+?\|>|</s>|<s>")
VQA_ANSWER_TERMINATORS = (
    "<|answer_end|>",
    "<|im_end|>",
    "<|endoftext|>",
    "<|cot_start|>",
    "<|cot_end|>",
    "<|meta_action_start|>",
    "<|meta_action_end|>",
    "<|question_start|>",
    "<|question_end|>",
)


def extract_text_field(extra, key):
    """Return the first non-empty decoded string stored under ``key`` in ``extra``."""
    if not isinstance(extra, dict) or key not in extra:
        return ""

    value = extra[key]
    if value is None:
        return ""

    while True:
        if isinstance(value, str):
            return str(value).strip()
        if isinstance(value, (list, tuple)):
            if len(value) == 0:
                return ""
            value = value[0]
            continue
        if isinstance(value, np.ndarray):
            if value.size == 0:
                return ""
            value = value.flat[0]
            continue
        if hasattr(value, "numel") and hasattr(value, "reshape"):
            if int(value.numel()) == 0:
                return ""
            value = value.reshape(-1)[0].item()
            continue
        return str(value).strip()


def clean_generated_answer_text(text):
    text = SPECIAL_TOKEN_RE.sub("", str(text))
    return " ".join(text.split()).strip()


def extract_answer_from_decoded_text(decoded_text):
    """Extract the answer span from a raw VQA generation with special tokens."""
    text = str(decoded_text).strip()
    if not text:
        return ""

    if "<|answer_end|>" in text:
        candidate = text.partition("<|answer_end|>")[0]
        if "<|answer_start|>" in candidate:
            candidate = candidate.rsplit("<|answer_start|>", 1)[1]
        return clean_generated_answer_text(candidate)

    if "<|answer_start|>" in text:
        candidate = text.rsplit("<|answer_start|>", 1)[1]
    else:
        candidate = text

    for terminator in VQA_ANSWER_TERMINATORS:
        if terminator == "<|answer_end|>":
            continue
        candidate = candidate.split(terminator, 1)[0]

    return clean_generated_answer_text(candidate)
