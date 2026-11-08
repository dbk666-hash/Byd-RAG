"""从解析后的比亚迪年报提取表格的金额单位及原文出处。"""
import argparse
import json
import re
from pathlib import Path
from unicodedata import normalize

PAGE_MARKER = re.compile(r"=====PAGE (\d+)=====")
REPORT_HEADER = re.compile(r"比亚迪股份有限公司\s*20\d\d\s*年\s*年度报告(?:全文)?")
FINANCIAL_START = re.compile(r"二、\s*财务报表")
FINANCIAL_END = re.compile(r"(?:三、\s*(?:公司)?基本情况|注:\s*财务报表附注中标记为.+)")
STATEMENT_TITLE = re.compile(
    r"\d+、\s*((?:(?:合并|母公司|公司)\s*)?"
    r"(?:资产负债表|利润表|现金流量表|(?:所有者|股东)权益变动表))"
)
NUMBERED_TITLE = re.compile(r"(?:\(\d+\)|\d+、|[一二三四五六七八九十]+、)\s*(\D.+)")
CONSOLIDATED_NOTES = re.compile(r"七、\s*合并财务报表主要项目注释")
NOTE_HEADING = re.compile(r"\d{1,3}[.、](?:\s*([^\W\d_].*))?")
YEAR_COLUMN = re.compile(r"(20\d{2})\s*年")
RECEIVABLES_AGING = re.compile(r".*应收账款的账龄分析如下:")
TAX_RECONCILIATION = re.compile(r"所得税费用与利润总额的关系列示如下:")
AMOUNT_UNIT = r"(亿元|百万元|万元|千元|元/股|元)"
UNIT_LINE = re.compile(
    rf"(?:注:\s*)?(?:本表\s*)?(?:金额\s*)?单位\s*(?:为\s*)?"
    rf":?\s*(?:人民币\s*)?{AMOUNT_UNIT}[。.]?"
)
UNIT_SENTENCE = re.compile(rf"以\s*(?:人民币\s*)?{AMOUNT_UNIT}\s*为\s*单位")
TABLE_UNIT_SENTENCE = re.compile(
    rf"(?:注:\s*)?本表\s*(?:金额\s*)?(?:均\s*)?{UNIT_SENTENCE.pattern}"
    r"(?:列示|表示)?[。.]?"
)
SECTION_UNIT_LINE = re.compile(
    rf"财务附注中报表的单位\s*(?:为\s*)?:?\s*(?:人民币\s*)?{AMOUNT_UNIT}[。.]?"
)


def read_lines(text):
    parts = PAGE_MARKER.split(text)
    rows = []
    for i in range(1, len(parts), 2):
        page = int(parts[i])
        previous_was_header = False
        for number, original in enumerate(parts[i + 1].splitlines(), start=1):
            original = original.strip()
            if not original:
                continue
            line = normalize("NFKC", original)
            if REPORT_HEADER.fullmatch(line):
                previous_was_header = True
                continue
            if previous_was_header and line.isdecimal() and len(line) <= 3:
                previous_was_header = False
                continue
            previous_was_header = False
            rows.append((page, number, original, line))
    return rows


def unit_notes(rows, *patterns):
    notes = []
    for page, _, original, line in rows:
        for pattern in patterns:
            match = pattern.fullmatch(line)
            if match:
                notes.append((page, match.group(1), original))
                break
    return notes


def table_record(name, start, end, notes, default=None):
    unit = None
    scope = None
    if notes:
        if len({note[1] for note in notes}) == 1:
            unit, scope = notes[0], "table"
        else:
            scope = "conflict"
    elif default:
        unit, scope = default, "section"
    return {
        "table_name": name,
        "table_pages": (start[0], end[0]) if end else None,
        "table_start_page": start[0],
        "table_start_line": start[1],
        "table_end_line": end[1] if end else None,
        "unit": unit[1] if unit else None,
        "unit_source_page": unit[0] if unit else None,
        "unit_note": unit[2] if unit else None,
        "unit_scope": scope,
    }


def report_unit_notes(rows):
    notes = []
    for page, _, original, line in rows:
        if "编制本财务报表" in line and "除有特别说明外" in line:
            match = UNIT_SENTENCE.search(line)
            if match:
                notes.append((page, match.group(1), original))
    return notes


