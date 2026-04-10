import { useState, useMemo, useEffect } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import {
  SPECIALTIES,
  UP_CITIES,
  UP_BOUNDARY_GEOJSON,
  haversineKm,
  type Specialty,
} from "@/data/up-geo-data";
import popGridRaw from "@/data/up_population_grid.json";

// Cities are considered to offer a specialty if their strength >= this threshold
const SPECIALTY_PRESENCE_THRESHOLD = 0.3;

interface PopCell {
  lat: number;
  lng: number;
  pop: number;
}

interface PopGrid {
  cell_size_deg: number;
  cells: PopCell[];
}

const POP_GRID = popGridRaw as PopGrid;
const BOUNDARY_GEOJSON = UP_BOUNDARY_GEOJSON;

/** For each specialty, list cities that offer it (strength >= threshold) */
const SPECIALTY_CITIES: Record<Specialty, { lat: number; lng: number }[]> =
  (() => {
    const result = {} as Record<Specialty, { lat: number; lng: number }[]>;
    for (const s of SPECIALTIES) {
      result[s] = UP_CITIES.filter(
        (c) => c.strengths[s] >= SPECIALTY_PRESENCE_THRESHOLD
      ).map((c) => ({ lat: c.lat, lng: c.lng }));
    }
    return result;
  })();

/** Compute distance (km) to nearest city offering the specialty */
function distanceToNearestSpecialty(
  lat: number,
  lng: number,
  specialty: Specialty
): number {
  const cities = SPECIALTY_CITIES[specialty];
  if (cities.length === 0) return 500;
  let minDist = Infinity;
  for (const c of cities) {
    const d = haversineKm(lat, lng, c.lat, c.lng);
    if (d < minDist) minDist = d;
  }
  return minDist;
}

/** Pre-compute per-cell scores for a specialty, return GeoJSON */
function buildGridGeoJSON(
  specialty: Specialty,
  cellSize: number
): GeoJSON.FeatureCollection {
  // First pass: compute raw scores (pop × distance) and find max for normalization
  const rawScores: number[] = new Array(POP_GRID.cells.length);
  const dists: number[] = new Array(POP_GRID.cells.length);
  let maxScore = 0;
  for (let i = 0; i < POP_GRID.cells.length; i++) {
    const cell = POP_GRID.cells[i];
    const dist = distanceToNearestSpecialty(cell.lat, cell.lng, specialty);
    dists[i] = dist;
    const score = cell.pop * dist;
    rawScores[i] = score;
    if (score > maxScore) maxScore = score;
  }

  // Build features with normalized scores
  const half = cellSize / 2;
  const features: GeoJSON.Feature[] = [];
  for (let i = 0; i < POP_GRID.cells.length; i++) {
    const cell = POP_GRID.cells[i];
    const normalized = maxScore > 0 ? rawScores[i] / maxScore : 0;
    features.push({
      type: "Feature",
      properties: { score: normalized, raw: rawScores[i], pop: cell.pop, dist: dists[i] },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [cell.lng - half, cell.lat - half],
            [cell.lng + half, cell.lat - half],
            [cell.lng + half, cell.lat + half],
            [cell.lng - half, cell.lat + half],
            [cell.lng - half, cell.lat - half],
          ],
        ],
      },
    });
  }

  return { type: "FeatureCollection", features };
}

/** Score (0-1) → red gradient (low = transparent, high = bright red) */
function underserviceColor(score: number): string {
  // Log-ish scaling — the top 5% should be saturated red
  if (score > 0.6) return "#67000d";
  if (score > 0.4) return "#a50f15";
  if (score > 0.25) return "#cb181d";
  if (score > 0.15) return "#ef3b2c";
  if (score > 0.08) return "#fb6a4a";
  if (score > 0.04) return "#fc9272";
  if (score > 0.02) return "#fcbba1";
  if (score > 0.01) return "#fee0d2";
  return "#fff5f0";
}

function underserviceOpacity(score: number): number {
  if (score < 0.005) return 0.15;
  if (score < 0.02) return 0.35;
  if (score < 0.1) return 0.5;
  return 0.65;
}

/** Imperative grid layer that updates style when specialty changes */
function GridOverlay({
  gridGeoJSON,
}: {
  gridGeoJSON: GeoJSON.FeatureCollection;
}) {
  const map = useMap();

  useEffect(() => {
    const renderer = L.canvas();
    const layer = L.geoJSON(gridGeoJSON, {
      style: (feature) => {
        const score = (feature?.properties?.score as number) ?? 0;
        return {
          fillColor: underserviceColor(score),
          fillOpacity: underserviceOpacity(score),
          weight: 0,
          color: "transparent",
          interactive: true,
        };
      },
      renderer,
      onEachFeature: (feature, sublayer) => {
        const pop = Math.round((feature.properties?.pop as number) ?? 0);
        const dist = (feature.properties?.dist as number) ?? 0;
        if (pop > 0) {
          const distLabel = dist < 10 ? dist.toFixed(1) : Math.round(dist).toString();
          (sublayer as L.Path).bindTooltip(
            `<strong>${pop.toLocaleString()}</strong> people<br/><strong>${distLabel} km</strong> to nearest hospital`,
            { sticky: true, direction: "top", offset: [0, -4], opacity: 0.9 }
          );
        }
      },
    }).addTo(map);

    return () => {
      map.removeLayer(layer);
    };
  }, [map, gridGeoJSON]);

  return null;
}

