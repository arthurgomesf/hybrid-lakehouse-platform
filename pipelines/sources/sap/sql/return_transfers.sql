-- Open lines of inventory transfer requests (OWTQ/WTQ1) and the stock transfers
-- (OWTR/WTR1) created from them, with the lead time between request and transfer.
--
-- Grain: one row per request line. When a line has several transfers, the first
-- one is used and transfer_count tells how many exist.
--
-- WTR1.BaseType must be checked: BaseEntry/BaseLine only point to a transfer
-- request when BaseType = 1250000001 (OWTQ object type). Without that filter a
-- transfer based on another document with the same DocEntry would be linked.
WITH request_lines AS (
    SELECT
        H."DocEntry",
        L."LineNum",
        H."DocNum",
        H."BPLName",
        H."DocStatus",
        H."CreateDate",
        L."ItemCode",
        L."Quantity",
        L."OpenQty",
        L."Price",
        L."FromWhsCod",
        L."WhsCode",
        L."LineStatus"
    FROM SBO_CONTOSO_PRD.OWTQ H
    JOIN SBO_CONTOSO_PRD.WTQ1 L ON L."DocEntry" = H."DocEntry"
    WHERE H."CANCELED" = 'N'
      AND L."LineStatus" = 'O'
      AND H."CreateDate" >= :start_date
),
transfers AS (
    SELECT
        L."BaseEntry",
        L."BaseLine",
        MIN(H."CreateDate") AS first_transfer_date,
        MIN(H."DocNum")     AS first_transfer_doc_num,
        COUNT(*)            AS transfer_count
    FROM SBO_CONTOSO_PRD.OWTR H
    JOIN SBO_CONTOSO_PRD.WTR1 L ON L."DocEntry" = H."DocEntry"
    WHERE H."CANCELED" = 'N'
      AND L."BaseType" = 1250000001
    GROUP BY L."BaseEntry", L."BaseLine"
)
SELECT
    R."DocEntry"            AS doc_entry,
    R."LineNum"             AS line_num,
    R."DocNum"              AS doc_num,
    R."BPLName"             AS branch_name,
    CASE R."DocStatus" WHEN 'O' THEN 'open' WHEN 'C' THEN 'closed' ELSE R."DocStatus" END AS doc_status,
    R."CreateDate"          AS created_date,
    R."ItemCode"            AS item_code,
    R."Quantity"            AS quantity,
    R."OpenQty"             AS open_quantity,
    R."Price"               AS unit_price,
    R."FromWhsCod"          AS from_warehouse,
    R."WhsCode"             AS to_warehouse,
    T.first_transfer_doc_num,
    T.first_transfer_date,
    COALESCE(T.transfer_count, 0) AS transfer_count,
    DAYS_BETWEEN(R."CreateDate", T.first_transfer_date) AS lead_time_days
FROM request_lines R
LEFT JOIN transfers T
       ON T."BaseEntry" = R."DocEntry"
      AND T."BaseLine"  = R."LineNum"
