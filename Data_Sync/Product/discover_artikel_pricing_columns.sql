/*
 * 在 KHK 中找「可当作售价 / 进价」的列、以及可能存价目的表/视图
 * ------------------------------------------------
 * 在 SSMS 中**整文件执行**（F5）：
 *   1)–3)  KHKArtikel / 供应商子表 上的价相关列
 *   4)–5)  名含 Preis/VK/Listen… 的**用户表/视图**（主售价常在子表/价目表，不在 KHKArtikel 行上）
 *   6)     以 KHKArtikel 为父表的外键，便于跟到价目/条件表
 * 在 export_artikel_sage_mssql.sql 为 [VK1_Preis] 映真实列时，右端列名须仍为 [VK1_Preis]。
 */
SET NOCOUNT ON;
USE [methatec];  /* 与 export_artikel 一致，改为你的库名 */
GO

PRINT N'-- 1) 列名含 Preis / VK / EK / Netto / Brutto / Betrag / Kosten（大小写不敏感）';
SELECT
    c.ORDINAL_POSITION,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE
    c.TABLE_SCHEMA = N'dbo'
    AND c.TABLE_NAME = N'KHKArtikel'
    AND (
        UPPER(c.COLUMN_NAME) LIKE N'%PREIS%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%VK%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%EK%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%NETTO%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%BRUTTO%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%BETRAG%'
        OR UPPER(c.COLUMN_NAME) LIKE N'%KOST%'
    )
ORDER BY c.ORDINAL_POSITION;
GO

PRINT N'-- 2) 所有货币/小数字段（在 KHKArtikel 中，常含价或数量，需人工判断列含义）';
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.NUMERIC_PRECISION,
    c.NUMERIC_SCALE
FROM INFORMATION_SCHEMA.COLUMNS AS c
WHERE
    c.TABLE_SCHEMA = N'dbo'
    AND c.TABLE_NAME = N'KHKArtikel'
    AND c.DATA_TYPE IN (N'decimal', N'numeric', N'money', N'smallmoney', N'float', N'real')
ORDER BY c.COLUMN_NAME;
GO

PRINT N'-- 3) 进价常在供应商子表；若有 Einzelpreis 可做成本参考（一物料多行需自行聚合/取 MIN）';
IF OBJECT_ID(N'[dbo].[KHKArtikelLieferant]', N'U') IS NOT NULL
BEGIN
    SELECT
        c.COLUMN_NAME,
        c.DATA_TYPE
    FROM INFORMATION_SCHEMA.COLUMNS AS c
    WHERE
        c.TABLE_SCHEMA = N'dbo'
        AND c.TABLE_NAME = N'KHKArtikelLieferant'
        AND (
            UPPER(c.COLUMN_NAME) LIKE N'%PREIS%'
            OR UPPER(c.COLUMN_NAME) LIKE N'%EINZEL%'
        )
    ORDER BY c.ORDINAL_POSITION;
END
ELSE
    SELECT N'[dbo].[KHKArtikelLieferant] 不存在' AS [msg];
GO

PRINT N'-- 4) 用户表：表名含 Preis / VK / Listen / Kondition / Verkaufs 等（价目/销售常在此，不在主表行）';
SELECT
    t.[TABLE_SCHEMA],
    t.[TABLE_NAME]
FROM [INFORMATION_SCHEMA].[TABLES] AS t
WHERE
    t.[TABLE_TYPE] = N'BASE TABLE'
    AND t.[TABLE_SCHEMA] = N'dbo'
    AND (
        t.[TABLE_NAME] LIKE N'%Preis%'
        OR t.[TABLE_NAME] LIKE N'%Kondition%'
        OR t.[TABLE_NAME] LIKE N'KHK%VK%'
        OR t.[TABLE_NAME] LIKE N'%Verkaufs%'
        OR t.[TABLE_NAME] LIKE N'%Vertrieb%'
        OR t.[TABLE_NAME] LIKE N'%Listen%'
    )
ORDER BY t.[TABLE_NAME];
GO

PRINT N'-- 5) 同条件筛选视图（若有）';
SELECT
    t.[TABLE_SCHEMA],
    t.[TABLE_NAME]
FROM [INFORMATION_SCHEMA].[VIEWS] AS t
WHERE
    t.[TABLE_SCHEMA] = N'dbo'
    AND (
        t.[TABLE_NAME] LIKE N'%Preis%'
        OR t.[TABLE_NAME] LIKE N'%Kondition%'
        OR t.[TABLE_NAME] LIKE N'KHK%VK%'
        OR t.[TABLE_NAME] LIKE N'%Verkaufs%'
        OR t.[TABLE_NAME] LIKE N'%Vertrieb%'
        OR t.[TABLE_NAME] LIKE N'%Listen%'
    )
ORDER BY t.[TABLE_NAME];
GO

PRINT N'-- 6) 外键：KHKArtikel 为父表或子表时关联到的表（价目/条件/供应关系等）';
SELECT
    sch_p.[name] AS [parent_schema],
    pt.[name] AS [parent_table],
    pc.[name] AS [parent_column],
    sch_r.[name] AS [referenced_schema],
    rt.[name] AS [referenced_table],
    rc.[name] AS [referenced_column]
FROM [sys].[foreign_keys] AS f
INNER JOIN [sys].[foreign_key_columns] AS fkc
    ON f.[object_id] = fkc.[constraint_object_id]
INNER JOIN [sys].[tables] AS pt
    ON f.[parent_object_id] = pt.[object_id]
INNER JOIN [sys].[schemas] AS sch_p
    ON pt.[schema_id] = sch_p.[schema_id]
INNER JOIN [sys].[columns] AS pc
    ON
        fkc.[parent_object_id] = pc.[object_id]
        AND fkc.[parent_column_id] = pc.[column_id]
INNER JOIN [sys].[tables] AS rt
    ON f.[referenced_object_id] = rt.[object_id]
INNER JOIN [sys].[schemas] AS sch_r
    ON rt.[schema_id] = sch_r.[schema_id]
INNER JOIN [sys].[columns] AS rc
    ON
        fkc.[referenced_object_id] = rc.[object_id]
        AND fkc.[referenced_column_id] = rc.[column_id]
WHERE
    sch_p.[name] = N'dbo'
    AND sch_r.[name] = N'dbo'
    AND (pt.[name] = N'KHKArtikel' OR rt.[name] = N'KHKArtikel')
ORDER BY
    pt.[name], pc.[name], rt.[name];
GO
