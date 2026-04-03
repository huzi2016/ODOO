import logging

from odoo import http
from odoo.http import request
from odoo.addons.wp_base.controllers.base import WpBaseController

_logger = logging.getLogger(__name__)


class WpCustomerController(WpBaseController):

    @http.route(
        '/wp/api/sync_customer',
        type='json',
        auth='none',
        methods=['POST'],
        csrf=False,
    )
    def receive_customer(self, **post):
        # ── 1. Token validation (shared logic from WpBaseController) ─────
        # TODO: enable token validation before going to production
        # if not self._validate_token():
        #     return {'status': 'error', 'message': 'Unauthorized'}

        # ── 2. Parse payload ─────────────────────────────────────────────
        data = request.jsonrequest
        email = (data.get('email') or '').strip().lower()
        if not email:
            return {'status': 'error', 'message': 'No email provided'}

        Partner = request.env['res.partner'].sudo()
        Country = request.env['res.country'].sudo()

        full_name = (
            f"{data.get('first_name', '')} {data.get('last_name', '')}".strip()
            or email
        )

        # ── 3. Find or create the main contact (parent) ──────────────────
        parent = Partner.search(
            [('email', '=', email), ('parent_id', '=', False)], limit=1
        )

        main_vals = {
            'name': full_name,
            'email': email,
            'phone': data.get('billing', {}).get('phone'),
            'lang': 'de_DE',
            'company_type': 'person',
            'customer_rank': 1,
        }

        if parent:
            parent.write(main_vals)
            _logger.info('WP Sync: Updated partner %s (id=%s)', email, parent.id)
        else:
            wp_user_id = data.get('id')
            if wp_user_id:
                main_vals['comment'] = f"WordPress User ID: {wp_user_id}"
            parent = Partner.create(main_vals)
            _logger.info('WP Sync: Created partner %s (id=%s)', email, parent.id)

        # ── 4. Billing address ───────────────────────────────────────────
        billing = data.get('billing', {})
        if billing.get('address_1'):
            self._sync_address(
                Partner, Country, parent,
                addr_type='invoice',
                addr_data=billing,
                name=full_name,
            )

        # ── 5. Shipping address ──────────────────────────────────────────
        shipping = data.get('shipping', {})
        if shipping.get('address_1'):
            self._sync_address(
                Partner, Country, parent,
                addr_type='delivery',
                addr_data=shipping,
                name=full_name,
            )

        return {'status': 'success', 'odoo_id': parent.id}

    # ─────────────────────────────────────────────────────────────────────
    def _sync_address(self, Partner, Country, parent, addr_type, addr_data, name):
        """Create an address child record if one with the same street+zip does not exist."""
        existing = Partner.search([
            ('parent_id', '=', parent.id),
            ('type', '=', addr_type),
            ('zip', '=', addr_data.get('postcode')),
            ('street', '=', addr_data.get('address_1')),
        ], limit=1)

        if existing:
            return

        country = Country.search(
            [('code', '=', addr_data.get('country'))], limit=1
        )
        Partner.create({
            'parent_id': parent.id,
            'type': addr_type,
            'name': name,
            'street': addr_data.get('address_1'),
            'street2': addr_data.get('address_2') or False,
            'city': addr_data.get('city'),
            'zip': addr_data.get('postcode'),
            'country_id': country.id if country else False,
        })
        _logger.info(
            'WP Sync: Created %s address for partner id=%s', addr_type, parent.id
        )
