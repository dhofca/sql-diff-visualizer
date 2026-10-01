"""Generate a synthetic pair of ~110-table MySQL dumps for manual/perf testing (fake data only)."""

import random
import sys
from pathlib import Path

TYPES = ["int NOT NULL", "bigint unsigned NOT NULL", "varchar(64) DEFAULT NULL", "varchar(255) NOT NULL",
         "datetime NOT NULL DEFAULT CURRENT_TIMESTAMP", "decimal(10,2) NOT NULL DEFAULT '0.00'",
         "tinyint(1) NOT NULL DEFAULT '0'", "text", "json DEFAULT NULL"]
WORDS = ["account", "invoice", "product", "customer", "shipment", "warehouse", "price", "tax", "discount",
         "category", "supplier", "contract", "ticket", "session", "report", "setting", "region", "currency"]


def table_sql(name, columns, indexes, fks):
    lines = [f"  `{c}` {t}" for c, t in columns]
    lines.append("  PRIMARY KEY (`id`)")
    lines += [f"  KEY `idx_{name}_{c}` (`{c}`)" for c in indexes]
    lines += [f"  CONSTRAINT `fk_{name}_{c}` FOREIGN KEY (`{c}`) REFERENCES `{ref}` (`id`){opt}" for c, ref, opt in fks]
    body = ",\n".join(lines)
    return (f"DROP TABLE IF EXISTS `{name}`;\nCREATE TABLE `{name}` (\n{body}\n) ENGINE=InnoDB "
            f"AUTO_INCREMENT={random.randint(1, 99999)} DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;\n")


def build(n_tables=110, seed=7):
    random.seed(seed)
    tables = {}
    for i in range(n_tables):
        name = f"{random.choice(WORDS)}_{random.choice(WORDS)}_{i:03d}"
        cols = [("id", "bigint unsigned NOT NULL AUTO_INCREMENT")]
        cols += [(f"{random.choice(WORDS)}_{j}", random.choice(TYPES)) for j in range(random.randint(3, 14))]
        idx = [c for c, t in cols[1:] if "NOT NULL" in t and random.random() < 0.3]
        refs = list(tables)
        fks = [(c, random.choice(refs), "") for c in idx if refs and random.random() < 0.4]
        tables[name] = {"cols": cols, "idx": idx, "fks": fks}
    return tables


def mutate(tables, seed=11):
    random.seed(seed)
    new = {k: {"cols": list(v["cols"]), "idx": list(v["idx"]), "fks": list(v["fks"])} for k, v in tables.items()}
    names = list(new)
    for name in random.sample(names, 3):
        del new[name]
        for t in new.values():
            t["fks"] = [fk for fk in t["fks"] if fk[1] != name]
    for i in range(4):
        new[f"feature_{WORDS[i]}_{i}"] = {"cols": [("id", "bigint unsigned NOT NULL AUTO_INCREMENT"),
                                                   ("label", "varchar(128) NOT NULL")], "idx": [], "fks": []}
    for name in random.sample(list(new), 12):
        t = new[name]
        if random.random() < 0.5:
            t["cols"].append((f"added_{random.choice(WORDS)}", "varchar(32) DEFAULT NULL"))
        if len(t["cols"]) > 3 and random.random() < 0.4:
            victim = t["cols"].pop(random.randrange(2, len(t["cols"])))[0]
            t["idx"] = [c for c in t["idx"] if c != victim]
            t["fks"] = [fk for fk in t["fks"] if fk[0] != victim]
        if random.random() < 0.6:
            j = random.randrange(1, len(t["cols"]))
            t["cols"][j] = (t["cols"][j][0], random.choice(TYPES))
        if t["fks"] and random.random() < 0.5:
            c, ref, _ = t["fks"][0]
            t["fks"][0] = (c, ref, " ON DELETE CASCADE")
    return new


def dump(tables):
    header = "-- MySQL dump (synthetic)\n/*!40101 SET NAMES utf8mb4 */;\n\n"
    return header + "\n".join(table_sql(n, t["cols"], t["idx"], t["fks"]) for n, t in tables.items())


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    old = build()
    (out / "large_v1.sql").write_text(dump(old))
    (out / "large_v2.sql").write_text(dump(mutate(old)))
