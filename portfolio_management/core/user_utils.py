from common.models import BrokerAccounts
from users.models import AccountGroup

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

def get_broker_account_choices(user):
    """
    Get broker account choices for a user, including individual accounts and account groups.
    
    Args:
        user: The CustomUser object
    
    Returns:
        List of tuples containing broker account choices in grouped format:
        [
            ('General', [('All accounts', 'All accounts')]),
            ('Your Accounts', [(account.name, account.id), ...]),
            ('Account Groups', [(group.name, group.id), ...])
        ]
    """
    account_choices = [
        ('General', [('All accounts', 'All accounts')]),
        ('__SEPARATOR__', '__SEPARATOR__'),
    ]
    
    if user is not None:
        # Get individual broker accounts
        accounts = BrokerAccounts.objects.filter(broker__investor=user).order_by('name')
        user_accounts = [(account.name, account.name) for account in accounts]
        if user_accounts:
            account_choices.append(('Your Accounts', user_accounts))
            account_choices.append(('__SEPARATOR__', '__SEPARATOR__'))
        
        # Get broker account groups
        user_groups = AccountGroup.objects.filter(user=user).order_by('name')
        group_choices = [(group.name, group.name) for group in user_groups]
        if group_choices:
            account_choices.append(('Account Groups', group_choices))

    return account_choices

def get_broker_account_ids_from_choice(user, choice):
    """
    Convert a broker account choice to a list of account IDs.
    
    Args:
        user: The CustomUser object
        choice: String representing the selected choice (account ID, group ID, or 'All accounts')
    
    Returns:
        List of broker account IDs
    """
    if not choice or choice == 'All accounts':
        return list(BrokerAccounts.objects.filter(broker__investor=user).values_list('id', flat=True))
    
    if choice.startswith('group_'):
        group_id = int(choice.replace('group_', ''))
        try:
            group = AccountGroup.objects.get(id=group_id, user=user)
            return list(group.broker_accounts.values_list('id', flat=True))
        except AccountGroup.DoesNotExist:
            return []
    
    try:
        account_id = int(choice)
        if BrokerAccounts.objects.filter(id=account_id, broker__investor=user).exists():
            return [account_id]
    except (ValueError, TypeError):
        pass
    
    return []

def get_account_display_name(user, account_id):
    """
    Get display name for a broker account.
    
    Args:
        user: The CustomUser object
        account_id: The broker account ID
    
    Returns:
        String: Account name or group name
    """
    try:
        if isinstance(account_id, str) and account_id.startswith('group_'):
            group_id = int(account_id.replace('group_', ''))
            group = AccountGroup.objects.get(id=group_id, user=user)
            return f"Group: {group.name}"
        else:
            account = BrokerAccounts.objects.get(id=account_id, broker__investor=user)
            return account.name
    except (BrokerAccounts.DoesNotExist, AccountGroup.DoesNotExist, ValueError):
        return "Unknown Account"