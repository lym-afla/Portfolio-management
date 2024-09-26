from decimal import Decimal
from django.db import IntegrityError, models
from django.db.models import F, Sum
from django.core.exceptions import ValidationError
import networkx as nx
from datetime import timedelta
import requests
import yfinance as yf
import logging

from constants import CURRENCY_CHOICES, ASSET_TYPE_CHOICES, TRANSACTION_TYPE_BUY, TRANSACTION_TYPE_CHOICES, EXPOSURE_CHOICES, TRANSACTION_TYPE_SELL
# from .utils import update_FX_database
from users.models import CustomUser

logger = logging.getLogger(__name__)

# Table with FX data
class FX(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField(unique=True)
    investors = models.ManyToManyField(CustomUser, related_name='fx_rates')
    USDEUR = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    USDGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    CHFGBP = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True)
    RUBUSD = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    PLNUSD = models.DecimalField(max_digits=9, decimal_places=5, null=True, blank=True)

    class Meta:
        ordering = ['-date']

    # Get FX quote for date
    @classmethod
    def get_rate(cls, source, target, date, investor=None):
        fx_rate = 1
        dates_async = False
        dates_list = []

        if source == target:
            return {
                'FX': fx_rate,
                'conversions': 0,
                'dates_async': dates_async,
                'FX dates used': dates_list
            }

        # Get all existing pairs
        pairs_list = [field.name for field in FX._meta.get_fields() if field.name not in ['date', 'id', 'investors']]
        
        # Create undirected graph with currencies, import networkx library working with graphs
        G = nx.Graph()
        for entry in pairs_list:
            G.add_nodes_from([entry[:3], entry[3:]])
            G.add_edge(entry[:3], entry[3:])

        # Finding shortest path for cross-currency conversion using "Bellman-Ford" algorithm
        cross_currency = nx.shortest_path(G, source, target, method='bellman-ford')

        for i in range(1, len(cross_currency)):
            i_source = cross_currency[i - 1]
            i_target = cross_currency[i]
            
            for element in pairs_list:
                if i_source in element and i_target in element:
                    if element.find(i_source) == 0:
                        field_name = f'{i_source}{i_target}'
                        multiplier = Decimal('1')
                    else:
                        field_name = f'{i_target}{i_source}'
                        multiplier = Decimal('-1')
                    
                    filter_kwargs = {f'{field_name}__isnull': False}
                    if investor is not None:
                        filter_kwargs['investors'] = investor
                    
                    fx_call = cls.objects.filter(
                        date__lte=date,
                        **filter_kwargs
                    ).values(
                        'date', quote=F(field_name)
                    ).order_by("-date").first()
                    
                    if fx_call is None or fx_call['quote'] is None:
                        fx_call = cls.objects.filter(
                            date__gte=date,
                            **filter_kwargs
                        ).values(
                            'date', quote=F(field_name)
                        ).order_by("date").first()
                        if fx_call is None or fx_call['quote'] is None:
                            raise ValueError(f"No FX rate found for {field_name} before {date}")
                    
                    quote = Decimal(str(fx_call['quote']))
                    if multiplier == Decimal('1'):
                        fx_rate *= quote
                    else:
                        fx_rate /= quote
                    dates_list.append(fx_call['date'])
                    dates_async = (dates_list[0] != fx_call['date']) or dates_async
                    break
        
        # The target is to multiply when using, not divide
        fx_rate = round(Decimal(1 / fx_rate), 6)
                
        return {
            'FX': fx_rate,
            'conversions': len(cross_currency) - 1,
            'dates_async': dates_async,
            'dates': dates_list
        }
    @classmethod
    def update_fx_rate(cls, date, investor):
        # Get FX model variables, except 'date', 'id' and 'investors'
        fx_variables = [field for field in cls._meta.get_fields() if field.name not in ['date', 'id', 'investors']]

        # Extract source and target currencies
        currency_pairs = [(field.name[:3], field.name[3:]) for field in fx_variables]

        # Create or get the fx_instance once before the loop
        fx_instance, created = cls.objects.get_or_create(date=date)
        fx_instance.investors.add(investor)

        for source, target in currency_pairs:
            # Check if an FX rate exists for the date and currency pair
            existing_rate = getattr(fx_instance, f'{source}{target}', None)

            if existing_rate is None:
                # Get the FX rate for the date
                try:
                    rate_data = update_FX_from_Yahoo(source, target, date)

                    if rate_data is not None:
                        # Update the fx_instance with the new rate
                        setattr(fx_instance, f'{source}{target}', rate_data['exchange_rate'])
                except:
                    print(f'{source}{target} for {date} is NOT updated. Yahoo Finance is not responding correctly')
                    continue

        # Save the fx_instance once after updating all currency pairs
        fx_instance.save()

    @classmethod
    def get_investor_fx_entries(cls, investor):
        return cls.objects.filter(investors=investor)

