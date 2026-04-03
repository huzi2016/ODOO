import pandas as pd

input_file = 'Artikel.csv'

# CSV is encoded in ISO-8859-1 (Windows Latin-1)
df = pd.read_csv(input_file, sep=';', encoding='ISO-8859-1')

# UOM mapping: ERP Wert -> Odoo name
uom_map = {
    'Stk': 'Units',
    'Ktn': 'Units',   # Karton, fallback to Units
    'Ktn.': 'Units',  # Karton, fallback to Units
    'Pck': 'Units',  # Packung, fallback to Units
}

# product type: 'product' = storable, 'consu' = consumable
def map_type(row):
    if row['Verkauf'] == 'Ja' or row['Beschaffung'] == 'Ja':
        return 'Goods'  # storable product
    return 'Service'

odoo_map = {
    'ManusLfdNr':    df['ManusLfdNr'],               # Manual Sequence Number
    'default_code':  df['Artikelnummer'],           # Internal Reference
    'name':          df['Matchcode Artikel'],        # Product Name
    'categ_id':      df['Artikelgruppe_Bezeichnung'],# Product Category
    'uom_id':        df['Basismengeneinheit_Wert'].map(uom_map),   # Unit of Measure
    'uom_po_id':     df['Basismengeneinheit_Wert'].map(uom_map),   # Purchase UoM
    'active':        df['Aktiv'].map({'Ja': True, 'Nein': False}),
    'sale_ok':       df['Verkauf'].map({'Ja': True, 'Nein': False}),
    'purchase_ok':   df['Beschaffung'].map({'Ja': True, 'Nein': False}),
    'type':          df.apply(map_type, axis=1),
}

odoo_df = pd.DataFrame(odoo_map)

output_file = 'Odoo_Products_Import.csv'
odoo_df.to_csv(output_file, index=False, encoding='utf-8')

print(f"Conversion complete! {len(odoo_df)} products → {output_file}")
