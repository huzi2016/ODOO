"""
Sage 100 -> Odoo Product Category Import Script
================================================
Reads an exported CSV/Excel file from SSMS and generates three Odoo-compatible
CSV files, split by category level, ready to be imported in order.

How to export from SQL Server Management Studio (SSMS):
    1. Run the following query:
         SELECT
             Hauptartikelgruppe,
             VaterArtikelgruppe,
             Artikelgruppe,
             Bezeichnung,
             Gruppenebene
         FROM KHKArtikelgruppen
         WHERE Artikelgruppe != 'Dummy'
         ORDER BY Gruppenebene, Artikelgruppe
    2. Right-click the results grid -> "Save Results As..."
    3. Save as CSV, e.g. khk_categories.csv

Import order in Odoo (Inventory -> Configuration -> Product Categories):
    1. product_category_1_toplevel.csv  (27 rows,  parent = Odoo root)
    2. product_category_2_mid.csv       (185 rows, parent = level-1 path)
    3. product_category_3_detail.csv    (260 rows, parent = level-2 path)

Duplicate categories / Odoo 17+:
    If the database already has several categories with the same path (e.g. four
    "Goods / Labor"), matching by name shows "Found N matches". This script
    outputs ``id`` (``__import__.pc_*``) and ``parent_id/id`` so each row links
    to a single parent. Set ODOO_ROOT_PARENT_XMLID to your real parent of L1
    (e.g. "Goods") from Export → External ID, or the first file may be ambiguous
    for the root parent when left empty.

Dependencies:
    pip install pandas openpyxl

Usage:
    python gen_product_category.py
"""

import csv
import os
from typing import Optional, Tuple

import pandas as pd

from categ_xid import categ_xid

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────

# Path to the exported file from SSMS (CSV or Excel)
INPUT_FILE = "product_category.csv"

# Output file names (will be created in the same folder as this script)
OUTPUT_LEVEL1 = "product_category_1_toplevel.csv"
OUTPUT_LEVEL2 = "product_category_2_mid.csv"
OUTPUT_LEVEL3 = "product_category_3_detail.csv"

# Column names in the exported file
# Adjust these if your SSMS export uses different headers
COL_HAUPTGRUPPE = "Hauptartikelgruppe"
COL_VATER       = "VaterArtikelgruppe"
COL_CODE        = "Artikelgruppe"
COL_NAME        = "Bezeichnung"
COL_LEVEL       = "Gruppenebene"

# Category codes to exclude from the import
EXCLUDE_CODES = ["Dummy"]

# The Odoo root category that all level-1 categories will be attached to.
# Check your Odoo: Inventory -> Configuration -> Product Categories
# Use the exact name shown there (e.g. "Goods", "All", "Alle Produkte")
ODOO_ROOT_CATEGORY = "Goods"
# If set, L1 file uses parent_id/id (unambiguous). Export your "Goods" row from
# Odoo to see the External ID (e.g. product.xxx). Leave "" to use parent_id
# = ODOO_ROOT_CATEGORY (can match multiple if duplicates exist).
ODOO_ROOT_PARENT_XMLID = ""

# ─────────────────────────────────────────────
# Read input file
# ─────────────────────────────────────────────

def read_input(filepath):
    """Load CSV or Excel exported from SSMS into a DataFrame."""
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".csv":
        # SSMS may export with comma, semicolon, or tab separator
        for sep in [",", ";", "\t"]:
            try:
                df = pd.read_csv(filepath, sep=sep, dtype=str, encoding="utf-8-sig")
                if COL_CODE in df.columns:
                    print(f"  Detected separator: {repr(sep)}")
                    return df
            except Exception:
                continue
        raise ValueError(
            f"Could not parse '{filepath}'. "
            "Check that the separator is comma, semicolon, or tab."
        )

    elif ext in [".xlsx", ".xls"]:
        return pd.read_excel(filepath, dtype=str)

    else:
        raise ValueError(f"Unsupported format: '{ext}'. Use .csv or .xlsx")


# ─────────────────────────────────────────────
# Write a single CSV file
# ─────────────────────────────────────────────

def _l1_l2_for_l2code(l2c, code_to_vater, code_to_name):
    l2c = str(l2c).strip()
    l2n = str(code_to_name.get(l2c, "")).strip()
    v1 = str(code_to_vater.get(l2c, "") or "").strip()
    l1n = str(code_to_name.get(v1, "")).strip() if v1 and v1 in code_to_name else ""
    return l1n, l2n


