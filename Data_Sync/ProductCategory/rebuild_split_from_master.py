"""Rebuild product_category_1/2/3 from monolithic product_category.csv (KHK-style).

Uses stable ``__import__.pc_*`` external IDs and ``parent_id/id`` so imports do
not hit "Found N matches" when duplicate display names exist in the database.

Set ODOO_ROOT_PARENT_XMLID to the External ID of the Odoo parent of your L1
categories (e.g. "Goods" under "All") — see Inventory → export one row, or
Developer → View External Identifier.
If left empty, L1 files use the ``parent_id`` column (display name) instead,
which can still be ambiguous.
"""

import csv
import os
from collections import defaultdict

from categ_xid import categ_xid

# If input CSV looks like an SSMS KHK export, delegate to gen_product_category.py
# (it uses Gruppenebene, not the fixed 27+185 row monolith).
KHK_HEADER_MARKERS = ("Bezeichnung", "Artikelgruppe", "Gruppenebene")

ROOT = "Goods"
# External ID of the *existing* Odoo category that is the direct parent of your
# L1 rows (the one named e.g. "Goods" in the UI). Export from list view to find it.
# Examples (database-dependent): "product.product_category_1" or a custom one.
ODOO_ROOT_PARENT_XMLID = ""
MASTER = "product_category.csv"
# Layout: 27 L1, 185 L2, then all remaining rows = L3 (see n1, n2 below)


def rebuild_from_file(master_path: str) -> None:
    base = os.path.dirname(os.path.abspath(master_path))
    with open(master_path, newline="", encoding="utf-8") as f:
        all_rows = list(csv.reader(f))
    if not all_rows:
        raise SystemExit(f"empty file: {master_path!r}")
    h0 = ",".join(all_rows[0])
    if all(m in h0 for m in KHK_HEADER_MARKERS):
        from gen_product_category import generate_khk_from_path

        print("Input is KHK export (SSMS) — running gen_product_category logic.")
        r = generate_khk_from_path(master_path, base)
        if r is None:
            raise SystemExit(1)
        total, skipped = r
        print(
            f"\nDone! Total written: {total}, skipped: {len(skipped)}. "
            "Map id, name, parent_id/id in Odoo import."
        )
        if skipped:
            for code, reason in skipped:
                print(f"  - [{code}] {reason}")
        return
    # Monolithic: two columns (name + parent), 27 L1, 185 L2, then L3
    data = [r for r in all_rows[1:] if len(r) >= 2]
    # 27 L1, 185 L2, then L3 (must match KHK / monolith layout)
    n1, n2 = 27, 185
    rows_l1 = data[0:n1]
    rows_l2 = data[n1 : n1 + n2]
    rows_l3 = data[n1 + n2 :]

    def _pair(row):
        return row[0].strip(), row[1].strip()


    l1s_for_l2 = {}
    for row in rows_l2:
        c, p = _pair(row)
        if c not in l1s_for_l2:
            l1s_for_l2[c] = []
        if not l1s_for_l2[c] or l1s_for_l2[c][-1] != p:
            l1s_for_l2[c].append(p)

    out1 = os.path.join(base, "product_category_1_toplevel.csv")
    out2 = os.path.join(base, "product_category_2_mid.csv")
    out3 = os.path.join(base, "product_category_3_detail.csv")

    l1_tuples = []
    for r in rows_l1:
        c, _p = _pair(r)
        l1_tuples.append((categ_xid("L1", ROOT, c), c))

    with open(out1, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if ODOO_ROOT_PARENT_XMLID:
            w.writerow(["id", "name", "parent_id/id"])
            for xid, n in l1_tuples:
                w.writerow([xid, n, ODOO_ROOT_PARENT_XMLID])
        else:
            w.writerow(["id", "name", "parent_id"])
            for xid, n in l1_tuples:
                w.writerow([xid, n, ROOT])

    with open(out2, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "parent_id/id"])
        for row in rows_l2:
            c, p = _pair(row)
            child_xid = categ_xid("L2", ROOT, p, c)
            parent_l1 = categ_xid("L1", ROOT, p)
            w.writerow([child_xid, c, parent_l1])

    by_par = defaultdict(list)
    for i, row in enumerate(rows_l3):
        _c, p = _pair(row)
        by_par[p].append(i)

    out3_rows: list = [None] * len(rows_l3)  # type: list[list[str]]

    for par, idxs in by_par.items():
        l1_list = l1s_for_l2.get(par, [])

        if not l1_list:
            # parent column is a level-1 name (L3 direct under e.g. Diagnostik)
            l1n = par
            parent_xid = categ_xid("L1", ROOT, l1n)
            for i in idxs:
                c, _p = _pair(rows_l3[i])
                ch_xid = categ_xid("L3uL1", ROOT, l1n, c)
                out3_rows[i] = [ch_xid, c, parent_xid]
            continue

        if len(l1_list) == 1:
            l1n = l1_list[0]
            parent_xid = categ_xid("L2", ROOT, l1n, par)
            for i in idxs:
                c, _p = _pair(rows_l3[i])
                ch_xid = categ_xid("L3", ROOT, l1n, par, c)
                out3_rows[i] = [ch_xid, c, parent_xid]
            continue

        k = len(l1_list)
        n = len(idxs)
        if n % k != 0:
            raise SystemExit(
                f"level3 parent {par!r}: {n} rows, {k} L1 options — check master CSV"
            )
        g = n // k
        for b in range(k):
            l1n = l1_list[b]
            parent_xid = categ_xid("L2", ROOT, l1n, par)
            for j in range(g):
                i = idxs[b * g + j]
                c, _p = _pair(rows_l3[i])
                ch_xid = categ_xid("L3", ROOT, l1n, par, c)
                out3_rows[i] = [ch_xid, c, parent_xid]

    with open(out3, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "parent_id/id"])
        for row in out3_rows:
            w.writerow(row)

    print(
        f"Wrote {out1}, {out2}, {out3} "
        f"({len(rows_l1)}, {len(rows_l2)}, {len(rows_l3)} rows). "
        "Map id → External id, name → Name, parent_id/id → Parent Category."
    )


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, MASTER)
    rebuild_from_file(path)


if __name__ == "__main__":
    main()
