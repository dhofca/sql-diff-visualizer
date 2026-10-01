from pathlib import Path

from backend.diff import diff_schemas
from backend.parser import parse_schema

FIXTURES = Path(__file__).parent / "fixtures"


def _result():
    old = parse_schema((FIXTURES / "v1.sql").read_text())
    new = parse_schema((FIXTURES / "v2.sql").read_text())
    return diff_schemas(old, new)


def _index(node, acc=None):
    acc = {} if acc is None else acc
    acc[node["key"]] = node
    for child in node["children"]:
        _index(child, acc)
    return acc


def test_table_statuses():
    nodes = _index(_result()["tree"])
    assert nodes["table:payments"]["status"] == "added"
    assert nodes["table:audit_log"]["status"] == "removed"
    assert nodes["table:users"]["status"] == "modified"
    assert nodes["table:orders"]["status"] == "modified"


def test_column_changes():
    nodes = _index(_result()["tree"])
    email = nodes["table:users/column:email"]
    assert email["status"] == "modified"
    assert email["changes"] == [{"field": "type", "before": "VARCHAR(100)", "after": "VARCHAR(255)"}]
    assert nodes["table:users/column:last_login_at"]["status"] == "added"
    assert nodes["table:users/column:legacy_flag"]["status"] == "removed"
    assert nodes["table:users/column:name"]["status"] == "unchanged"


def test_removed_column_keeps_its_position():
    nodes = _index(_result()["tree"])
    names = [c["name"] for c in nodes["table:users/columns"]["children"]]
    assert names == ["id", "email", "name", "legacy_flag", "created_at", "last_login_at"]


def test_foreign_key_and_view_changes():
    nodes = _index(_result()["tree"])
    fk = nodes["table:orders/fk:fk_orders_user"]
    assert fk["changes"] == [{"field": "on_delete", "before": "CASCADE", "after": "RESTRICT"}]
    assert nodes["view:v_active_users"]["status"] == "modified"


def test_identical_schemas_have_no_changes():
    schema = parse_schema((FIXTURES / "v1.sql").read_text())
    result = diff_schemas(schema, parse_schema((FIXTURES / "v1.sql").read_text()))
    assert result["tree"]["status"] == "unchanged"
    assert all(set(c) == {"unchanged"} for c in result["summary"].values())


def test_summary_counts():
    summary = _result()["summary"]
    assert summary["table"] == {"added": 1, "removed": 1, "modified": 2}


def test_groups_of_added_table_are_added():
    nodes = _index(_result()["tree"])
    assert nodes["table:payments/columns"]["status"] == "added"
    assert nodes["table:audit_log/indexes"]["status"] == "removed"
    assert nodes["table:users/columns"]["status"] == "modified"


def test_tables_are_top_level_followed_by_definition_groups():
    top = [(c["kind"], c["name"]) for c in _result()["tree"]["children"]]
    assert top == [("table", "audit_log"), ("table", "orders"), ("table", "payments"),
                   ("table", "users"), ("group", "Widoki")]
