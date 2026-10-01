"""Parse a MySQL structure dump (mysqldump --no-data) into a Schema model."""

import logging
import re
from typing import Iterator, List, Optional

import sqlglot
from sqlglot import exp

from .models import Column, Definition, ForeignKey, Index, Schema, Table

logging.getLogger("sqlglot").setLevel(logging.CRITICAL)

DIALECT = "mysql"

_VERSIONED_COMMENT = re.compile(r"/\*!\d*\s?(.*?)\*/", re.DOTALL)
_DELIMITER = re.compile(r"^\s*DELIMITER\s+(\S+)\s*$", re.IGNORECASE)
_DEFINITION_HEAD = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:ALGORITHM\s*=\s*\w+\s+)?(?:DEFINER\s*=\s*\S+\s+)?"
    r"(?:SQL\s+SECURITY\s+\w+\s+)?(?:AGGREGATE\s+)?(VIEW|TRIGGER|PROCEDURE|FUNCTION|EVENT)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?((?:`[^`]+`|\w+)(?:\.(?:`[^`]+`|\w+))?)",
    re.IGNORECASE,
)
_NOISE = [
    re.compile(r"\bDEFINER\s*=\s*\S+\s*", re.IGNORECASE),
    re.compile(r"\bALGORITHM\s*=\s*\w+\s*", re.IGNORECASE),
    re.compile(r"\bSQL\s+SECURITY\s+\w+\s*", re.IGNORECASE),
]
_INT_DISPLAY_WIDTH = re.compile(r"^(TINYINT|SMALLINT|MEDIUMINT|INT|BIGINT)\(\d+\)")


def parse_schema(sql: str) -> Schema:
    schema = Schema()
    for statement in split_statements(_VERSIONED_COMMENT.sub(r"\1", sql)):
        head = statement.lstrip()[:200].upper()
        if not head.startswith("CREATE"):
            continue
        definition = _DEFINITION_HEAD.match(statement.strip())
        if definition:
            item = _parse_definition(statement, definition.group(1).upper(), definition.group(2))
            schema.definitions[f"{item.kind}:{item.name}"] = item
        elif re.match(r"CREATE\s+(TEMPORARY\s+)?TABLE", head):
            table = _parse_table(statement, schema.warnings)
            if table:
                schema.tables[table.name] = table
        else:
            schema.warnings.append(f"Skipped unsupported statement: {head.split('(')[0][:60]}")

    # mysqldump creates placeholder tables for views; the real view replaces them.
    for item in schema.definitions.values():
        if item.kind == "VIEW":
            schema.tables.pop(item.name, None)
    return schema


def split_statements(sql: str) -> Iterator[str]:
    """Split on the active delimiter, honouring quotes, comments and DELIMITER lines."""
    delimiter = ";"
    buf: List[str] = []
    i, n = 0, len(sql)
    at_line_start = True
    while i < n:
        if at_line_start:
            end = sql.find("\n", i)
            end = n if end == -1 else end
            match = _DELIMITER.match(sql[i:end])
            if match:
                yield from _flush(buf)
                delimiter = match.group(1)
                i = end + 1
                continue
        ch = sql[i]
        at_line_start = ch == "\n"
        if ch in "'\"`":
            j = i + 1
            while j < n:
                if sql[j] == "\\" and ch != "`":
                    j += 2
                    continue
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            buf.append(sql[i : j + 1])
            i = j + 1
        elif sql.startswith("--", i) and (i + 2 >= n or sql[i + 2] in " \t\r\n") or ch == "#":
            end = sql.find("\n", i)
            i = n if end == -1 else end
        elif sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif sql.startswith(delimiter, i):
            yield from _flush(buf)
            i += len(delimiter)
        else:
            buf.append(ch)
            i += 1
    yield from _flush(buf)


def _flush(buf: List[str]) -> Iterator[str]:
    statement = "".join(buf).strip()
    buf.clear()
    if statement:
        yield statement


def _parse_definition(statement: str, kind: str, raw_name: str) -> Definition:
    name = _unquote(raw_name.split(".")[-1])
    text = statement.strip()
    for pattern in _NOISE:
        text = pattern.sub("", text)
    if kind == "VIEW":
        match = re.search(r"\bAS\s+(.*)$", text, re.IGNORECASE | re.DOTALL)
        if match:
            try:
                text = sqlglot.parse_one(match.group(1), read=DIALECT).sql(DIALECT, pretty=True).replace("`", "")
            except Exception:
                text = match.group(1)
    return Definition(name=name, kind=kind, sql=_collapse_ws(text) if kind != "VIEW" else text.strip())


