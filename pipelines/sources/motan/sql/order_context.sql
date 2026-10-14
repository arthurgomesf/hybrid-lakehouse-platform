SELECT
    machine,
    order_number,
    started_at,
    next_order_started_at,
    duration_minutes
FROM public.vw_order_number_changes
WHERE started_at >= now() - (:window_days * interval '1 day');
