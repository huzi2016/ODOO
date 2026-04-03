import pandas as pd

input_file = 'Kundenstamm.csv'

# CSV is UTF-8 encoded
df = pd.read_csv(input_file, sep=';', encoding='utf-8')

# Fiscal Position mapping — exact names from Odoo
def map_fp(row):
    country = str(row['Land_Wert'])
    if country in ['US', 'CN', 'CH']:
        return 'Steuergebiete Drittland'
    elif country != 'DE':
        return 'Business partner EU (without VAT ID)'
    return 'Domestic business partner'

# Language mapping based on country code -> Odoo lang code
lang_map = {
    'DE': 'de_DE',
    'AT': 'de_DE',
    'CH': 'de_DE',
    'IT': 'it_IT',
    'NL': 'nl_NL',
    'BE': 'nl_NL',  # or fr_BE depending on region, default Dutch
    'FR': 'fr_FR',
    'US': 'en_US',
    'CN': 'zh_CN',
}

# Payment terms mapping — exact names from Odoo
payment_map = {
    '7 Tage 2,00%, 14 Tage Netto':                  '7 Tage 2,00%, 14 Tage Netto',
    'Bankeinzug (4% Skonto)':                        'Bankeinzug (4% Skonto)',
    'Betrag dankend per Paypal erhalten':             'Immediate Payment',
    'Vorkasse, Ware bleibt max. 14 Tage reserviert': 'Vorkasse, Ware bleibt max. 14 Tage reserviert',
}

odoo_map = {
    'ref':                          df['Kundennummer'],
    'name':                         df['Name'],
    'street':                       df['Straße/Postfach'],
    'zip':                          df['PLZ'],
    'city':                         df['Ort'],
    'country':                      df['Land_Wert'],
    'email':                        df['E-Mail'],
    'is_company':                   True,
    'customer_rank':                1,
    'active':                       df['Aktiv-Kunden'].map({'Ja': True, 'Nein': False}),
    'property_account_position_id': df.apply(map_fp, axis=1),
    'property_payment_term_id':     df['Zahlungskondition_Bezeichnung'].map(payment_map),
    'lang':                         df['Land_Wert'].map(lang_map).fillna('de_DE'),
}

odoo_df = pd.DataFrame(odoo_map)

# Phone: preserve as string
odoo_df['phone'] = df['Telefon'].apply(
    lambda x: '' if pd.isna(x) else str(x).strip()
)

output_file = 'Odoo_Customers_Import.csv'
odoo_df.to_csv(output_file, index=False, encoding='utf-8')

print(f"Conversion complete! {len(odoo_df)} customers → {output_file}")