def _parse_table(statement: str, warnings: List[str]) -> Optional[Table]:
    try:
        create = sqlglot.parse_one(statement, read=DIALECT)
    except Exception as error:
        name = re.search(r"TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(`[^`]+`|\S+)", statement, re.IGNORECASE)
        label = _unquote(name.group(1)) if name else "?"
        warnings.append(f"Could not parse table {label}: {type(error).__name__}")
        return None

    if not isinstance(create, exp.Create) or not isinstance(create.this, exp.Schema):
        warnings.append("Skipped CREATE TABLE without column definitions (e.g. CREATE TABLE ... LIKE)")
        return None

    table = Table(name=create.this.this.name)
    for element in create.this.expressions:
        if isinstance(element, exp.ColumnDef):
            column = _parse_column(element, table)
            table.columns[column.name] = column
        elif isinstance(element, exp.PrimaryKey):
            table.indexes["PRIMARY"] = Index("PRIMARY", "PRIMARY", _names(element.expressions))
        elif isinstance(element, exp.UniqueColumnConstraint) and isinstance(element.this, exp.Schema):
            index_name = element.this.this.name if element.this.this else ""
            columns = _names(element.this.expressions)
            table.indexes[index_name or "_".join(columns)] = Index(index_name, "UNIQUE", columns)
        elif isinstance(element, exp.IndexColumnConstraint):
            kind = str(element.args.get("kind") or "INDEX").upper()
            columns = _names(element.expressions)
            index_name = element.this.name if element.this else "_".join(columns)
            table.indexes[index_name] = Index(index_name, kind, columns)
        elif isinstance(element, exp.Constraint) and isinstance(element.expressions[0], exp.ForeignKey):
            fk = _parse_foreign_key(element.name, element.expressions[0])
            table.foreign_keys[fk.name] = fk
        elif isinstance(element, exp.ForeignKey):
            fk = _parse_foreign_key("", element)
            table.foreign_keys[fk.name] = fk
        else:
            label = element.name if isinstance(element, exp.Constraint) else type(element).__name__
            table.options[f"constraint {label}"] = _sql(element)

    for prop in (create.args.get("properties") or exp.Properties(expressions=[])).expressions:
        if isinstance(prop, exp.AutoIncrementProperty):
            continue
        key, _, value = _sql(prop).partition("=")
        key = re.sub(r"^DEFAULT\s+", "", key.strip(), flags=re.IGNORECASE).lower()
        table.options[key] = value.strip()
    return table


def _parse_column(element: exp.ColumnDef, table: Table) -> Column:
    column_type = _sql(element.args["kind"]) if element.args.get("kind") else "?"
    if not column_type.startswith("TINYINT(1)"):
        column_type = _INT_DISPLAY_WIDTH.sub(r"\1", column_type)
    column = Column(name=element.name, type=column_type)
    extra: List[str] = []
    for constraint in element.constraints:
        kind = constraint.kind
        if isinstance(kind, exp.NotNullColumnConstraint):
            column.nullable = bool(kind.args.get("allow_null"))
        elif isinstance(kind, exp.DefaultColumnConstraint):
            column.default = None if isinstance(kind.this, exp.Null) else _sql(kind.this)
        elif isinstance(kind, exp.AutoIncrementColumnConstraint):
            extra.append("AUTO_INCREMENT")
        elif isinstance(kind, exp.CharacterSetColumnConstraint):
            column.charset = _sql(kind.this)
        elif isinstance(kind, exp.CollateColumnConstraint):
            column.collation = _sql(kind.this)
        elif isinstance(kind, exp.CommentColumnConstraint):
            column.comment = kind.this.name
        elif isinstance(kind, exp.PrimaryKeyColumnConstraint):
            table.indexes["PRIMARY"] = Index("PRIMARY", "PRIMARY", (column.name,))
        elif isinstance(kind, exp.UniqueColumnConstraint):
            table.indexes[column.name] = Index(column.name, "UNIQUE", (column.name,))
        else:
            extra.append(_sql(kind))
    column.extra = tuple(extra)
    return column


def _parse_foreign_key(name: str, fk: exp.ForeignKey) -> ForeignKey:
    reference = fk.args["reference"]
    target = reference.this
    ref_table = target.this.name if isinstance(target, exp.Schema) else target.name
    ref_columns = _names(target.expressions) if isinstance(target, exp.Schema) else ()
    columns = _names(fk.expressions)
    result = ForeignKey(name or "fk_" + "_".join(columns), columns, ref_table, ref_columns)
    for option in reference.args.get("options") or []:
        text = str(option).upper()
        if text.startswith("ON DELETE "):
            result.on_delete = text[len("ON DELETE "):]
        elif text.startswith("ON UPDATE "):
            result.on_update = text[len("ON UPDATE "):]
    return result


def _names(expressions) -> tuple:
    return tuple(e.name if isinstance(e, (exp.Identifier, exp.Column)) else _sql(e) for e in expressions)


def _sql(node: exp.Expression) -> str:
    return node.sql(DIALECT).replace("`", "")


def _unquote(name: str) -> str:
    return name.strip("`")


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
