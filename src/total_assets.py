"""从指定年份和报表口径直接取得期末资产总计。"""
import re
from pathlib import Path
from unicodedata import normalize

import config
from context import build_table_ranges, format_evidence
from extract_unit import PAGE_MARKER
from retrieval import extract_years

CONSOLIDATED = r"合并(?:口径|资产负债表|报表)?|集团(?:口径)?"
PARENT = r"母公司(?:单体|口径|资产负债表|报表)?|公司资产负债表"
QUALIFIERS = re.compile(
    rf"比亚迪(?:股份有限公司)?|20\d{{2}}(?:年(?:末|底)?)?|12月31日|截至|期末|"
    rf"{PARENT}|{CONSOLIDATED}|以及|[和与及、,?。]"
)
METRIC = r"的?(?:总资产|资产总额|资产总计|账上(?:的)?资产(?:一共|总共)?|资产(?:一共|总共))"
TOTAL_ASSETS = re.compile(
    rf"{METRIC}(?P<second>{METRIC})?(?:分别|各)?(?:是|有|为)?(?:多少)?"
)
BALANCE_SHEETS = {
    "合并资产负债表": "合并",
    "母公司资产负债表": "母公司",
    "公司资产负债表": "母公司",
}
DATE_COLUMN = re.compile(r"(20\d{2})\s*年\s*12\s*月\s*31\s*日")
AMOUNT = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
ASSET_ROW = re.compile(rf"^[ \t]*资产总计[ \t]*\n\s*({AMOUNT})[ \t]*\n\s*({AMOUNT})[ \t]*$", re.M)


def balance_sheet_assets(path, year, meta):
    text = path.read_text(encoding="utf-8")
    markers = list(PAGE_MARKER.finditer(text))
    stride = config.CHUNK_SIZE - config.OVERLAP
    for start, end, table in build_table_ranges(text):
        name = re.sub(r"\s+", "", table["table_name"])
        scope = BALANCE_SHEETS.get(name)
        if scope is None or table["unit"] is None:
            continue
        rows = list(ASSET_ROW.finditer(text, start, end))
        if len(rows) != 1:
            continue
        row = rows[0]
        column_years = list(dict.fromkeys(DATE_COLUMN.findall(text, start, row.start())))
        if len(column_years) != len(row.groups()) or year not in column_years:
            continue

        cid = f"{path.stem}_{row.start() // stride}"
        record = meta.get(cid)
        if record is None or row.group() not in record[3]:
            continue
        page = next(int(marker[1]) for marker in reversed(markers) if marker.start() < row.start())
        amount = row.group(column_years.index(year) + 1)
        years = "、".join(column_years)
        body = (
            f"{table['table_name']}｜{year} 年末资产总计：{amount} {table['unit']}｜"
            f"原表列顺序：{years}｜单位来源：PDF 第 {table['unit_source_page']} 页\n"
            f"原文：\n{row.group().strip()}"
        )
        yield scope, (cid, year, page, record[3]), body


def lookup_total_assets(query, engine):
    """非本类问题返回 None，缺少任一指定年份或口径的证据则返回空结果。"""
    query = re.sub(r"\s+", "", normalize("NFKC", query))
    years = extract_years(query)
    parsed_dir = getattr(engine, "parsed_dir", None)
    match = TOTAL_ASSETS.fullmatch(QUALIFIERS.sub("", query))
    if not years or parsed_dir is None or match is None:
        return None

    parent = re.search(PARENT, query)
    consolidated = re.search(CONSOLIDATED, query)
    scopes = ("母公司",) if parent else ("合并",)
    if parent and consolidated:
        left, right = sorted((parent, consolidated), key=lambda term: term.start())
        between = query[left.end():right.start()]
        if re.search(r"[和与及、,]", between):
            if extract_years(between):
                return None
            scopes = ("合并", "母公司")
    if match["second"] and len(scopes) == 1:
        return None

    requested = {(year, scope): [] for year in years for scope in scopes}
    for path in sorted(Path(parsed_dir).glob("*.txt")):
        report_years = extract_years(path.stem)
        if report_years and report_years[0] in years:
            year = report_years[0]
            for scope, record, body in balance_sheet_assets(path, year, engine.meta):
                if (year, scope) in requested:
                    requested[year, scope].append((record, body))

    if any(len(matches) != 1 for matches in requested.values()):
        return [], ""
    records, evidence = [], []
    for number, matches in enumerate(requested.values(), start=1):
        record, body = matches[0]
        records.append(record)
        evidence.append(format_evidence(number, *record[:3], body))
    return records, "\n\n".join(evidence)
