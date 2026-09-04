"""Versioned custodian workbook adapters.

Adapters are selected by sender domain when available and by workbook signature for
manual uploads. Each adapter returns raw canonical fields; validation stays in the
main parsing module so every source follows the same numerical safety rules.
"""

from dataclasses import dataclass
import re


def clean(value):
    return re.sub(r"\s+", "", str(value or "")).strip()


def header_index(row):
    return {clean(value): index for index, value in enumerate(row) if clean(value)}


def cell(row, indices, label, default=None):
    index = indices.get(label)
    return row[index] if index is not None and index < len(row) else default


def share_from_text(value):
    text = str(value or "")
    match = re.search(r"[_（(]?([A-Za-z])(?:级|类(?:份额)?)[）)]?$", text)
    if match:
        return f"{match.group(1).upper()}类"
    match = re.search(r"[（(]([^（）()]+)[）)]", text)
    if match and match.group(1) not in {"总", "总份额"}:
        value = match.group(1).replace("级", "类")
        return value
    return None


def base_name(value):
    return re.sub(r"[_（(]?[A-Za-z](?:级|类(?:份额)?)[）)]?$", "", str(value or "")).strip()


@dataclass(frozen=True)
class AdapterResult:
    records: list[dict]
    errors: list[dict]


class CustodianAdapter:
    name = "base"
    version = "1"
    domains = ()

    def domain_matches(self, context):
        return context.get("sender_domain", "").lower() in self.domains

    def signature_matches(self, tables):
        raise NotImplementedError

    def parse(self, filename, tables, context):
        raise NotImplementedError

    @property
    def parser_version(self):
        return f"custodian:{self.name}:{self.version}"


class CiticsAdapter(CustodianAdapter):
    name = "citics"
    version = "1"
    domains = ("citics.com",)

    def signature_matches(self, tables):
        return any(
            (
                "估值基准日" in header_index(row)
                and "母基金单位净值" in header_index(row)
                and "协会备案代码" in header_index(row)
            )
            or (
                {"日期", "资产代码", "资产份额净值(元)", "实收资本(元)"}
                <= set(header_index(row))
            )
            for _, rows in tables
            for row in rows[:8]
        )

    def parse(self, filename, tables, context):
        records = []
        for sheet, rows in tables:
            for row_number, row in enumerate(rows, 1):
                indices = header_index(row)
                if {"日期", "资产代码", "资产份额净值(元)"} <= set(indices):
                    for data_number, data in enumerate(rows[row_number:], row_number + 1):
                        date_value = cell(data, indices, "日期")
                        code_value = str(cell(data, indices, "资产代码") or "").strip()
                        if not date_value or not code_value:
                            continue
                        records.append(
                            {
                                "product_code": re.sub(r"[（(].*?[）)]$", "", code_value),
                                "product_name": base_name(cell(data, indices, "资产名称")),
                                "share_class": share_from_text(code_value) or "总",
                                "valuation_date": date_value,
                                "unit_nav": cell(data, indices, "资产份额净值(元)"),
                                "accumulated_nav": cell(data, indices, "资产份额累计净值(元)"),
                                "net_assets": cell(data, indices, "资产净值(元)"),
                                "total_shares": cell(data, indices, "实收资本(元)"),
                                "row_key": f"{sheet}:{data_number}",
                            }
                        )
                    break
                if not {"估值基准日", "单位净值", "协会备案代码"} <= set(indices):
                    continue
                for data_number, data in enumerate(rows[row_number:], row_number + 1):
                    if not cell(data, indices, "估值基准日"):
                        continue
                    code_value = cell(data, indices, "产品代码")
                    records.append(
                        {
                            "product_code": cell(data, indices, "协会备案代码"),
                            "product_name": base_name(cell(data, indices, "产品名称")),
                            "share_class": share_from_text(code_value)
                            or share_from_text(cell(data, indices, "产品名称"))
                            or "总",
                            "valuation_date": cell(data, indices, "估值基准日"),
                            "unit_nav": cell(data, indices, "单位净值"),
                            "accumulated_nav": cell(data, indices, "累计净值"),
                            "net_assets": cell(data, indices, "资产净值"),
                            "total_shares": cell(data, indices, "实收资本"),
                            "row_key": f"{sheet}:{data_number}",
                        }
                    )
                break
        return AdapterResult(records, [])


