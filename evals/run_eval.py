"""Run tool-selection evals against the MCP server with a Cohere model."""
import argparse
import json
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import anyio
import yaml
from mcp import Client

from bridge.run import MODEL, co, server, to_cohere_tools

TODAY = "2026-11-26"  # fixed so that expected dates never change
SYSTEM_PROMPT = f"Today is {TODAY}."
COORD_TOLERANCE = 0.5  # Open-Meteo snaps to grid points, so allow small offsets
SECONDS_BETWEEN_CALLS = 3.5  # trial key allows about 20 chat calls per minute


def normalize(text) -> str:
    """Lowercase and strip accents so 'İzmir' and 'Izmir' compare equal."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold().strip()


def values_match(expected, actual) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and abs(expected - actual) <= COORD_TOLERANCE
    if isinstance(expected, list):
        return isinstance(actual, list) and sorted(map(normalize, expected)) == sorted(map(normalize, actual))
    return normalize(expected) == normalize(actual)


def args_match(expected_args: dict, actual_args: dict) -> bool:
    """Check only the arguments the case specifies; extra arguments are fine."""
    return all(
        key in actual_args and values_match(value, actual_args[key])
        for key, value in expected_args.items()
    )


def score_case(case: dict, calls: list[dict]) -> tuple[bool, bool]:
    """Return (tool_ok, args_ok) for one case, given the model's first-turn calls."""
    if "expected_calls" in case:
        remaining = list(calls)
        tool_ok = args_ok = True
        for expected in case["expected_calls"]:
            exp_args = expected.get("args", {})
            same_tool = [c for c in remaining if c["tool"] == expected["tool"]]
            if not same_tool:
                tool_ok = args_ok = False
                continue
            # Prefer a call whose arguments also match, so two calls to the
            # same tool are paired with the right locations
            match = next((c for c in same_tool if args_match(exp_args, c["args"])), same_tool[0])
            remaining.remove(match)
            if not args_match(exp_args, match["args"]):
                args_ok = False
        return tool_ok, args_ok

    expected_tool = case.get("expected_tool")
    if expected_tool is None:
        ok = len(calls) == 0
        return ok, ok
    if not calls or calls[0]["tool"] != expected_tool:
        return False, False
    return True, args_match(case.get("expected_args", {}), calls[0]["args"])


def first_turn_calls(question: str, tools: list[dict]) -> list[dict]:
    """Ask the model once and return the tool calls it makes in its first turn."""
    response = co.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
        tools=tools,
        temperature=0,
    )
    return [
        {"tool": tc.function.name, "args": json.loads(tc.function.arguments)}
        for tc in response.message.tool_calls or []
    ]


def summarize(results: list[dict]) -> None:
    categories = sorted({r["category"] for r in results})
    print(f"\n{'category':<12}{'tool':>10}{'args':>10}")
    for cat in categories + ["ALL"]:
        rows = results if cat == "ALL" else [r for r in results if r["category"] == cat]
        tool = sum(r["tool_ok"] for r in rows)
        args = sum(r["args_ok"] for r in rows)
        print(f"{cat:<12}{tool:>5}/{len(rows):<4}{args:>5}/{len(rows):<4}")
    print("\nFailures:")
    for r in results:
        if not (r["tool_ok"] and r["args_ok"]):
            print(f"  {r['id']}: got {r['calls']}")


async def main(cases_path: str, out_path: str, label: str) -> None:
    cases = yaml.safe_load(Path(cases_path).read_text(encoding="utf-8"))

    async with Client(server) as client:
        tools = to_cohere_tools((await client.list_tools()).tools)

    results = []
    for i, case in enumerate(cases):
        calls = first_turn_calls(case["question"], tools)
        tool_ok, args_ok = score_case(case, calls)
        results.append({**case, "calls": calls, "tool_ok": tool_ok, "args_ok": args_ok})
        print(f"[{i + 1}/{len(cases)}] {case['id']}: tool={'ok' if tool_ok else 'FAIL'} args={'ok' if args_ok else 'FAIL'}")
        time.sleep(SECONDS_BETWEEN_CALLS)

    summarize(results)
    Path(out_path).parent.mkdir(exist_ok=True)
    Path(out_path).write_text(json.dumps({
        "label": label,
        "model": MODEL,
        "today": TODAY,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "results": results,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="evals/cases.yaml")
    parser.add_argument("--out", default="results/v1.json")
    parser.add_argument("--label", default="v1 baseline")
    args = parser.parse_args()
    anyio.run(main, args.cases, args.out, args.label)