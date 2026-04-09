import { useState, useMemo, useEffect } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  UP_BOUNDARY,
  SPECIALTIES,
  isInsidePolygon,
  computeCoverage,
  coverageColor,
  type Specialty,
} from "@/data/up-geo-data";

const GRID_SIZE = 0.1; // ~11km cells

// Pre-compute the boundary GeoJSON (outline only)
const boundaryGeoJSON: GeoJSON.Feature = {
  type: "Feature",
  properties: {},
  geometry: {
    type: "Polygon",
    coordinates: [UP_BOUNDARY],
  },
};

interface GridCell {
  lat: number;
  lng: number;
  coverage: Record<Specialty, number>;
}

/** Build grid cells that fall inside UP boundary, with coverage per specialty */
function buildGrid(): GridCell[] {
  // Bounding box
  let minLng = Infinity,
    maxLng = -Infinity,
    minLat = Infinity,
    maxLat = -Infinity;
  for (const [lng, lat] of UP_BOUNDARY) {
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
  }

  const cells: GridCell[] = [];
  for (let lat = minLat; lat < maxLat; lat += GRID_SIZE) {
    for (let lng = minLng; lng < maxLng; lng += GRID_SIZE) {
      const cLat = lat + GRID_SIZE / 2;
      const cLng = lng + GRID_SIZE / 2;
      if (!isInsidePolygon([cLng, cLat], UP_BOUNDARY)) continue;

      const coverage = {} as Record<Specialty, number>;
      for (const s of SPECIALTIES) {
        coverage[s] = computeCoverage(cLat, cLng, s);
      }
      cells.push({ lat, lng, coverage });
    }
  }
  return cells;
}

/** Convert grid cells to GeoJSON FeatureCollection */
function gridToGeoJSON(cells: GridCell[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: cells.map((c) => ({
      type: "Feature" as const,
      properties: { coverage: c.coverage },
      geometry: {
        type: "Polygon" as const,
        coordinates: [
          [
            [c.lng, c.lat],
            [c.lng + GRID_SIZE, c.lat],
            [c.lng + GRID_SIZE, c.lat + GRID_SIZE],
            [c.lng, c.lat + GRID_SIZE],
            [c.lng, c.lat],
          ],
        ],
      },
    })),
  };
}

/** Imperative grid layer that updates style when specialty changes */
function GridOverlay({
  gridGeoJSON,
  specialty,
}: {
  gridGeoJSON: GeoJSON.FeatureCollection;
  specialty: Specialty;
}) {
  const map = useMap();

  useEffect(() => {
    const layer = L.geoJSON(gridGeoJSON, {
      style: (feature) => {
        const score = feature?.properties?.coverage?.[specialty] ?? 0;
        return {
          fillColor: coverageColor(score),
          fillOpacity: 0.55,
          weight: 0.3,
          color: "#aaa",
        };
      },
      renderer: L.canvas(),
    }).addTo(map);

    return () => {
      map.removeLayer(layer);
    };
  }, [map, gridGeoJSON, specialty]);

  return null;
}

/** Fit map bounds to UP on mount */
function FitBounds() {
  const map = useMap();
  useEffect(() => {
    const lats = UP_BOUNDARY.map(([, lat]) => lat);
    const lngs = UP_BOUNDARY.map(([lng]) => lng);
    map.fitBounds([
      [Math.min(...lats), Math.min(...lngs)],
      [Math.max(...lats), Math.max(...lngs)],
    ]);
  }, [map]);
  return null;
}

const LEGEND_ITEMS = [
  { label: "High", color: "#1a9850" },
  { label: "", color: "#66bd63" },
  { label: "Medium", color: "#a6d96a" },
  { label: "", color: "#fee08b" },
  { label: "", color: "#fc8d59" },
  { label: "Low", color: "#d73027" },
];

export function GeographicCoverage() {
  const [selectedSpecialty, setSelectedSpecialty] =
    useState<Specialty>("Cardiology");

  const gridCells = useMemo(() => buildGrid(), []);
  const gridGeoJSON = useMemo(() => gridToGeoJSON(gridCells), [gridCells]);

  return (
    <div className="flex flex-1 min-h-0">
      {/* Specialty sidebar */}
      <div className="w-52 shrink-0 border-r border-border bg-[hsl(var(--sidebar-bg))] flex flex-col">
        <div className="px-4 py-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Specialty
        </div>
        <div className="flex-1 overflow-y-auto px-2 space-y-1">
          {SPECIALTIES.map((s) => (
            <button
              key={s}
              onClick={() => setSelectedSpecialty(s)}
              className={`flex w-full items-center rounded-md px-3 py-2 text-sm transition-colors ${
                selectedSpecialty === s
                  ? "bg-[hsl(var(--sidebar-active))] text-[hsl(var(--sidebar-primary))] font-medium"
                  : "text-[hsl(var(--sidebar-fg))] hover:bg-[hsl(var(--sidebar-hover))]"
              }`}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Legend */}
        <div className="border-t border-border px-4 py-3">
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            Coverage
          </div>
          <div className="flex items-center gap-0.5">
            {LEGEND_ITEMS.map((item, i) => (
              <div key={i} className="flex-1 flex flex-col items-center">
                <div
                  className="w-full h-3 rounded-sm"
                  style={{ backgroundColor: item.color }}
                />
                {item.label && (
                  <span className="text-[10px] text-muted-foreground mt-0.5">
                    {item.label}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 min-w-0">
        <MapContainer
          center={[27.0, 80.5]}
          zoom={7}
          minZoom={5}
          maxZoom={12}
          style={{ height: "100%", width: "100%" }}
          preferCanvas
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={boundaryGeoJSON}
            style={{
              color: "#0f4c5c",
              weight: 2.5,
              fillOpacity: 0,
            }}
          />
          <GridOverlay
            gridGeoJSON={gridGeoJSON}
            specialty={selectedSpecialty}
          />
          <FitBounds />
        </MapContainer>
      </div>
    </div>
  );
}
