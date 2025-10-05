# Yahoo Finance API Access Fix

## Problem

Yahoo Finance was blocking API requests with errors like:
- "Edge: Too Many Requests"
- "$USDEUR=X: possibly delisted; No price data found"
- "Yahoo API requires curl_cffi session not <class 'requests.sessions.Session'>"
- "Setting period, start and end is nonsense. Set maximum 2 of them."

## Root Cause

Multiple issues were involved:

1. **Anti-bot Protection**: Yahoo Finance blocks requests without proper browser headers
2. **Modern yfinance Architecture**: Newer versions of yfinance use `curl_cffi` internally and don't accept custom `requests.Session()` objects
3. **API Parameter Constraints**: The yfinance `history()` method only accepts a maximum of 2 out of 3 parameters: `period`, `start`, `end`

## Solution

The fix evolved through several iterations:

### Final Solution
Modern yfinance (v0.2.30+) uses `curl_cffi` internally to handle browser mimicking automatically. The solution is:
1. **Let yfinance handle the session** - Don't pass custom session objects
2. **Use only start and end dates** - Don't set `period` when using explicit date ranges
3. **Keep custom headers for direct requests** - Still use browser headers for `is_yahoo_finance_available()`

### Changes Made

#### 1. `is_yahoo_finance_available()` Function
**File:** `portfolio_management/common/models.py` (lines 1212-1229)

**Before:**
```python
def is_yahoo_finance_available():
    url = "https://finance.yahoo.com"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True
    except requests.ConnectionError:
        pass
    return False
```

**After:**
```python
def is_yahoo_finance_available():
    """Check if Yahoo Finance is available by making a test request with proper headers"""
    url = "https://finance.yahoo.com"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return True
    except (requests.ConnectionError, requests.Timeout):
        pass
    return False
```

#### 2. `update_FX_from_Yahoo()` Function
**File:** `portfolio_management/common/models.py` (lines 1232-1308)

**Key Changes:**
- **Removed custom session** - Let yfinance use its internal `curl_cffi` session
- **Removed period parameter** - Only use `start` and `end` dates (yfinance limitation)
- Added 0.5 second delay between requests to avoid rate limiting
- Improved error logging and handling

**Final Working Code:**
```python
# Let yfinance handle the session internally (uses curl_cffi for better browser mimicking)
ticker = yf.Ticker(currency_pair)

# Note: Only set start and end, not period (yfinance allows max 2 of period/start/end)
exchange_rate_data = ticker.history(
    start=start_date.strftime('%Y-%m-%d'),
    end=end_date.strftime('%Y-%m-%d')
)
```

#### 3. `import_security_prices_from_yahoo()` Function
**File:** `portfolio_management/core/import_utils.py` (lines 591-649)

**Key Changes:**
- **Removed custom session** - Let yfinance use its internal `curl_cffi` session
- Simplified ticker creation in async executor

```python
# Let yfinance handle the session internally (uses curl_cffi for better browser mimicking)
ticker = await loop.run_in_executor(None, yf.Ticker, security.yahoo_symbol)
```

## Testing

### Test FX Rate Fetch
```python
from common.models import FX
from datetime import date

# This should now work
user = CustomUser.objects.first()
FX.update_fx_rate(date(2024, 10, 4), user)
```

### Test Direct Function Call
```python
from common.models import update_FX_from_Yahoo
from datetime import date

result = update_FX_from_Yahoo('USD', 'EUR', date(2024, 10, 4))
print(result)
# Should return: {'exchange_rate': 0.xxxxx, 'actual_date': ..., 'requested_date': ...}
```

### Test Availability Check
```python
from common.models import is_yahoo_finance_available

available = is_yahoo_finance_available()
print(f"Yahoo Finance available: {available}")
# Should print: Yahoo Finance available: True
```

## Important Notes

### Rate Limiting
Even with proper headers, Yahoo Finance may rate-limit if you make too many requests too quickly:
- Added 0.5 second delay between FX rate requests
- Consider adding delays if importing large amounts of data
- If you get rate-limited, wait a few minutes before retrying

### Headers Maintenance
The User-Agent string mimics Chrome 91. If Yahoo Finance updates their blocking:
- Update the User-Agent to a newer browser version
- Check that all required headers are present
- Test with the latest browser headers

### Alternative Approaches
If issues persist:
1. **Use a rotating User-Agent library** like `fake_useragent`
2. **Add request delays** (increase from 0.5s to 1-2s)
3. **Use proxies** for high-volume requests
4. **Consider yfinance alternatives** like `pandas_datareader` or direct API calls

## How It Works

### Modern yfinance Architecture

Modern versions of yfinance (v0.2.30+) use `curl_cffi` internally, which:
- Automatically mimics real browser TLS fingerprints
- Handles proper headers without manual configuration
- Bypasses most anti-bot protection

**What this means:**
- ✅ No need to pass custom sessions to yfinance
- ✅ Browser mimicking handled automatically
- ✅ Simpler, more maintainable code
- ❌ Don't try to override with `requests.Session()` - it will fail

### Browser Headers for Direct Requests

For direct requests (like `is_yahoo_finance_available()`), we still use custom headers:

```python
{
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}
```

## Common Errors and Solutions

### Error: "Yahoo API requires curl_cffi session"
**Cause:** Trying to pass a custom `requests.Session()` to yfinance
**Solution:** Remove the session parameter, let yfinance handle it

```python
# ❌ Wrong
session = requests.Session()
ticker = yf.Ticker(symbol, session=session)

# ✅ Correct
ticker = yf.Ticker(symbol)
```

### Error: "Setting period, start and end is nonsense"
**Cause:** Passing all three parameters: `period`, `start`, and `end`
**Solution:** Only use `start` and `end` (remove `period`)

```python
# ❌ Wrong
ticker.history(period="1d", start="2024-01-01", end="2024-01-02")

# ✅ Correct
ticker.history(start="2024-01-01", end="2024-01-02")
```

### Still Getting Blocked?
1. **Check if Yahoo Finance is having issues**: Visit https://finance.yahoo.com manually
2. **Wait a few minutes**: You might have hit rate limits
3. **Check your IP**: Some IPs may be blocked by Yahoo
4. **Update yfinance**: Make sure you have the latest version with `curl_cffi` support

### "No data found" Errors
1. **Check currency pair format**: Should be `XXXYYY=X` (e.g., `USDEUR=X`)
2. **Verify date**: Market might be closed on that date
3. **Check symbol**: Currency pair might not be available on Yahoo Finance
4. **Check date range**: Start date should be before end date

### Import Still Failing?
Check logs for specific error messages:
```bash
# In Django shell
import logging
logging.basicConfig(level=logging.DEBUG)

from common.models import update_FX_from_Yahoo
from datetime import date
result = update_FX_from_Yahoo('USD', 'EUR', date.today())
```

## Resources

- [Yahoo Finance API Documentation](https://finance.yahoo.com)
- [yfinance Library](https://github.com/ranaroussi/yfinance)
- [HTTP Headers Reference](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers)

---

**Status:** ✅ Fixed
**Date:** October 4, 2025
**Impact:** High - Restores all Yahoo Finance data imports (FX rates and security prices)
