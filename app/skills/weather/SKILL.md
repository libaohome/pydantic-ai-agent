---
name: weather
description: Get current weather and forecasts (no API key required).
homepage: https://wttr.in/:help
metadata: {"clawdbot":{"emoji":"🌤️","requires":{"bins":["curl"]}}}
---

# Weather

Two free services, no API keys needed.

## When to Use

Use this skill when the user asks about weather, temperature, or forecasts for a city.

## Scripts

Always call `load_skill("weather")` first, then run:

- **`scripts/forecast.py`** — query weather for a city
  - `city` (required): e.g. `"北京"`, `"Beijing"`
  - `tomorrow` (optional, boolean): `true` for tomorrow's forecast
  - `days` (optional, int 1-7): multi-day forecast; use `7` for "next week" / 下周

Example (next week rain):

```text
run_skill_script(
  skill_name="weather",
  script_name="scripts/forecast.py",
  args={"city": "上海", "days": 7}
)
```

Example (tomorrow):

```text
run_skill_script(
  skill_name="weather",
  script_name="scripts/forecast.py",
  args={"city": "北京", "tomorrow": true}
)
```

Do **not** guess script names. Only use `scripts/forecast.py`.

## wttr.in (primary)

Quick one-liner:
```bash
curl -s "wttr.in/London?format=3"
# Output: London: ⛅️ +8°C
```

Compact format:
```bash
curl -s "wttr.in/London?format=%l:+%c+%t+%h+%w"
# Output: London: ⛅️ +8°C 71% ↙5km/h
```

Full forecast:
```bash
curl -s "wttr.in/London?T"
```

Format codes: `%c` condition · `%t` temp · `%h` humidity · `%w` wind · `%l` location · `%m` moon

Tips:
- URL-encode spaces: `wttr.in/New+York`
- Airport codes: `wttr.in/JFK`
- Units: `?m` (metric) `?u` (USCS)
- Today only: `?1` · Current only: `?0`
- PNG: `curl -s "wttr.in/Berlin.png" -o /tmp/weather.png`

## Open-Meteo (fallback, JSON)

Free, no key, good for programmatic use:
```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=51.5&longitude=-0.12&current_weather=true"
```

Find coordinates for a city, then query. Returns JSON with temp, windspeed, weathercode.

Docs: https://open-meteo.com/en/docs
