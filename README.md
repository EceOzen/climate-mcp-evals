# climate-mcp-evals

An MCP server that exposes Open-Meteo weather forecasts and ERA5-based historical weather as LLM tools, plus (in progress) a tool-use eval suite that measures how well a Cohere model picks and chains those tools.

The goal is less the weather data itself than the integration work around it: designing tool schemas a model can use reliably, returning errors a model can recover from, and measuring tool-selection quality with a repeatable eval.

## Status

| Part | State |
|---|---|
| MCP server with three tools | Done |
| Bridge: MCP client + Cohere tool-use loop | In progress |
| Eval suite (tool selection and argument accuracy) | Planned |
| Tool-description tuning rounds | Planned |
| CI: evals on every PR | Planned |

## Tools

| Tool | What it does | Source |
|---|---|---|
| `geocode_city` | Turns a place name (optionally filtered by country) into coordinates | Open-Meteo Geocoding API |
| `get_forecast` | Daily forecast from today up to 16 days ahead | Open-Meteo Forecast API |
| `get_historical` | Observed daily weather for any range from 1940 up to yesterday | Open-Meteo Historical Weather API (ERA5 reanalysis) |

The data tools take coordinates, so a question about a named place needs two calls: `geocode_city`, then the right data tool. Measuring whether the model chains them correctly is part of the eval.

Full schemas, parameter limits and output examples are in [docs/tools.md](docs/tools.md).

## Design decisions

- **A hard boundary between forecast and history.** Both Open-Meteo endpoints can return today, which would leave the model guessing. The rule is stated in both tool descriptions: yesterday and earlier → `get_historical`; today and later → `get_forecast`. This boundary is where the eval's hardest cases sit.
- **Errors are returned, not raised.** An unhandled exception reaches the model as a bare "Error executing tool". Every tool instead returns `{"error": "..."}` with a reason the model can act on, for example: *"end_date must be before today. For today or future dates, use get_forecast."* Open-Meteo's own error reasons are passed through.
- **Variables are an enum, not free text.** `variables` accepts only `temperature_max`, `temperature_min`, `precipitation` and `wind_speed_max`, so the model cannot invent names. The tools map these to Open-Meteo's names internally, which keeps the tool schema stable if the data source changes.
- **Reshaped output.** Open-Meteo returns parallel lists. The tools return one object per day, with units in the field names (`temperature_max_c`, `precipitation_mm`).
- **Filtering is delegated to the API.** `geocode_city` passes `countryCode` to Open-Meteo rather than checking the first result itself, so "Paris, US" finds Paris, Texas instead of failing on Paris, France.
- **Coordinates are compared with a tolerance.** Open-Meteo snaps requests to the nearest grid point, and the forecast and archive endpoints use different grids (Ankara at 39.93, 32.86 came back as 39.904, 32.859 from forecast and 39.965, 32.807 from archive). The tools report the coordinates the data actually comes from, and the eval will not require exact matches.
- **Pinned to MCP Python SDK v2.** Version 2.0 renamed `FastMCP` to `MCPServer` and broke unpinned v1 code. `requirements.txt` pins `mcp>=2,<3`.

## Setup

Requires Python 3.10+ and Node.js (for the MCP Inspector).

```bash
git clone https://github.com/<your-username>/climate-mcp-evals.git
cd climate-mcp-evals
python -m venv .venv            # or: conda create -n climate-mcp python=3.11
# activate the environment, then:
pip install -r requirements.txt
```

The bridge and evals call the Cohere API. Put your key in a `.env` file in the repo root (it is git-ignored):

```
COHERE_API_KEY=your_key_here
```

The server itself needs no key: Open-Meteo is free for non-commercial use.

## Try the server

```bash
npx @modelcontextprotocol/inspector python server/server.py
```

In the Inspector, connect, open **Tools**, and try for example `geocode_city` with `name: Ankara`, then `get_forecast` with the returned coordinates.

## Roadmap

1. Bridge: list the server's tools over MCP, convert them to Cohere's tool format, and run the tool-call loop end to end.
2. Eval set: cases covering clear requests, forecast/history boundary cases, multi-step requests and requests that need no tool, with a held-out split.
3. Metrics: tool-selection accuracy, argument accuracy, per-category breakdown, each case run several times at temperature 0.
4. Description tuning: change one thing per round and record the score.
5. CI: run the eval on every pull request and flag regressions.

## Data attribution

Weather data by [Open-Meteo.com](https://open-meteo.com/), licensed under CC BY 4.0. Historical data is based on ERA5 reanalysis from the Copernicus Climate Change Service (ECMWF).
