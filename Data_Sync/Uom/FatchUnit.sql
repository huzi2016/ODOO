

SELECT DISTINCT Verkaufsmengeneinheit AS Mengeneinheit
FROM KHKArtikel WHERE Verkaufsmengeneinheit IS NOT NULL
UNION
SELECT DISTINCT Basismengeneinheit
FROM KHKArtikel WHERE Basismengeneinheit IS NOT NULL
UNION
SELECT DISTINCT Lagermengeneinheit
FROM KHKArtikel WHERE Lagermengeneinheit IS NOT NULL
ORDER BY Mengeneinheit;