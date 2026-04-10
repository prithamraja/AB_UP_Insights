"""
Extract the UP state boundary from the population TIFF.
The TIFF is already masked to UP, so we can trace the edge of valid data.
"""

import json
import os
import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import unary_union

TIFF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "up_pop_2025_CN_100m_R2025A_v1.tif",
)
OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "ab-dashboard-main", "src", "data", "up_boundary.json",
)


DOWNSAMPLE = 20  # 100m -> 2km mask; still plenty of detail


def main():
    print(f"Reading {TIFF_PATH} ...", flush=True)
    with rasterio.open(TIFF_PATH) as src:
        data = src.read(1)
        nodata = src.nodata
        transform = src.transform
        print(f"  Shape: {data.shape}, nodata={nodata}", flush=True)

        # Build mask then downsample by max-pool
        full_mask = ((data != nodata) & np.isfinite(data)).astype(np.uint8)
        h, w = full_mask.shape
        new_h = h // DOWNSAMPLE
        new_w = w // DOWNSAMPLE
        trimmed = full_mask[: new_h * DOWNSAMPLE, : new_w * DOWNSAMPLE]
        mask = trimmed.reshape(new_h, DOWNSAMPLE, new_w, DOWNSAMPLE).max(axis=(1, 3))
        print(f"  Downsampled mask: {mask.shape}, valid={mask.sum():,}", flush=True)

        # Adjust transform for the downsampled raster
        from rasterio.transform import Affine
        new_transform = Affine(
            transform.a * DOWNSAMPLE, transform.b, transform.c,
            transform.d, transform.e * DOWNSAMPLE, transform.f,
        )

        # Extract shapes from the mask
        print("  Extracting polygons ...", flush=True)
        results = []
        for geom, val in shapes(mask, mask=mask.astype(bool), transform=new_transform):
            if val == 1:
                results.append(shape(geom))
        print(f"  Found {len(results)} polygons", flush=True)

        # Merge into one multi-polygon
        merged = unary_union(results)
        print(f"  Merged area bounds: {merged.bounds}")

        # Pick the largest polygon (main UP landmass) and simplify
        if merged.geom_type == "MultiPolygon":
            # Keep only polygons larger than 0.01 sq degrees (~1200 km^2)
            polys = sorted(merged.geoms, key=lambda p: p.area, reverse=True)
            polys = [p for p in polys if p.area > 0.01]
            print(f"  Kept {len(polys)} polygons after area filter")
        else:
            polys = [merged]

        # Simplify the main polygon to reduce point count
        # Tolerance 0.005 deg ~ 500m — plenty of detail for a state map
        simplified = []
        total_pts = 0
        for p in polys:
            s = p.simplify(0.005, preserve_topology=True)
            simplified.append(s)
            if s.geom_type == "Polygon":
                total_pts += len(s.exterior.coords)
        print(f"  Simplified to {total_pts:,} total exterior points")

        # Build GeoJSON — a MultiPolygon
        features = []
        for s in simplified:
            features.append(
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": mapping(s),
                }
            )

        output = {
            "type": "FeatureCollection",
            "features": features,
        }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f)
    print(f"Wrote {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