# Brokers
class Brokers(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='brokers')
    name = models.CharField(max_length=30, null=False)
    country = models.CharField(max_length=20)
    securities = models.ManyToManyField('Assets', related_name='brokers')
    comment = models.TextField(null=True, blank=True)
    restricted = models.BooleanField(default=False, null=False, blank=False)

    # List of currencies used
    def get_currencies(self):
        currencies = set()
        for transaction in self.transactions.all():
            currencies.add(transaction.currency)
        return currencies

    # Cash balance at date
    def balance(self, date):
        balance = {}

        # This approach in order to match how balances are calculated in 'transactions' app after each transaction
        transactions = self.transactions.filter(date__lte=date)
        for transaction in transactions:
            balance[transaction.currency] = balance.get(transaction.currency, Decimal(0)) - Decimal((transaction.price or 0) * Decimal(transaction.quantity or 0) \
            - Decimal(transaction.cash_flow or 0) \
                - Decimal(transaction.commission or 0))
            
        # Calculate balance from FX transactions
        fx_transactions = self.fx_transactions.filter(date__lte=date)
        for fx_transaction in fx_transactions:
            balance[fx_transaction.from_currency] = balance.get(fx_transaction.from_currency, Decimal(0)) - fx_transaction.from_amount
            balance[fx_transaction.to_currency] = balance.get(fx_transaction.to_currency, Decimal(0)) + fx_transaction.to_amount
            if fx_transaction.commission:
                commission_currency = fx_transaction.from_currency  # Assume commission is in the source currency
                balance[commission_currency] = balance.get(commission_currency, Decimal(0)) - fx_transaction.commission
            
        for key, value in balance.items():
            balance[key] = round(Decimal(value), 2)

        return balance
    
    def __str__(self):
        return self.name  # Define how the broker is represented as a string

