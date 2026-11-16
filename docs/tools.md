# Tool design

Three tools wrap the Open-Meteo APIs. All three need no API key.

## Boundary rule

| Date asked about | Tool |
|---|---|
| Yesterday or earlier | `get_historical` |
| Today or later | `get_forecast` |
| A place name, no coordinates | `geocode_city` first |

The two data tools overlap on today in the underlying APIs, so the rule is stated in both descriptions to remove the ambiguity.

## `geocode_city`

**Description:** Convert a place name into latitude and longitude. Call this before get_forecast or get_historical when the user names a place instead of giving coordinates.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `name` | string | yes | Place name, e.g. "Ankara" |
| `country_code` | string | no | ISO 3166-1 alpha-2, e.g. "TR" |

**Output:**

```json
{"name": "Ankara", "country": "Türkiye", "latitude": 39.92, "longitude": 32.85}
```

**Error:** `{"error": "No place found for 'Ankra'"}`

## `get_forecast`

**Description:** Get the daily weather forecast for a location, starting today and up to 16 days ahead. Use this for today and any future date. For yesterday or any earlier date, use get_historical instead. Requires coordinates; if you only have a place name, call geocode_city first.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `latitude` | float | yes | -90 to 90 |
| `longitude` | float | yes | -180 to 180 |
| `days` | int | no, default 7 | 1 to 16 |
| `variables` | list of enum | no, default all | `temperature_max`, `temperature_min`, `precipitation`, `wind_speed_max` |

**Output:**

```json
{
  "location": {"latitude": 39.90, "longitude": 32.86},
  "days": [
    {"date": "2026-11-16", "temperature_max_c": 13.3, "precipitation_mm": 0.1},
    {"date": "2026-11-17", "temperature_max_c": 13.6, "precipitation_mm": 3.0}
  ]
}
```

**Error:** `{"error": "days must be between 1 and 16"}`

## `get_historical`

**Description:** Get observed daily weather for a location from ERA5 reanalysis, for any date range from 1940-01-01 up to yesterday. Use this for yesterday and earlier dates. For today or future dates, use get_forecast instead. Dates must be YYYY-MM-DD. Requires coordinates; if you only have a place name, call geocode_city first.

| Parameter | Type | Required | Notes |
|---|---|---|---|
| `latitude` | float | yes | -90 to 90 |
| `longitude` | float | yes | -180 to 180 |
| `start_date` | string | yes | YYYY-MM-DD |
| `end_date` | string | yes | YYYY-MM-DD, not earlier than `start_date`, not later than yesterday |
| `variables` | list of enum | no, default all | `temperature_max`, `temperature_min`, `precipitation`, `wind_speed_max` |

The tool, not the model, checks that `start_date <= end_date` and caps the range at 366 days to keep the output small.

**Output:**

```json
{
  "location": {"latitude": 39.96, "longitude": 32.81},
  "days": [
    {"date": "2026-11-09", "temperature_max_c": 13.3, "precipitation_mm": 0.1},
    {"date": "2026-11-10", "temperature_max_c": 13.6, "precipitation_mm": 3.0}
  ]
}
```

**Error:** `{"error": "end_date must not be earlier than start_date"}`

## Design notes

- `variables` is an enum rather than free text so the model cannot invent names ("rain", "precip"). The tool maps these names to Open-Meteo's own (`temperature_2m_max`, etc.).
- Open-Meteo returns parallel lists (`time`, `temperature_2m_max`, ...). The tools reshape them into one object per day, with units in the field names.
- Open-Meteo snaps coordinates to the nearest grid point, and the forecast and archive endpoints use different grids (Ankara 39.93, 32.86 came back as 39.904, 32.859 from forecast and 39.965, 32.807 from archive). Evals therefore compare coordinates with a tolerance.
- API errors are returned to the model as text, not raised, so the model can recover (for example, switch to the other tool on an out-of-range date).
