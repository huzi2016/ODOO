SELECT 
    Hauptartikelgruppe,   -- 主分类
    VaterArtikelgruppe,   -- 父分类
    Artikelgruppe,        -- 分类编码
    Bezeichnung,          -- 分类名称
    Gruppenebene          -- 层级（1=顶级，2=二级...）
FROM KHKArtikelgruppen
WHERE Artikelgruppe != 'Dummy'
ORDER BY Gruppenebene, Artikelgruppe;