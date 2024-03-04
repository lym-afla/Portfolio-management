import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")

import django
django.setup()

from dashboard.models import Brokers, PA_transactions, FX
from dashboard.utils import NAV_at_date, PA_irr, chart_dates, chart_labels, chart_colour, portfolio_at_date, calculate_security_nav
from datetime import date

selected_brokers = broker_ids = [2]
date_ = date.today()
target_currency = 'USD'

portfolio = portfolio_at_date(date_, selected_brokers)
portfolio_brokers = Brokers.objects.filter(id__in=broker_ids)
analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'aggregate': 0}

print(portfolio, portfolio_brokers)

for item in portfolio:
        current_quote = item.current_price(date_)
        print(current_quote.date, current_quote.price)
        current_value = calculate_security_nav(item, date_, target_currency)
        print(current_value)

        for breakdown_type in ['Asset type', 'Currency', 'Asset class', 'Broker']:
            if breakdown_type == 'Broker':
                continue
            key = getattr(analysis, breakdown_type)
            print(key)