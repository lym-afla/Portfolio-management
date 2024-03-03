from django.db import models
import networkx as nx

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
    name = models.CharField(max_length=20, null=False)
    country = models.CharField(max_length=20)

    # List of currencies used
    def currencies(self):
        currencies = set()
        for transaction in self.transactions.all():
            currencies.add(transaction.currency)
        return currencies

    # Cash balance at date
    def balance(self, date):
        balance = {}
        for cur in self.currencies():
            query = self.transactions.filter(broker_id=self.id, currency=cur, date__lte=date).aggregate(
                balance=models.Sum(
                    models.Case(
                        models.When(models.Q(quantity__gte=0), then=-1*models.F('quantity')*models.F('price')),
                        models.When(models.Q(cash_flow__isnull=False), then=models.F('cash_flow')),
                        models.When(models.Q(commission__isnull=False), then=models.F('commission')),
                        default=0
                    )
                )
            )['balance']
            balance[cur] = query or 0
        return balance

# Public assets
class PA(models.Model):
    type = models.CharField(max_length=10, null=False)
    ISIN = models.CharField(max_length=12)
    name = models.CharField(max_length=30, null=False)
    currency = models.CharField(max_length=3, null=False)
    exposure = models.TextField(null=False)

    # Returns price at the date or latest available before the date
    def current_price(self, price_date):
        try:
            quote = self.prices.filter(date__lte=price_date).order_by('-date').values_list('price', 'date').first()
            return quote
        except:
            return None

    # Define position at date by summing all movements to date
    def position(self, date, broker_id_list=[]):
        query = self.transactions.filter(date__lte=date).aggregate(total=models.Sum('quantity'))
        if broker_id_list:
            query = query.filter(broker_id__in=broker_id_list)
        return query['total'] or 0

    # Investment date
    def investment_date(self, broker_id_list=[]):
        query = self.transactions.order_by('date').values_list('date', flat=True).first()
        if broker_id_list:
            query = query.filter(broker_id__in=broker_id_list)
        return query

# Table with public asset transactions
class PA_transactions(models.Model):
    broker = models.ForeignKey(Brokers, on_delete=models.CASCADE, related_name='transactions')
    security = models.ForeignKey(PA, on_delete=models.CASCADE, related_name='transactions')
    currency = models.CharField(max_length=3, null=False)
    type = models.CharField(max_length=30, null=False)
    date = models.DateField(null=False)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=False)
    cash_flow = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    commission = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    comment = models.TextField(null=True)

# Table with non-public asset prices
class PA_prices(models.Model):
    date = models.DateField(primary_key=True)
    security = models.ForeignKey(PA, on_delete=models.CASCADE, related_name='prices')
    price = models.DecimalField(max_digits=10, decimal_places=2, null=False)
