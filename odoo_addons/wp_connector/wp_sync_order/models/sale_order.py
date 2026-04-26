import logging

from odoo import fields, models
from odoo.addons.wp_base.utils import WooCommerceClient

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wc_order_id = fields.Integer(
        string='WooCommerce Order ID',
        copy=False,
        help='Populated automatically from client_order_ref (WC#xxxxx) '
             'or set manually. Used to push status back to WooCommerce.',
    )

    # ── WC order ID resolution ────────────────────────────────────────────

    def _resolve_wc_order_id(self):
        """Return the WC order ID for this sale order.

        Priority:
        1. wc_order_id field (manual override)
        2. client_order_ref in format 'WC#12345' (set by LIMO Odoo Connector WP plugin)
        """
        if self.wc_order_id:
            return self.wc_order_id
        ref = (self.client_order_ref or '').strip()
        if ref.upper().startswith('WC#'):
            try:
                return int(ref[3:])
            except ValueError:
                pass
        return 0

    # ── Status push ──────────────────────────────────────────────────────────

    def _push_wc_status(self, wc_status):
        """Push *wc_status* to WooCommerce for each order that has a resolvable WC order ID.

        Errors are logged but never raise, so Odoo workflows are never blocked.
        """
        for order in self:
            wc_id = order._resolve_wc_order_id()
            if not wc_id:
                continue
            try:
                client = WooCommerceClient(self.env)
                client.put(f'orders/{wc_id}', {'status': wc_status})
                _logger.info(
                    'WP Sync Order: %s → WC #%s set to "%s"',
                    order.name, wc_id, wc_status,
                )
            except Exception as exc:
                _logger.error(
                    'WP Sync Order: failed to update WC #%s to "%s": %s',
                    wc_id, wc_status, exc,
                )

    # ── Odoo action overrides ──────────────────────────────────────────────

    def action_confirm(self):
        result = super().action_confirm()
        self._push_wc_status('processing')
        return result

    def action_lock(self):
        result = super().action_lock()
        self._push_wc_status('completed')
        return result

    def action_cancel(self):
        result = super().action_cancel()
        self._push_wc_status('cancelled')
        return result
