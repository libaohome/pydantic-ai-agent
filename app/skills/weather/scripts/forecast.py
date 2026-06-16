#!/usr/bin/env python3
"""
城市天气查询脚本 — 使用 wttr.in 免费 API，无需 API Key。

供 weather Skill 调用，支持：
- 当前天气简要一行（format=3）
- 明日预报（format=j1 JSON，取第二天数据）

命令行示例::

        python forecast.py --city 北京
        python forecast.py --city Beijing --tomorrow

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
                "city": data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", city),
                "date": day.get("date"),
                # hourly[4] 约等于中午时段的天气描述
                "summary": day.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", ""),
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
    """命令行入口：解析参数、调用 get_weather、打印 JSON。"""
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
