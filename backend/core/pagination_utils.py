from typing import Any, Dict, List, Tuple

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator


def paginate_table(table: List[Any], page: int, items_per_page: int) -> Tuple[Any, Dict[str, int]]:
    """
    Paginate a table of data.

    :param table: The data to be paginated
    :param page: The current page number
    :param items_per_page: Number of items to display per page
    :return: A tuple containing the paginated data and pagination information
    """
    paginator = Paginator(table, items_per_page)
    try:
        paginated_table = paginator.page(int(page))
    except PageNotAnInteger:
        paginated_table = paginator.page(1)
    except EmptyPage:
        paginated_table = paginator.page(paginator.num_pages)

    return paginated_table, {
        "total_items": paginator.count,
        "current_page": paginated_table.number,
        "total_pages": paginator.num_pages,
    }
