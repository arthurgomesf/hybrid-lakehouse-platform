-- Incoming service invoices (OPCH lines with a service CFOP) with withheld taxes,
-- consolidating two companies that live in separate SAP B1 databases.
--
-- Teaching version of the rule:
-- - withholding codes are mapped explicitly (tax_codes) instead of LIKE '%PIS%',
--   so one combined code can never be summed into several tax columns;
-- - cancelled invoices are kept and flagged (is_cancelled);
-- - a missing vendor tax id stays NULL instead of a placeholder string.
WITH headers AS (
    SELECT 'CONTOSO' AS company, H."DocEntry", H."DocNum", H."DocDate", H."TaxDate",
           H."CardCode", H."CardName", H."BPLName", H."Serial", H."DocTotal", H."CANCELED"
    FROM SBO_CONTOSO_PRD.OPCH H
    UNION ALL
    SELECT 'FABRIKAM', H."DocEntry", H."DocNum", H."DocDate", H."TaxDate",
           H."CardCode", H."CardName", H."BPLName", H."Serial", H."DocTotal", H."CANCELED"
    FROM SBO_FABRIKAM_PRD.OPCH H
),
service_lines AS (
    SELECT 'CONTOSO' AS company, L."DocEntry", SUM(L."LineTotal") AS lines_total,
           MAX(CASE WHEN L."BaseType" = 22 THEN L."BaseRef" END) AS purchase_order_ref
    FROM SBO_CONTOSO_PRD.PCH1 L
    WHERE L."CFOPCode" IN ('1933', '2933')
    GROUP BY L."DocEntry"
    UNION ALL
    SELECT 'FABRIKAM', L."DocEntry", SUM(L."LineTotal"),
           MAX(CASE WHEN L."BaseType" = 22 THEN L."BaseRef" END)
    FROM SBO_FABRIKAM_PRD.PCH1 L
    WHERE L."CFOPCode" IN ('1933', '2933')
    GROUP BY L."DocEntry"
),
tax_codes AS (
    SELECT 'WT-INSS' AS wt_code, 'inss' AS tax FROM DUMMY UNION ALL
    SELECT 'WT-IRRF', 'irrf'   FROM DUMMY UNION ALL
    SELECT 'WT-PIS',  'pis'    FROM DUMMY UNION ALL
    SELECT 'WT-COF',  'cofins' FROM DUMMY UNION ALL
    SELECT 'WT-CSL',  'csll'   FROM DUMMY UNION ALL
    SELECT 'WT-CSRF', 'csrf'   FROM DUMMY
),
withholdings AS (
    SELECT 'CONTOSO' AS company, W."AbsEntry" AS "DocEntry", T.tax, SUM(W."WTAmnt") AS amount
    FROM SBO_CONTOSO_PRD.PCH5 W
    JOIN tax_codes T ON T.wt_code = W."WTCode"
    WHERE W."Category" = 'I'
    GROUP BY W."AbsEntry", T.tax
    UNION ALL
    SELECT 'FABRIKAM', W."AbsEntry", T.tax, SUM(W."WTAmnt")
    FROM SBO_FABRIKAM_PRD.PCH5 W
    JOIN tax_codes T ON T.wt_code = W."WTCode"
    WHERE W."Category" = 'I'
    GROUP BY W."AbsEntry", T.tax
),
iss AS (
    SELECT 'CONTOSO' AS company, X."DocEntry", SUM(X."TaxSum") AS amount
    FROM SBO_CONTOSO_PRD.PCH4 X
    JOIN SBO_CONTOSO_PRD.OSTT S ON S."AbsId" = X."staType" AND S."Name" = 'ISS'
    GROUP BY X."DocEntry"
    UNION ALL
    SELECT 'FABRIKAM', X."DocEntry", SUM(X."TaxSum")
    FROM SBO_FABRIKAM_PRD.PCH4 X
    JOIN SBO_FABRIKAM_PRD.OSTT S ON S."AbsId" = X."staType" AND S."Name" = 'ISS'
    GROUP BY X."DocEntry"
),
tax_ids AS (
    SELECT 'CONTOSO' AS company, "DocEntry", NULLIF(COALESCE("TaxId0", "TaxId4"), '') AS tax_id
    FROM SBO_CONTOSO_PRD.PCH12
    UNION ALL
    SELECT 'FABRIKAM', "DocEntry", NULLIF(COALESCE("TaxId0", "TaxId4"), '')
    FROM SBO_FABRIKAM_PRD.PCH12
)
SELECT
    H.company,
    H."DocEntry"   AS doc_entry,
    H."DocNum"     AS doc_num,
    H."DocDate"    AS posting_date,
    H."TaxDate"    AS document_date,
    H."CardCode"   AS vendor_code,
    H."CardName"   AS vendor_name,
    TI.tax_id      AS vendor_tax_id,
    H."BPLName"    AS branch_name,
    H."Serial"     AS invoice_number,
    SL.purchase_order_ref,
    CASE WHEN H."CANCELED" = 'Y' THEN TRUE ELSE FALSE END AS is_cancelled,
    H."DocTotal"   AS document_total,
    SL.lines_total,
    ISS.amount     AS iss_amount,
    SUM(CASE WHEN W.tax = 'inss'   THEN W.amount END) AS inss_amount,
    SUM(CASE WHEN W.tax = 'irrf'   THEN W.amount END) AS irrf_amount,
    SUM(CASE WHEN W.tax = 'pis'    THEN W.amount END) AS pis_amount,
    SUM(CASE WHEN W.tax = 'cofins' THEN W.amount END) AS cofins_amount,
    SUM(CASE WHEN W.tax = 'csll'   THEN W.amount END) AS csll_amount,
    SUM(CASE WHEN W.tax = 'csrf'   THEN W.amount END) AS csrf_amount
FROM headers H
JOIN service_lines SL ON SL.company = H.company AND SL."DocEntry" = H."DocEntry"
LEFT JOIN withholdings W ON W.company = H.company AND W."DocEntry" = H."DocEntry"
LEFT JOIN iss ISS        ON ISS.company = H.company AND ISS."DocEntry" = H."DocEntry"
LEFT JOIN tax_ids TI     ON TI.company = H.company AND TI."DocEntry" = H."DocEntry"
WHERE H."DocDate" >= :start_date
GROUP BY
    H.company, H."DocEntry", H."DocNum", H."DocDate", H."TaxDate", H."CardCode",
    H."CardName", TI.tax_id, H."BPLName", H."Serial", SL.purchase_order_ref,
    H."CANCELED", H."DocTotal", SL.lines_total, ISS.amount
