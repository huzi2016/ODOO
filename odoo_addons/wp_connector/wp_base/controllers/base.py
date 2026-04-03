import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WpBaseController(http.Controller):
    """Shared base for all WooCommerce webhook controllers.

    Subclasses call ``_validate_token()`` at the start of every route handler
    and return an error response immediately if it returns False.
    """

    def _validate_token(self):
        """Return True if the incoming X-WP-Token header matches the value
        stored in ir.config_parameter (wp_base.api_token), False otherwise.
        """
        expected = (
            request.env['ir.config_parameter']
            .sudo()
            .get_param('wp_base.api_token', default='')
        )
        incoming = request.httprequest.environ.get('HTTP_X_WP_TOKEN', '')

        if not expected or incoming != expected:
            _logger.warning(
                'WP Connector: rejected webhook – invalid or missing X-WP-Token'
            )
            return False
        return True
