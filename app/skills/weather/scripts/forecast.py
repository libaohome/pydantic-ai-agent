#!/usr/bin/env python3
"""
城市天气查询脚本 — 使用 wttr.in 免费 API，无需 API Key。

供 weather Skill 调用，支持：
- 当前天气简要一行（format=3）
- 明日预报（format=j1 JSON，取第二天数据）
- 多日预报（format=j1，最多 7 天，含是否下雨）

命令行示例::

        python forecast.py --city 北京
        python forecast.py --city 北京 --days 7

面向小白：
- argparse 解析命令行参数
- urllib 是标准库 HTTP 客户端（此处未用 requests）
- wttr.in 是公共服务，请合理控制请求频率
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

# 部分服务会拒绝默认 Python User-Agent，伪装为 curl
_USER_AGENT = "curl/8.0 (pydantic-ai-agent)"
_RAIN_HINTS = ("rain", "drizzle", "shower", "storm", "thunder", "雨", "雷", "雪")


def _fetch(url: str) -> str:
    """
    发起 GET 请求并返回 UTF-8 解码后的响应体。

    参数:
            url: 完整 URL

    返回:
            响应文本字符串
    """
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def _fetch_json(city: str) -> dict:
    """
    获取 wttr.in 的 JSON 格式天气预报（j1）。

    参数:
            city: 城市名（会 URL 编码）

    返回:
            解析后的 Python dict
    """
    encoded = urllib.parse.quote(city)
    raw = _fetch(f"https://wttr.in/{encoded}?format=j1")
    return json.loads(raw)


def _city_name(data: dict, fallback: str) -> str:
    areas = data.get("nearest_area") or [{}]
    names = areas[0].get("areaName") or [{}] if areas else [{}]
    return names[0].get("value", fallback) if names else fallback


def _day_summary(day: dict) -> str:
    hourly = day.get("hourly") or [{}]
    mid = hourly[4] if len(hourly) > 4 else hourly[0]
    desc = (mid.get("weatherDesc") or [{}])[0]
    return desc.get("value", "")


def _looks_like_rain(summary: str) -> bool:
    text = summary.lower()
    return any(hint in text for hint in _RAIN_HINTS)


def get_forecast(city: str, *, days: int = 1, tomorrow: bool = False) -> dict:
    """查询城市天气；days>1 时返回多日预报及 rain_expected_on。"""
    if days <= 1 and not tomorrow:
        return get_weather(city, tomorrow=False)
    if days <= 1 and tomorrow:
        return get_weather(city, tomorrow=True)

    try:
        data = _fetch_json(city)
    except Exception as e:
        return {"error": str(e), "city": city}

    weather_days = data.get("weather") or []
    limit = max(1, min(days, 7))
    if not weather_days:
        return {"error": "Forecast unavailable", "city": city}

    daily: list[dict[str, str | None]] = []
    rain_days: list[str | None] = []
    for day in weather_days[:limit]:
        summary = _day_summary(day)
        date = day.get("date")
        daily.append(
            {
                "date": date,
                "summary": summary,
                "max_temp_c": day.get("maxtempC"),
                "min_temp_c": day.get("mintempC"),
            }
        )
        if _looks_like_rain(summary):
            rain_days.append(date)

    return {
        "city": _city_name(data, city),
        "days": daily,
        "rain_expected_on": rain_days,
        "will_rain_in_period": bool(rain_days),
        "source": "wttr.in",
    }


def get_weather(city: str, *, tomorrow: bool = False) -> dict:
    """
    查询指定城市的天气。

    参数:
            city: 城市名称，中英文均可
            tomorrow: True 返回明日预报；False 返回当前一行摘要

    返回:
            结构化 dict；数据不足时可能含 error 字段
    """
    if tomorrow:
        data = _fetch_json(city)
        days = data.get("weather", [])
        # weather[1] 通常为「明天」
        if len(days) >= 2:
            day = days[1]
            return {
                "city": _city_name(data, city),
                "date": day.get("date"),
                # hourly[4] 约等于中午时段的天气描述
                "summary": _day_summary(day),
                "max_temp_c": day.get("maxtempC"),
                "min_temp_c": day.get("mintempC"),
                "source": "wttr.in",
            }
        return {"error": "Tomorrow forecast unavailable", "raw_days": len(days)}

    # 当前天气：format=3 返回类似 "Beijing: ⛅️ +8°C" 的一行
    encoded = urllib.parse.quote(city)
    line = _fetch(f"https://wttr.in/{encoded}?format=3").strip()
    return {"city": city, "summary": line, "source": "wttr.in"}


def main() -> None:
    """命令行入口：解析参数、调用 get_forecast、打印 JSON。"""
    parser = argparse.ArgumentParser(description="Get weather for a city via wttr.in")
    parser.add_argument("--city", required=True, help='City name, e.g. "北京" or "Beijing"')
    parser.add_argument("--tomorrow", action="store_true", help="Return tomorrow's forecast")
    parser.add_argument("--days", type=int, default=1, help="Forecast days (1-7), e.g. 7 for next week")
    args = parser.parse_args()

    try:
        if args.tomorrow:
            result = get_forecast(args.city, days=1, tomorrow=True)
        else:
            result = get_forecast(args.city, days=args.days)
    except Exception as e:
        result = {"error": str(e), "city": args.city}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
