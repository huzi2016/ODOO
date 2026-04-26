"""
Generate Missing Vendor Placeholder Import File
================================================
Compares KHKArtikelLieferant supplier refs against the Odoo partner map,
and generates a CSV of missing suppliers with placeholder names.

These placeholders can be imported into Odoo immediately so that vendor
pricelists can be linked. Names should be updated later once the original
Sage 100 system is accessible.

Required input files (same folder as this script):
    - odoo_partner_id_map.xlsx     : exported from Odoo Contacts (ID, Reference, Name)
    - khk_lieferants.csv           : exported from SSMS using the query below

SSMS export query:
    SELECT DISTINCT
        Lieferant AS ref
    FROM KHKArtikelLieferant
    WHERE Mandant = 1
      AND Einzelpreis > 0
      AND NULLIF(LTRIM(RTRIM(Lieferant)), '') IS NOT NULL
    ORDER BY Lieferant

Output:
    missing_vendors_placeholder.csv  -> import into Odoo Contacts

Import steps in Odoo:
    Contacts -> gear icon -> Import
    Field mapping (auto-detected from column names):
      ref           -> Reference
      name          -> Name
      is_company    -> Company
      supplier_rank -> Supplier Rank
      active        -> Active
      country_id    -> Country

Dependencies:
    pip install pandas openpyxl

Usage:
    python gen_missing_vendors.py
"""

import os
import pandas as pd

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

BASE_DIR           = os.path.dirname(os.path.abspath(__file__))
PARTNER_MAP_FILE   = os.path.join(BASE_DIR, "odoo_partner_id_map.xlsx")
KHK_LIEFERANT_FILE = os.path.join(BASE_DIR, "khk_lieferants.csv")
OUTPUT_FILE        = os.path.join(BASE_DIR, "missing_vendors_placeholder.csv")

# Default values for placeholder contacts
DEFAULT_COUNTRY    = "DE"
PLACEHOLDER_SUFFIX = "[placeholder]"

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def normalize_ref(value) -> str:
    """Normalize a ref value to string, stripping trailing .0"""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        return s[:-2]
    return s if s.lower() not in ("nan", "none", "") else ""


# ─────────────────────────────────────────────
# Load files
# ─────────────────────────────────────────────

def load_odoo_refs(path: str) -> set:
    """Load existing Odoo partner refs as a set of normalized strings."""
    df = pd.read_excel(path)
    df.columns = [str(c).strip() for c in df.columns]
    ref_col = next((c for c in df.columns if "reference" in c.lower()), None)
    if not ref_col:
        raise ValueError(f"Column 'Reference' not found in {path}. Found: {list(df.columns)}")
    return set(normalize_ref(r) for r in df[ref_col] if normalize_ref(r))


def load_khk_refs(path: str) -> list:
    """Load KHKArtikelLieferant supplier refs from CSV export."""
    # Try common separators
    for sep in [",", ";", "\t"]:
        try:
            df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
            ref_col = next((c for c in df.columns if "lieferant" in c.lower() or "ref" in c.lower()), None)
            if ref_col:
                refs = [normalize_ref(r) for r in df[ref_col] if normalize_ref(r)]
                return sorted(set(refs), key=lambda x: int(x) if x.isdigit() else x)
        except Exception:
            continue
    raise ValueError(f"Could not parse {path}. Expected column: 'ref' or 'Lieferant'")


# ─────────────────────────────────────────────
# Generate placeholder CSV
# ─────────────────────────────────────────────

def generate_placeholders(missing_refs: list, output_file: str):
    rows = []
    for ref in missing_refs:
        rows.append({
            "ref":           ref,
            "name":          f"Supplier {ref} {PLACEHOLDER_SUFFIX}",
            "is_company":    True,
            "supplier_rank": 1,
            "active":        True,
            "street":        "",
            "zip":           "",
            "city":          "",
            "country_id":    DEFAULT_COUNTRY,
            "phone":         "",
            "email":         "",
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_file, index=False, encoding="utf-8")
    return len(rows)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    # Validate input files
    for path in [PARTNER_MAP_FILE, KHK_LIEFERANT_FILE]:
        if not os.path.exists(path):
            print(f"ERROR: File not found — '{path}'")
            if "khk_lieferants" in path:
                print("  Export from SSMS:")
                print("  SELECT DISTINCT Lieferant AS ref")
                print("  FROM KHKArtikelLieferant")
                print("  WHERE Mandant = 1 AND Einzelpreis > 0")
                print("  AND NULLIF(LTRIM(RTRIM(Lieferant)), '') IS NOT NULL")
                print("  ORDER BY Lieferant")
            return

    print("Loading Odoo partner refs...")
    try:
        odoo_refs = load_odoo_refs(PARTNER_MAP_FILE)
        print(f"  Found {len(odoo_refs)} existing suppliers in Odoo")
    except Exception as e:
        print(f"ERROR: {e}")
        return

    print("Loading KHK supplier refs...")
    try:
        khk_refs = load_khk_refs(KHK_LIEFERANT_FILE)
        print(f"  Found {len(khk_refs)} unique suppliers in KHKArtikelLieferant")
    except Exception as e:
        print(f"ERROR: {e}")
        return

    # Find missing
    missing = [r for r in khk_refs if r not in odoo_refs]
    already = [r for r in khk_refs if r in odoo_refs]

    print()
    print(f"Already in Odoo : {len(already)}")
    print(f"Missing from Odoo: {len(missing)}")

    if not missing:
        print("All suppliers already exist in Odoo — nothing to do!")
        return

    print(f"\nGenerating {OUTPUT_FILE}...")
    count = generate_placeholders(missing, OUTPUT_FILE)

    print(f"\nDone! {count} placeholder suppliers written to:")
    print(f"  {os.path.abspath(OUTPUT_FILE)}")
    print()
    print("Import steps in Odoo:")
    print("  Contacts -> gear icon -> Import -> upload missing_vendors_placeholder.csv")
    print("  Fields should auto-map. Click Test, then Import.")
    print()
    print("After importing, run vendor_price_to_odoo_v2.py again with the updated")
    print("odoo_partner_id_map.xlsx to generate the final vendor pricelist import file.")


if __name__ == "__main__":
    main()
