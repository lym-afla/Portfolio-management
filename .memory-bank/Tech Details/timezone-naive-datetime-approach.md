# Timezone-Naive DateTime Approach

## Overview

This document describes the standardized approach for handling datetime objects in the portfolio management application. The application has been migrated from timezone-aware datetime objects to timezone-naive datetime objects for internal consistency and simplicity.

## Key Principles

### 1. **Internal Storage: Timezone-Naive**
- All datetime objects stored in the database are timezone-naive
- Custom field classes (`NaiveDateTimeField`, `NaiveDateField`) automatically convert timezone-aware inputs to naive
- No timezone information is stored in the database

### 2. **External API Integration: Context-Aware**
- External API calls (Tinkoff, Yahoo Finance) still use timezone-aware objects when required
- Conversion happens at the boundary: naive → timezone-aware for API calls, timezone-aware → naive for storage

### 3. **User Input: Naive Parsing**
- Date strings from HTTP requests are parsed as naive datetime objects
- No automatic timezone assignment based on user location or server timezone

## Custom Field Classes

### `NaiveDateTimeField`
- **Purpose**: Handles datetime fields without timezone information
- **Input Types**: `datetime`, `date`, `string`
- **Behavior**:
  - Strips timezone from timezone-aware inputs using `.replace(tzinfo=None)`
  - Converts `date` to `datetime` at start of day
  - Parses ISO and YYYY-MM-DD format strings
  - Always stores as timezone-naive `datetime`

### `NaiveDateField`
- **Purpose**: Handles date fields without timezone information
- **Input Types**: `datetime`, `date`, `string`
- **Behavior**:
  - Extracts date portion from datetime objects
  - Accepts date objects directly
  - Parses YYYY-MM-DD format strings
  - Always stores as `date` (not datetime)

## Migration Strategy

### Database Migration
- Migration `0084_convert_to_naive_datetime_fields.py` converts all timezone-aware fields to naive
- Existing timezone-aware data is preserved by stripping timezone information
- No data loss occurs during migration

### Code Changes
- All model fields in `common/models.py` updated to use naive field classes
- External API integration updated to handle conversion at boundaries
- View functions updated to parse dates as naive objects
- Test fixtures updated to use naive datetime objects

## External API Handling

### Tinkoff API Integration
```python
# Internal processing (naive)
target_date = datetime.combine(date, datetime.min.time())

# Convert to timezone-aware for API call
api_date = timezone.make_aware(target_date)
response = client.instruments.get_operations(from_=api_date, to=api_date)

# Response data automatically converted to naive by field classes
```

### Yahoo Finance Integration
```python
# Similar pattern: convert naive → timezone-aware for API, store as naive
api_date = timezone.make_aware(naive_date)
rate_data = yf.Ticker(currency_pair).history(start=api_date, end=api_date)
# Stored in database using NaiveDateTimeField → becomes naive
```

## Benefits

### 1. **Simplicity**
- No timezone-related bugs in internal calculations
- Consistent datetime comparisons throughout the application
- Easier debugging and testing

### 2. **Performance**
- No timezone conversion overhead in database queries
- Faster date comparisons and calculations

### 3. **Maintainability**
- Clear boundary between internal and external datetime handling
- Predictable behavior across all application components

## Usage Guidelines

### When Creating New Models
```python
from common.fields import NaiveDateTimeField, NaiveDateField

class MyModel(models.Model):
    # Use NaiveDateTimeField for timestamp fields
    created_at = NaiveDateTimeField(auto_now_add=True)
    updated_at = NaiveDateTimeField(auto_now=True)

    # Use NaiveDateField for date-only fields
    effective_date = NaiveDateField()
    maturity_date = NaiveDateField()
```

### When Parsing User Input
```python
# HTTP request parameter parsing
effective_date = datetime.strptime(request.GET.get('date'), "%Y-%m-%d")

# No timezone assignment needed - field handles it
my_instance.effective_date = effective_date
my_instance.save()
```

### When Working with External APIs
```python
# Convert to timezone-aware for API call
from django.utils import timezone
api_date = timezone.make_aware(naive_date)

# Make API call
response = external_api.get_data(date=api_date)

# Store response using naive field classes
my_instance.timestamp = response.timestamp  # Automatically converted to naive
```

## Testing

### Test Fixtures
- All test datetime objects should be naive
- Use `datetime(2023, 1, 15, 12, 0, 0)` instead of `datetime(2023, 1, 15, 12, 0, 0, tzinfo=timezone.utc)`
- Custom field classes will handle any timezone-aware data during testing

### Date Comparisons
```python
# This works correctly with naive datetimes
assert transaction1.date < transaction2.date

# For date-only comparisons
assert transaction1.date.date() == expected_date
```

## Migration from Previous Approach

If you're working with code that still uses timezone-aware objects:

1. **Internal Processing**: Strip timezone immediately
   ```python
   # Before
   aware_dt = timezone.make_aware(naive_dt)

   # After
   aware_dt = naive_dt  # Keep it naive
   ```

2. **External API Calls**: Convert at the boundary
   ```python
   # Convert only when making API calls
   api_dt = timezone.make_aware(internal_dt)
   response = external_api.call(date=api_dt)
   ```

3. **Date Parsing**: Remove timezone assignment
   ```python
   # Before
   dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

   # After
   dt = datetime.strptime(date_str, "%Y-%m-%d")
   ```

## Compatibility

### Django Settings
- Application works with `USE_TZ = True` or `USE_TZ = False`
- Custom field classes ensure consistent behavior regardless of Django timezone settings

### Database Backend
- Compatible with all supported Django database backends
- No special database configuration required

## Future Considerations

### Multi-Timezone Support
If future requirements include multi-timezone support:
- Store all timestamps in UTC (naive, but representing UTC)
- Convert to user's local timezone only in presentation layer
- Keep internal processing timezone-naive for performance

### External Integrations
New external API integrations should follow the established pattern:
1. Keep internal data naive
2. Convert to timezone-aware only for API calls
3. Use custom field classes for automatic conversion back to naive

## Related Files

- `backend/common/fields.py` - Custom field implementations
- `backend/common/models.py` - Updated model definitions
- `backend/core/tinkoff_utils.py` - External API integration example
- `backend/tests/` - Updated test fixtures
- `backend/common/migrations/0084_convert_to_naive_datetime_fields.py` - Database migration

## Troubleshooting

### Common Issues

1. **"datetime is not JSON serializable" errors**
   - Solution: Use `.isoformat()` for JSON serialization, custom fields handle the rest

2. **Timezone comparison errors**
   - Solution: Ensure all datetime objects are naive before comparison
   - Use `.replace(tzinfo=None)` to strip timezone if needed

3. **External API timezone requirements**
   - Solution: Convert to timezone-aware only at API boundary using `timezone.make_aware()`

### Debugging Tips

1. Check datetime awareness: `hasattr(dt, 'tzinfo') and dt.tzinfo is not None`
2. Strip timezone: `dt.replace(tzinfo=None)`
3. Verify field type: `isinstance(field, NaiveDateTimeField)`
