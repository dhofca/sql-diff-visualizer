"""Compare two Schema models and build a tree annotated with diff statuses."""

from collections import Counter
from typing import Dict, List, Optional

from .models import Schema, Table

ADDED, REMOVED, MODIFIED, UNCHANGED = "added", "removed", "modified", "unchanged"

DEFINITION_GROUPS = [
    ("VIEW", "Widoki"),
    ("TRIGGER", "Triggery"),
    ("PROCEDURE", "Procedury"),
    ("FUNCTION", "Funkcje"),
    ("EVENT", "Eventy"),
]


def diff_schemas(old: Schema, new: Schema) -> dict:
    tables = _group(
        "tables",
        "Tabele",
        [
            _table_node(name, old.tables.get(name), new.tables.get(name))
            for name in sorted(old.tables.keys() | new.tables.keys(), key=str.lower)
        ],
    )
    children = [tables]
    for kind, label in DEFINITION_GROUPS:
        names = {d.name for d in old.definitions.values() if d.kind == kind} | {
            d.name for d in new.definitions.values() if d.kind == kind
        }
        if names:
            children.append(
                _group(
                    kind.lower(),
                    label,
                    [
                        _leaf(f"{kind.lower()}:{n}", n, kind.lower(),
                              old.definitions.get(f"{kind}:{n}"), new.definitions.get(f"{kind}:{n}"))
                        for n in sorted(names, key=str.lower)
                    ],
                )
            )
    root = _group("schema", "Schemat", children)
    return {"tree": root, "summary": _summary(root), "warnings": {"old": old.warnings, "new": new.warnings}}


def _table_node(name: str, old: Optional[Table], new: Optional[Table]) -> dict:
    key = f"table:{name}"
    node = _leaf(key, name, "table", old, new)

    def section(attr: str, kind: str, label: str) -> dict:
        # group key reuses the model attribute name: table:x/columns, table:x/indexes, table:x/foreign_keys
        old_items = getattr(old, attr) if old else {}
        new_items = getattr(new, attr) if new else {}
        return _group(
            f"{key}/{attr}",
            label,
            [_leaf(f"{key}/{kind}:{n}", n, kind, old_items.get(n), new_items.get(n))
             for n in _merge_order(list(old_items), list(new_items))],
        )

    node["children"] = [
        section("columns", "column", "Kolumny"),
        section("indexes", "index", "Indeksy"),
        section("foreign_keys", "fk", "Klucze obce"),
    ]
    node["children"] = [c for c in node["children"] if c["children"]]
    if node["status"] == UNCHANGED and any(c["status"] != UNCHANGED for c in node["children"]):
        node["status"] = MODIFIED
    return node


def _leaf(key: str, name: str, kind: str, old, new) -> dict:
    node = {"key": key, "name": name, "kind": kind, "children": []}
    if old is None:
        node.update(status=ADDED, after=new.summary())
    elif new is None:
        node.update(status=REMOVED, before=old.summary())
    else:
        before, after = old.attrs(), new.attrs()
        changes = [
            {"field": f, "before": before.get(f), "after": after.get(f)}
            for f in sorted(before.keys() | after.keys())
            if before.get(f) != after.get(f)
        ]
        node.update(status=MODIFIED if changes else UNCHANGED, before=old.summary(), after=new.summary())
        if changes:
            node["changes"] = changes
    return node


def _group(key: str, name: str, children: List[dict]) -> dict:
    statuses = {c["status"] for c in children}
    if statuses <= {UNCHANGED}:
        status = UNCHANGED
    elif statuses in ({ADDED}, {REMOVED}):
        status = statuses.pop()
    else:
        status = MODIFIED
    return {"key": key, "name": name, "kind": "group", "status": status, "children": children}


def _merge_order(old: List[str], new: List[str]) -> List[str]:
    """Keep the new order; slot removed items right after their old predecessor."""
    result = list(new)
    present = set(new)
    for i, name in enumerate(old):
        if name in present:
            continue
        anchor = next((old[j] for j in range(i - 1, -1, -1) if old[j] in result), None)
        result.insert(result.index(anchor) + 1 if anchor else 0, name)
    return result


def _summary(root: dict) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Counter] = {}

    def walk(node: dict) -> None:
        if node["kind"] != "group":
            counts.setdefault(node["kind"], Counter())[node["status"]] += 1
        for child in node["children"]:
            walk(child)

    walk(root)
    return {kind: dict(c) for kind, c in counts.items()}
