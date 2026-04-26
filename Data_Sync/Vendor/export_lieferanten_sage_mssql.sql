/*
 * Sage 100 / 离线 KHK 风格 MSSQL — 供应商（Lieferanten）主数据导出
 * ----------------------------------------------------------------
 * 使用前请按你库实际名称修改：
 *   - USE [你的数据库名];
 * 若仍报“无效列名”，在 SSMS 中执行（改表名如需要）：
 *   SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
 *   WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = 'KHKAdressen' ORDER BY ORDINAL_POSITION;
 * 下面 SELECT 只含本库中已验证存在的列；需要税号/传真等时按上句查出真实列名后自行追加。
 * 说明：
 *   - 主条件：`Gruppe = 'LIEF'` 常见为供应商地址；但 **KHKArtikelLieferant.Lieferant** 可能指向在地址表里 **Gruppe 不是 LIEF** 仍被用作供货商的编号，这类若只按 LIEF 导会**缺行**（价目里出现 70707、干净表里却没有）。
 *   - 下面对 WHERE 已加：子表里 **Lieferant** 既可能 = `USER_ManusLfdNr`，在不少库里也 = **`Adresse`（地址主键）**；只按「与 USER 同号」会仍缺 70707 这类号。
 *   - 列 [Vendor_ID] 输出为**与 KHKArtikelLieferant 中 Lieferant 一致**的编号（在能关联时），价目/ Odoo 的 `ref` 与 **export_vendor_price 的 Lieferant** 才能对上。
 *   - **目标**：导出**全部**供应商的 **[Vendor_ID] = 价目/子表 KHKArtikelLieferant 所用 Lieferant（Lieferantennummer）**；用单家（如 70707）只作**对账样例**，非单独写死。对多数行：首段子查询在 **Lieferant=USER** 或 **Lieferant 数值=地址主键 a.Adresse** 时已为正确号。
 *   - 若 **USER 与子表价目用 Lieferant 不同号** 且子表**无**行级 Adresse 列：可（A）在 **`KHKAdressen` 上找到=价目号的那一列**并在「一」内加 `v0.Lieferant = a.该列`（一次适用**所有**含该列结构的行，见「四」）；（B）在 **[liefer_map]** 的 **VALUES** 里为**每个**对不齐的 USER 加一行 **(用户号, 价目Lieferant)**（与 `export_vendor_price` 的 `Lieferant` 一致）。**`liefer_map` 无对应行**时第二段为 NULL，**`Vendor_ID` 会等于 USER**（你截图 207/111394 即此况）；勿再使用「整段空」的 CTE 除非确已用（A）解决。
 *   - 子表有某 Lieferant 在 `KHKAdressen` 的 USER/Adresse 上**对不上**时：为 KHK 断档，用「一-b」占位行或主数据里补 `KHKAdressen`；示例号仅说明场景。
 *   - 银行：并集 D/A/CH/L 后按 **有 IBAN 优先** 取 TOP 1；输出列 [IBAN] 为 `COALESCE(IBAN, Konto)` 供 Odoo 账号。若 A/CH 等表有 **IBAN 列**而本脚本的 UNION 仍写 `NULL AS IBAN`，可改为直接选 `[IBAN]`（若 207 列名无效再改回）。`KHKBankverbindungen*` 列名用 INFORMATION_SCHEMA 核对。
 *   - 条数/对账：Odoo 的 `ref` 须唯一。若 `KHKAdressen` 中多行对应同一 **USER_ManusLfdNr** 或导出的 [Vendor_ID] 相同，原查询会**多行同 ref**；**「一」内已按 [Vendor_ID] 去重**（优 LIFF，再小 Adresse_Key）。若你期望条数=地址表行数，不要合并去重版，在 SSMS 中只保留 CTE 内层 `raw` 部分自行导出（见下注释占位）。
 *   - 若行数**偏少**：子查询/EXISTS 里 `Einzelpreis > 0` 会排掉进价为 0 的供应关系，可在该脚本中**全局替换**为 `IS NOT NULL` 或 `>= 0`（依业务，慎用）。
 */

SET NOCOUNT ON;

USE [methatec];  -- 改成你的库名
GO