# Public assets
class Assets(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='assets')
    type = models.CharField(max_length=15, choices=ASSET_TYPE_CHOICES, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=50, null=False)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', null=False)
    exposure = models.TextField(null=False, choices=EXPOSURE_CHOICES, default='Equity')
    restricted = models.BooleanField(default=False, null=False)
    comment = models.TextField(null=True, blank=True)
    DATA_SOURCE_CHOICES = [
        ('FT', 'Financial Times'),
        ('YAHOO', 'Yahoo Finance'),
        # Add more sources as needed
    ]
    data_source = models.CharField(max_length=10, choices=[('', 'None')] + DATA_SOURCE_CHOICES, blank=True, null=True)
    update_link = models.URLField(null=True, blank=True) # For FT
    yahoo_symbol = models.CharField(max_length=50, blank=True, null=True)  # For Yahoo Finance symbol

    # Returns price at the date or latest available before the date
    def price_at_date(self, price_date, currency=None):
        quote = self.prices.filter(date__lte=price_date).order_by('-date').first()
        if quote is None:
            # If no quote is found, take the price from the last transaction
            last_transaction = self.transactions.filter(date__lte=price_date).order_by('-date').first()
            if last_transaction:
                quote = type('obj', (object,), {'price': last_transaction.price, 'date': last_transaction.date})
            else:
                return None
        
        if currency is not None:
            quote.price = quote.price * FX.get_rate(self.currency, currency, price_date)['FX']
        return quote

    # Define position at date by summing all movements to date
    def position(self, date, broker_id_list=None):
        query = self.transactions.filter(date__lte=date)
        # print(f"models.py. line 134. {query}")
        if broker_id_list is not None:
            query = query.filter(broker_id__in=broker_id_list)
        total_quantity = query.aggregate(total=models.Sum('quantity'))['total']
        return round(Decimal(total_quantity), 6) if total_quantity else Decimal(0)

    # The very first investment date
    def investment_date(self, broker_id_list=None):
        queryset = self.transactions
        if broker_id_list:
            queryset = queryset.filter(broker_id__in=broker_id_list)
        query = queryset.order_by('date').values_list('date', flat=True).first()
        return query

    def entry_dates(self, date, broker_id_list=None):
        """
        Returns a list of dates when the position changes from 0 to non-zero.
        """
        transactions = self.transactions.filter(date__lte=date, quantity__isnull=False)
        if broker_id_list is not None:
            transactions = transactions.filter(broker_id__in=broker_id_list)
        
        transactions = transactions.order_by('date')

        entry_dates = []
        position = 0

        for transaction in transactions:
            new_position = position + transaction.quantity
            if position == 0 and new_position != 0:
                entry_dates.append(transaction.date)
            position = new_position

        return entry_dates

    def exit_dates(self, end_date, broker_id_list=None, start_date=None):
        """
        Returns a list of dates when the position changes from non-zero to 0.
        """
        transactions = self.transactions.filter(date__lte=end_date, quantity__isnull=False)
        if broker_id_list is not None:
            transactions = transactions.filter(broker_id__in=broker_id_list)
        if start_date is not None:
            transactions = transactions.filter(date__gte=start_date)
        
        transactions = transactions.order_by('date')

        exit_dates = []
        if start_date is not None:
            position = self.position(start_date, broker_id_list)
        else:
            position = 0

        for transaction in transactions:
            new_position = position + transaction.quantity
            if position != 0 and new_position == 0:
                exit_dates.append(transaction.date)
            position = new_position

        return exit_dates

    def calculate_buy_in_price(self, date, currency=None, broker_id_list=None, start_date=None):
        """
        Calculates the buy-in price for the given date, currency, broker ID list, and start date.

        Args:
            date (datetime.date): The date for which to calculate the buy-in price.
            currency (str): The currency in which to calculate the buy-in price.
            broker_id_list (Optional[List[str]]): A list of broker IDs to filter the transactions by. Defaults to None.
            start_date (Optional[datetime.date]): The start date for the calculation. Defaults to None.

        Returns:
            float: The calculated buy-in price. Returns None if an error occurs.
        """
        is_long_position = None

        transactions = self.transactions.filter(
            quantity__isnull=False,
            date__lte=date
        ).order_by('date')  # Order transactions by date

        if broker_id_list is not None:
            transactions = transactions.filter(broker_id__in=broker_id_list) 
        
        if not transactions:
            return None

        # Get latest entry date
        entry_dates = self.entry_dates(date, broker_id_list)
        if not entry_dates:
            return None
        entry_date = entry_dates[-1]

        if start_date and start_date > entry_date:
            # Add artificial transaction at start_date
            position = self.position(start_date, broker_id_list)
            if position != 0:
                price_at_start = self.price_at_date(start_date)
                if price_at_start:
                    artificial_transaction = {
                        'date': start_date,
                        'quantity': position,
                        'price': price_at_start.price,
                        'currency': self.currency
                    }
                    transactions = list(transactions.filter(date__gte=start_date))
                    transactions.insert(0, type('obj', (object,), artificial_transaction))
                    is_long_position = position > 0
            entry_date = start_date

        transactions = [t for t in transactions if t.date >= entry_date]

        if is_long_position is None and transactions:
            is_long_position = transactions[0].quantity > 0

        # Calculate the buy-in price
        value_entry = Decimal(0)
        quantity_entry = Decimal(0)
        previous_entry_price = Decimal(0)

        for transaction in transactions:
            if currency is not None:
                fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)['FX']
            else:
                fx_rate = Decimal(1)

            current_price = transaction.price * fx_rate
            weight_current = transaction.quantity

            # Calculate entry price
            previous_entry_price = value_entry / quantity_entry if quantity_entry != 0 else Decimal(0)
            weight_entry_previous = quantity_entry
            # If it's a long position and the quantity is positive, or if it's a short position and the quantity is negative, use the current price. Otherwise, use the previous buy-in price.
            entry_price = current_price if (is_long_position and transaction.quantity > 0) or (not is_long_position and transaction.quantity < 0) else previous_entry_price
            
            if (weight_entry_previous + weight_current) == 0:
                entry_price = previous_entry_price
            else:
                entry_price = (previous_entry_price * weight_entry_previous + entry_price * weight_current) / (weight_entry_previous + weight_current)
            quantity_entry += transaction.quantity
            value_entry = entry_price * quantity_entry

        return round(Decimal(value_entry / quantity_entry), 6) if quantity_entry else previous_entry_price

        # except Exception as e:
        #     print(f"Error when calculating buy-in price for {self.name}: {e}")
        #     return None

    def realized_gain_loss(self, date, currency=None, broker_id_list=None, start_date=None):
        """
        Calculates the realized gain or loss of a security as of a specific date.

        Parameters:
            date (datetime.date): The date as of which the gain or loss is calculated.
            currency (str): The currency in which the gain or loss is calculated.
            broker_id_list (list, optional): A list of broker IDs to filter the transactions. Defaults to None.
            start_date (datetime.date, optional): The start date for the calculation. Defaults to None.

        Returns:
            float: The realized gain or loss of the security as of the given date,
            rounded to 2 decimal places. If there are no dates when the position was
            zero, it returns 0.

        This method calculates the realized gain or loss by first
        finding the latest date when the position was zero.
        It then sums up the values of all transactions before that date.
        It determines whether the position at the current date is a long or
        short position, and calculates the realized gain/loss based on
        the exit price and the average buy-in price for each exit transaction.
        The exit price and the average buy-in price are converted to
        the specified currency using the FX.get_rate function.
        """

        logger.info(f"Calculating realized gain/loss for {self.name} as of {date}")
        logger.info(f"Parameters: currency={currency}, broker_id_list={broker_id_list}, start_date={start_date}")

        realized_gain_loss_for_current_position = 0
        total_gl_before_current_position = 0
        latest_exit_date = None

        exit_dates = self.exit_dates(date, broker_id_list)
        logger.info(f"Exit dates: {exit_dates}")

        if len(exit_dates) != 0:
            # Step 1: Find the latest date when position is 0
            latest_exit_date = exit_dates[-1]
            logger.info(f"Latest exit date: {latest_exit_date}")

            # Step 2: Sum up values of all transactions before that date
            transactions_before_entry = self.transactions.filter(date__lte=latest_exit_date, quantity__isnull=False)
            if start_date is not None:
                transactions_before_entry = transactions_before_entry.filter(date__gte=start_date)
            if broker_id_list is not None:
                transactions_before_entry = transactions_before_entry.filter(broker_id__in=broker_id_list)
            
            logger.info(f"Number of transactions before entry: {transactions_before_entry.count()}")

            if transactions_before_entry.exists():
                if currency is not None:
                    for transaction in transactions_before_entry:
                        fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)['FX']
                        logger.info(f"Transaction: {transaction.date}, {transaction.type}, Quantity: {transaction.quantity}, Price: {transaction.price}, FX rate: {fx_rate}")
                        if fx_rate:
                            total_gl_before_current_position -= transaction.price * transaction.quantity * fx_rate
                    if start_date is not None:
                        start_price = self.price_at_date(start_date, currency).price
                        start_position = self.position(start_date)
                        logger.info(f"Start date adjustment: Price at {start_date}: {start_price}, Position: {start_position}")
                        total_gl_before_current_position -= start_price * start_position
                else:
                    total_gl_before_current_position = -transactions_before_entry.aggregate(total=Sum(F('price') * F('quantity')))['total'] or 0
                    if start_date is not None:
                        start_price = self.price_at_date(start_date).price
                        start_position = self.position(start_date)
                        logger.info(f"Start date adjustment: Price at {start_date}: {start_price}, Position: {start_position}")
                        total_gl_before_current_position -= start_price * start_position

        logger.info(f"Total G/L before current position: {total_gl_before_current_position}")

        # Step 3: Determine whether it is a long or short position
        position_at_date = self.position(date)
        logger.info(f"Position at {date}: {position_at_date}")

        if position_at_date != 0:
            is_long_position = position_at_date > 0
            exit_type = TRANSACTION_TYPE_SELL if is_long_position else TRANSACTION_TYPE_BUY
            logger.info(f"Position type: {'Long' if is_long_position else 'Short'}, Exit type: {exit_type}")

            # Step 4: Calculate realized gain/loss based on exit price and buy-in price
            exit_transactions = self.transactions.filter(type=exit_type, date__lte=date)
            if latest_exit_date:
                exit_transactions = exit_transactions.filter(date__gt=latest_exit_date)
            if start_date:
                exit_transactions = exit_transactions.filter(date__gte=start_date)
            if broker_id_list is not None:
                exit_transactions = exit_transactions.filter(broker_id__in=broker_id_list)
            
            logger.info(f"Number of exit transactions: {exit_transactions.count()}")
            
            for exit in exit_transactions:
                buy_in_price = self.calculate_buy_in_price(exit.date, exit.currency, broker_id_list, start_date)
                logger.info(f"Exit transaction: Date: {exit.date}, Price: {exit.price}, Quantity: {exit.quantity}, Buy-in price: {buy_in_price}")
                if buy_in_price is not None:
                    if currency is not None:
                        fx_rate = FX.get_rate(exit.currency, currency, exit.date)['FX']
                    else:
                        fx_rate = 1
                    if fx_rate:
                        realized_gain_loss = (exit.price - buy_in_price) * fx_rate * (exit.quantity)
                        realized_gain_loss_for_current_position -= realized_gain_loss
                        logger.info(f"Realized gain/loss for this exit: {realized_gain_loss}")
                else:
                    logger.warning("Buy-in price is not available")
                    return None
                
        logger.info(f"Realized gain/loss for current position: {realized_gain_loss_for_current_position}")
        logger.info(f"Total realized gain/loss: {total_gl_before_current_position + realized_gain_loss_for_current_position}")

        return {
            "current_position": round(Decimal(realized_gain_loss_for_current_position), 2),
            "all_time": round(Decimal(total_gl_before_current_position + realized_gain_loss_for_current_position), 2)
        }
    
    def unrealized_gain_loss(self, date, currency=None, broker_id_list=None, start_date=None):
        """
        Calculates the capital distribution (dividends) for a security as of a specific date.

        Parameters:
            date (datetime.date): The date as of which the capital distribution is calculated.
            currency (str, optional): The currency in which the capital distribution is calculated. If None, the original currency of the dividends is used. Defaults to None.
            broker_id_list (list, optional): A list of broker IDs to filter the transactions. Defaults to None.

        Returns:
            float: The total capital distribution (dividends) for the security as of the given date, rounded to 2 decimal places. If there are no dividend transactions, it returns 0.

        This method calculates the capital distribution by summing up the cash flow from all 'dividend' type transactions as of the given date. If a currency is provided, the dividends are converted to that currency using the FX.get_rate function.
        """
        unrealized_gain_loss = 0

        current_position = self.position(date, broker_id_list)
        
        current_price = self.price_at_date(date, currency).price if self.price_at_date(date) else 0
        buy_in_price = self.calculate_buy_in_price(date, currency, broker_id_list, start_date)
        if buy_in_price is not None:
            unrealized_gain_loss = (current_price - buy_in_price) * current_position

        return round(Decimal(unrealized_gain_loss), 2)
    
    def get_capital_distribution(self, date, currency=None, broker_id_list=None, start_date=None):
        """
        Calculate the capital distribution (dividends) for this asset.
        Capital distribution is the total cash flow from 'dividend' type transactions.
        """
        total_dividends = 0
        dividend_transactions = self.transactions.filter(type='Dividend', date__lte=date)

        if broker_id_list is not None:
            dividend_transactions = dividend_transactions.filter(broker_id__in=broker_id_list)

        if start_date is not None:
            dividend_transactions = dividend_transactions.filter(date__gte=start_date)

        if dividend_transactions:
            if currency is None:
                total_dividends += dividend_transactions.aggregate(total=Sum('cash_flow'))['total']
            else:
                for dividend in dividend_transactions:
                    fx_rate = FX.get_rate(dividend.currency, currency, dividend.date)['FX']
                    if fx_rate:
                        total_dividends += dividend.cash_flow * fx_rate
            return round(Decimal(total_dividends), 2)
        else:
            return Decimal(0)
        
    def get_commission(self, date, currency=None, broker_id_list=None, start_date=None):
        """
        Calculate the comission for this asset.
        """
        total_commission = 0
        commission_transactions = self.transactions.filter(commission__isnull=False, date__lte=date)

        if broker_id_list is not None:
            commission_transactions = commission_transactions.filter(broker_id__in=broker_id_list)

        if start_date is not None:
            commission_transactions = commission_transactions.filter(date__gte=start_date)

        if commission_transactions:
            if currency is None:
                total_commission += commission_transactions.aggregate(total=Sum('commission'))['total']
            else:
                for commission in commission_transactions:
                    fx_rate = FX.get_rate(commission.currency, currency, commission.date)['FX']
                    if fx_rate:
                        total_commission += commission.commission * fx_rate
            return round(Decimal(total_commission), 2)
        else:
            return Decimal(0)

    def __str__(self):
        return self.name  # Define how the broker is represented as a string

