from __future__ import annotations

from bottom_hunter.src.price_alerts import PriceAlertStore, evaluate_alert_rule


def test_price_alert_rule_persists_and_rearms_after_crossing_back(tmp_path) -> None:
    store = PriceAlertStore(tmp_path / "price_alerts.json")
    rule = store.add_rule(
        canonical_id="CN:600000",
        symbol="600000.SS",
        name="浦发银行",
        market="CN",
        condition="price_above",
        threshold=10.0,
    )

    updated, notify = evaluate_alert_rule(rule, price=10.2, change_percent=1.0)
    assert notify is True
    assert updated.triggered is True
    store.update_rules([updated])

    persisted = store.list_rules()[0]
    assert persisted.triggered is True
    rearmed, notify_again = evaluate_alert_rule(persisted, price=9.8, change_percent=0.4)
    assert notify_again is False
    assert rearmed.triggered is False
    crossed_again, notify_second_cross = evaluate_alert_rule(rearmed, price=10.1, change_percent=0.8)
    assert crossed_again.triggered is True
    assert notify_second_cross is True


def test_price_alert_rejects_invalid_thresholds(tmp_path) -> None:
    store = PriceAlertStore(tmp_path / "price_alerts.json")
    try:
        store.add_rule(
            canonical_id="CN:600000",
            symbol="600000.SS",
            name="浦发银行",
            market="CN",
            condition="price_below",
            threshold=0,
        )
    except ValueError as exc:
        assert "大于 0" in str(exc)
    else:
        raise AssertionError("非正数价格阈值必须被拒绝")
