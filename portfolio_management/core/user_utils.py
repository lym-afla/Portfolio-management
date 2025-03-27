from common.models import Accounts, Brokers
from users.models import AccountGroup

FREQUENCY_CHOICES = [
    ("D", "Daily"),
    ("W", "Weekly"),
    ("M", "Monthly"),
    ("Q", "Quarterly"),
    ("Y", "Yearly"),
]

TIMELINE_CHOICES = [
    ("YTD", "Year to Date"),
    ("3m", "Last 3 months"),
    ("6m", "Last 6 months"),
    ("12m", "Last 12 months"),
    ("3Y", "Last 3 years"),
    ("5Y", "Last 5 years"),
    ("All", "All history"),
    ("Custom", "Custom"),
]


def prepare_account_choices(user):
    """
    Get broker account choices for a user, including individual accounts,
    account groups, and brokers.

    Args:
        user: The CustomUser object

    Returns:
        Dictionary containing:
        - options: List of tuples with sections and choices, including separators
        - selected: Dictionary with type and id of current selection
    """
    if user is None:
        return {"options": [], "selected": {"type": "all", "id": None}}

    # Initialize options with 'All accounts'
    options = [
        ("General", [("All accounts", {"type": "all", "id": None})]),
        ("__SEPARATOR__", "__SEPARATOR__"),
    ]

    # Get individual accounts with their brokers
    accounts = (
        Accounts.objects.filter(broker__investor=user)
        .select_related("broker")
        .order_by("broker__name", "name")
    )

    if accounts:
        account_choices = [
            (
                f"{account.name}",
                {
                    "type": "account",
                    "id": account.id,
                    "display_name": f"{account.broker.name} – {account.name}",
                },
            )
            for account in accounts
        ]
        options.extend(
            [
                ("Your Accounts", account_choices),
                ("__SEPARATOR__", "__SEPARATOR__"),
            ]
        )

    # Get brokers
    brokers = Brokers.objects.filter(investor=user).order_by("name")

    if brokers:
        broker_choices = [
            (
                broker.name,
                {"type": "broker", "id": broker.id, "display_name": f"All {broker.name} accounts"},
            )
            for broker in brokers
        ]
        options.extend(
            [
                ("Brokers", broker_choices),
                ("__SEPARATOR__", "__SEPARATOR__"),
            ]
        )

    # Get account groups
    groups = AccountGroup.objects.filter(user=user).order_by("name")

    if groups:
        group_choices = [
            (group.name, {"type": "group", "id": group.id, "display_name": group.name})
            for group in groups
        ]
        options.append(("Account Groups", group_choices))

    return {
        "options": options,
        "selected": {"type": user.selected_account_type, "id": user.selected_account_id},
    }


def get_account_ids_from_choice(user, choice):
    """
    Convert a broker account choice to a list of account IDs.

    Args:
        user: The CustomUser object
        choice: String representing the selected choice (account ID, group ID, or 'All accounts')

    Returns:
        List of broker account IDs
    """
    if not choice or choice == "All accounts":
        return list(Accounts.objects.filter(broker__investor=user).values_list("id", flat=True))

    if choice.startswith("group_"):
        group_id = int(choice.replace("group_", ""))
        try:
            group = AccountGroup.objects.get(id=group_id, user=user)
            return list(group.accounts.values_list("id", flat=True))
        except AccountGroup.DoesNotExist:
            return []

    try:
        account_id = int(choice)
        if Accounts.objects.filter(id=account_id, broker__investor=user).exists():
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
        if isinstance(account_id, str) and account_id.startswith("group_"):
            group_id = int(account_id.replace("group_", ""))
            group = AccountGroup.objects.get(id=group_id, user=user)
            return f"Group: {group.name}"
        else:
            account = Accounts.objects.get(id=account_id, broker__investor=user)
            return account.name
    except (Accounts.DoesNotExist, AccountGroup.DoesNotExist, ValueError):
        return "Unknown Account"
