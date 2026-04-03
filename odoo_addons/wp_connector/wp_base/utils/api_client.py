"""WooCommerce REST API v3 client.

Usage from any wp_sync_* module::

    from odoo.addons.wp_base.utils import WooCommerceClient

    client = WooCommerceClient(self.env)
    customers = client.get('customers', params={'per_page': 100})
"""

import logging

import requests
from requests.auth import HTTPBasicAuth

_logger = logging.getLogger(__name__)

_API_VERSION = 'wc/v3'


class WooCommerceClient:
    """Thin wrapper around the WooCommerce REST API v3.

    Credentials are read from ``ir.config_parameter`` (set via Odoo Settings →
    WooCommerce).  Raises ``UserError`` if the store URL is not configured.
    """

    def __init__(self, env):
        ICP = env['ir.config_parameter'].sudo()
        self._base_url = (ICP.get_param('wp_base.store_url') or '').rstrip('/')
        self._auth = HTTPBasicAuth(
            ICP.get_param('wp_base.consumer_key', default=''),
            ICP.get_param('wp_base.consumer_secret', default=''),
        )
        if not self._base_url:
            from odoo.exceptions import UserError
            raise UserError(
                'WooCommerce store URL is not configured. '
                'Go to Settings → WooCommerce to set it up.'
            )

    # ── helpers ──────────────────────────────────────────────────────────

    def _url(self, endpoint):
        return f"{self._base_url}/wp-json/{_API_VERSION}/{endpoint.lstrip('/')}"

    def _handle(self, response):
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            _logger.error('WooCommerce API error: %s – %s', exc, response.text)
            raise
        return response.json()

    # ── public interface ─────────────────────────────────────────────────

    def get(self, endpoint, params=None):
        """GET /wp-json/wc/v3/<endpoint> and return parsed JSON."""
        resp = requests.get(
            self._url(endpoint),
            params=params or {},
            auth=self._auth,
            timeout=15,
        )
        return self._handle(resp)

    def post(self, endpoint, data):
        """POST JSON body to /wp-json/wc/v3/<endpoint>."""
        resp = requests.post(
            self._url(endpoint),
            json=data,
            auth=self._auth,
            timeout=15,
        )
        return self._handle(resp)

    def put(self, endpoint, data):
        """PUT JSON body to /wp-json/wc/v3/<endpoint>."""
        resp = requests.put(
            self._url(endpoint),
            json=data,
            auth=self._auth,
            timeout=15,
        )
        return self._handle(resp)

    def delete(self, endpoint, params=None):
        """DELETE /wp-json/wc/v3/<endpoint>."""
        resp = requests.delete(
            self._url(endpoint),
            params=params or {},
            auth=self._auth,
            timeout=15,
        )
        return self._handle(resp)
