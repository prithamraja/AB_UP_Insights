"""
Aggregate the UP 100m population TIFF to a coarser grid (~5km cells)
and emit JSON for the frontend geographic coverage map.

Output format: [{lat, lng, pop}] — one entry per non-zero cell.
"""

import json
import os
import numpy as np
import rasterio

TIFF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "up_pop_2025_CN_100m_R2025A_v1.tif",
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "ab-dashboard-main", "src", "data", "up_population_grid.json",
)

# Aggregation factor: 50 pixels of 100m ≈ 5km cells
AGGREGATION = 50

# Cells with fewer people than this are dropped to keep the JSON small
MIN_POP = 10


def main():
    print(f"Reading {TIFF_PATH} ...")
    with rasterio.open(TIFF_PATH) as src:
        data = src.read(1)
        nodata = src.nodata
        transform = src.transform
        height, width = data.shape
        print(f"  Source: {width}x{height} @ 100m, nodata={nodata}")

        # Replace nodata with 0
        if nodata is not None:
            data = np.where(data == nodata, 0, data)
        data = np.where(np.isfinite(data), data, 0)

        # Aggregate by sum over AGGREGATION x AGGREGATION blocks
        new_h = height // AGGREGATION
        new_w = width // AGGREGATION
        trimmed = data[: new_h * AGGREGATION, : new_w * AGGREGATION]
        reshaped = trimmed.reshape(new_h, AGGREGATION, new_w, AGGREGATION)
        agg = reshaped.sum(axis=(1, 3)).astype(np.int32)

        # Compute cell centers in lat/lng
        # Each aggregated cell spans AGGREGATION source pixels
        cell_size_deg = transform.a * AGGREGATION  # pixel width * agg
        # Origin: top-left corner
        origin_lng = transform.c
        origin_lat = transform.f

        cells = []
        for r in range(new_h):
            for c in range(new_w):
                pop = int(agg[r, c])
                if pop < MIN_POP:
                    continue
                # Center of cell
                lng = origin_lng + (c + 0.5) * cell_size_deg
                lat = origin_lat - (r + 0.5) * cell_size_deg
                cells.append({"lat": round(lat, 4), "lng": round(lng, 4), "pop": pop})

        total = sum(c["pop"] for c in cells)
        print(f"  Aggregated to {new_w}x{new_h} = {new_w*new_h:,} total cells")
        print(f"  Kept {len(cells):,} cells with pop >= {MIN_POP}")
        print(f"  Total population: {total:,}")
        print(f"  Cell size: {cell_size_deg:.4f} deg ~ {cell_size_deg*111:.2f} km")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(
            {
                "cell_size_deg": cell_size_deg,
                "cells": cells,
            },
            f,
        )
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