# Table with public asset transactions
class Transactions(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='transactions')
    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name='transactions')
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', null=False, blank=False)
    type = models.CharField(max_length=30, choices=TRANSACTION_TYPE_CHOICES, null=False)
    date = models.DateField(null=False)
    quantity = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    price = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)

    # def save(self, *args, **kwargs):
    #     super().save(*args, **kwargs)
    #     # Update broker balance after each transaction
    #     self.broker.balance(self.date)

    def __str__(self):
        return f"{self.type} || {self.date}"

# Table with non-public asset prices
class Prices(models.Model):
    date = models.DateField(null=False)
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name='prices')
    price = models.DecimalField(max_digits=15, decimal_places=6, null=False)

    def __str__(self):
        return f"{self.security.name} is at {self.price} on {self.date}"

    class Meta:

        # Add constraints
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'security'],
                name='unique_security_price_entry'
            ),
        ]
    


def is_yahoo_finance_available():
    url = "https://finance.yahoo.com"  # Replace with the Yahoo Finance API endpoint if needed
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return True
    except requests.ConnectionError:
        pass
    return False

def update_FX_from_Yahoo(base_currency, target_currency, date, max_attempts=5):
    
    if not is_yahoo_finance_available():
        raise ConnectionError("Yahoo Finance is not available")

    # Define the currency pair
    currency_pair = f"{target_currency}{base_currency}=X"

    # Initialize a counter for the number of attempts
    attempt = 0

    while attempt < max_attempts:
        # Define the date for which you want the exchange rate
        end_date = date - timedelta(days=attempt - 1)  # Go back in time for each attempt. Need to deduct 1 to get rate for exactly the date
        start_date = end_date - timedelta(days=1)  # Go back one day to ensure the date is covered
        
        # Fetch historical data for the currency pair within the date range
        data = yf.Ticker(currency_pair)
        # exchange_rate_data = data.history(period="1d", start=start_date, end=end_date)
        try:
            exchange_rate_data = data.history(period="1d", start=start_date, end=end_date)
        except:
            attempt += 1
            continue

        if not exchange_rate_data.empty and not exchange_rate_data["Close"].isnull().all():
            # Get the exchange rate for the specified date
            exchange_rate = round(exchange_rate_data["Close"].iloc[0], 6)
            actual_date = exchange_rate_data.index[0].date()  # Extract the actual date

            return {
                'exchange_rate': exchange_rate,
                'actual_date': actual_date,
                'requested_date': date
            }

        # Increment the attempt counter
        attempt += 1

    # If no data is found after max_attempts, return None or an appropriate error message
    return None


