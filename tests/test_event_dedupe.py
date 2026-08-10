from datetime import timedelta

from app.models import BehaviorEvent, utcnow
from app.recommendations import scored_event_weights


def test_rapid_repeated_product_click_has_zero_recommendation_weight():
    now = utcnow()
    events = [
        BehaviorEvent(id=1, event_type="product_click", product_id=7, session_id="s", occurred_at=now),
        BehaviorEvent(id=2, event_type="product_click", product_id=7, session_id="s", occurred_at=now + timedelta(minutes=1)),
        BehaviorEvent(id=3, event_type="product_click", product_id=7, session_id="s", occurred_at=now + timedelta(minutes=6)),
    ]
    assert scored_event_weights(events) == {1: 2, 2: 0, 3: 2}