class HtscAdapter(CustodianAdapter):
    name = "htsc"
    version = "1"
    domains = ("htsc.com",)

    def signature_matches(self, tables):
        return any(
            {"日期", "资产代码", "资产份额净值(元)", "资产份额累计净值(元)"}
            <= set(header_index(row))
            for _, rows in tables
            for row in rows[:8]
        )

    def parse(self, filename, tables, context):
        records = []
        for sheet, rows in tables:
            for row_number, row in enumerate(rows, 1):
                indices = header_index(row)
                if not {"日期", "资产代码", "资产份额净值(元)"} <= set(indices):
                    continue
                for data_number, data in enumerate(rows[row_number:], row_number + 1):
                    if not cell(data, indices, "日期"):
                        continue
                    records.append(
                        {
                            "product_code": cell(data, indices, "资产代码"),
                            "product_name": base_name(cell(data, indices, "资产名称")),
                            "share_class": share_from_text(cell(data, indices, "资产名称"))
                            or share_from_text(filename)
                            or "总",
                            "valuation_date": cell(data, indices, "日期"),
                            "unit_nav": cell(data, indices, "资产份额净值(元)"),
                            "accumulated_nav": cell(data, indices, "资产份额累计净值(元)"),
                            "net_assets": cell(data, indices, "资产净值(元)"),
                            "total_shares": cell(data, indices, "总份额"),
                            "row_key": f"{sheet}:{data_number}",
                        }
                    )
                break
        return AdapterResult(records, [])


class EbscnAdapter(CustodianAdapter):
    name = "ebscn"
    version = "1"
    domains = ("ebscn.com",)

    def signature_matches(self, tables):
        labels = {clean(value) for _, rows in tables for row in rows[:10] for value in row}
        return {"产品名称", "产品代码", "资产份额", "单位净值", "累计净值"} <= labels

    def parse(self, filename, tables, context):
        records = []
        for sheet, rows in tables:
            header_row = next(
                (index for index, row in enumerate(rows) if "产品名称" in header_index(row)),
                None,
            )
            if header_row is None or header_row + 1 >= len(rows):
                continue
            top, lower = rows[header_row], rows[header_row + 1]
            product_name_col = header_index(top).get("产品名称", 0)
            product_code_col = header_index(top).get("产品代码", 2)
            date_col = header_index(top).get("净值日期")
            lower_indices = header_index(lower)
            nav_col = lower_indices.get("单位净值")
            accumulated_col = lower_indices.get("累计净值")
            shares_col = lower_indices.get("资产份额")
            net_asset_columns = [
                index
                for index, value in enumerate(lower)
                if clean(value) == "资产净值" and index >= product_code_col
            ]
            net_assets_col = max(net_asset_columns) if net_asset_columns else None
            fixed_date = None
            for row in rows[:header_row]:
                if row and clean(row[0]) in {"日期:", "日期："} and len(row) > 1:
                    fixed_date = row[1]
            base_code = base_product_name = None
            for data in rows[header_row + 2 :]:
                name = data[product_name_col] if product_name_col < len(data) else None
                code = data[product_code_col] if product_code_col < len(data) else None
                if name and code and not share_from_text(name):
                    base_code, base_product_name = code, name
                    break
            for offset, data in enumerate(rows[header_row + 2 :], header_row + 3):
                name = data[product_name_col] if product_name_col < len(data) else None
                code = data[product_code_col] if product_code_col < len(data) else None
                nav = data[nav_col] if nav_col is not None and nav_col < len(data) else None
                if not name or not code or nav in (None, ""):
                    continue
                derived_base_code = (
                    f"S{str(code)[:-1]}" if share_from_text(name) and not str(code).startswith("S") else code
                )
                records.append(
                    {
                        "product_code": base_code or derived_base_code,
                        "product_name": base_name(base_product_name or name),
                        "share_class": share_from_text(name) or "总",
                        "valuation_date": data[date_col] if date_col is not None and date_col < len(data) else fixed_date,
                        "unit_nav": nav,
                        "accumulated_nav": data[accumulated_col] if accumulated_col is not None and accumulated_col < len(data) else None,
                        "net_assets": data[net_assets_col] if net_assets_col is not None and net_assets_col < len(data) else None,
                        "total_shares": data[shares_col] if shares_col is not None and shares_col < len(data) else None,
                        "row_key": f"{sheet}:{offset}",
                    }
                )
        return AdapterResult(records, [])