/* ========= 一、供应商主数据 + 一条银行行（同 Vendor_ID 去重 = Odoo 一个 ref 一行） ========= */
;WITH [liefer_map] AS (
    /* 首段 v0 未命中时：此处用 KHKAdressen.USER → 子表价目用 Lieferant。若**整段无行**或某 USER 无对应行，COALESCE 会落回 111394 这类 **USER 本身**（与价目 70707 会不一致）—— 故「对不齐」的每家都要在 VALUES 里占一行。 */
    /* 全量：在下方 VALUES 里继续 (N'用户号',N'子表Lieferant') ；**不用**本表时改为「SELECT ukey, lief FROM (VALUES (CAST(NULL as nvarchar(80)), NULL)) t(ukey,lief) WHERE 0=1」 */
    SELECT
        t.ukey,
        t.lief
    FROM (VALUES
        (N'111394', N'70707')  /* 对账用一行；**全库**把其余 USER≠价目 的也补成多行，或见「四」在 KHKAdressen 加 OR 省掉手填 */
    ) AS t (ukey, lief)
)
, [raw] AS (
SELECT
    a.[Adresse]              AS [Adresse_Key],
    /* Odoo ref：① 子表 v0 在 Lieferant=USER 或 =地址主键数值时命中 ②[liefer_map] 手填 ③ 回退 USER。 */
    COALESCE(
        (
            SELECT TOP (1)
                LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80))))
            FROM [dbo].[KHKArtikelLieferant] AS v0
            WHERE
                v0.[Mandant] = a.[Mandant]
                AND v0.[Einzelpreis] > 0
                AND v0.[Lieferant] IS NOT NULL
                AND LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
                AND (
                    LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80))))
                    OR (
                        TRY_CONVERT(BIGINT, LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))))
                        = TRY_CONVERT(BIGINT, a.[Adresse])
                    )
                    /* 在 KHKAdressen 找到与价目 Lieferant 同值的列 <Col> 后取消并改名:
                    OR LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(a.[<Col>] AS nvarchar(80))))
                    */
                )
            ORDER BY
                v0.[Einzelpreis] ASC, v0.[Lieferant] ASC
        ),
        (
            SELECT TOP (1)
                m.lief
            FROM [liefer_map] AS m
            WHERE
                m.ukey = LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80))))
        ),
        LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80))))
    ) AS [Vendor_ID],
    a.[Matchcode]           AS [Short_Name],
    COALESCE(
        NULLIF(LTRIM(RTRIM(CAST(a.[Name1] AS nvarchar(500)))), N''),
        NULLIF(LTRIM(RTRIM(CAST(a.[Matchcode] AS nvarchar(500)))), N''),
        N'—'
    ) AS [Company_Name],
    /* a.[Name2]  AS [Name2],  -- 若你库有第二名称再取消注释 */

    a.[LieferStrasse]       AS [Street],
    a.[LieferLand]          AS [Country],
    a.[LieferPLZ]           AS [Zip_Code],
    a.[LieferOrt]           AS [City],

    a.[Telefon]              AS [Phone],
    a.[EMail]                AS [Email],

    a.[Mandant]              AS [Mandant],
    a.[Gruppe]               AS [Gruppe],

    /* Odoo `bank_ids/acc_number`：有 IBAN 用 IBAN；KHK 在 A/CH/L 子表里常无 IBAN 列或列为空，用 Konto/账号回退。 */
    COALESCE(
        NULLIF(LTRIM(RTRIM(CAST(b.[IBAN] AS nvarchar(60)))), N''),
        NULLIF(LTRIM(RTRIM(CAST(b.[Konto] AS nvarchar(50)))), N'')
    ) AS [IBAN],
    b.[Swift]                AS [BIC_Swift],
    b.[Institut]            AS [Bank_Name],
    b.[Konto]                AS [Bank_Account_No]
