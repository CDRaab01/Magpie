"""Alert latching (CLAUDE.md §5/§9) — pure. A deviation alert must fire once per condition
*episode*, not once per sweep (a missing bill must not page every 15 minutes): the latch is
data (was the condition already true last time we checked?), not a timer.
"""


def should_alert(currently_true: bool, previously_true: bool) -> bool:
    """Fires only on the true rising edge — condition just became true. Already-true stays
    silent (already alerted); condition resolving and recurring later is a *new* episode and
    fires again, since `previously_true` reflects the latest check, not "ever true before"."""
    return currently_true and not previously_true
