from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Column:
    name: str
    type: str
    nullable: bool = True
    default: Optional[str] = None
    extra: Tuple[str, ...] = ()
    charset: Optional[str] = None
    collation: Optional[str] = None
    comment: Optional[str] = None

    def attrs(self) -> Dict[str, object]:
        return {
            "type": self.type,
            "nullable": self.nullable,
            "default": self.default,
            "extra": " ".join(self.extra) or None,
            "charset": self.charset,
            "collation": self.collation,
            "comment": self.comment,
        }

    def summary(self) -> str:
        parts = [self.type, "NULL" if self.nullable else "NOT NULL"]
        if self.default is not None:
            parts.append(f"DEFAULT {self.default}")
        parts.extend(self.extra)
        return " ".join(parts)


@dataclass
class Index:
    name: str
    kind: str
    columns: Tuple[str, ...]

    def attrs(self) -> Dict[str, object]:
        return {"kind": self.kind, "columns": ", ".join(self.columns)}

    def summary(self) -> str:
        return f"{self.kind} ({', '.join(self.columns)})"


@dataclass
class ForeignKey:
    name: str
    columns: Tuple[str, ...]
    ref_table: str
    ref_columns: Tuple[str, ...]
    on_delete: Optional[str] = None
    on_update: Optional[str] = None

    def attrs(self) -> Dict[str, object]:
        return {
            "columns": ", ".join(self.columns),
            "references": f"{self.ref_table} ({', '.join(self.ref_columns)})",
            "on_delete": self.on_delete,
            "on_update": self.on_update,
        }

    def summary(self) -> str:
        s = f"({', '.join(self.columns)}) → {self.ref_table} ({', '.join(self.ref_columns)})"
        if self.on_delete:
            s += f" ON DELETE {self.on_delete}"
        if self.on_update:
            s += f" ON UPDATE {self.on_update}"
        return s


@dataclass
class Table:
    name: str
    columns: Dict[str, Column] = field(default_factory=dict)
    indexes: Dict[str, Index] = field(default_factory=dict)
    foreign_keys: Dict[str, ForeignKey] = field(default_factory=dict)
    options: Dict[str, str] = field(default_factory=dict)

    def attrs(self) -> Dict[str, object]:
        return dict(self.options)

    def summary(self) -> str:
        return " ".join(f"{k}={v}" for k, v in sorted(self.options.items()))


@dataclass
class Definition:
    """View, trigger, procedure, function or event — compared by normalized SQL text."""

    name: str
    kind: str
    sql: str

    def attrs(self) -> Dict[str, object]:
        return {"definition": self.sql}

    def summary(self) -> str:
        return self.sql


@dataclass
class Schema:
    tables: Dict[str, Table] = field(default_factory=dict)
    definitions: Dict[str, Definition] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
