import logging

from odoo import http
from odoo.http import request
from odoo.addons.wp_base.controllers.base import WpBaseController
from odoo.addons.wp_base.utils.api_client import WooCommerceClient

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

        odoo_id = parent.id

        # ── 6. Write Odoo partner_id back to WordPress user meta ─────────
        # This keeps _loc_odoo_partner_id in sync so the WP plugin never
        # uses a stale / deleted partner id when pushing sale orders.
        wp_user_id = data.get('id')
        if wp_user_id:
            self._writeback_partner_id(wp_user_id, odoo_id)

        return {'status': 'success', 'odoo_id': odoo_id}

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

    # ─────────────────────────────────────────────────────────────────────
    def _writeback_partner_id(self, wp_user_id: int, odoo_partner_id: int):
        """
        POST the resolved Odoo partner id back to WooCommerce so that
        wp_usermeta._loc_odoo_partner_id is always up to date.

        WooCommerce REST endpoint used:
            PUT /wp-json/wc/v3/customers/<wp_user_id>
        with a custom meta_data payload.

        Failures are logged but never raised — the sync_customer response
        must not fail just because the write-back could not complete.
        """
        try:
            client = WooCommerceClient(request.env)
            client.put(
                f'customers/{wp_user_id}',
                {
                    'meta_data': [
                        {
                            'key': '_loc_odoo_partner_id',
                            'value': str(odoo_partner_id),
                        }
                    ]
                },
            )
            _logger.info(
                'WP Sync: wrote back odoo_partner_id=%s to WP user %s',
                odoo_partner_id, wp_user_id,
            )
        except Exception as exc:
            _logger.warning(
                'WP Sync: could not write back partner_id to WP user %s: %s',
                wp_user_id, exc,
            )
