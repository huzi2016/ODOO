from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # WooCommerce store URL, e.g. https://myshop.de
    wp_store_url = fields.Char(
        string='WooCommerce Store URL',
        config_parameter='wp_base.store_url',
    )

    # WooCommerce REST API consumer key (ck_...)
    wp_consumer_key = fields.Char(
        string='Consumer Key',
        config_parameter='wp_base.consumer_key',
    )

    # WooCommerce REST API consumer secret (cs_...)
    wp_consumer_secret = fields.Char(
        string='Consumer Secret',
        config_parameter='wp_base.consumer_secret',
    )

    # Shared secret token that WooCommerce sends in X-WP-Token header
    wp_api_token = fields.Char(
        string='Webhook API Token',
        config_parameter='wp_base.api_token',
        help='Set the same value in WooCommerce webhook headers as X-WP-Token.',
    )