FROM [dbo].[KHKAdressen] AS a
OUTER APPLY (
    /* 并集 D/A/CH/L 后**优先**有 IBAN 的行（原 ORDER 仅按 Institut 易先命中无 IBAN 的 A/CH，导致 IBAN 列全空） */
    SELECT TOP (1) *
    FROM (
        SELECT [Adresse], [IBAN], [Swift], [Institut], [Konto]
        FROM [dbo].[KHKBankverbindungenD]
        UNION ALL
        SELECT [Adresse], NULL AS [IBAN], [Swift], [Institut], [Konto]
        FROM [dbo].[KHKBankverbindungenA]
        UNION ALL
        SELECT [Adresse], NULL AS [IBAN], [Swift], [Institut], [Konto]
        FROM [dbo].[KHKBankverbindungenCH]
        UNION ALL
        SELECT [Adresse], NULL AS [IBAN], [Swift], [Institut], [Konto]
        FROM [dbo].[KHKBankverbindungenL]
    ) AS u
    WHERE u.[Adresse] = a.[Adresse]
    ORDER BY
        CASE
            WHEN NULLIF(LTRIM(RTRIM(CAST(u.[IBAN] AS nvarchar(60)))), N'') IS NOT NULL THEN 0
            WHEN NULLIF(LTRIM(RTRIM(CAST(u.[Konto] AS nvarchar(50)))), N'') IS NOT NULL THEN 1
            ELSE 2
        END,
        u.[Institut],
        u.[Konto]
) AS b
WHERE
    a.[Mandant] = 1
    /* 至少能写出 Vendor_ID：有 USER 或 能被子表按 Adresse 连上 */
    AND (
        NULLIF(LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80)))), N'') IS NOT NULL
        OR EXISTS (
            SELECT 1
            FROM [dbo].[KHKArtikelLieferant] AS v3
            WHERE
                v3.[Mandant] = a.[Mandant]
                AND v3.[Einzelpreis] > 0
                AND v3.[Lieferant] IS NOT NULL
                AND TRY_CONVERT(BIGINT, LTRIM(RTRIM(CAST(v3.[Lieferant] AS nvarchar(80)))))
                    = TRY_CONVERT(BIGINT, a.[Adresse])
        )
    )
    /* 主数据 LIEF，或 子表 Lieferant 与（USER 或 Adresse）对齐 */
    AND (
        a.[Gruppe] = 'LIEF'
        OR EXISTS (
            SELECT 1
            FROM [dbo].[KHKArtikelLieferant] AS v
            WHERE
                v.[Mandant] = a.[Mandant]
                AND v.[Einzelpreis] > 0
                AND v.[Lieferant] IS NOT NULL
                AND LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
                AND (
                    LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))
                    OR (
                        TRY_CONVERT(BIGINT, LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))))
                        = TRY_CONVERT(BIGINT, a.[Adresse])
                    )
                )
        )
    )
    /* 若你确定只信 Gruppe=LIEF、不要子表补全，可改回: AND a.[Gruppe] = 'LIEF' */
    -- AND a.[Geloescht] = 0   -- 若表中有“已删除”标记，可取消注释排除
)
, [z] AS (
    SELECT
        r.*,
        ROW_NUMBER() OVER (
            PARTITION BY LTRIM(RTRIM(CAST(r.[Vendor_ID] AS nvarchar(100))))
            ORDER BY
                CASE WHEN r.[Gruppe] = N'LIEF' THEN 0 ELSE 1 END,
                r.[Adresse_Key]
        ) AS [__row_one_per_ref]
    FROM
        [raw] AS r
)
SELECT
    z.[Adresse_Key],
    z.[Vendor_ID],
    z.[Short_Name],
    z.[Company_Name],
    z.[Street],
    z.[Country],
    z.[Zip_Code],
    z.[City],
    z.[Phone],
    z.[Email],
    z.[Mandant],
    z.[Gruppe],
    z.[IBAN],
    z.[BIC_Swift],
    z.[Bank_Name],
    z.[Bank_Account_No]
FROM
    [z]
WHERE
    z.[__row_one_per_ref] = 1
ORDER BY
    z.[Vendor_ID] ASC;
/* 若需「每地址一行」做审计：SELECT * FROM [raw] ORDER BY [Adresse_Key] — 将上一段 SELECT 临时改为该句（同一 CTE 需复制 raw 段） */
GO

/* ========= 一-b、孤儿 Lieferant：仅出现在 KHKArtikelLieferant、KHKAdressen 中无 USER/Adresse 能对应行（例：70707）*/
/* 与「一」列结构一致；[Company_Name] 尽量用子表 Bezeichnung1（有则作展示名+含 ref），无则占位。无 Bezeichnung1 时改 h 中列名。 */
SELECT
    CAST(NULL AS int)         AS [Adresse_Key],
    o.[Lief]                  AS [Vendor_ID],
    COALESCE(
        NULLIF(LEFT(h.[Bezeichnung1], 120), N''),
        (N'ORPH-' + o.[Lief])
    ) AS [Short_Name],
    CONCAT(
        N'[', o.[Lief], N'] ',
        COALESCE(
            NULLIF(LTRIM(RTRIM(CAST(h.[Bezeichnung1] AS nvarchar(500)))), N''),
            N'Lieferant (KHK: KHKAdressen fehlt – s. Bezeichnung1 in Tabelle / manuell pflegen)'
        )
    ) AS [Company_Name],
    CAST(NULL AS nvarchar(200))  AS [Street],
    CAST(NULL AS nvarchar(10))   AS [Country],
    CAST(NULL AS nvarchar(20))   AS [Zip_Code],
    CAST(NULL AS nvarchar(80))     AS [City],
    CAST(NULL AS nvarchar(60))  AS [Phone],
    CAST(NULL AS nvarchar(200))  AS [Email],
    1                            AS [Mandant],
    N'ORPH'                      AS [Gruppe],
    CAST(NULL AS nvarchar(50))  AS [IBAN],
    CAST(NULL AS nvarchar(20))  AS [BIC_Swift],
    CAST(NULL AS nvarchar(120))  AS [Bank_Name],
    CAST(NULL AS nvarchar(40))   AS [Bank_Account_No]
