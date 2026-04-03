import logging

from odoo import fields, models
from odoo.addons.wp_base.utils import WooCommerceClient

_logger = logging.getLogger(__name__)

# Odoo sale.order state → WooCommerce order status
_ODOO_TO_WC_STATUS = {
    'draft':  'pending',
    'sent':   'pending',
    'sale':   'processing',
    'done':   'completed',
    'cancel': 'cancelled',
}


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wc_order_id = fields.Integer(
        string='WooCommerce Order ID',
        copy=False,
        help='The WooCommerce order ID linked to this sale order. '
             'Set automatically when a WC order webhook is received.',
    )

    # ── status push ───────────────────────────────────────────────────────

    def _push_wc_status(self, wc_status):
        """Push *wc_status* to every linked WooCommerce order.

        Silently logs and skips orders without a wc_order_id or when the
        WooCommerce API is not reachable, so Odoo workflows are never blocked.
        """
        for order in self.filtered('wc_order_id'):
            try:
                client = WooCommerceClient(self.env)
                client.put(f'orders/{order.wc_order_id}', {'status': wc_status})
                _logger.info(
                    'WP Sync Order: %s → WC #%s set to "%s"',
                    order.name, order.wc_order_id, wc_status,
                )
            except Exception as exc:
                _logger.error(
                    'WP Sync Order: failed to update WC #%s to "%s": %s',
                    order.wc_order_id, wc_status, exc,
                )

    # ── Odoo action overrides ─────────────────────────────────────────────

    def action_confirm(self):
        """Confirmed → WC: processing"""
        result = super().action_confirm()
        self._push_wc_status('processing')
        return result

    def action_lock(self):
        """Locked / Done → WC: completed"""
        result = super().action_lock()
        self._push_wc_status('completed')
        return result

    def action_cancel(self):
        """Cancelled → WC: cancelled"""
        result = super().action_cancel()
        self._push_wc_status('cancelled')
        return result
