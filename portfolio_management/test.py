import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portfolio_management.settings")

import django
django.setup()

from common.models import Brokers, Prices, Transactions, FX, Assets
from users.models import CustomUser
from utils import NAV_at_date, Irr, chart_dates, chart_labels, chart_colour, portfolio_at_date, calculate_security_nav
from datetime import date

selected_brokers = broker_ids = [2]
table_date = date.today()
target_currency = 'USD'

print(Assets.objects.filter(type='ETF').values_list('id', flat=True))

# transactions = Transactions.objects.filter(
#         date__lte=table_date,
#         broker_id__in=selected_brokers
#     )

# for t in transactions:
#     try:
#         print(t.security.name)
#     except:
#         print(t.security)



# portfolio = portfolio_at_date(table_date, selected_brokers)
# portfolio_brokers = Brokers.objects.filter(id__in=broker_ids)
# analysis = {'Asset type': {}, 'Currency': {}, 'Asset class': {}, 'Broker': {}, 'aggregate': 0}

# print(portfolio_brokers[0].transactions.all())

# security = Assets.objects.get(id=4)
# print(security.id, security.name, security.transactions.all())
# print(Transactions.objects.filter(security_id=4))

# print(Transactions.objects.filter(security_id=None))

# print(portfolio, portfolio_brokers)

# p = Transactions.objects.filter(broker__in=selected_brokers, currency=target_currency, date__lte=table_date, type__in=['Cash in', 'Cash out']).values_list('cash_flow', 'date', 'type')

# print(p)

# print(portfolio[0].prices.all())