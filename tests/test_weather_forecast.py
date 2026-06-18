"""单元测试 — 天气预报脚本（离线逻辑）。"""

from __future__ import annotations

from app.skills.weather.scripts.forecast import _looks_like_rain, get_forecast


def test_looks_like_rain():
    assert _looks_like_rain("Light rain shower")
    assert _looks_like_rain("小雨")
    assert not _looks_like_rain("Sunny")


def test_get_forecast_multi_day(monkeypatch):
    sample = {
        "nearest_area": [{"areaName": [{"value": "Shanghai"}]}],
        "weather": [
            {
                "date": "2026-06-17",
                "maxtempC": "28",
                "mintempC": "22",
                "hourly": [{"weatherDesc": [{"value": "Sunny"}]}],
            },
            {
                "date": "2026-06-18",
                "maxtempC": "26",
                "mintempC": "21",
                "hourly": [{"weatherDesc": [{"value": "Light rain"}]}],
            },
        ],
    }

    monkeypatch.setattr(
        "app.skills.weather.scripts.forecast._fetch_json",
        lambda _city: sample,
    )

    result = get_forecast("上海", days=2)

    assert result["city"] == "Shanghai"
    assert result["will_rain_in_period"] is True
    assert result["rain_expected_on"] == ["2026-06-18"]
    assert len(result["days"]) == 2
