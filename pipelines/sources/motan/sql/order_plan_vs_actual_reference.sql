SELECT
    machine,
    order_number,
    started_at,
    ended_at,
    duration_minutes,
    sap_status,
    sap_status_description,
    sap_released_for_production,
    product_item_code,
    product_description,
    sap_planned_production_quantity,
    sap_completed_production_quantity,
    sap_start_date,
    sap_due_date,
    sap_date_match_status,
    planned_resin_total_kg,
    actual_consumed_total_kg,
    variance_kg,
    variance_percent,
    comparison_status,
    windows_count,
    windows_without_consumption,
    resin_filter_applied,
    sap_synced_at
FROM public.vw_order_plan_vs_actual_consolidated
WHERE started_at >= now() - (:window_days * interval '1 day')
   OR sap_synced_at >= now() - (:window_days * interval '1 day')
   OR ended_at IS NULL;
