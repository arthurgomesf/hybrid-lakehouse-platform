SELECT
    order_number,
    line_number,
    item_code,
    item_description,
    planned_quantity,
    issued_quantity,
    warehouse,
    uom,
    included_in_resin_total,
    raw_data,
    synced_at,
    created_at
FROM public.sap_production_order_components
WHERE synced_at >= now() - (:window_days * interval '1 day')
   OR order_number IN (
        SELECT DISTINCT order_number
        FROM public.vw_order_number_changes
        WHERE order_number IS NOT NULL
          AND started_at >= now() - (:window_days * interval '1 day')
   );
