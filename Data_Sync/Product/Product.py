from __future__ import annotations

import os
import re
import sys
import unicodedata
from typing import Any, Dict, Optional

import pandas as pd

# 输入：SSMS/ Sage 导出的产品 CSV（与 export_artikel_sage_mssql 列名一致，或老版分号+德文列名）
_INPUT_DIR = os.path.dirname(os.path.abspath(__file__))
# 同 export_artikel 列名；ProductCategory/product_category.csv = KHKArtikelgruppen 与 gen_product_category 一致
INPUT_FILE = os.path.join(_INPUT_DIR, "Artikel.csv")
OUTPUT_FILE = os.path.join(_INPUT_DIR, "Odoo_Products_Import.csv")
CATEGORY_MASTER_CSV = os.path.normpath(
    os.path.join(_INPUT_DIR, "..", "ProductCategory", "product_category.csv")
)
_PRODUCT_CATEGORY_DIR = os.path.normpath(
    os.path.join(_INPUT_DIR, "..", "ProductCategory")
)
# product.template 的 type：多数库只有 consu + service。输出 ``product`` 会报 “not found in selection”。
# Odoo 17+ 若需“可库存/ Storable”，且库里确有该选项，可：ODOO_PRODUCT_TYPE_PHYSICAL=product python3 Product.py
_PHYSICAL_TYPE = os.environ.get("ODOO_PRODUCT_TYPE_PHYSICAL", "consu").strip() or "consu"
# KHK 虚拟组 Dummy 不在 product_category 中时：优先用 ODOO_CATEG_XID_FOR_DUMMY，否则用下面编码对应分类的 xid（默认同 Sonstiges = U）
_CATEG_XID_FOR_DUMMY = os.environ.get("ODOO_CATEG_XID_FOR_DUMMY", "").strip()
_DUMMY_FALLBACK_ARTIKELGRUPPE = os.environ.get(
    "ODOO_DUMMY_FALLBACK_ARTIKELGRUPPE", "U"
).strip() or "U"
# KHK 的 VK1_Preis(GrundpreisBasis) 常为 0/1 而非欧元价时，默认用进价(standard_price)写回 list_price；关：ODOO_LIST_PRICE_NO_EK0_FALLBACK=1
def _list_price_ek0_fallback_enabled() -> bool:
    v = os.environ.get("ODOO_LIST_PRICE_NO_EK0_FALLBACK", "").lower()
    if v in ("1", "true", "yes"):
        return False
    return True


# 默认不导出 KHK 占位/Excel 错行；置 PRODUCT_IMPORT_NO_FILTER=1 则全部保留；置 PRODUCT_IMPORT_EXCLUDE_DEFAULT_CODES= 可只按品名规则筛
def _excluded_default_codes() -> set[str]:
    raw = os.environ.get("PRODUCT_IMPORT_EXCLUDE_DEFAULT_CODES", "4000,5000")
    if not raw.strip():
        return set()
    return {x.strip() for x in raw.split(",") if x.strip()}


def _load_categ_xid_by_code() -> Optional[Dict[str, str]]:
    """Artikelgruppe 编码 -> ``__import__.pc_*``，与分层的 category CSV 相同算法；无主数据文件则返回 None。"""
    if not os.path.exists(CATEGORY_MASTER_CSV):
        return None
    if _PRODUCT_CATEGORY_DIR not in sys.path:
        sys.path.insert(0, _PRODUCT_CATEGORY_DIR)
    from gen_product_category import build_artikelgruppe_to_xid, read_input

    master = read_input(CATEGORY_MASTER_CSV)
    return build_artikelgruppe_to_xid(master)


def _categ_xid_by_casefold(m: Dict[str, str]) -> Dict[str, str]:
    """主数据里 Artikelgruppe 常见大小写 (Rb) 与物料表导出 (rb) 不一致。"""
    return {str(k).strip().casefold(): v for k, v in m.items()}


def _read_csv_flexible(path: str) -> pd.DataFrame:
    # Comma first: ";" on comma-separated data yields a single fake column
    # "Artikelnummer,Matchcode,..." and breaks column lookup.
    # 德国 KHK/SSMS 常导出 Windows-1252；UTF-8 失败后应优先 cp1252，再 ISO-8859-1
    # （否则 0x8A 在 Latin-1 下成 U+008A 控制符，在 Odoo 中显示为方块/乱码）。
    for sep in (",", ";"):
        for enc in ("utf-8-sig", "utf-8", "cp1252", "ISO-8859-1"):
            try:
                df = pd.read_csv(path, sep=sep, encoding=enc, dtype=str)
                if len(df.columns) < 1:
                    continue
                df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]
                if len(df.columns) == 1 and "," in df.columns[0] and sep == ";":
                    continue
                return df
            except Exception:
                continue
    raise FileNotFoundError(
        f"Could not read {path!r} with common sep/enc (try , or ;, utf-8 or latin-1)"
    )