FROM (
    SELECT DISTINCT
        LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) AS [Lief]
    FROM [dbo].[KHKArtikelLieferant] AS v
    WHERE
        v.[Mandant] = 1
        AND v.[Einzelpreis] > 0
        AND v.[Lieferant] IS NOT NULL
        AND LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
        AND NOT EXISTS (
            SELECT 1
            FROM [dbo].[KHKAdressen] AS a
            WHERE
                a.[Mandant] = v.[Mandant]
                AND (
                    LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))
                    OR (
                        TRY_CONVERT(BIGINT, a.[Adresse]) = TRY_CONVERT(
                            BIGINT,
                            LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))
                        )
                    )
                )
        )
) AS o
OUTER APPLY (
    /* 任取一行有 Bezeichnung1 的供货物料行，作 Odoo 显示名参考；无则全 NULL。若报 207 列名，改为你库中实际列(如 Bemerkung) */
    SELECT TOP (1)
        v1.[Bezeichnung1] AS [Bezeichnung1]
    FROM [dbo].[KHKArtikelLieferant] AS v1
    WHERE
        v1.[Mandant] = 1
        AND LTRIM(RTRIM(CAST(v1.[Lieferant] AS nvarchar(80)))) = o.[Lief]
        AND v1.[Einzelpreis] > 0
    ORDER BY
        v1.[Artikelnummer] ASC
) AS h
ORDER BY
    o.[Lief] ASC;
GO

/*
 * ========= 二、（可选）供应商联系人 KHKAnsprechpartner =========
 * 表/列名因版本可能不同；若报“无效对象/列名”，在 SSMS 中展开该表字段后改下方 SELECT。
 * 与主数据关联键一般为 Adresse 或 Kunden/Adress-Nummer，请以你库为准。
 */
/*
SELECT
    p.[AnsprechPartner]  AS [Contact_ID],
    p.[Adresse]          AS [Adresse],                -- 对应 KHKAdressen.Adresse
    p.[Titel]            AS [Title],
    p.[Vorname]          AS [First_Name],
    p.[Name]             AS [Last_Name],
    p.[Name]             AS [Full_Name_If_Single],     -- 若仅一个姓名字段可改成实际列
    p.[Abteilung]        AS [Department],
    p.[Funktion]         AS [Job_Title],
    p.[Telefon]          AS [Phone_Direct],
    p.[Email]            AS [Email],
    p.[Bemerkung]        AS [Note]
FROM [dbo].[KHKAnsprechpartner] AS p
INNER JOIN [dbo].[KHKAdressen] AS a
    ON a.[Adresse] = p.[Adresse]
WHERE
    a.[Mandant] = 1
    AND a.[Gruppe] = 'LIEF'
ORDER BY
    p.[Adresse], p.[Name];
*/
GO

/*
 三、诊断：在 KHKAdressen 中找不到与 Lieferant 同号的 USER_ManusLfdNr 的供货编号
 将下面整段复制到新建查询窗执行，若有行则主数据缺地址或键不一致。

SELECT DISTINCT
    LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) AS [Lieferant_Only_In_Artikel],
    v.[Mandant] AS [Mandant]
FROM [dbo].[KHKArtikelLieferant] AS v
WHERE
    v.[Mandant] = 1
    AND v.[Lieferant] IS NOT NULL
    AND v.[Einzelpreis] > 0
    AND LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
    AND NOT EXISTS (
        SELECT 1
        FROM [dbo].[KHKAdressen] AS a
        WHERE
            a.[Mandant] = v.[Mandant]
            AND (
                LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))
                OR (
                    TRY_CONVERT(BIGINT, a.[Adresse]) = TRY_CONVERT(
                        BIGINT,
                        LTRIM(RTRIM(CAST(v.[Lieferant] AS nvarchar(80))))
                    )
                )
            )
    )
ORDER BY
    1, 2;
*/
GO