class CmschinaAdapter(CustodianAdapter):
    name = "cmschina"
    version = "1"
    domains = ("cmschina.com.cn",)

    def signature_matches(self, tables):
        return any(
            {"日期", "产品代码", "总资产净值", "总资产份额", "单位净值"}
            <= set(header_index(row))
            for _, rows in tables
            for row in rows[:8]
        )

    def parse(self, filename, tables, context):
        records = []
        for sheet, rows in tables:
            for row_number, row in enumerate(rows, 1):
                indices = header_index(row)
                if not {"日期", "产品代码", "单位净值"} <= set(indices):
                    continue
                total_names = {}
                for data in rows[row_number:]:
                    total_code = str(cell(data, indices, "产品代码") or "").strip()
                    if total_code.startswith("S"):
                        total_names[total_code] = base_name(
                            cell(data, indices, "产品名称")
                        )
                for data_number, data in enumerate(rows[row_number:], row_number + 1):
                    code = str(cell(data, indices, "产品代码") or "").strip()
                    if not code or not cell(data, indices, "日期"):
                        continue
                    is_total = code.startswith("S")
                    base_code = code if is_total else f"S{code[:-1]}"
                    records.append(
                        {
                            "product_code": base_code,
                            "product_name": total_names.get(base_code)
                            or base_name(cell(data, indices, "产品名称")),
                            "share_class": "总" if is_total else f"{code[-1].upper()}类",
                            "valuation_date": cell(data, indices, "日期"),
                            "unit_nav": cell(data, indices, "单位净值"),
                            "accumulated_nav": cell(data, indices, "累计单位净值"),
                            "net_assets": cell(data, indices, "总资产净值"),
                            "total_shares": cell(data, indices, "总资产份额"),
                            "row_key": f"{sheet}:{data_number}",
                        }
                    )
                break
        return AdapterResult(records, [])


class SwhyscAdapter(CustodianAdapter):
    name = "swhysc"
    version = "1"
    domains = ("swhysc.com",)

    def signature_matches(self, tables):
        return any(
            {"产品名称", "TA代码", "净值日期", "单位净值", "累计单位净值"}
            <= set(header_index(row))
            for _, rows in tables
            for row in rows[:8]
        )

    def parse(self, filename, tables, context):
        records = []
        for sheet, rows in tables:
            for row_number, row in enumerate(rows, 1):
                indices = header_index(row)
                if not {"产品名称", "TA代码", "净值日期", "单位净值"} <= set(indices):
                    continue
                for data_number, data in enumerate(rows[row_number:], row_number + 1):
                    if not cell(data, indices, "净值日期"):
                        continue
                    records.append(
                        {
                            "product_code": cell(data, indices, "TA代码"),
                            "product_name": base_name(cell(data, indices, "产品名称")),
                            "share_class": share_from_text(cell(data, indices, "产品名称")) or "总",
                            "valuation_date": cell(data, indices, "净值日期"),
                            "unit_nav": cell(data, indices, "单位净值"),
                            "accumulated_nav": cell(data, indices, "累计单位净值"),
                            "row_key": f"{sheet}:{data_number}",
                        }
                    )
                break
        return AdapterResult(records, [])


ADAPTERS = [CiticsAdapter(), HtscAdapter(), EbscnAdapter(), CmschinaAdapter(), SwhyscAdapter()]
KNOWN_DOMAINS = {domain for adapter in ADAPTERS for domain in adapter.domains}


def is_known_custodian(context=None):
    return (context or {}).get("sender_domain", "").lower() in KNOWN_DOMAINS


def select_adapter(tables, context=None):
    context = context or {}
    domain_matches = [adapter for adapter in ADAPTERS if adapter.domain_matches(context)]
    for adapter in domain_matches:
        if adapter.signature_matches(tables):
            return adapter
    # A known custodian domain with a changed layout must enter review instead of
    # being misclassified as another custodian whose labels happen to overlap.
    if domain_matches:
        return None
    for adapter in ADAPTERS:
        if adapter.signature_matches(tables):
            return adapter
    return None
