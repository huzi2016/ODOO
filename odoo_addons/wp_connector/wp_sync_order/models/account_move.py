import logging

from odoo import models
from odoo.addons.wp_base.utils import WooCommerceClient

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        result = super().action_post()

        # Only process credit notes (out_refund = customer refund)
        for move in self.filtered(lambda m: m.move_type == 'out_refund'):
            self._push_wc_refunded(move)

        return result

    def _push_wc_refunded(self, credit_note):
        """Find the sale order linked to *credit_note* and set WC status to 'refunded'."""

        # 1. Try to find the original invoice via the reversal link
        original_invoice = credit_note.reversed_entry_id

        # 2. Locate sale orders that reference the original invoice
        if original_invoice:
            sale_orders = self.env['sale.order'].search([
                ('invoice_ids', 'in', original_invoice.id),
            ])
        else:
            # Fallback: match by invoice_origin (sale order name)
            sale_orders = self.env['sale.order'].search([
                ('name', '=', credit_note.invoice_origin),
            ])

        for order in sale_orders.filtered('wc_order_id'):
            try:
                client = WooCommerceClient(self.env)
                client.put(f'orders/{order.wc_order_id}', {'status': 'refunded'})
                _logger.info(
                    'WP Sync Order: refund posted on %s → WC #%s set to "refunded"',
                    order.name, order.wc_order_id,
                )
            except Exception as exc:
                _logger.error(
                    'WP Sync Order: failed to set WC #%s to "refunded": %s',
                    order.wc_order_id, exc,
                )
