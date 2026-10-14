-- Purchase invoice headers (SAP Business One table OPCH).
--
-- Incremental extraction: the watermark is UpdateDate, not DocDate, so edits and
-- cancellations of older documents are captured as long as they happen inside
-- the window. Cancelled documents are kept and flagged so the cancellation
-- reaches the Silver layer instead of the row silently disappearing.
SELECT
    H."DocEntry"                                   AS doc_entry,
    H."DocNum"                                     AS doc_num,
    H."DocDate"                                    AS posting_date,
    H."UpdateDate"                                 AS updated_date,
    H."CardCode"                                   AS vendor_code,
    H."CardName"                                   AS vendor_name,
    H."DocTotal"                                   AS document_total,
    H."Serial"                                     AS invoice_number,
    CASE WHEN H."CANCELED" = 'Y' THEN TRUE ELSE FALSE END AS is_cancelled
FROM SBO_CONTOSO_PRD.OPCH H
WHERE H."UpdateDate" >= ADD_DAYS(CURRENT_DATE, -:window_days)
