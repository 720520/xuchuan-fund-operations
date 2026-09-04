import io
import zipfile

import pytest
from openpyxl import Workbook

from app.parsing import parse


def workbook(rows, title="Sheet1"):
    book = Workbook()
    sheet = book.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


@pytest.mark.parametrize(
    ("domain", "title", "rows", "expected"),
    [
        (
            "citics.com",
            "日间净值列表",
            [
                ["日期", "资产代码", "资产名称", "资产份额净值(元)", "资产份额累计净值(元)", "资产净值(元)", "实收资本(元)"],
                ["2026-08-28", "SB7648(A级)", "示例基金", "1.0123", "1.1200", "10,123,000", "10,000,000"],
            ],
            ("custodian:citics:1", "SB7648", "A类"),
        ),
        (
            "htsc.com",
            "基金净值表",
            [
                ["日期", "资产代码", "资产名称", "资产份额净值(元)", "资产份额累计净值(元)", "资产净值(元)", "分级情况", "总份额"],
                ["2026-08-28", "SBNN47", "示例基金", "1.0123", "1.1200", "10,123,000", "非分级产品", "10,000,000"],
            ],
            ("custodian:htsc:1", "SBNN47", "总"),
        ),
        (
            "cmschina.com.cn",
            "发送每日净值信息",
            [
                ["集合计划每日净值表"],
                ["日期", "产品代码", "产品名称", "总资产净值", "总资产份额", "单位净值", "累计单位净值"],
                ["2026年08月28日", "AAK02A", "示例基金A", "10,123,000", "10,000,000", "1.0123", "1.1200"],
            ],
            ("custodian:cmschina:1", "SAAK02", "A类"),
        ),
        (
            "swhysc.com",
            "Sheet1",
            [
                [],
                [None, "产品名称", "TA代码", "净值日期", "单位净值", "累计单位净值"],
                [None, "示例基金", "SA2889", "20260828", "1.0123", "1.1200"],
            ],
            ("custodian:swhysc:1", "SA2889", "总"),
        ),
    ],
)
def test_single_header_custodian_adapters(domain, title, rows, expected):
    result = parse("净值.xlsx", workbook(rows, title), context={"sender_domain": domain})
    assert result["errors"] == []
    assert result["parser_version"] == expected[0]
    assert result["records"][0]["product_code"] == expected[1]
    assert result["records"][0].get("share_class") == expected[2]
    assert result["records"][0]["valuation_date"] == "2026-08-28"
    assert result["records"][0]["unit_nav"] == "1.0123"


def test_ebscn_two_level_header_maps_share_to_master_product():
    rows = [
        ["资产净值表"],
        [],
        ["日期：", "2026-08-28"],
        [],
        ["产品名称", "", "产品代码", "净值情况", "", "净值情况", ""],
        ["", "", "资产净值", "资产净值", "资产份额", "单位净值", "累计净值"],
        ["示例基金", "", "SAYW68", "10,123,000", "10,000,000", "1.0123", "1.1200"],
        ["示例基金_A类份额", "", "AYW68A", "5,100,000", "5,000,000", "1.0200", "1.1300"],
    ]
    result = parse(
        "净值.xlsx", workbook(rows), context={"sender_domain": "ebscn.com"}
    )
    assert result["errors"] == []
    assert result["parser_version"] == "custodian:ebscn:1"
    assert [item["product_code"] for item in result["records"]] == ["SAYW68", "SAYW68"]
    assert result["records"][1]["share_class"] == "A类"
    assert result["records"][1]["net_assets"] == "5100000"


def test_zip_dispatches_members_through_registry():
    content = workbook(
        [
            ["日期", "资产代码", "资产名称", "资产份额净值(元)", "资产份额累计净值(元)", "资产净值(元)", "分级情况", "总份额"],
            ["2026-08-28", "SBNN47", "示例基金", "1.0123", "1.1200", "10,123,000", "非分级产品", "10,000,000"],
        ],
        "基金净值表",
    )
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("folder/净值.xlsx", content)
    result = parse(
        "托管附件.zip", archive.getvalue(), context={"sender_domain": "htsc.com"}
    )
    assert result["errors"] == []
    assert result["parser_version"] == "custodian:htsc:1"
    assert result["records"][0]["row_key"].startswith("净值.xlsx:")
