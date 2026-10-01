# SQL Schema Diff

Lokalne narzędzie do porównywania struktury bazy MySQL między releasami.
Wrzucasz dwa pliki `.sql` (eksport struktury), dostajesz drzewo z zaznaczonymi różnicami
i eksport do SVG.

Działa w całości lokalnie: serwer nasłuchuje tylko na `127.0.0.1`, pliki są przetwarzane w pamięci
i nigdzie nie są zapisywane ani logowane, frontend nie ładuje nic z internetu.

## Uruchomienie

```bash
./run.sh            # pierwsze uruchomienie tworzy .venv i instaluje zależności
# → http://127.0.0.1:8765
```

## Eksport struktury

```bash
mysqldump --no-data --routines --triggers --events -u USER -p DB > release_X.sql
```

## Co jest porównywane

| Element | Atrybuty |
|---|---|
| Tabele | engine, charset, collate, row_format, comment, CHECK |
| Kolumny | typ, NULL/NOT NULL, default, AUTO_INCREMENT, ON UPDATE, generated, charset, collation, comment |
| Indeksy | rodzaj (PRIMARY/UNIQUE/INDEX/FULLTEXT/SPATIAL), kolumny |
| Klucze obce | kolumny, referencja, ON DELETE / ON UPDATE |
| Widoki, triggery, procedury, funkcje, eventy | znormalizowany tekst definicji |

Normalizacja (ignorowane, by uniknąć fałszywych różnic): licznik `AUTO_INCREMENT=`, `DEFINER`,
`ALGORITHM`, `SQL SECURITY`, szerokość wyświetlania typów całkowitych (`int(11)` = `int`, poza `tinyint(1)`),
białe znaki, komentarze, kolejność kolumn.

## Struktura

```
backend/parser.py   dump → model (sqlglot + własny splitter instrukcji / DELIMITER)
backend/diff.py     model A vs B → drzewo ze statusami added/removed/modified/unchanged
backend/main.py     FastAPI: POST /api/diff + serwowanie frontendu
frontend/           D3 (vendorowane), filtry, panel szczegółów, eksport SVG
```

## Testy

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
python scripts/generate_fixtures.py /tmp   # syntetyczna para dumpów ~110 tabel
```
