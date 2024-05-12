from django.db import models
from django.db.models import F
import networkx as nx
from datetime import timedelta

from constants import CURRENCY_CHOICES, ASSET_TYPE_CHOICES
from users.models import CustomUser

# Table with FX data
class FX(models.Model):
    date = models.DateField(primary_key=True)
    USDEUR = models.DecimalField(max_digits=7, decimal_places=4)
    USDGBP = models.DecimalField(max_digits=7, decimal_places=4)
    CHFGBP = models.DecimalField(max_digits=7, decimal_places=4)
    RUBUSD = models.DecimalField(max_digits=7, decimal_places=4)
    PLNUSD = models.DecimalField(max_digits=7, decimal_places=4)

    # Get FX quote for date
    @classmethod
    def get_rate(cls, source, target, date):
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
        pairs_list = [field.name for field in FX._meta.get_fields() if (field.name != 'date' and field.name != 'id')]
        
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
                        try:
                            fx_call = cls.objects.filter(date__lte=date).values('date', quote=F(f'{i_source}{i_target}')).order_by("-date").first()
                        except:
                            raise ValueError
                        fx_rate *= fx_call['quote']
                        # dates_list.append(fx_call['date'])
                        # dates_async = (dates_list[0] != fx_call['date']) or dates_async
                    else:
                        try:
                            fx_call = cls.objects.filter(date__lte=date).values('date', quote=F(f'{i_target}{i_source}')).order_by("-date").first()
                        except:
                            raise ValueError
                        fx_rate /= fx_call['quote']
                    dates_list.append(fx_call['date'])
                    dates_async = (dates_list[0] != fx_call['date']) or dates_async
                    break
        
        # Thea target is to multiply when using, not divide
        fx_rate = round(1 / fx_rate, 6)
                
        return {
            'FX': fx_rate,
            'conversions': len(cross_currency) - 1,
            'dates_async': dates_async,
            'dates': dates_list
        }

# Brokers
class Brokers(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='brokers')
    name = models.CharField(max_length=20, null=False)
    country = models.CharField(max_length=20)
    securities = models.ManyToManyField('Assets', related_name='brokers')

    # List of currencies used
    def get_currencies(self):
        currencies = set()
        for transaction in self.transactions.all():
            currencies.add(transaction.currency)
        return currencies

    # Cash balance at date
    def balance(self, date):
        balance = {}
        for cur in self.get_currencies():
            query = self.transactions.filter(broker_id=self.id, currency=cur, date__lte=date).aggregate(
                balance=models.Sum(
                    models.Case(
                        models.When(quantity__gte=0, then=-1*models.F('quantity')*models.F('price')),
                        models.When(cash_flow__isnull=False, then=models.F('cash_flow')),
                        models.When(commission__isnull=False, then=models.F('commission')),
                        default=0,
                        output_field=models.DecimalField()
                    )
                )
            )['balance']
            balance[cur] = query or 0
        return balance
    
    def __str__(self):
        return self.name  # Define how the broker is represented as a string

