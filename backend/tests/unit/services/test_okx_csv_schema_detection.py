"""Funding vs trading CSV schema detection."""


def _write(path, meta_line, header_line):
    with open(path, "w", encoding="utf-8-sig") as fh:
        fh.write(meta_line + "\n")
        fh.write(header_line + "\n")


def test_funding_schema_detected(tmp_path):
    p = tmp_path / "f.csv"
    _write(p, "\ufeffUID:x,\ufeffTime Zone:UTC+3",
           "\ufeffid,\ufeffTime,\ufeffType,\ufeffAmount,\ufeffBefore Balance,\ufeffAfter Balance,\ufeffSymbol")
    from services.importer import _okx_csv_is_funding_schema
    assert _okx_csv_is_funding_schema(str(p)) is True


def test_trading_schema_not_detected_as_funding(tmp_path):
    p = tmp_path / "t.csv"
    _write(p, "\ufeffUID:x,\ufeffTime Zone:UTC+3",
           "\ufeffid,\ufeffOrder id,\ufeffTime,\ufeffTrade Type,\ufeffSymbol,\ufeffAction,\ufeffAmount")
    from services.importer import _okx_csv_is_funding_schema
    assert _okx_csv_is_funding_schema(str(p)) is False