def write_csv_tier1(filepath, xid_name_pairs, root_name):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if ODOO_ROOT_PARENT_XMLID:
            w.writerow(["id", "name", "parent_id/id"])
            for xid, n in xid_name_pairs:
                w.writerow([xid, n, ODOO_ROOT_PARENT_XMLID])
        else:
            w.writerow(["id", "name", "parent_id"])
            for xid, n in xid_name_pairs:
                w.writerow([xid, n, root_name])
    print(f"  {os.path.basename(filepath)}: {len(xid_name_pairs)} rows written")


def write_csv_tier2_3(filepath, rows):
    """rows: list of (record_xid, name, parent_xid)"""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "parent_id/id"])
        w.writerows(rows)
    print(f"  {os.path.basename(filepath)}: {len(rows)} rows written")


# ─────────────────────────────────────────────
# Generate the three split CSV files
# ─────────────────────────────────────────────

def generate_split_csvs(
    df,
    out1=None,
    out2=None,
    out3=None,
):
    out1 = out1 or OUTPUT_LEVEL1
    out2 = out2 or OUTPUT_LEVEL2
    out3 = out3 or OUTPUT_LEVEL3
    # Remove excluded codes
    df = df[~df[COL_CODE].isin(EXCLUDE_CODES)].copy()

    # Ensure level is an integer
    df[COL_LEVEL] = pd.to_numeric(df[COL_LEVEL], errors="coerce").fillna(0).astype(int)

    # Sort by level then code to guarantee parents appear before children
    df = df.sort_values(by=[COL_LEVEL, COL_CODE]).reset_index(drop=True)

    # Build lookups (parent category is stored by code in the export)
    code_to_name = dict(zip(df[COL_CODE], df[COL_NAME]))
    code_to_vater = {}
    for _, row in df.iterrows():
        c = str(row[COL_CODE]).strip()
        v = str(row[COL_VATER]).strip() if row[COL_VATER] is not None else ""
        if v in ("", "nan", "None"):
            v = ""
        code_to_vater[c] = v

    level1_rows = []
    level2_rows = []
    level3_rows = []
    skipped     = []

    for _, row in df.iterrows():
        vater = str(row[COL_VATER]).strip()
        code  = str(row[COL_CODE]).strip()
        name  = str(row[COL_NAME]).strip()
        level = int(row[COL_LEVEL])

        if not name or name == "nan":
            skipped.append((code, "empty name"))
            continue

        if level == 1:
            l1x = categ_xid("L1", ODOO_ROOT_CATEGORY, name)
            level1_rows.append((l1x, name))

        elif level == 2:
            if not vater or vater not in code_to_name or str(vater) == "nan":
                skipped.append((code, f"parent not found (vater={vater})"))
                continue
            l1n = str(code_to_name[vater]).strip()
            c2x = categ_xid("L2", ODOO_ROOT_CATEGORY, l1n, name)
            p1x = categ_xid("L1", ODOO_ROOT_CATEGORY, l1n)
            level2_rows.append((c2x, name, p1x))

        elif level == 3:
            if not vater or vater not in code_to_name or str(vater) == "nan":
                skipped.append((code, f"parent not found (vater={vater})"))
                continue
            l1n, l2n = _l1_l2_for_l2code(vater, code_to_vater, code_to_name)
            if not l1n or not l2n:
                skipped.append((code, f"could not resolve L1/L2 for vater={vater}"))
                continue
            c3x = categ_xid("L3", ODOO_ROOT_CATEGORY, l1n, l2n, name)
            p2x = categ_xid("L2", ODOO_ROOT_CATEGORY, l1n, l2n)
            level3_rows.append((c3x, name, p2x))

        else:
            skipped.append((code, f"unexpected level {level}"))

    write_csv_tier1(out1, level1_rows, ODOO_ROOT_CATEGORY)
    write_csv_tier2_3(out2, level2_rows)
    write_csv_tier2_3(out3, level3_rows)

    total = len(level1_rows) + len(level2_rows) + len(level3_rows)
    return total, skipped