def _repair_german_mojibake(s: str) -> str:
    """
    修正 Sage/KHK/Excel 导出的常见错误：
    - Latin-1 读入时 C1 控制符 U+008A 多对应漏掉的 ä
    - cp1252 下误显示为 Š（U+0160），本库数据多为 intended ä/Ä
    - UTF-8 被误作 Latin-1 保存时的“Ã¼” 类双编（尽力修复）
    """
    if s is None:
        return ""
    t = s
    if "Ã" in t or (len(t) > 1 and "Â" in t):
        try:
            fix = t.encode("latin-1", errors="strict").decode("utf-8", errors="strict")
            t = fix
        except (UnicodeDecodeError, UnicodeError):
            pass
    t = t.replace("\u008a", "ä")
    if os.environ.get("KHK_NO_SH_CARON_FIX", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        t = t.replace("Š", "ä").replace("š", "ä")
    return unicodedata.normalize("NFC", t)


def _cell_repair(v: Any) -> Any:
    try:
        if pd.isna(v):
            return v
    except (TypeError, ValueError):
        return v
    s = str(v)
    if s in ("", "nan", "None"):
        return s
    return _repair_german_mojibake(s)


def _repair_dataframe_text(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == object:
            out[c] = out[c].map(_cell_repair)
    return out


def _apply_import_row_filter(df: pd.DataFrame) -> pd.DataFrame:
    """排除 Excel #NAME?、-Dummy- 等占位行及（默认）物料号 4000、5000。"""
    if os.environ.get("PRODUCT_IMPORT_NO_FILTER", "").lower() in (
        "1",
        "true",
        "yes",
    ):
        return df
    art = _col(df, "Artikelnummer", "Product_Number")
    if art is None:
        return df
    mc = _col(df, "Matchcode", "Matchcode Artikel")
    n0 = len(df)
    a = art.astype(str).str.strip()
    excl = _excluded_default_codes()
    drop = a.isin(excl) if excl else pd.Series([False] * n0, index=df.index)
    if mc is not None:
        m = mc.fillna("").astype(str).str.strip().str.casefold()
        drop = drop | m.isin(("#name?", "-dummy-"))
    out = df.loc[~drop].reset_index(drop=True)
    n_drop = n0 - len(out)
    if n_drop:
        print(
            f"  Excluded {n_drop} placeholder / error row(s) "
            f"(#NAME? / -Dummy- / default_code in exclude list; "
            f"PRODUCT_IMPORT_NO_FILTER=1 to disable)."
        )
    return out


def _col(df, *candidates):
    for c in candidates:
        if c in df.columns:
            return df[c]
    return None


def _col_with_name(df, *candidates) -> tuple[Optional[str], Any]:
    for c in candidates:
        if c in df.columns:
            return c, df[c]
    return None, None


def _de_number_one(x: Any) -> float:
    """德文/Excel 数：'12,5'、'1.234,56'、空；写 CSV 用点作 Odoo 小数点。"""
    if x is None:
        return 0.0
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            if pd.isna(x):
                return 0.0
        except (TypeError, ValueError):
            pass
        return round(float(x), 6)
    try:
        if pd.isna(x):
            return 0.0
    except (TypeError, ValueError):
        return 0.0
    s = str(x).strip()
    if s in ("", "nan", "None", "-", "—"):
        return 0.0
    s = s.replace(" ", "").replace("\xa0", "")
    s = s.replace("€", "").replace("EUR", "", 1)
    if re.fullmatch(r"-?\d+(\.\d+)?(E-?\d+)?", s, re.I):
        return round(float(s), 6)
    if "," in s and "." in s:
        if s.rindex(",") > s.rindex("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(",") == 1 and "." not in s:
        s = s.replace(",", ".")
    elif s.count(".") == 1 and "," not in s and re.search(r"\d\.\d{3}$", s):
        s = s.replace(".", "")
    try:
        return round(float(s), 6)
    except (ValueError, TypeError):
        return 0.0


def _de_number_series(series: pd.Series) -> pd.Series:
    return series.map(_de_number_one).astype("float64")


def _apply_list_price_ek0_fallback(odoo_df: pd.DataFrame) -> pd.DataFrame:
    """
    当 list_price 为 0 或 1（常见于 KHK GrundpreisBasis=1）且进价更高时，用进价列填销售价（默认开）。
    避免误伤真·1 欧元品：仅当 进价 > 售价 且 售价 ≤1。
    """
    if "list_price" not in odoo_df.columns or "standard_price" not in odoo_df.columns:
        return odoo_df
    lp = odoo_df["list_price"]
    sp = odoo_df["standard_price"]
    trivial = (lp <= 1.0) & (lp >= 0.0) & (sp > lp)
    if not bool(trivial.any()):
        return odoo_df
    out = odoo_df.copy()
    out.loc[trivial, "list_price"] = out.loc[trivial, "standard_price"]
    n = int(trivial.sum())
    print(
        f"  list_price: filled {n} row(s) from standard_price (sale was 0/1 and cost higher; default). "
        f"To keep raw KHK list_price: ODOO_LIST_PRICE_NO_EK0_FALLBACK=1"
    )
    return out


# Sage 简称 -> Odoo 计量单位**名称**（与库存/设置里已创建的一致）
UOM_MAP = {
    "Stk": "Units",
    "Ktn": "Units",
    "Ktn.": "Units",
    "Pck": "Units",
    "Pck.": "Units",
}


def _uom_series(series):
    s = series.fillna("Stk").astype(str).str.strip()
    return s.map(lambda x: UOM_MAP.get(x, x if x else "Units"))


def _bool_series_ja(s, n, default_true=True):
    """Ja/Nein -> bool；列缺失时整列 default_true。"""
    if s is None:
        return pd.Series([default_true] * n, dtype=bool)
    x = s.fillna("Nein" if not default_true else "Ja")
    m = {
        "Ja": True, "Nein": False, "ja": True, "nein": False, "1": True, "0": False,
    }
    return x.map(lambda v: m.get(str(v).strip(), default_true))


def _type_series(df):
    n = len(df)
    vk = _col(df, "Verkauf", "verkauf")
    be = _col(df, "Beschaffung", "Einkauf")
    if vk is None and be is None:
        return pd.Series([_PHYSICAL_TYPE] * n, dtype=object, index=df.index)
    out = []
    for i in range(n):
        ok = False
        if vk is not None and str(vk.iloc[i]).strip().lower() in ("ja", "1", "true", "wahr"):
            ok = True
        if be is not None and str(be.iloc[i]).strip().lower() in ("ja", "1", "true", "wahr"):
            ok = True
        out.append(_PHYSICAL_TYPE if ok else "service")
    return pd.Series(out, dtype=object, index=df.index)


def build_odoo_frame(
    df: pd.DataFrame, categ_xid_by_code: Optional[Dict[str, str]] = None
) -> pd.DataFrame:
    n = len(df)
    art = _col(df, "Artikelnummer", "Product_Number")
    if art is None:
        raise KeyError("Need Artikelnummer (or Product_Number) in CSV")
    name = _col(df, "Matchcode Artikel", "Matchcode")
    if name is None:
        raise KeyError("Need Matchcode (or Matchcode Artikel) in CSV")
    ag = _col(df, "Artikelgruppe")
    categ = _col(df, "Artikelgruppe_Bezeichnung", "Kategorie", "categ_id")
    if categ is None:
        categ = pd.Series([""] * n, index=df.index)
    uom_src = _col(df, "Basismengeneinheit_Wert", "Basismengeneinheit", "Mengeneinheit")

    man = _col(df, "ManusLfdNr", "USER_ManusLfdNr")
    if man is None:
        man = art.astype(str)

    aktiv = _col(df, "Aktiv", "aktiv")
    ver = _col(df, "Verkauf", "verkauf")
    bes = _col(df, "Beschaffung", "Einkauf")

    active = _bool_series_ja(aktiv, n, default_true=True)
    sale_ok = _bool_series_ja(ver, n, default_true=True)
    purchase_ok = _bool_series_ja(bes, n, default_true=True)
    ptype = _type_series(df)

    u1 = _uom_series(
        uom_src if uom_src is not None else pd.Series(["Stk"] * n, index=df.index)
    )

    if categ_xid_by_code is not None and ag is not None:
        cf = _categ_xid_by_casefold(categ_xid_by_code)
        keys = ag.fillna("").map(lambda x: str(x).strip())
        categ_id_id = keys.map(
            lambda k: (
                cf.get(k.casefold(), "")
                if k and str(k) not in ("nan", "None")
                else ""
            )
        )
        if ag is not None:
            categ_id_id = categ_id_id.copy()
            is_dummy = ag.fillna("").map(
                lambda x: str(x).strip().casefold() == "dummy"
            )
            need_dummy = (
                categ_id_id.fillna("").astype(str).str.strip() == ""
            ) & is_dummy
            if _CATEG_XID_FOR_DUMMY:
                categ_id_id.loc[need_dummy] = _CATEG_XID_FOR_DUMMY
            else:
                xid_fb = cf.get(_DUMMY_FALLBACK_ARTIKELGRUPPE.casefold(), "")
                if xid_fb:
                    categ_id_id.loc[need_dummy] = xid_fb
        categ_cols: dict[str, Any] = {"categ_id/id": categ_id_id}
    else:
        categ_cols = {
            "categ_id": categ.astype(str) if not isinstance(categ, str) else categ
        }

    lp_n, lp = _col_with_name(
        df,
        "list_price",
        "List_Price",
        "VK1_Preis",
        "VK0",
        "VK1",  # 列名同 Excel 时无 _Preis 后缀
        "Verkaufs_Preis1",
        "StammVK0",
        "NettoVK0",
        "BruttoVK0",
        "A_VK0",
        "Verkaufspreis",
        "VK_Preis",
        "Listenpreis",
        "Listenverkaufspreis",
    )
    sp_n, sp = _col_with_name(
        df,
        "standard_price",
        "EK0_Preis",
        "Stamm_EK0",
        "EK_Preis",
        "Einkaufs_Preis0",
        "EK0",
        "A_EK0",
        "Einkaufspreis",
    )

    row: dict[str, Any] = {
        "ManusLfdNr": man,
        "default_code": art.astype(str).str.strip(),
        "name": name.astype(str),
    }
    if lp is not None:
        row["list_price"] = _de_number_series(lp)
    if sp is not None:
        row["standard_price"] = _de_number_series(sp)
    row.update(categ_cols)
    row["uom_id"] = u1
    row["uom_po_id"] = u1
    row["active"] = active
    row["sale_ok"] = sale_ok
    row["purchase_ok"] = purchase_ok
    row["type"] = ptype

    if lp_n:
        print(f"  list_price (销售价) <- {lp_n!r}")
    else:
        print("  list_price: (no source column) — 输出中无此列，Odoo 将不会从本文件更新销售价；请检查 Artikel 是否含 VK1_Preis 等列。")
    if sp_n:
        print(f"  standard_price (成本) <- {sp_n!r}")

    return pd.DataFrame(row)


def main():
    if not os.path.exists(INPUT_FILE):
        print(f"ERROR: {INPUT_FILE} not found.")
        return
    df = _read_csv_flexible(INPUT_FILE)
    df = _repair_dataframe_text(df)
    df = _apply_import_row_filter(df)
    xid_map = _load_categ_xid_by_code()
    odoo_df = build_odoo_frame(df, categ_xid_by_code=xid_map)
    if "list_price" in odoo_df.columns and "standard_price" in odoo_df.columns:
        lpv = odoo_df["list_price"]
        triv = int(((lpv <= 1.0) & (lpv >= 0.0) & (odoo_df["standard_price"] > lpv)).sum())
        if triv and not _list_price_ek0_fallback_enabled():
            print(
                f"  NOTE: {triv} row(s) have list_price 0/1 but higher cost; "
                "KHK 的 GrundpreisBasis 多非实际售价。在 MSSQL 中可将 [VK1_Preis] 改为真实销售列，或本脚本已默认用进价补全，"
                f"若不要补全可设 ODOO_LIST_PRICE_NO_EK0_FALLBACK=1。"
            )
    if _list_price_ek0_fallback_enabled():
        odoo_df = _apply_list_price_ek0_fallback(odoo_df)
    odoo_df.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")
    print(f"OK: {len(odoo_df)} products -> {OUTPUT_FILE}")
    if xid_map is not None and "categ_id/id" in odoo_df.columns:
        m = (
            odoo_df["categ_id/id"]
            .fillna("")
            .astype(str)
            .str.strip()
            == ""
        )
        miss = int(m.sum())
        if miss:
            bad = (
                odoo_df.loc[m, "default_code"]
                .astype(str)
                .head(15)
                .tolist()
            )
            extra = f" … (+{int(m.sum()) - len(bad)} more)" if int(m.sum()) > len(bad) else ""
            print(
                f"WARNING: {miss} row(s) with empty categ_id/id "
                f"({os.path.basename(CATEGORY_MASTER_CSV)} / unknown Artikelgruppe). "
                f"default_code: {', '.join(bad)}{extra}"
            )
            if miss and not _CATEG_XID_FOR_DUMMY:
                print(
                    f"  (Set ODOO_CATEG_XID_FOR_DUMMY=__import__.pc_... or "
                    f"ODOO_DUMMY_FALLBACK_ARTIKELGRUPPE=<KHK code with a known xid>.)"
                )
    elif xid_map is None:
        print(
            f"NOTE: {os.path.basename(CATEGORY_MASTER_CSV)} not found — "
            "categ_id uses display names (must exist in Odoo as category names)."
        )


if __name__ == "__main__":
    main()
