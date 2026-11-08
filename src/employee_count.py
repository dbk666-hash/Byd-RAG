"""用年报披露的在职员工合计计算两年人数差。"""
from collections import defaultdict
import re

COMPARISON = re.compile(
    r"20\d{2}\s*年(?:末)?\s*(?:比亚迪\s*)?在职员工(?:的?(?:人数|数量))?\s*比\s*"
    r"(?:去年|上(?:一)?年(?:度)?|20\d{2}\s*年(?:末)?)\s*"
    r"(?:多了?|少了?|增加了?|减少了?|变化了?)\s*多少(?:人)?[？?。]?"
)
TOTAL_ROW = re.compile(
    r"^[ \t]*报告期末在职员工的数量合计[（(]人[）)][ \t]*\n\s*"
    r"((?:\d{1,3}(?:,\d{3})+|\d+))[ \t]*$", re.M
)


def employee_totals(query, records):
    """返回各年可核实的员工总数和证据编号，其他问法返回 None。"""
    if not COMPARISON.fullmatch(query.strip()):
        return None

    by_year = defaultdict(dict)
    for number, (_, year, _, body) in enumerate(records, start=1):
        for amount in TOTAL_ROW.findall(body):
            by_year[year].setdefault(int(amount.replace(",", "")), number)
    return {year: next(iter(values.items())) for year, values in by_year.items() if len(values) == 1}


def employee_difference(years, totals):
    current, previous = years
    current_total, current_cite = totals[current]
    previous_total, previous_cite = totals[previous]
    delta = current_total - previous_total
    if delta:
        direction = "增加" if delta > 0 else "减少"
        change = f"{direction} {abs(delta):,} 人"
    else:
        change = "人数持平"
    return (
        f"比亚迪 {current} 年末在职员工为 {current_total:,} 人 [证据{current_cite}]，"
        f"{previous} 年末为 {previous_total:,} 人 [证据{previous_cite}]，两年相比{change}。"
    )