/** Fit map bounds to UP on mount, then bump zoom by 1 */
function FitBounds() {
  const map = useMap();
  useEffect(() => {
    const layer = L.geoJSON(BOUNDARY_GEOJSON);
    map.fitBounds(layer.getBounds());
    map.setZoom(map.getZoom() + 1);
  }, [map]);
  return null;
}

const MOST_UNDERSERVED: Record<Specialty, { block: string; district: string }[]> = {
  "Cardiology": [
    { block: "Obra", district: "Sonbhadra" },
    { block: "Tindwari", district: "Banda" },
    { block: "Nautanwa", district: "Maharajganj" },
  ],
  "Oncology": [
    { block: "Ghurma", district: "Shrawasti" },
    { block: "Sihund", district: "Mahoba" },
    { block: "Baberu", district: "Banda" },
  ],
  "Neurology": [
    { block: "Duddhi", district: "Sonbhadra" },
    { block: "Meja", district: "Prayagraj" },
    { block: "Babhnan", district: "Gonda" },
  ],
  "Orthopedics": [
    { block: "Huzurpur", district: "Shrawasti" },
    { block: "Charkhari", district: "Mahoba" },
    { block: "Churk", district: "Sonbhadra" },
  ],
  "Kidney & Urology": [
    { block: "Rajapur", district: "Chitrakoot" },
    { block: "Obra", district: "Sonbhadra" },
    { block: "Tambaur", district: "Ballia" },
  ],
  "Gastroenterology": [
    { block: "Manikpur", district: "Chitrakoot" },
    { block: "Atraula", district: "Ballia" },
    { block: "Gilaula", district: "Shrawasti" },
  ],
  "Gynecology": [
    { block: "Ghurma", district: "Shrawasti" },
    { block: "Sihund", district: "Mahoba" },
    { block: "Kaptanganj", district: "Kushinagar" },
  ],
  "General Surgery & Burns": [
    { block: "Obra", district: "Sonbhadra" },
    { block: "Baberu", district: "Banda" },
    { block: "Babhnan", district: "Gonda" },
  ],
  "Pediatrics": [
    { block: "Tulsipur", district: "Balrampur" },
    { block: "Ghurma", district: "Shrawasti" },
    { block: "Charkhari", district: "Mahoba" },
  ],
};

const LEGEND_ITEMS = [
  { label: "Low", color: "#fee0d2" },
  { label: "", color: "#fc9272" },
  { label: "", color: "#fb6a4a" },
  { label: "", color: "#ef3b2c" },
  { label: "", color: "#cb181d" },
  { label: "High", color: "#67000d" },
];

export function GeographicCoverage() {
  const [selectedSpecialty, setSelectedSpecialty] =
    useState<Specialty>("Cardiology");

  const gridGeoJSON = useMemo(
    () => buildGridGeoJSON(selectedSpecialty, POP_GRID.cell_size_deg),
    [selectedSpecialty]
  );

  return (
    <div className="flex flex-1 min-h-0">
      {/* Specialty sidebar */}
      <div className="w-64 shrink-0 border-r border-border bg-[hsl(var(--sidebar-bg))] flex flex-col">
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
          <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-1">
            Underservice
          </div>
          <div className="text-[10px] text-muted-foreground mb-2">
            Population × distance to nearest hospital
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
      <div className="flex-1 min-w-0 relative">
        {/* Underserved blocks panel */}
        <div className="absolute top-3 right-3 z-[1000] bg-white/90 backdrop-blur-sm border border-border rounded-lg shadow-md px-4 py-3 max-w-[220px]">
          <p className="text-[11px] font-semibold text-foreground leading-snug mb-2">
            Most underserved blocks, by population and hospital coverage:
          </p>
          <ol className="space-y-1">
            {MOST_UNDERSERVED[selectedSpecialty].map((item, i) => (
              <li key={i} className="flex items-baseline gap-1.5 text-[11px]">
                <span className="text-muted-foreground font-medium w-3 shrink-0">{i + 1}.</span>
                <span>
                  <span className="font-medium text-foreground">{item.block}</span>
                  <span className="text-muted-foreground">, {item.district}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>

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
            data={BOUNDARY_GEOJSON}
            style={{
              color: "#0f4c5c",
              weight: 2,
              fillOpacity: 0,
            }}
          />
          <GridOverlay gridGeoJSON={gridGeoJSON} />
          <FitBounds />
        </MapContainer>
      </div>
    </div>
  );
}
