/*
 * Sage / KHK — 产品主数据 (KHKArtikel) MSSQL 导出
 * ------------------------------------------------
 * 与 Data_Sync/Product/Product.py、Vendor_Price 中已用列名对齐。
 * 若报 207 或主表上无目标价列，执行 `discover_artikel_pricing_columns.sql` 全文（1–6 段）：
 *   1–2) KHKArtikel 价相关列；3) 供应商进价；4–5) 价目类**表/视图**名；6) 与 KHKArtikel 相关的**外键**。
 * 再按需改本脚本或 JOIN 价目表。亦可：
 *   SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
 *   WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'KHKArtikel' ORDER BY ORDINAL_POSITION;
 *
 * 导出给 Odoo：default_code, name, VK1_Preis(→list_price), EK0_Preis(→standard_price), 分类, UoM…
 * Product.py 会识别别名列 VK1_Preis、EK0_Preis。
 *
 * 售价 [VK1_Preis]（避免 GrundpreisBasis 全 1.0 的假「单价」）：
 *   逻辑：先取 CAST(GrundpreisBasis)。若 = 1.0（多数字库表示「计价基数/倍率」）则改用与进价相同的最小供应商进价 e0；否则用 GrundpreisBasis。
 *   若 INFORMATION_SCHEMA 中有真实销售列（如 StammVK0、VK0、NettoVK0），可在 SELECT 里把下式整段换为
 *   COALESCE( CAST(a.[你的售价列] AS decimal(19,4)), 下面 CASE … END ) AS [VK1_Preis]
 * 进价 [EK0_Preis]：KHKArtikelLieferant.Einzelpreis 的最小正价（与 e0 相同表达式，见 OUTER APPLY）。
 * Product.py 仍可用 ODOO_LIST_PRICE_NO_EK0_FALLBACK=1 关闭用进价补全（若 CSV 中 VK1 已与 SQL 一致则通常可关）。
 */

SET NOCOUNT ON;

USE [methatec];  /* 改为你的库名 */
GO

/* ========= 主数据：KHKArtikel + 品名分类（KHKArtikelgruppen）========= */
SELECT
    a.[Artikelnummer]     AS [Artikelnummer],           -- 物料号 = Odoo default_code
    a.[Matchcode]         AS [Matchcode],               -- 短名/搜索码
    a.[Mandant]            AS [Mandant],

    a.[Artikelgruppe]     AS [Artikelgruppe],           -- 分类编码（对 Odoo 内部分类）
    g.[Bezeichnung]       AS [Artikelgruppe_Bezeichnung],  -- 分类显示名 -> Odoo 产品分类名

    /* 计量 */
    a.[Basismengeneinheit] AS [Basismengeneinheit],

    /* 价格：Sachkonto* 为总账科目(文本)。售价：GrundpreisBasis=1 时改用最小进价 e0，否则用 Grund（见文件头；合法单价确为 1€ 时请在 KHK 用专用价列并改下式第一分支）。 */
    (
        CASE
            WHEN CAST(a.[GrundpreisBasis] AS decimal(19, 4)) = CAST(1.0 AS decimal(19, 4)) THEN
                COALESCE(e0.[MinEK0], CAST(1.0 AS decimal(19, 4)))
            ELSE
                CAST(a.[GrundpreisBasis] AS decimal(19, 4))
        END
    ) AS [VK1_Preis],
    e0.[MinEK0] AS [EK0_Preis]

    /* 其他字段（在上一行 EK0_Preis 后加英文逗号再取消注释或新增一行）:
    , a.[Aktiv]  AS [Aktiv] */
    /* , a.[Verkauf] AS [Verkauf] */
    /* , a.[Beschaffung] AS [Beschaffung] */
    /* , a.[Text] AS [Langtext] */
    /* , a.[EAN] AS [EAN] */
    /* , a.[USER_ManusLfdNr] AS [ManusLfdNr] */
FROM [dbo].[KHKArtikel] AS a
LEFT JOIN [dbo].[KHKArtikelgruppen] AS g
    ON  g.[Mandant]         = a.[Mandant]
    AND g.[Artikelgruppe]  = a.[Artikelgruppe]
OUTER APPLY (
    /* 每物料一条聚合；无供应关系时 MinEK0 为 NULL */
    SELECT
        MIN(CAST(v2.[Einzelpreis] AS decimal(19, 4))) AS [MinEK0]
    FROM [dbo].[KHKArtikelLieferant] AS v2
    WHERE
        v2.[Mandant] = a.[Mandant]
        AND v2.[Artikelnummer] = a.[Artikelnummer]
        AND v2.[Einzelpreis] IS NOT NULL
        AND v2.[Einzelpreis] > 0
) AS e0
WHERE
    a.[Mandant] = 1
    -- AND ISNULL(a.[Geloescht], 0) = 0   -- 若有删除标记可启用
    AND NULLIF(LTRIM(RTRIM(a.[Artikelnummer])), '') IS NOT NULL
ORDER BY
    a.[Artikelnummer];
GO

/*
 * -- 二、变体/规格（如库中有 KHKArtikelVarianten，列名用 INFORMATION_SCHEMA 核对后使用）
 * SELECT
 *   v.*,
 *   a.[Matchcode] AS [Hauptartikel_Matchcode]
 * FROM [dbo].[KHKArtikelVarianten] v
 * INNER JOIN [dbo].[KHKArtikel] a
 *   ON a.[Mandant] = v.[Mandant] AND a.[Artikelnummer] = v.[Hauptartikelnummer]
 * WHERE a.[Mandant] = 1;
 * GO
 */

/*
 * -- 三、列名速查
 * -- 3a 全表
 * SELECT COLUMN_NAME, DATA_TYPE
 * FROM INFORMATION_SCHEMA.COLUMNS
 * WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME IN ('KHKArtikel', 'KHKArtikelgruppen', 'KHKArtikelVarianten')
 * ORDER BY TABLE_NAME, ORDINAL_POSITION;
 * GO
 *
 * -- 3b 只查售价/进价可能字段（在 KHKArtikel 上搜 VK / EK / Preis）
 * SELECT COLUMN_NAME, DATA_TYPE
 * FROM INFORMATION_SCHEMA.COLUMNS
 * WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'KHKArtikel'
 *   AND (
 *         COLUMN_NAME LIKE '%VK%'  OR COLUMN_NAME LIKE '%vk%'
 *      OR COLUMN_NAME LIKE '%EK%'  OR COLUMN_NAME LIKE '%ek%'
 *      OR COLUMN_NAME LIKE '%Preis%'
 *      OR COLUMN_NAME LIKE '%preis%'
 *     )
 * ORDER BY ORDINAL_POSITION;
 * GO
 *
 * 若主 SELECT 中 a.[VK1] 或 a.[EK0] 报 207，可改试（只保留**一行**售价、一行**进价**并 AS 为 VK1_Preis / EK0_Preis）:
 *   销售: a.[A_VK0] / a.[VK0] / a.[N_VK0] / a.[G_VK0] 等
 *   进价: a.[A_EK0] / a.[Stamm_EK0] / a.[Basis_EK] 等
 * 主价若在子表/价目表，见同目录 `discover_artikel_pricing_columns.sql` 第 4–6 段后在此 SELECT 中 LEFT JOIN 并选金额列 AS [VK1_Preis]。
 */
