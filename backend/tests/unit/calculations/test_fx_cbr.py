"""Tests for the Central Bank of Russia FX source and RUBUSD routing.

Covers:
- ``update_FX_from_CBR`` success / failure paths with mocked SOAP responses.
- Routing in ``FX.update_fx_rate``: RUB pairs must go to CBR and non-RUB pairs
  must keep using Yahoo.
- A stored-value regression fixture so we notice if ``FX.get_rate`` semantics
  change around RUBUSD.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import requests

from common import models as common_models
from common.models import FX, CBRRateLimitError, update_FX_from_CBR


# --- XML fixtures ----------------------------------------------------------

CBR_XML_WITH_USD = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <GetCursOnDateResponse xmlns="http://web.cbr.ru/">
      <GetCursOnDateResult>
        <ValuteData xmlns="" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
          <diffgr:diffgram>
            <ValuteData>
              <ValuteCursOnDate>
                <Vname>US Dollar</Vname>
                <Vnom>1</Vnom>
                <Vcurs>90.1234</Vcurs>
                <Vcode>840</Vcode>
                <VchCode>USD</VchCode>
              </ValuteCursOnDate>
              <ValuteCursOnDate>
                <Vname>Euro</Vname>
                <Vnom>1</Vnom>
                <Vcurs>97.5678</Vcurs>
                <Vcode>978</Vcode>
                <VchCode>EUR</VchCode>
              </ValuteCursOnDate>
            </ValuteData>
          </diffgr:diffgram>
        </ValuteData>
      </GetCursOnDateResult>
    </GetCursOnDateResponse>
  </soap:Body>
</soap:Envelope>
"""

CBR_XML_WITH_JPY_VNOM_100 = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <GetCursOnDateResponse xmlns="http://web.cbr.ru/">
      <GetCursOnDateResult>
        <ValuteData xmlns="" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
          <diffgr:diffgram>
            <ValuteData>
              <ValuteCursOnDate>
                <Vname>Japanese Yen</Vname>
                <Vnom>100</Vnom>
                <Vcurs>60.5432</Vcurs>
                <Vcode>392</Vcode>
                <VchCode>JPY</VchCode>
              </ValuteCursOnDate>
            </ValuteData>
          </diffgr:diffgram>
        </ValuteData>
      </GetCursOnDateResult>
    </GetCursOnDateResponse>
  </soap:Body>
</soap:Envelope>
"""

CBR_XML_EMPTY = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <GetCursOnDateResponse xmlns="http://web.cbr.ru/">
      <GetCursOnDateResult>
        <ValuteData xmlns="" xmlns:diffgr="urn:schemas-microsoft-com:xml-diffgram-v1">
          <diffgr:diffgram>
            <ValuteData/>
          </diffgr:diffgram>
        </ValuteData>
      </GetCursOnDateResult>
    </GetCursOnDateResponse>
  </soap:Body>
</soap:Envelope>
"""


def _mock_response(text, status_code=200):
    """Build a MagicMock shaped like a ``requests.Response``."""
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


# --- update_FX_from_CBR unit tests (no DB needed) --------------------------


