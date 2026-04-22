import { useState, useMemo, useEffect } from "react";
import { MapContainer, TileLayer, GeoJSON, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { Search, ChevronRight, Plus, Minus } from "lucide-react";
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

  const half = cellSize / 2 * 1.05; // slight overlap to eliminate sub-pixel gaps
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

/** Score (0-1) -> dark purple sequential ramp */
function underserviceColor(score: number): string {
  if (score > 0.6) return "#2A0F47";
  if (score > 0.4) return "#3F1D6B";
  if (score > 0.25) return "#54278F";
  if (score > 0.15) return "#756BB1";
  if (score > 0.08) return "#9E9AC8";
  if (score > 0.04) return "#BCBDDC";
  if (score > 0.02) return "#BCBDDC";
  if (score > 0.01) return "#BCBDDC";
  return "#BCBDDC";
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

/** Fit map bounds to UP on mount */
function FitBounds() {
  const map = useMap();
  useEffect(() => {
    // Center on UP and set a fixed zoom level
    map.setView([27.0, 80.5], 6);
  }, [map]);
  return null;
}

/** Store map ref for external zoom controls */
function MapRefSetter({ onMap }: { onMap: (map: L.Map) => void }) {
  const map = useMap();
  useEffect(() => { onMap(map); }, [map, onMap]);
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

const LEGEND_COLORS = ["#BCBDDC", "#9E9AC8", "#756BB1", "#54278F", "#3F1D6B", "#2A0F47"];

export function GeographicCoverage() {
  const [selectedSpecialty, setSelectedSpecialty] = useState<Specialty>("Cardiology");
  const [specialtySearch, setSpecialtySearch] = useState("");
  const [mapRef, setMapRef] = useState<L.Map | null>(null);

  const gridGeoJSON = useMemo(
    () => buildGridGeoJSON(selectedSpecialty, POP_GRID.cell_size_deg),
    [selectedSpecialty]
  );

  const filteredSpecialties = SPECIALTIES.filter((s) =>
    s.toLowerCase().includes(specialtySearch.toLowerCase())
  );

  return (
    <div className="flex flex-1 min-h-0">
      {/* Specialty list column */}
      <div className="w-64 border-r border-line bg-white/40 flex flex-col">
        <div className="px-4 pt-6 pb-3 border-b border-line">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-design mb-3">
            Specialty
          </div>
          <div className="relative">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-design" />
            <input
              value={specialtySearch}
              onChange={(e) => setSpecialtySearch(e.target.value)}
              placeholder="Search specialties"
              className="w-full pl-7 pr-3 py-1.5 text-[12px] bg-ivory border border-line rounded-md outline-none focus:border-ink/30 placeholder:text-muted-design text-ink"
            />
          </div>
        </div>
        <div className="flex-1 overflow-y-auto py-2">
          {filteredSpecialties.length === 0 ? (
            <div className="px-4 py-3 text-[12px] text-muted-design italic">No matches</div>
          ) : (
            filteredSpecialties.map((s) => {
              const active = selectedSpecialty === s;
              return (
                <button
                  key={s}
                  onClick={() => setSelectedSpecialty(s)}
                  className={`w-full text-left px-4 py-2 text-[13px] transition-colors flex items-center justify-between group ${
                    active
                      ? "bg-accent-saffron/10 text-ink font-medium border-l-2 border-accent-saffron"
                      : "text-ink hover:bg-ink/[0.03] border-l-2 border-transparent"
                  }`}
                >
                  <span>{s}</span>
                  {active && <ChevronRight size={12} className="text-accent-saffron" />}
                </button>
              );
            })
          )}
        </div>
      </div>

      {/* Map column */}
      <div className="flex-1 relative bg-ivory overflow-hidden">
        {/* Map header overlay */}
        <div className="absolute top-0 left-0 right-0 z-[1000] bg-gradient-to-b from-white via-white/95 to-white/0 px-6 pt-5 pb-10 pointer-events-none">
          <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-accent-saffron mb-1">
            Speciality Coverage · {selectedSpecialty}
          </div>
          <h1 className="font-display text-[22px] tracking-tight text-ink">
            Where {selectedSpecialty} care is reaching Uttar Pradesh
          </h1>
          <p className="text-[12px] text-muted-design mt-1 max-w-lg leading-snug">
            Each block shaded by population × distance to the nearest empanelled {selectedSpecialty.toLowerCase()} hospital.
          </p>
        </div>

        {/* Map */}
        <MapContainer
          center={[27.0, 80.5]}
          zoom={8}
          minZoom={5}
          maxZoom={12}
          style={{ height: "100%", width: "100%" }}
          preferCanvas
          zoomControl={false}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={BOUNDARY_GEOJSON}
            style={{
              color: "#1F4E5F",
              weight: 2,
              fillOpacity: 0,
            }}
          />
          <GridOverlay gridGeoJSON={gridGeoJSON} />
          <FitBounds />
          <MapRefSetter onMap={setMapRef} />
        </MapContainer>

        {/* Custom zoom controls */}
        <div className="absolute left-4 top-28 z-[1000] bg-white border border-line rounded-md shadow-sm flex flex-col">
          <button
            onClick={() => mapRef?.zoomIn()}
            className="w-8 h-8 flex items-center justify-center hover:bg-ivory border-b border-line"
            aria-label="Zoom in"
          >
            <Plus size={14} className="text-ink" />
          </button>
          <button
            onClick={() => mapRef?.zoomOut()}
            className="w-8 h-8 flex items-center justify-center hover:bg-ivory"
            aria-label="Zoom out"
          >
            <Minus size={14} className="text-ink" />
          </button>
        </div>

        {/* Underserved blocks panel */}
        <div className="absolute top-28 right-4 z-[1000] w-60 bg-white border border-line rounded-lg shadow-sm overflow-hidden">
          <div className="px-3 py-2 border-b border-line bg-ivory/40">
            <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-ink">
              Most underserved blocks
            </div>
            <div className="text-[10px] text-muted-design mt-0.5">
              by population × distance to nearest hospital
            </div>
          </div>
          <div className="divide-y divide-line">
            {MOST_UNDERSERVED[selectedSpecialty].map((b, i) => (
              <div key={i} className="px-3 py-2 flex items-center gap-2.5">
                <div className="text-[10px] font-semibold text-muted-design w-3">
                  {i + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="text-[12px] text-ink font-medium leading-tight">{b.block}</div>
                  <div className="text-[10px] text-muted-design">{b.district}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Legend — amber-to-brown ramp */}
        <div className="absolute bottom-4 right-4 z-[1000] bg-white border border-line rounded-md shadow-sm px-3 py-2.5">
          <div className="text-[10px] font-semibold uppercase tracking-[0.1em] text-ink mb-1.5">
            Underservice
          </div>
          <div className="text-[10px] text-muted-design mb-2 leading-tight">
            Population × distance to nearest hospital
          </div>
          <div className="flex items-center gap-0 h-3 w-40">
            {LEGEND_COLORS.map((c, i) => (
              <div key={i} className="flex-1 h-full" style={{ background: c }} />
            ))}
          </div>
          <div className="flex justify-between text-[10px] text-muted-design mt-1">
            <span>Low</span>
            <span>High</span>
          </div>
        </div>
      </div>
    </div>
  );
}
