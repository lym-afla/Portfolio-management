"""Signal handlers for the common app.

Currently only the FX graph-cache invalidation handler is wired here. The
``FX`` ``post_save`` / ``post_delete`` signals bump the version counter in
:func:`services.fx._invalidate_fx_graph_cache` so the currency graph built by
``services.fx.get_rate`` is rebuilt on the next call.

Note on ``bulk_create``: :class:`common.models.FXManager` saves rows one-by-one
for batches <= 50 (firing ``post_save`` per row, so invalidation works
transparently), but falls back to native ``bulk_create`` for larger batches
which emits no signals and leaves the cache stale. After any large bulk load,
call ``services.fx._invalidate_fx_graph_cache()`` explicitly.
"""

from django.db.models.signals import post_delete, post_save

from services.fx import _invalidate_fx_graph_cache

from .models import FX


def register_signals():
    """Connect FX cache-invalidation signals.

    Called from :meth:`common.apps.CommonConfig.ready`. Kept as a function so
    the wiring is explicit and easy to grep for.
    """
    post_save.connect(_invalidate_fx_graph_cache, sender=FX)
    post_delete.connect(_invalidate_fx_graph_cache, sender=FX)
