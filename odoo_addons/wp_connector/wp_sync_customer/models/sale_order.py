from odoo import api, fields, models
import re


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    wc_order_id = fields.Char(
        string='WooCommerce Order',
        compute='_compute_wc_order_id',
        store=True,
        index=True,
    )

    @api.depends('client_order_ref')
    def _compute_wc_order_id(self):
        """
        Extract the WooCommerce order number from client_order_ref.
        The WP plugin sets client_order_ref = 'WC#<order_id>'.
        """
        for order in self:
            ref = order.client_order_ref or ''
            match = re.match(r'^WC#(\d+)$', ref.strip())
            order.wc_order_id = match.group(1) if match else False
