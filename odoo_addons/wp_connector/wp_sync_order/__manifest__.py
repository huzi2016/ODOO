{
    'name': 'LIMO WP Sync Order',
    'version': '19.0.1.0.0',
    'summary': 'Push Odoo sale order status changes to WooCommerce',
    'description': 'When an Odoo sale order is confirmed, completed, cancelled or refunded, '
                   'the corresponding WooCommerce order status is updated via REST API.',
    'author': '',
    'website': '',
    'category': 'Technical',
    'depends': ['wp_base', 'sale', 'account'],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