def note_table(name, rows, default):
    notes = unit_notes(rows, UNIT_LINE, TABLE_UNIT_SENTENCE)
    record = table_record(name, rows[0], rows[-1], notes, default)
    for left, right in zip(rows, rows[1:]):
        first = YEAR_COLUMN.fullmatch(left[3])
        second = YEAR_COLUMN.fullmatch(right[3])
        if first and second and first[1] != second[1]:
            record["table_years"] = (first[1], second[1])
            break
    return record


def extract_note_tables(rows, financial_end):
    chapter = next(
        (i for i in range(financial_end, len(rows)) if CONSOLIDATED_NOTES.fullmatch(rows[i][3])),
        None,
    )
    if chapter is None:
        return []
    end = next(
        (i for i in range(chapter + 1, len(rows)) if rows[i][3].startswith("八、")),
        len(rows),
    )
    defaults = report_unit_notes(rows[financial_end:chapter])
    default = defaults[0] if len({note[1] for note in defaults}) == 1 else None

    headings = []
    for index in range(chapter + 1, end - 1):
        match = NOTE_HEADING.fullmatch(rows[index][3])
        if match:
            title = match[1] or rows[index + 1][3]
            title_index = index if match[1] else index + 1
            headings.append((index, title_index, title))

    records = []
    for position, (_, title_index, title) in enumerate(headings):
        stop = headings[position + 1][0] if position + 1 < len(headings) else end
        if title == "应收账款":
            start = next(
                (i for i in range(title_index + 1, stop) if RECEIVABLES_AGING.fullmatch(rows[i][3])),
                None,
            )
            if start is None:
                continue
            table_end = next(
                (i for i in range(start + 1, stop) if rows[i][3].startswith("上述应收账款")),
                None,
            )
            if table_end is not None:
                records.append(note_table("应收账款账龄分析", rows[start:table_end], default))
        elif title == "所得税费用":
            reconciliation = next(
                (i for i in range(title_index + 1, stop) if TAX_RECONCILIATION.fullmatch(rows[i][3])),
                None,
            )
            if reconciliation is None:
                continue
            records.append(note_table(title, rows[title_index:reconciliation], default))
            table_end = next(
                (i for i in range(reconciliation + 1, stop) if re.match(r"注\s*\d+\s*:", rows[i][3])),
                stop,
            )
            records.append(
                note_table("所得税费用与利润总额的关系", rows[reconciliation:table_end], default)
            )
    return records


def extract_table_units(text):
    rows = read_lines(text)
    financial_start = next(
        (i for i, row in enumerate(rows) if FINANCIAL_START.fullmatch(row[3])), len(rows)
    )
    financial_end = next(
        (i for i in range(financial_start + 1, len(rows)) if FINANCIAL_END.fullmatch(rows[i][3])),
        len(rows),
    )
    records = []

    # 正文里的编号标题，只有紧跟明确的表级单位声明时才建立关联。
    for index, row in enumerate(rows[:financial_start]):
        title = NUMBERED_TITLE.fullmatch(row[3])
        if not title:
            continue
        for candidate in rows[index + 1:min(index + 4, financial_start)]:
            if candidate[0] != row[0] or NUMBERED_TITLE.fullmatch(candidate[3]):
                break
            notes = unit_notes([candidate], UNIT_LINE, TABLE_UNIT_SENTENCE)
            if notes:
                records.append(table_record(title.group(1), row, None, notes))
                break

    headings = []
    for index in range(financial_start + 1, financial_end):
        title = STATEMENT_TITLE.fullmatch(rows[index][3])
        if title:
            headings.append((index, title.group(1)))
    if not headings:
        return records

    defaults = unit_notes(rows[financial_start:headings[0][0]], SECTION_UNIT_LINE)
    if not defaults:
        defaults = report_unit_notes(rows[financial_end:])
    default = defaults[0] if len({note[1] for note in defaults}) == 1 else None

    # 按标题行分表。同页上的下一张表也能形成边界，续页和表尾一起检查。
    for position, (start, name) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else financial_end
        notes = unit_notes(rows[start + 1:end], UNIT_LINE, TABLE_UNIT_SENTENCE)
        records.append(table_record(name, rows[start], rows[end - 1], notes, default))
    records.extend(extract_note_tables(rows, financial_end))
    return records


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="匹配比亚迪年报的表格金额单位及出处")
    parser.add_argument(
        "report",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parent.parent / "data" / "parsed" / "BYD_2022.txt",
    )
    args = parser.parse_args()
    tables = extract_table_units(args.report.read_text(encoding="utf-8"))
    print(json.dumps(tables, ensure_ascii=False, indent=2))
