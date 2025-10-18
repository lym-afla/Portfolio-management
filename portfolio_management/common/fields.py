"""
Custom Django fields for timezone-aware date handling.
This eliminates the need to manually call ensure_datetime_for_query everywhere.
"""

from datetime import date, datetime

from django.db import models
from django.utils import timezone


class TimezoneAwareDateTimeField(models.DateTimeField):
    """
    A DateTimeField that automatically handles timezone conversion for queries.

    This field accepts date, datetime, or string inputs and automatically
    converts them to timezone-aware datetime for database queries.

    Examples:
        - date(2021-03-15) → timezone-aware datetime at start of day
        - datetime(2021-03-15) → timezone-aware datetime (preserves time)
        - "2021-03-15" → timezone-aware datetime at start of day
    """

    def from_db_value(self, value, expression, connection):
        """Convert from database value to Python object"""
        if value is None:
            return None
        if isinstance(value, datetime):
            # Database should already be timezone-aware
            return value
        return value

    def to_python(self, value):
        """Convert Python object to database value"""
        if value is None:
            return None

        # Handle different input types
        if isinstance(value, datetime):
            # If it's already a datetime, ensure it's timezone-aware
            if timezone.is_naive(value):
                return timezone.make_aware(value)
            return value
        elif isinstance(value, date):
            # Convert date to datetime at start of day in current timezone
            tz = timezone.get_current_timezone()
            return timezone.make_aware(datetime.combine(value, datetime.min.time()), tz)
        elif isinstance(value, str):
            # Parse string to date/datetime
            try:
                # Try ISO format datetime first
                if "T" in value:
                    parsed = datetime.fromisoformat(value)
                else:
                    parsed = datetime.strptime(value, "%Y-%m-%d").date()
                    # Convert date to datetime at start of day
                    tz = timezone.get_current_timezone()
                    parsed = timezone.make_aware(datetime.combine(parsed, datetime.min.time()), tz)

                if timezone.is_naive(parsed):
                    tz = timezone.get_current_timezone()
                    parsed = timezone.make_aware(parsed, tz)
                return parsed
            except (ValueError, TypeError):
                raise ValueError(f"Invalid date string format: {value}")
        else:
            raise TypeError(f"Unsupported date type: {type(value)}")

    def pre_save(self, model_instance, add):
        """Convert to database format before saving"""
        value = getattr(model_instance, self.attname)
        if value is not None:
            setattr(model_instance, self.attname, self.to_python(value))
        return super().pre_save(model_instance, add)

    def get_prep_value(self, value):
        """Convert Python object to database format"""
        return self.to_python(value)

    def get_db_prep_save(self, value, connection):
        """Convert Python object to database format for saving"""
        return self.to_python(value)

    def value_to_string(self, obj):
        """Convert Python object to string representation"""
        if obj is None:
            return ""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        else:
            return str(obj)

    def value_from_string(self, value):
        """Parse string value to Python object"""
        return self.to_python(value)


class TimezoneAwareDateField(models.DateField):
    """
    A DateField that automatically handles timezone conversion for queries.

    This field accepts date or string inputs and automatically converts them
    to timezone-aware datetime for database queries.

    Examples:
        - date(2021-03-15) → timezone-aware datetime at start of day
        - "2021-03-15" → timezone-aware datetime at start of day
    """

    def to_python(self, value):
        """Convert string/date to Python object"""
        if value is None:
            return None

        if isinstance(value, datetime):
            # If it's a datetime, ensure it's timezone-aware
            if timezone.is_naive(value):
                return timezone.make_aware(value)
            return value
        elif isinstance(value, date):
            # Convert date to datetime at start of day in current timezone
            tz = timezone.get_current_timezone()
            return timezone.make_aware(datetime.combine(value, datetime.min.time()), tz)
        elif isinstance(value, str):
            # Parse string to date
            try:
                parsed = datetime.strptime(value, "%Y-%m-%d").date()
                tz = timezone.get_current_timezone()
                return timezone.make_aware(datetime.combine(parsed, datetime.min.time()), tz)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid date string format: {value}")
        else:
            raise TypeError(f"Unsupported date type: {type(value)}")

    def pre_save(self, model_instance, add):
        """Convert to database format before saving"""
        value = getattr(model_instance, self.attname)
        if value is not None:
            setattr(model_instance, self.attname, self.to_python(value))
        return super().pre_save(model_instance, add)

    def get_prep_value(self, value):
        """Convert Python object to database format"""
        return self.to_python(value)

    def get_db_prep_save(self, value, connection):
        """Convert Python object to database format for saving"""
        return self.to_python(value)

    def value_to_string(self, obj):
        """Convert Python object to string representation"""
        if obj is None:
            return ""
        if isinstance(obj, datetime):
            return obj.date().isoformat()
        elif isinstance(obj, date):
            return obj.isoformat()
        else:
            return str(obj)

    def value_from_string(self, value):
        """Parse string value to Python object"""
        return self.to_python(value)
