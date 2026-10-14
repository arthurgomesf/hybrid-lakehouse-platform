SELECT
    machine,
    order_number,
    started_at,
    ended_at,
    duration_minutes,
    actual_consumed_total_kg,
    actual_coverage
FROM public.vw_order_actual_consumption_total
WHERE started_at >= now() - (:window_days * interval '1 day');
