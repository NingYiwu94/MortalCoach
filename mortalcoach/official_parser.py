from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


class Node:
    def __init__(self, tag: str = "", attrs: dict[str, str] | None = None, parent: "Node | None" = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.parent = parent
        self.children: list[Node] = []
        self.text_parts: list[str] = []

    def text(self, direct: bool = False) -> str:
        parts = list(self.text_parts)
        if not direct:
            for child in self.children:
                parts.append(child.text())
        return clean_text(" ".join(parts))

    def has_class(self, name: str) -> bool:
        return name in self.attrs.get("class", "").split()

    def ancestors(self) -> list["Node"]:
        node = self.parent
        result = []
        while node is not None:
            result.append(node)
            node = node.parent
        return result


class TreeParser(HTMLParser):
    VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag.lower(), {key.lower(): value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag.lower() not in self.VOID_TAGS:
            self.current = node

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.current.text_parts.append(data)


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def find_all(node: Node, predicate) -> list[Node]:
    found = []
    if predicate(node):
        found.append(node)
    for child in node.children:
        found.extend(find_all(child, predicate))
    return found


def first(node: Node, predicate) -> Node | None:
    if predicate(node):
        return node
    for child in node.children:
        item = first(child, predicate)
        if item is not None:
            return item
    return None


def direct_children(node: Node, tag: str | None = None) -> list[Node]:
    if tag is None:
        return list(node.children)
    return [child for child in node.children if child.tag == tag]


def parse_rating(text: str) -> float | None:
    plain = clean_text(re.sub(r"<[^>]+>", " ", text))
    patterns = [
        r"\brating\b[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)",
        r"评分[^0-9]{0,80}([0-9]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, plain, re.IGNORECASE)
        if not match:
            continue
        value = float(match.group(1))
        if 0 <= value <= 100:
            return value
    return None


def parse_match_rate(text: str) -> tuple[int, int]:
    plain = clean_text(re.sub(r"<[^>]+>", " ", text))
    match = re.search(r"(\d+)\s*/\s*(\d+)\s*=\s*[0-9]+(?:\.[0-9]+)?%", plain)
    if not match:
        return 0, 0
    return int(match.group(1)), int(match.group(2))


def parse_round_from_section(section: Node) -> str:
    heading = first(section, lambda item: item.tag in {"h1", "h2"} and item.attrs.get("id", "").startswith("kyoku-"))
    if heading is None:
        heading = first(section, lambda item: item.tag in {"h1", "h2"})
    heading_id = heading.attrs.get("id", "") if heading else ""
    match = re.search(r"kyoku-(\d+)-(\d+)", heading_id)
    if match:
        kyoku = int(match.group(1))
        honba = int(match.group(2))
        wind = ["E", "S", "W", "N"][kyoku // 4] if kyoku // 4 < 4 else "?"
        seat = kyoku % 4 + 1
        return f"{wind}{seat}.{honba}" if honba else f"{wind}{seat}"
    return (heading.text() if heading else "?").split(" ")[0] or "?"


def parse_action_cell(cell: Node, fallback: str) -> str:
    text = cell.text()
    tiles = extract_tiles(cell)
    if text and tiles:
        return f"{text} {' '.join(tiles)}"
    if text:
        return text
    if tiles:
        return " ".join(tiles)
    title = first(cell, lambda item: bool(item.attrs.get("title") or item.attrs.get("alt")))
    if title is not None:
        return title.attrs.get("title") or title.attrs.get("alt") or fallback
    img_titles = [item.attrs.get("title") or item.attrs.get("alt") for item in find_all(cell, lambda item: item.tag in {"img", "svg"})]
    img_titles = [item for item in img_titles if item]
    return " ".join(img_titles) if img_titles else fallback


def extract_tiles(node: Node) -> list[str]:
    tiles = []
    for item in find_all(node, lambda child: child.tag == "use"):
        href = item.attrs.get("href") or item.attrs.get("xlink:href") or ""
        match = re.search(r"#pai-([0-9][mps]|[ewsnpcf])", href)
        if match:
            tiles.append(tile_label(match.group(1)))
    return tiles


def tile_label(code: str) -> str:
    if len(code) == 2 and code[0].isdigit():
        suit = {"m": "万", "p": "筒", "s": "索"}.get(code[1], "")
        return f"{code[0]}{suit}"
    return {
        "e": "东",
        "s": "南",
        "w": "西",
        "n": "北",
        "p": "白",
        "f": "发",
        "c": "中",
    }.get(code, code)


def parse_float(value: str) -> float | None:
    value = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", value.replace(",", ""))
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group(0)) if match else None


def parse_candidate_rows(entry: Node) -> list[dict[str, Any]]:
    table = first(entry, lambda item: item.tag == "table" and item.has_class("data"))
    if table is None:
        table = first(entry, lambda item: item.tag == "table")
    if table is None:
        return []
    rows = []
    for tr in find_all(table, lambda item: item.tag == "tr"):
        cells = [child for child in tr.children if child.tag in {"td", "th"}]
        if len(cells) < 2:
            continue
        q_value = parse_float(cells[1].text())
        if q_value is None:
            continue
        rows.append(
            {
                "action": parse_action_cell(cells[0], f"候选 {len(rows) + 1}"),
                "q_value": q_value,
                "prob": parse_float(cells[2].text()) if len(cells) > 2 else None,
            }
        )
    return rows


def parse_entry_state(entry: Node) -> dict[str, Any]:
    hand_node = first(entry, lambda item: item.tag == "ul" and item.has_class("tehai-state"))
    hand_tiles = extract_tiles(hand_node) if hand_node is not None else []
    tsumo_node = first(entry, lambda item: item.tag == "li" and item.has_class("tsumo"))
    tsumo_tiles = extract_tiles(tsumo_node) if tsumo_node is not None else []
    red_nodes = find_all(entry, lambda item: item.tag == "span" and "ffd5d5" in item.attrs.get("style", "").lower())
    actual_tiles: list[str] = []
    for node in red_nodes:
        actual_tiles.extend(extract_tiles(node))
    return {
        "hand_tiles": hand_tiles,
        "tsumo_tiles": tsumo_tiles,
        "actual_tiles": actual_tiles,
        "summary_text": clean_text(entry.text(direct=True)),
    }


def parse_official_html(html: str) -> dict[str, Any]:
    parser = TreeParser()
    parser.feed(html or "")
    root = parser.root
    text = root.text()
    errors: list[dict[str, Any]] = []
    entries = find_all(root, lambda item: item.tag == "details" and item.has_class("entry") and "data-mark-red" in item.attrs)

    for entry_index, entry in enumerate(entries):
        summary = next((child for child in entry.children if child.tag == "summary"), None)
        summary_text = summary.text() if summary else entry.text(direct=True)
        rank_match = re.search(r"#\s*(\d+)\s*/\s*(\d+)", summary_text)
        actual_rank = None
        candidate_count = None
        if rank_match:
            actual_rank = int(rank_match.group(1))
            candidate_count = int(rank_match.group(2))
        else:
            rank_match = re.search(r"/\s*(\d+)\s*#\s*(\d+)", summary_text)
            if rank_match:
                candidate_count = int(rank_match.group(1))
                actual_rank = int(rank_match.group(2))
        if not actual_rank or not candidate_count:
            continue
        nums = [int(num) for num in re.findall(r"\d+", summary_text)]
        junme = nums[0] if nums else None
        tiles_left = nums[1] if len(nums) > 1 else None
        section = next((node for node in entry.ancestors() if node.tag == "section"), None)
        round_label = parse_round_from_section(section) if section is not None else "?"
        rows = parse_candidate_rows(entry)
        if not rows or actual_rank < 1 or actual_rank > len(rows):
            continue
        state = parse_entry_state(entry)
        best = rows[0]
        actual = rows[actual_rank - 1]
        q_gap = float(best["q_value"] or 0) - float(actual["q_value"] or 0)
        if q_gap <= 0:
            continue
        errors.append(
            {
                "kyoku_index": 0,
                "entry_index": entry_index,
                "round": round_label,
                "junme": junme,
                "tiles_left": tiles_left,
                "shanten": None,
                "q_gap": q_gap,
                "actual_rank": actual_rank,
                "candidate_count": candidate_count or len(rows),
                "expected": {"type": "text", "text": best["action"]},
                "actual": {"type": "text", "text": actual["action"]},
                "best_detail": best,
                "actual_detail": actual,
                "candidates": rows,
                "state": state,
            }
        )

    errors.sort(key=lambda item: (float(item.get("q_gap") or 0), int(item.get("actual_rank") or 0)), reverse=True)
    total_matches, total_reviewed = parse_match_rate(text)
    return {
        "rating_percent": parse_rating(text),
        "total_matches": total_matches,
        "total_reviewed": total_reviewed,
        "errors": errors,
    }
