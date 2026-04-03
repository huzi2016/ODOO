import pandas as pd

input_file = 'Lieferantenstamm.csv'

# Fix: CSV is encoded in ISO-8859-1 (Windows Latin-1), not UTF-8
df = pd.read_csv(input_file, sep=';', encoding='ISO-8859-1')  # Fix: was 'utf-8'

# field mapping logic
odoo_map = {
    'ref': df['Lieferantennummer'],
    'name': df['Name'],
    'street': df['Straße/Postfach'],
    'zip': df['PLZ'],
    'city': df['Ort'],
    'country': df['Land_Wert'],  # auto DE, US, CN, AT
    'email': df['E-Mail'],
}

# create DataFrame
odoo_df = pd.DataFrame(odoo_map)

# Fix: handle phone number — avoid scientific notation AND NaN values
odoo_df['phone'] = df['Telefon'].apply(
    lambda x: '' if pd.isna(x) else str(int(x)) if isinstance(x, float) else str(x).replace('.0', '')
)

# core logic: map Fiscal Position based on country and original description
def map_fp(row):
    country = str(row['Land_Wert'])
    desc = str(row['Besteuerungsart_Bezeichnung'])

    # logic A: clearly marked as §13b or from non-EU countries (US, CN)
    if '§13b' in desc or country in ['US', 'CN']:
        return 'Steuergebiete Drittland'
    # logic B: EU countries and not Germany (e.g. AT)
    elif country == 'AT' or 'EU mit UStID' in desc:
        return 'EU-Auslands'
    # logic C: Germany or default
    return ''

odoo_df['property_account_position_id'] = df.apply(map_fp, axis=1)

# additional properties: marked as company and active
odoo_df['is_company'] = True
odoo_df['active'] = df['Aktiv'].map({'Ja': True, 'Nein': False})

# export
output_file = 'Odoo_Suppliers_Import.csv'
odoo_df.to_csv(output_file, index=False, encoding='utf-8')

print(f"Conversion complete! Use {output_file} for import.")