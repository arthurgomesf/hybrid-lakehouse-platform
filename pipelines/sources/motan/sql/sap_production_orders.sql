SELECT
    order_number,
    sap_abs_entry,
    sap_document_number,
    status,
    product_item_code,
    product_description,
    planned_quantity,
    completed_quantity,
    planned_resin_total_kg,
    resin_filter_applied,
    start_date,
    due_date,
    raw_data,
    synced_at,
    created_at
FROM public.sap_production_orders
WHERE synced_at >= now() - (:window_days * interval '1 day')
   OR order_number IN (
        SELECT DISTINCT order_number
        FROM public.vw_order_number_changes
        WHERE order_number IS NOT NULL
          AND started_at >= now() - (:window_days * interval '1 day')
   );