# Model to store the annual performance data
class AnnualPerformance(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, null=True, blank=True)
    broker_group = models.CharField(max_length=100, null=True, blank=True)
    year = models.IntegerField()
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    bop_nav = models.DecimalField(max_digits=20, decimal_places=2)
    invested = models.DecimalField(max_digits=20, decimal_places=2)
    cash_out = models.DecimalField(max_digits=20, decimal_places=2)
    price_change = models.DecimalField(max_digits=20, decimal_places=2)
    capital_distribution = models.DecimalField(max_digits=20, decimal_places=2)
    commission = models.DecimalField(max_digits=20, decimal_places=2)
    tax = models.DecimalField(max_digits=20, decimal_places=2)
    fx = models.DecimalField(max_digits=20, decimal_places=2)
    eop_nav = models.DecimalField(max_digits=20, decimal_places=2)
    tsr = models.CharField(max_length=10) # Can be non numeric
    restricted = models.BooleanField(default=False, null=True, blank=True)

    class Meta:

        # Add constraints
        constraints = [
            models.CheckConstraint(
                check=models.Q(broker__isnull=False) | models.Q(broker_group__isnull=False),
                name='either_broker_or_group'
            ),
            models.CheckConstraint(
                check=~(models.Q(broker__isnull=False) & models.Q(broker_group__isnull=False)),
                name='not_both_broker_and_group'
            ),
            models.UniqueConstraint(
                fields=['investor', 'year', 'currency', 'restricted', 'broker'],
                name='unique_investor_broker_year_currency'
            ),
            models.UniqueConstraint(
                fields=['investor', 'year', 'currency', 'restricted', 'broker_group'],
                name='unique_investor_broker_group_year_currency'
            ),
        ]

class FXTransaction(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='fx_transactions')
    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name='fx_transactions')
    date = models.DateField(null=False)
    from_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    to_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, null=False)
    from_amount = models.DecimalField(max_digits=15, decimal_places=6, null=False)
    to_amount = models.DecimalField(max_digits=15, decimal_places=6, null=False)
    exchange_rate = models.DecimalField(max_digits=15, decimal_places=6, null=False, blank=True)
    commission = models.DecimalField(max_digits=15, decimal_places=6, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.exchange_rate:
            self.exchange_rate = self.from_amount / self.to_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"FX: {self.from_currency} to {self.to_currency} on {self.date}"