@pytest.mark.fx
@pytest.mark.unit
class TestUpdateFXFromCBR:
    """Unit tests for the CBR fetcher (pure function, no DB)."""

    def test_success_returns_decimal_rate(self):
        """A normal USD response should parse into a Decimal rate."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response(CBR_XML_WITH_USD)
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3))

        assert result is not None
        assert isinstance(result["exchange_rate"], Decimal)
        assert result["exchange_rate"] == Decimal("90.123400")
        assert result["actual_date"] == date(2024, 6, 3)
        assert result["requested_date"] == date(2024, 6, 3)
        mock_post.assert_called_once()

    def test_looks_up_foreign_side_regardless_of_arg_order(self):
        """Passing ``('USD', 'RUB')`` should still fetch the USD rate."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response(CBR_XML_WITH_USD)
            result = update_FX_from_CBR("USD", "RUB", date(2024, 6, 3))

        assert result is not None
        assert result["exchange_rate"] == Decimal("90.123400")

    def test_vnom_greater_than_one_applies_division(self):
        """``Vnom=100`` (e.g. JPY) must divide to get per-unit rate."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response(CBR_XML_WITH_JPY_VNOM_100)
            result = update_FX_from_CBR("RUB", "JPY", date(2024, 6, 3))

        # 60.5432 / 100 = 0.605432
        assert result is not None
        assert result["exchange_rate"] == Decimal("0.605432")

    def test_http_error_returns_none_after_retries(self):
        """HTTP 500 on every attempt should exhaust retries and return None."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response("", status_code=500)
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3), max_attempts=3)

        assert result is None
        assert mock_post.call_count == 3

    def test_missing_currency_returns_none_after_retries(self):
        """If the target currency is not in the payload, retries exhaust to None."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response(CBR_XML_EMPTY)
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3), max_attempts=2)

        assert result is None
        assert mock_post.call_count == 2

    def test_weekend_backoff_walks_to_earlier_date(self):
        """First empty response, second with data: actual_date must reflect the earlier day."""
        requested = date(2024, 6, 8)  # Saturday
        responses = [
            _mock_response(CBR_XML_EMPTY),
            _mock_response(CBR_XML_WITH_USD),
        ]

        with patch.object(common_models.requests, "post", side_effect=responses) as mock_post:
            result = update_FX_from_CBR("RUB", "USD", requested, max_attempts=3)

        assert result is not None
        assert result["actual_date"] == requested - timedelta(days=1)
        assert result["requested_date"] == requested
        assert mock_post.call_count == 2

    def test_network_error_returns_none(self):
        """A raised ``requests`` exception on every attempt should return None."""
        with patch.object(
            common_models.requests,
            "post",
            side_effect=requests.ConnectionError("offline"),
        ) as mock_post:
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3), max_attempts=2)

        assert result is None
        assert mock_post.call_count == 2

    def test_invalid_xml_returns_none(self):
        """Malformed response body should be handled gracefully."""
        with patch.object(common_models.requests, "post") as mock_post:
            mock_post.return_value = _mock_response("not xml <<<")
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3), max_attempts=2)

        assert result is None
        assert mock_post.call_count == 2

    def test_rate_limit_retries_then_succeeds(self):
        """HTTP 429 should sleep-and-retry the SAME date, not walk back."""
        responses = [
            _mock_response("", status_code=429),
            _mock_response("", status_code=429),
            _mock_response(CBR_XML_WITH_USD),
        ]
        with patch.object(
            common_models.requests, "post", side_effect=responses
        ) as mock_post, patch.object(common_models.time, "sleep") as mock_sleep:
            result = update_FX_from_CBR("RUB", "USD", date(2024, 6, 3))

        assert result is not None
        assert result["exchange_rate"] == Decimal("90.123400")
        # Should have retried on the SAME date (no walk-back), so actual == requested.
        assert result["actual_date"] == date(2024, 6, 3)
        assert mock_post.call_count == 3
        # Exponential backoff: 2.0s, then 4.0s between the two 429s.
        sleeps = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleeps == [2.0, 4.0]

    def test_rate_limit_exhausted_raises(self):
        """If CBR keeps returning 429, function must raise CBRRateLimitError (not clear data)."""
        with patch.object(
            common_models.requests, "post",
            return_value=_mock_response("", status_code=429),
        ), patch.object(common_models.time, "sleep"):
            with pytest.raises(CBRRateLimitError):
                update_FX_from_CBR("RUB", "USD", date(2024, 6, 3))

    def test_rub_on_both_sides_returns_none_without_http(self):
        """RUB→RUB is nonsensical for CBR; should short-circuit with no request."""
        with patch.object(common_models.requests, "post") as mock_post:
            result = update_FX_from_CBR("RUB", "RUB", date(2024, 6, 3))

        assert result is None
        mock_post.assert_not_called()


# --- FX.update_fx_rate routing tests (DB-backed) ---------------------------


@pytest.mark.fx
@pytest.mark.unit
class TestFXUpdateRouting:
    """Verify RUB pairs go to CBR and non-RUB pairs keep going to Yahoo."""

    def test_rub_pair_routes_to_cbr_not_yahoo(self, user):
        """For each missing RUB field, CBR is queried; Yahoo is not."""
        fake_cbr = {
            "exchange_rate": Decimal("90.1234"),
            "actual_date": date(2024, 6, 3),
            "requested_date": date(2024, 6, 3),
        }
        fake_yahoo = {
            "exchange_rate": Decimal("1.1"),
            "actual_date": date(2024, 6, 3),
            "requested_date": date(2024, 6, 3),
        }

        with patch.object(common_models, "update_FX_from_CBR", return_value=fake_cbr) as cbr, patch.object(
            common_models, "update_FX_from_Yahoo", return_value=fake_yahoo
        ) as yahoo:
            FX.update_fx_rate(date(2024, 6, 3), user)

        rub_calls = [c for c in cbr.call_args_list if "RUB" in (c.args[0], c.args[1])]
        yahoo_rub_calls = [c for c in yahoo.call_args_list if "RUB" in (c.args[0], c.args[1])]

        assert rub_calls, "CBR should have been called for the RUBUSD pair"
        assert not yahoo_rub_calls, "Yahoo must not be called for any RUB pair"

        fx_row = FX.objects.get(date=date(2024, 6, 3))
        assert fx_row.RUBUSD == Decimal("90.1234")

    def test_non_rub_pair_routes_to_yahoo(self, user):
        """Non-RUB pairs must still be fetched from Yahoo Finance."""
        fake_cbr = {
            "exchange_rate": Decimal("90.0000"),
            "actual_date": date(2024, 6, 3),
            "requested_date": date(2024, 6, 3),
        }
        fake_yahoo = {
            "exchange_rate": Decimal("1.100000"),
            "actual_date": date(2024, 6, 3),
            "requested_date": date(2024, 6, 3),
        }

        with patch.object(common_models, "update_FX_from_CBR", return_value=fake_cbr) as cbr, patch.object(
            common_models, "update_FX_from_Yahoo", return_value=fake_yahoo
        ) as yahoo:
            FX.update_fx_rate(date(2024, 6, 3), user)

        # All CBR calls should only involve RUB pairs.
        for call in cbr.call_args_list:
            assert "RUB" in (call.args[0], call.args[1])

        # At least one non-RUB pair (e.g. USDEUR) must have hit Yahoo.
        non_rub_yahoo_calls = [
            call for call in yahoo.call_args_list if "RUB" not in (call.args[0], call.args[1])
        ]
        assert non_rub_yahoo_calls, "Non-RUB pairs should still be fetched via Yahoo"

        fx_row = FX.objects.get(date=date(2024, 6, 3))
        assert fx_row.USDEUR == Decimal("1.100000")


# --- Regression: stored RUBUSD must keep the same numeric meaning ----------


@pytest.mark.fx
@pytest.mark.unit
class TestRUBUSDGetRateRegression:
    """Protected-logic guard: a known RUBUSD must produce a stable get_rate result."""

    def test_stored_rubusd_drives_expected_rub_to_usd_rate(self, user):
        """Golden fixture: RUBUSD=90.5000 should make get_rate('RUB','USD') ≈ 1/90.5."""
        fx = FX.objects.create(date=date(2024, 6, 3), RUBUSD=Decimal("90.5000"))
        fx.investors.add(user)

        result = FX.get_rate("RUB", "USD", date(2024, 6, 3), investor=user)

        # FX.get_rate returns "multiply source by this to get target", so 1 RUB in USD.
        assert isinstance(result["FX"], Decimal)
        # 1 / 90.5 = 0.011049723... -> rounded to 6 dp
        assert result["FX"] == Decimal("0.011050")
        assert result["conversions"] == 1
