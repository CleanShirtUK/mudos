#!/usr/bin/env python3
"""Read-only corpus audit for the current Mudos metadata matcher."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
import time

from lulu.emulation import PLATFORMS
from lulu.metadata import MetadataMatcher, SteamGridDBMetadata


def load_manifest(path: Path) -> list[dict[str, str]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def audit(manifest: list[dict[str, str]], output: Path, cache: Path | None) -> list[dict[str, object]]:
    existing: dict[str, dict[str, object]] = {}
    if output.exists():
        for line in output.read_text().splitlines():
            if line.strip():
                item = json.loads(line)
                existing[str(item["path"])] = item
    provider = SteamGridDBMetadata(cache_dir=cache)
    matcher = MetadataMatcher(provider)
    output.parent.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, object]] = []
    with output.open("w", encoding="utf-8") as stream:
        for entry in manifest:
            path = str(entry["path"])
            if path in existing:
                result = existing[path]
            else:
                match = matcher.match(str(entry["source_title"]), str(entry["platform"]))
                result = {
                    "path": path,
                    "platform": entry["platform"],
                    "source_title": entry["source_title"],
                    "normalized_search_title": match.normalized_search_title,
                    "match_status": match.status,
                    "match_method": match.method,
                    "confidence": match.confidence,
                    "metadata_game_id": match.game_id,
                    "canonical_title": match.canonical_title,
                    "candidates": [
                        {"id": item.game_id, "title": item.title, "platforms": list(item.platforms)}
                        for item in match.candidates
                    ],
                    "audited_at": int(time.time()),
                }
            results.append(result)
            stream.write(json.dumps(result, sort_keys=True) + "\n")
            stream.flush()
    return results


def summarize(results: list[dict[str, object]], manifest: list[dict[str, str]]) -> dict[str, object]:
    by_platform: dict[str, Counter[str]] = defaultdict(Counter)
    collisions: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in results:
        platform = str(item["platform"])
        by_platform[platform][str(item["match_status"])] += 1
        game_id = str(item.get("metadata_game_id", ""))
        if game_id:
            collisions[game_id].append(item)

    def rates(counter: Counter[str]) -> dict[str, object]:
        total = sum(counter.values())
        return {"total": total, "counts": dict(sorted(counter.items())), "percentages": {
            key: round(value * 100 / total, 2) if total else 0 for key, value in sorted(counter.items())
        }}

    collision_report = []
    for game_id, items in sorted(collisions.items()):
        if len(items) < 2:
            continue
        titles = sorted({str(item["normalized_search_title"]) for item in items})
        collision_report.append({
            "metadata_game_id": game_id,
            "canonical_title": items[0].get("canonical_title", ""),
            "count": len(items),
            "source_titles": sorted(str(item["source_title"]) for item in items),
            "normalized_titles": titles,
            "classification": "review",
        })

    unsupported = Counter(str(item["platform"]) for item in manifest if str(item["platform"]) not in PLATFORMS)
    return {
        "total_audited": len(results),
        "platforms": {platform: rates(counter) for platform, counter in sorted(by_platform.items())},
        "overall": rates(Counter(str(item["match_status"]) for item in results)),
        "canonical_id_collisions": collision_report,
        "unsupported_platform_files": dict(sorted(unsupported.items())),
        "representative": {
            "ambiguous": [item for item in results if item["match_status"] == "ambiguous"][:10],
            "unmatched": [item for item in results if item["match_status"] == "unmatched"][:10],
            "matched": [item for item in results if item["match_status"] == "matched"][:10],
        },
    }


def write_report(summary: dict[str, object], path: Path) -> None:
    lines = ["# ROM Corpus Metadata Baseline", "", f"Audited files: {summary['total_audited']}", ""]
    lines += ["## Platform Results", "", "| Platform | Total | Matched | Ambiguous | Unmatched | Network error |", "|---|---:|---:|---:|---:|---:|"]
    for platform, data in summary["platforms"].items():
        counts = data["counts"]
        lines.append(f"| {platform} | {data['total']} | {counts.get('matched', 0)} | {counts.get('ambiguous', 0)} | {counts.get('unmatched', 0)} | {counts.get('network-error', 0)} |")
    lines += ["", "## Canonical ID Collisions", ""]
    for collision in summary["canonical_id_collisions"]:
        lines.append(f"- `{collision['metadata_game_id']}`: {collision['count']} files, {collision['canonical_title']}; classification remains `review`." )
    if not summary["canonical_id_collisions"]:
        lines.append("No canonical-ID collisions.")
    lines += ["", "## Unsupported Platform Files", "", json.dumps(summary["unsupported_platform_files"], sort_keys=True), "", "## Representative Items", ""]
    for status in ("matched", "ambiguous", "unmatched"):
        lines.append(f"### {status}")
        for item in summary["representative"][status]:
            lines.append(f"- `{item['platform']}` `{item['source_title']}` -> `{item['normalized_search_title']}` -> `{item.get('canonical_title', '')}` ({item.get('metadata_game_id', '')}, confidence {item.get('confidence', 0)})")
        if not summary["representative"][status]:
            lines.append("- None")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--jsonl", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    supported = [item for item in manifest if item["platform"] in PLATFORMS and Path(item["source_title"]).suffix.lower() in PLATFORMS[item["platform"]].extensions]
    results = audit(supported, args.jsonl, args.cache)
    summary = summarize(results, manifest)
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_report(summary, args.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
