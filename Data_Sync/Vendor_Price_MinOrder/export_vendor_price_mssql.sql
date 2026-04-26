/*
 * Sage / KHK — 供应商进价 + 最小订货量（KHKArtikel → KHKArtikelLieferant）
 * ---------------------------------------------------------------------------
 * 用途：为 Odoo `product.supplierinfo`（及 vendor_price_to_odoo.py）准备数据。
 * 一料多商：每个 (物料, 供应商) 一行，无聚合；多供应商 = 多行（INNER JOIN 自然产生）。
 * 列名与 vendor_price_to_odoo.py 一致：Vendor_ID, Product_Number, Product_Name, Vendor_Product_Code,
 *   UoM(→Odoo UoM 名称 e.g. Units), Purchase_Price, Min_Order_Qty
 * [Vendor_Product_Code]：供应商侧物料/订货号，多数为 v.[Bestellnummer]；无则 207 时查 INFORMATION_SCHEMA 改列名。
 *
 * 若报 207 无效列名，核对：
 *   SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
 *   WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = N'KHKArtikelLieferant' ORDER BY ORDINAL_POSITION;
 * Mindestbestellmenge 若不存在，可改 ISNULL(列名, 0) 或改为 CAST(0 AS decimal(19,4)) AS [Min_Order_Qty]。
 *
 * 导出：SSMS 结果网格 → 存为 `Vendor_Price_MinOrder.xlsx`（与 Python 的 INPUT_FILE 同列名），
 * 或 CSV 用 Excel 打开后另存为 xlsx。然后：python3 vendor_price_to_odoo.py
 */
SET NOCOUNT ON;

USE [methatec];  /* 改为你的库名 */
GO

SELECT
    LTRIM(RTRIM(CAST(a.[Artikelnummer] AS nvarchar(80))))  AS [Product_Number],
    LTRIM(RTRIM(CAST(a.[Matchcode] AS nvarchar(500))))     AS [Product_Name],
    LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))       AS [Vendor_ID],
    LTRIM(RTRIM(CAST(
        v.[Bestellnummer] AS nvarchar(120)
    ))) AS [Vendor_Product_Code],
    /* 与物料基本计量单位一致；Odoo 价目行必填 product_uom_id，Python 将 Stk 等映成 Units 等。若无列则 207：CAST(N'Stk' AS nvarchar(20)) AS [UoM] */
    LTRIM(RTRIM(CAST(a.[Basismengeneinheit] AS nvarchar(40))))  AS [UoM],
    CAST(v.[Einzelpreis] AS decimal(19, 4))                 AS [Purchase_Price],
    CAST(
        ISNULL(v.[Mindestbestellmenge], 0) AS decimal(19, 4)
    ) AS [Min_Order_Qty]
FROM [dbo].[KHKArtikel] AS a
INNER JOIN [dbo].[KHKArtikelLieferant] AS v
    ON v.[Mandant] = a.[Mandant]
    AND v.[Artikelnummer] = a.[Artikelnummer]
WHERE
    a.[Mandant] = 1
    AND NULLIF(LTRIM(RTRIM(CAST(a.[Artikelnummer] AS nvarchar(80)))), N'') IS NOT NULL
    AND NULLIF(LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))), N'') IS NOT NULL
    AND LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
    AND v.[Einzelpreis] IS NOT NULL
    AND v.[Einzelpreis] > 0
    /* 若需排除逻辑删除/停用供应商行，在核对列名后取消注释，例如:
       AND ISNULL(v.[Geloescht], 0) = 0
    */
ORDER BY
    a.[Artikelnummer] ASC,
    v.[Lieferant] ASC,
    v.[Einzelpreis] ASC;
GO

/*
 * -- 若 KHK 中同一 (Mandant, Artikel, Lieferant) 与同一 Einzelpreis 出现重复行，可用下面**替代**主 SELECT
 * -- 在 SSMS 试跑，确认不合并掉你需要的「多价阶段」行（多 MOQ/多价时勿用全 group）。
 *
 * SELECT
 *     s.[Product_Number],
 *     s.[Product_Name],
 *     s.[Vendor_ID],
 *     s.[Purchase_Price],
 *     s.[Min_Order_Qty]
 * FROM (
 *     SELECT
 *         LTRIM(RTRIM(CAST(a.[Artikelnummer] AS nvarchar(80))))  AS [Product_Number],
 *         LTRIM(RTRIM(CAST(a.[Matchcode] AS nvarchar(500))))   AS [Product_Name],
 *         LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))     AS [Vendor_ID],
 *         LTRIM(RTRIM(CAST(v.[Bestellnummer] AS nvarchar(120)))) AS [Vendor_Product_Code],
 *         LTRIM(RTRIM(CAST(a.[Basismengeneinheit] AS nvarchar(40))))  AS [UoM],
 *         CAST(v.[Einzelpreis] AS decimal(19, 4))              AS [Purchase_Price],
 *         CAST(ISNULL(v.[Mindestbestellmenge], 0) AS decimal(19, 4)) AS [Min_Order_Qty],
 *         ROW_NUMBER() OVER (
 *             PARTITION BY a.[Mandant], a.[Artikelnummer], v.[Lieferant], v.[Einzelpreis]
 *             ORDER BY (SELECT 0)
 *         ) AS [rn]
 *     FROM [dbo].[KHKArtikel] AS a
 *     INNER JOIN [dbo].[KHKArtikelLieferant] AS v
 *         ON v.[Mandant] = a.[Mandant] AND v.[Artikelnummer] = a.[Artikelnummer]
 *     WHERE
 *         a.[Mandant] = 1
 *         AND NULLIF(LTRIM(RTRIM(CAST(a.[Artikelnummer] AS nvarchar(80)))), N'') IS NOT NULL
 *         AND NULLIF(LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))), N'') IS NOT NULL
 *         AND v.[Einzelpreis] > 0
 * ) AS s
 * WHERE s.[rn] = 1
 * ORDER BY s.[Product_Number], s.[Vendor_ID], s.[Purchase_Price];
 * GO
 */