# Public assets
class Assets(models.Model):
    investor = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='assets')
    type = models.CharField(max_length=15, choices=ASSET_TYPE_CHOICES, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=30, null=False)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', null=False)
    exposure = models.TextField(null=False)

    # Returns price at the date or latest available before the date
    def price_at_date(self, price_date, currency=None):
        # print(f"Models. Assets. {self.name} Current_price. {self.prices.filter(date__lte=price_date).all()}")
        try:
            quote = self.prices.filter(date__lte=price_date).order_by('-date').first()
            if currency:
                quote.price = quote.price * FX.get_rate(self.currency, currency, price_date)['FX']
            return quote
        except:
            return None

    # Define position at date by summing all movements to date
    def position(self, date, broker_id_list=None):
        query = self.transactions.filter(date__lte=date)
        # print(f"models.py. line 134. {query}")
        if broker_id_list is not None:
            query = query.filter(broker_id__in=broker_id_list)
        total_quantity = query.aggregate(total=models.Sum('quantity'))['total']
        return total_quantity or 0

    # The very first investment date
    def investment_date(self, broker_id_list=None):
        queryset = self.transactions
        if broker_id_list:
            queryset = queryset.filter(broker_id__in=broker_id_list)
        query = queryset.order_by('date').values_list('date', flat=True).first()
        return query


    def dates_of_zero_positions(self, date, broker_id_list=None):
        """
        Calculate the entry dates for a specific position as of a given date.

        Parameters:
            date (datetime): The date for which the entry dates are calculated.
            broker_id_list (list, optional): A list of broker IDs to filter the transactions. Defaults to None.

        Returns:
            list: A list of entry dates for the position in reversed chronological order.
        """
        
        position = self.position(date, broker_id_list)

        # Get the transactions for this asset
        transactions = self.transactions.filter(date__lte=date, quantity__isnull=False).all()
        if broker_id_list is not None:
            transactions = transactions.filter(broker_id__in=broker_id_list)

        # Order the transactions by date in ascending order
        transactions = transactions.order_by('-date')

        # Initialize the list of entry dates
        entry_dates = []

        # Check if the position is 0
        if position == 0 and transactions:
            # Add the date of the last transaction to the list of entry dates
            entry_dates.append(transactions.first().date)

        # Iterate over the transactions
        for transaction in transactions:
            # Check if the quantity is not None before subtracting it from the position
            position -= transaction.quantity
            
            # Check if the position is 0
            if position == 0:
                # Add the date of this transaction to the list of entry dates
                entry_dates.append(transaction.date - timedelta(days=1))

        return entry_dates

    def calculate_buy_in_price(self, date, currency, broker_id_list=None, start_date=None):
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
        
        try:

            is_long_position = None

            transactions = self.transactions.filter(
                quantity__isnull=False,  # Filter out transactions where quantity is not empty
                date__lte=date
            ).values('price', 'quantity', 'date', 'currency')

            if broker_id_list is not None:
                transactions = transactions.filter(broker_id__in=broker_id_list) 

            # Step 2: Calculate based on the period starting from the previous position == 0 or start_date, whichever is later
            if self.position(date) == 0:
                entry_date = self.dates_of_zero_positions(date)[1]
            else:
                entry_date = self.dates_of_zero_positions(date)[0]

            if start_date and start_date > entry_date:
                entry_date = start_date

                transactions = transactions.filter(date__gt=entry_date)
                position = self.position(entry_date, broker_id_list)
                if position != 0:
                    transactions = list(transactions) + [{
                        'price': self.price_at_date(entry_date).price,
                        'quantity': position,
                        'date': entry_date,
                        'currency': self.currency,
                    }]
                    is_long_position = position > 0
            else:
                transactions = transactions.filter(date__gt=entry_date)

            if is_long_position is None:
                first_transaction = transactions.order_by('date').first()
                is_long_position = first_transaction['quantity'] > 0

            # Step 3: Amend the calculation method. For every entry transaction buy-in price is the weighted average of previous buy-in price and price for the current transaction.
            value = 0
            quantity = 0
            for transaction in transactions:
                fx_rate = FX.get_rate(transaction['currency'], currency, transaction['date'])['FX']
                if fx_rate:
                    previous_buy_in_price = value / quantity if quantity else 0
                    current_price = transaction['price'] * fx_rate
                    weight_previous = quantity
                    weight_current = transaction['quantity']
                    # If it's a long position and the quantity is positive, or if it's a short position and the quantity is negative, use the current price. Otherwise, use the previous buy-in price.
                    price = current_price if (is_long_position and transaction['quantity'] > 0) or (not is_long_position and transaction['quantity'] < 0) else previous_buy_in_price
                    
                    if (weight_previous + weight_current) == 0:
                        buy_in_price = previous_buy_in_price
                    else:
                        buy_in_price = (previous_buy_in_price * weight_previous + price * weight_current) / (weight_previous + weight_current)
                    value = buy_in_price * (quantity + transaction['quantity'])
                    quantity += transaction['quantity']

            return value / quantity if quantity else previous_buy_in_price

        except Exception as e:
            print(f"Error: {e}")
            return None

    def realized_gain_loss(security, date, currency, broker_id_list=None):
        """
        Calculates the realized gain or loss of a security as of a specific date.

        Parameters:
            date (datetime.date): The date as of which the gain or loss is calculated.
            currency (str): The currency in which the gain or loss is calculated.
            broker_id_list (list, optional): A list of broker IDs to filter the transactions. Defaults to None.

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
        realized_gain_loss = 0
        total_gl_before_entry = 0

        # Step 1: Find the latest date when position is 0
        zero_positions_dates = security.dates_of_zero_positions(date)
        if zero_positions_dates:
            latest_zero_position = security.dates_of_zero_positions(date)[0]
        else:
            return 0

        # Step 2: Sum up values of all transactions before that date
        transactions_before_entry = security.transactions.filter(date__lte=latest_zero_position)
        if broker_id_list is not None:
            transactions_before_entry = transactions_before_entry.filter(broker_id__in=broker_id_list)
        
        for transaction in transactions_before_entry:
            fx_rate = FX.get_rate(transaction.currency, currency, transaction.date)['FX']
            if fx_rate:
                total_gl_before_entry -= transaction.price * transaction.quantity * fx_rate

        # Step 3: Determine whether it is a long or short position
        position_at_date = security.position(date)

        if position_at_date != 0:
            is_long_position = position_at_date > 0
            exit_type = 'Sell' if is_long_position else 'Buy'

            # Step 4: Calculate realized gain/loss based on exit price and buy-in price
            exit_transactions = security.transactions.filter(type=exit_type, date__gte=latest_zero_position, date__lte=date)

            for exit in exit_transactions:
                buy_in_price = security.calculate_buy_in_price(exit.date, exit.currency, broker_id_list)
                if buy_in_price is not None:
                    fx_rate = FX.get_rate(exit.currency, currency, exit.date)['FX']
                    if fx_rate:
                        realized_gain_loss -= (exit.price * fx_rate - buy_in_price) * (exit.quantity)

        return round(total_gl_before_entry + realized_gain_loss, 2)
    
    def __str__(self):
        return self.name  # Define how the broker is represented as a string

# Table with public asset transactions
class Transactions(models.Model):
    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name='transactions')
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name='transactions', null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD', null=False)
    type = models.CharField(max_length=30, null=False)
    date = models.DateField(null=False)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    commission = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    comment = models.TextField(null=True, blank=True)

# Table with non-public asset prices
class Prices(models.Model):
    date = models.DateField(null=False)
    security = models.ForeignKey(Assets, on_delete=models.CASCADE, related_name='prices')
    price = models.DecimalField(max_digits=10, decimal_places=2, null=False)

    def __str__(self):
        return f"{self.security.name} is at {self.price} on {self.date}"