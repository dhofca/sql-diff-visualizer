from pathlib import Path

from backend.parser import parse_schema, split_statements

FIXTURES = Path(__file__).parent / "fixtures"


def test_parses_tables_from_mysqldump():
    schema = parse_schema((FIXTURES / "v1.sql").read_text())
    assert set(schema.tables) == {"users", "orders", "audit_log"}
    assert schema.warnings == []


def test_column_attributes():
    users = parse_schema((FIXTURES / "v1.sql").read_text()).tables["users"]
    assert users.columns["id"].type == "INT UNSIGNED"
    assert users.columns["id"].nullable is False
    assert users.columns["id"].extra == ("AUTO_INCREMENT",)
    assert users.columns["name"].nullable is True
    assert users.columns["name"].default is None
    assert users.columns["legacy_flag"].default == "'0'"


def test_indexes_and_foreign_keys():
    orders = parse_schema((FIXTURES / "v1.sql").read_text()).tables["orders"]
    assert orders.indexes["PRIMARY"].columns == ("id",)
    assert orders.indexes["idx_orders_user"].kind == "INDEX"
    fk = orders.foreign_keys["fk_orders_user"]
    assert (fk.ref_table, fk.ref_columns, fk.on_delete) == ("users", ("id",), "CASCADE")


def test_auto_increment_counter_is_ignored():
    sql_a = "CREATE TABLE t (id int) ENGINE=InnoDB AUTO_INCREMENT=5;"
    sql_b = "CREATE TABLE t (id int) ENGINE=InnoDB AUTO_INCREMENT=999;"
    assert parse_schema(sql_a).tables["t"].options == parse_schema(sql_b).tables["t"].options


def test_int_display_width_normalized_except_tinyint1():
    table = parse_schema("CREATE TABLE t (a int(11), b bigint(20) unsigned, c tinyint(1));").tables["t"]
    assert table.columns["a"].type == "INT"
    assert table.columns["b"].type == "BIGINT UNSIGNED"
    assert table.columns["c"].type == "TINYINT(1)"


def test_view_from_versioned_comments_replaces_placeholder_table():
    sql = """
    CREATE TABLE `v` (`id` tinyint NOT NULL);
    /*!50001 DROP TABLE IF EXISTS `v`*/;
    /*!50001 CREATE ALGORITHM=UNDEFINED */
    /*!50013 DEFINER=`app`@`%` SQL SECURITY DEFINER */
    /*!50001 VIEW `v` AS select 1 AS `id` */;
    """
    schema = parse_schema(sql)
    assert "v" not in schema.tables
    assert "VIEW:v" in schema.definitions


def test_trigger_with_custom_delimiter():
    sql = (
        "DELIMITER ;;\n"
        "/*!50003 CREATE*/ /*!50017 DEFINER=`app`@`%`*/ /*!50003 TRIGGER `trg` BEFORE INSERT ON `t` "
        "FOR EACH ROW BEGIN SET NEW.a = 'x;y'; END */;;\n"
        "DELIMITER ;\n"
    )
    trigger = parse_schema(sql).definitions["TRIGGER:trg"]
    assert "DEFINER" not in trigger.sql
    assert "SET NEW.a = 'x;y'; END" in trigger.sql


def test_split_respects_quotes_and_comments():
    sql = "SELECT 'a;b'; -- c;d\nSELECT `x;y`; /* e;f */ SELECT 1"
    assert list(split_statements(sql)) == ["SELECT 'a;b'", "SELECT `x;y`", "SELECT 1"]


def test_unparseable_table_produces_warning_not_crash():
    schema = parse_schema("CREATE TABLE `broken` (id int NOT NULL DEFAULT (;")
    assert schema.tables == {}
    assert any("broken" in w for w in schema.warnings)
