from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def get_review(payload: dict[str, Any]) -> dict[str, Any]:
    review = payload.get("review")
    if isinstance(review, dict):
        return review
    if "kyokus" in payload:
        return payload
    raise ValueError("Cannot find review data. Expected mjai-reviewer --json output.")


def summarize_review(payload: dict[str, Any]) -> dict[str, Any]:
    review = get_review(payload)
    total_reviewed = int(review.get("total_reviewed") or 0)
    total_matches = int(review.get("total_matches") or 0)
    rating = float(review.get("rating") or 0.0)
    match_rate = total_matches / total_reviewed if total_reviewed else 0.0
    errors = extract_errors(payload, limit=None)
    return {
        "rating": rating,
        "rating_percent": rating * 100.0,
        "total_reviewed": total_reviewed,
        "total_matches": total_matches,
        "match_rate": match_rate,
        "error_count": len(errors),
        "max_q_gap": errors[0]["q_gap"] if errors else 0.0,
        "avg_q_gap": sum(e["q_gap"] for e in errors) / len(errors) if errors else 0.0,
        "model_tag": review.get("model_tag") or "",
    }


def extract_errors(payload: dict[str, Any], limit: int | None = 10) -> list[dict[str, Any]]:
    review = get_review(payload)
    errors: list[dict[str, Any]] = []

    for kyoku_index, kyoku in enumerate(review.get("kyokus") or []):
        entries = kyoku.get("entries") or []
        for entry_index, entry in enumerate(entries):
            if entry.get("is_equal") is True:
                continue
            details = entry.get("details") or []
            actual_index = entry.get("actual_index")
            if not details or actual_index is None:
                continue
            if not isinstance(actual_index, int) or actual_index < 0 or actual_index >= len(details):
                continue

            best = details[0]
            actual_detail = details[actual_index]
            best_q = float(best.get("q_value") or 0.0)
            actual_q = float(actual_detail.get("q_value") or 0.0)
            q_gap = best_q - actual_q

            errors.append(
                {
                    "kyoku_index": kyoku_index,
                    "entry_index": entry_index,
                    "round": format_round(kyoku),
                    "junme": entry.get("junme"),
                    "tiles_left": entry.get("tiles_left"),
                    "shanten": entry.get("shanten"),
                    "at_furiten": bool(entry.get("at_furiten")),
                    "q_gap": q_gap,
                    "actual_rank": actual_index + 1,
                    "expected": entry.get("expected"),
                    "actual": entry.get("actual"),
                    "best_detail": best,
                    "actual_detail": actual_detail,
                    "candidate_count": len(details),
                }
            )

    errors.sort(key=lambda item: (item["q_gap"], item["actual_rank"]), reverse=True)
    if limit is None:
        return errors
    return errors[:limit]


def format_round(kyoku: dict[str, Any]) -> str:
    kyoku_num = int(kyoku.get("kyoku") or 0)
    honba = int(kyoku.get("honba") or 0)
    wind = ["E", "S", "W", "N"][kyoku_num // 4] if 0 <= kyoku_num // 4 < 4 else "?"
    seat = kyoku_num % 4 + 1
    return f"{wind}{seat}.{honba}" if honba else f"{wind}{seat}"


def action_to_text(action: Any) -> str:
    if not isinstance(action, dict):
        return str(action)
    typ = action.get("type", "?")
    if typ == "text":
        return str(action.get("text") or "")
    if typ == "dahai":
        return f"discard {action.get('pai')}"
    if typ in {"chi", "pon", "ankan", "daiminkan", "kakan"}:
        return typ
    if typ == "reach":
        return "riichi"
    if typ == "hora":
        return "win"
    if typ == "ryukyoku":
        return "abortive draw"
    if typ == "none":
        return "pass"
    return typ
