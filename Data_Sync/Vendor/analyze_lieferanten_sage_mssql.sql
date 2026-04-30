SELECT 
    k.Kto                   AS Kreditorennummer,
    k.Matchcode             AS Kurzname,
    a.Name1                 AS Firmenname,
    a.Name2                 AS Firmenname2,
    a.LieferStrasse         AS Strasse,
    a.LieferZusatz          AS Adresszusatz,
    a.LieferPLZ             AS PLZ,
    a.LieferOrt             AS Ort,
    a.LieferLand            AS Land,
    MAX(CASE WHEN t.Typ = 'T' THEN t.Telefon END) AS Telefon,
    MAX(CASE WHEN t.Typ = 'F' THEN t.Telefon END) AS Fax,
    MAX(CASE WHEN t.Typ = 'E' THEN t.Telefon END) AS Email,
    b.IBAN                  AS IBAN,
    b.Swift                 AS BIC,
    b.Institut              AS Bankname
FROM KHKKontokorrent k
JOIN KHKAdressen a ON k.Adresse = a.Adresse
LEFT JOIN KHKAdressenTelefon t ON a.Adresse = t.Adresse
LEFT JOIN KHKBankverbindungenD b ON k.Adresse = b.Adresse
WHERE k.KtoArt = 'K'
  AND k.Mandant = 1
GROUP BY 
    k.Kto, k.Matchcode,
    a.Name1, a.Name2,
    a.LieferStrasse, a.LieferZusatz,
    a.LieferPLZ, a.LieferOrt, a.LieferLand,
    b.IBAN, b.Swift, b.Institut
ORDER BY k.Kto