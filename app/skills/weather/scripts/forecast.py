#!/usr/bin/env python3
"""查询城市天气（wttr.in，无需 API Key）。"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request

_USER_AGENT = "curl/8.0 (pydantic-ai-agent)"


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def _fetch_json(city: str) -> dict:
    encoded = urllib.parse.quote(city)
    raw = _fetch(f"https://wttr.in/{encoded}?format=j1")
    return json.loads(raw)


def get_weather(city: str, *, tomorrow: bool = False) -> dict:
    if tomorrow:
        data = _fetch_json(city)
        days = data.get("weather", [])
        if len(days) >= 2:
            day = days[1]
            return {
                "city": data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city),
                "date": day.get("date"),
                "summary": day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", ""),
                "max_temp_c": day.get("maxtempC"),
                "min_temp_c": day.get("mintempC"),
                "source": "wttr.in",
            }
        return {"error": "Tomorrow forecast unavailable", "raw_days": len(days)}

    encoded = urllib.parse.quote(city)
    line = _fetch(f"https://wttr.in/{encoded}?format=3").strip()
    return {"city": city, "summary": line, "source": "wttr.in"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Get weather for a city via wttr.in")
    parser.add_argument("--city", required=True, help='City name, e.g. "北京" or "Beijing"')
    parser.add_argument("--tomorrow", action="store_true", help="Return tomorrow's forecast")
    args = parser.parse_args()

    try:
        result = get_weather(args.city, tomorrow=args.tomorrow)
    except Exception as e:
        result = {"error": str(e), "city": args.city}

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
