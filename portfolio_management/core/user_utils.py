from common.models import Brokers
from users.models import BrokerGroup

FREQUENCY_CHOICES = [
    ('D', 'Daily'),
    ('W', 'Weekly'),
    ('M', 'Monthly'),
    ('Q', 'Quarterly'),
    ('Y', 'Yearly'),
]

TIMELINE_CHOICES = [
    ('YTD', 'Year to Date'),
    ('3m', 'Last 3 months'),
    ('6m', 'Last 6 months'),
    ('12m', 'Last 12 months'),
    ('3Y', 'Last 3 years'),
    ('5Y', 'Last 5 years'),
    ('All', 'All history'),
    ('Custom', 'Custom'),
]

def get_broker_choices(user):
    """
    Get broker choices for a user, including individual brokers and broker groups.
    
    :param user: The user object
    :return: List of tuples containing broker choices in grouped format
    """
    broker_choices = [
        ('General', [('All brokers', 'All brokers')]),
        ('__SEPARATOR__', '__SEPARATOR__'),
    ]
    
    if user is not None:
        brokers = Brokers.objects.filter(investor=user).order_by('name')
        user_brokers = [(broker.name, broker.name) for broker in brokers]
        if user_brokers:
            broker_choices.append(('Your Brokers', user_brokers))
            broker_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
        
        user_groups = BrokerGroup.objects.filter(user=user).order_by('name')
        group_choices = [(group.name, group.name) for group in user_groups]
        if group_choices:
            broker_choices.append(('Broker Groups', group_choices))

    return broker_choices