def build_artikelgruppe_to_xid(df: pd.DataFrame) -> dict:
    """
    Map KHK ``Artikelgruppe`` (category code) -> Odoo import external id
    (``__import__.pc_*``), using the *same* rules as the split category CSVs.
    Used by ``Data_Sync/Product/Product.py`` for ``categ_id/id`` on product import.
    """
    df = df[~df[COL_CODE].isin(EXCLUDE_CODES)].copy()
    df[COL_LEVEL] = (
        pd.to_numeric(df[COL_LEVEL], errors="coerce").fillna(0).astype(int)
    )
    df = df.sort_values(by=[COL_LEVEL, COL_CODE]).reset_index(drop=True)

    code_to_name = dict(zip(df[COL_CODE], df[COL_NAME]))
    code_to_vater: dict = {}
    for _, row in df.iterrows():
        c = str(row[COL_CODE]).strip()
        v = str(row[COL_VATER]).strip() if row[COL_VATER] is not None else ""
        if v in ("", "nan", "None"):
            v = ""
        code_to_vater[c] = v

    out: dict = {}
    for _, row in df.iterrows():
        vater = str(row[COL_VATER]).strip()
        code = str(row[COL_CODE]).strip()
        name = str(row[COL_NAME]).strip()
        level = int(row[COL_LEVEL])

        if not name or name == "nan":
            continue

        if level == 1:
            out[code] = categ_xid("L1", ODOO_ROOT_CATEGORY, name)
        elif level == 2:
            if not vater or vater not in code_to_name or str(vater) == "nan":
                continue
            l1n = str(code_to_name[vater]).strip()
            out[code] = categ_xid("L2", ODOO_ROOT_CATEGORY, l1n, name)
        elif level == 3:
            if not vater or vater not in code_to_name or str(vater) == "nan":
                continue
            l1n, l2n = _l1_l2_for_l2code(
                vater, code_to_vater, code_to_name
            )
            if not l1n or not l2n:
                continue
            out[code] = categ_xid("L3", ODOO_ROOT_CATEGORY, l1n, l2n, name)
    return out


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def generate_khk_from_path(
    in_path: str,
    out_dir: Optional[str] = None,
) -> Optional[Tuple[int, list]]:
    """Read KHK export from ``in_path``; write the three split CSVs into ``out_dir`` (script dir if None)."""
    b = out_dir or os.path.dirname(os.path.abspath(__file__))
    o1 = os.path.join(b, OUTPUT_LEVEL1)
    o2 = os.path.join(b, OUTPUT_LEVEL2)
    o3 = os.path.join(b, OUTPUT_LEVEL3)
    if not os.path.exists(in_path):
        print(f"ERROR: File not found — {in_path!r}")
        return None
    try:
        df = read_input(in_path)
        print(f"  Loaded {len(df)} rows | Columns: {list(df.columns)}")
    except Exception as e:
        print(f"ERROR reading file: {e}")
        return None
    required = [COL_HAUPTGRUPPE, COL_VATER, COL_CODE, COL_NAME, COL_LEVEL]
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"ERROR: Missing columns: {missing}")
        print(f"  Found: {list(df.columns)}")
        return None
    print(f"\nGenerating CSV files (root category = '{ODOO_ROOT_CATEGORY}')...")
    return generate_split_csvs(df, o1, o2, o3)


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    in_path = INPUT_FILE if os.path.isabs(INPUT_FILE) else os.path.join(here, INPUT_FILE)
    print(f"Reading input file: {in_path}")

    if not os.path.exists(in_path):
        print(f"ERROR: File not found — '{in_path}'")
        print("Export the query result from SSMS and place it in the same folder as this script.")
        return

    res = generate_khk_from_path(in_path, here)
    if res is None:
        return
    total, skipped = res

    print(f"\nDone!")
    print(f"  Total written : {total} categories")
    print(f"  Skipped       : {len(skipped)} rows")
    if skipped:
        for code, reason in skipped:
            print(f"    - [{code}] {reason}")

    print()
    print("Import order in Odoo (Inventory -> Configuration -> Product Categories):")
    print(f"  1. {OUTPUT_LEVEL1}  <- import first")
    print(f"  2. {OUTPUT_LEVEL2}  <- import second")
    print(f"  3. {OUTPUT_LEVEL3}  <- import third")
    print()
    print(
        "Map: id -> External id, name -> Name, parent_id/id -> Parent Category; "
        "or parent_id (tier 1) if you left ODOO_ROOT_PARENT_XMLID empty."
    )


if __name__ == "__main__":
    main()