/*
 四、若 KHKAdressen 有列存「与价目子表 Lieferant 相同」的 Lieferantennummer，在「一」首段加 OR 可**一次**修正所有此类行，无需为每家填 liefer_map。
 1) 列清单，打开任意对账有偏差的行，看哪一列=子表价目号。
 2) 把该列名补进「一、raw」子查询： v0.Lieferant = a.<你的列名>。

-- SELECT COLUMN_NAME, DATA_TYPE
-- FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = N'KHKAdressen' ORDER BY ORDINAL_POSITION;

-- SELECT TOP (50) a.* FROM [dbo].[KHKAdressen] a WHERE a.[Mandant]=1 AND a.[Gruppe]=N'LIEF' ORDER BY a.[Adresse];
*/

/*
 五、KHKArtikelLieferant 无行级 Adresse 时，列仅有 Lieferant、Artikelnummer、Mandant、…（价目/导出以 **Lieferant** 为供应商号）。
 全库纠正路径：**四** 列 OR 优先；否则 **liefer_map** 填**全部** (USER, Lieferant) 对；**六** 可先看每家首段是否已命中。

-- SELECT COLUMN_NAME, DATA_TYPE
-- FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = N'KHKArtikelLieferant' ORDER BY ORDINAL_POSITION;

-- SELECT DISTINCT LTRIM(RTRIM(CAST([Lieferant] AS nvarchar(80)))) AS Lief
-- FROM [dbo].[KHKArtikelLieferant] WHERE [Mandant] = 1 AND [Einzelpreis] > 0;

-- 与上面结果 + KHK 地址 USER 在 Excel 里对出 (USER, Lief) 后，把多行 (N'…',N'…') 粘进「一」liefer_map 的 VALUES。
-- SELECT a.[Adresse], a.[USER_ManusLfdNr], a.[Matchcode] FROM [dbo].[KHKAdressen] a
-- WHERE a.[Mandant] = 1 AND a.[Gruppe] = N'LIEF' ORDER BY a.[Adresse];
*/
GO

/*
 六、全量对账：每个 LIEF 地址上「首段自动命中的 Lieferant」与 USER；无命中时 COALESCE 会再用 [liefer_map]、再回退 USER。
 跑完看 [vendor_from_v0]：非空则已与子表某 Lieferant 对齐；若与价目仍不符，再补 liefer_map 或「一」中 KHKAdressen 的 OR。

-- ;WITH [chk] AS (
--     SELECT
--         a.[Adresse],
--         a.[USER_ManusLfdNr],
--         a.[Matchcode],
--         (
--             SELECT TOP (1)
--                 LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80))))
--             FROM [dbo].[KHKArtikelLieferant] AS v0
--             WHERE
--                 v0.[Mandant] = a.[Mandant]
--                 AND v0.[Einzelpreis] > 0
--                 AND v0.[Lieferant] IS NOT NULL
--                 AND LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))) NOT IN (N'0', N'')
--                 AND (
--                     LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))) = LTRIM(RTRIM(CAST(a.[USER_ManusLfdNr] AS nvarchar(80))))
--                     OR (
--                         TRY_CONVERT(BIGINT, LTRIM(RTRIM(CAST(v0.[Lieferant] AS nvarchar(80)))))
--                         = TRY_CONVERT(BIGINT, a.[Adresse])
--                     )
--                 )
--             ORDER BY
--                 v0.[Einzelpreis] ASC, v0.[Lieferant] ASC
--         ) AS [vendor_from_v0]
--     FROM [dbo].[KHKAdressen] AS a
--     WHERE
--         a.[Mandant] = 1
--         AND a.[Gruppe] = N'LIEF'
-- )
-- SELECT
--     c.*,
--     LTRIM(RTRIM(CAST(c.[USER_ManusLfdNr] AS nvarchar(80)))) AS [user_txt],
--     CASE
--         WHEN c.[vendor_from_v0] IS NULL THEN N'首段无命中→将用 liefer_map 或回退 USER，请与价目子表对'
--         ELSE N'首段已命中，多数情况已是正确 Lieferantennummer'
--     END AS [note]
-- FROM [chk] AS c
-- ORDER BY
--     c.[Adresse] ASC;
*/
GO
