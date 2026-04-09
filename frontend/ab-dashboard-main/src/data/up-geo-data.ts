// Detailed Uttar Pradesh boundary polygon [lng, lat]
// ~130 points tracing the actual border clockwise from NW
export const UP_BOUNDARY: [number, number][] = [
  // NW — jagged Uttarakhand border (Saharanpur → Bijnor)
  [77.57, 30.40], [77.62, 30.35], [77.70, 30.38], [77.78, 30.32],
  [77.85, 30.35], [77.92, 30.28], [78.00, 30.32], [78.08, 30.25],
  [78.18, 30.28], [78.28, 30.20], [78.38, 30.22], [78.48, 30.15],
  [78.55, 30.18], [78.65, 30.10], [78.75, 30.05], [78.82, 29.95],
  [78.90, 29.85],
  // N — Uttarakhand / Nepal border (Terai belt)
  [79.00, 29.68], [79.12, 29.55], [79.25, 29.42], [79.40, 29.30],
  [79.55, 29.15], [79.70, 29.02], [79.85, 28.88], [80.00, 28.78],
  [80.15, 28.68], [80.30, 28.58], [80.45, 28.50], [80.58, 28.42],
  [80.72, 28.35], [80.88, 28.24],
  // Nepal border — smoother, running east-southeast
  [81.05, 28.12], [81.20, 28.02], [81.35, 27.92], [81.50, 27.82],
  [81.65, 27.72], [81.80, 27.62], [81.95, 27.55], [82.10, 27.48],
  [82.28, 27.42], [82.45, 27.36], [82.62, 27.30], [82.78, 27.22],
  [82.95, 27.15], [83.10, 27.10], [83.28, 27.05], [83.45, 27.00],
  [83.60, 26.95], [83.75, 26.88], [83.88, 26.82],
  // NE corner — Nepal/Bihar junction
  [84.00, 26.78], [84.15, 26.72], [84.28, 26.68], [84.40, 26.63],
  [84.52, 26.58], [84.63, 26.52],
  // E — Bihar border (runs south)
  [84.60, 26.38], [84.55, 26.22], [84.48, 26.08], [84.42, 25.92],
  [84.35, 25.78], [84.28, 25.62], [84.20, 25.48], [84.12, 25.35],
  [84.05, 25.22], [83.98, 25.10],
  // SE — Bihar/Jharkhand border
  [83.88, 24.98], [83.78, 24.88], [83.65, 24.78], [83.52, 24.70],
  [83.38, 24.62],
  // Sonbhadra protrusion (distinctive southern dip)
  [83.25, 24.52], [83.18, 24.38], [83.22, 24.22], [83.15, 24.10],
  [83.05, 24.05], [82.90, 24.02], [82.75, 24.05], [82.58, 24.10],
  // S — MP border heading west
  [82.40, 24.18], [82.22, 24.22], [82.05, 24.28], [81.88, 24.32],
  [81.70, 24.38], [81.52, 24.42], [81.35, 24.45], [81.18, 24.50],
  [81.00, 24.48], [80.82, 24.42], [80.65, 24.35], [80.48, 24.25],
  [80.30, 24.18], [80.12, 24.15], [79.95, 24.20],
  // SW — Bundelkhand (MP/Rajasthan border)
  [79.75, 24.28], [79.55, 24.38], [79.35, 24.50], [79.15, 24.62],
  [78.95, 24.75], [78.78, 24.88], [78.60, 25.02], [78.42, 25.18],
  [78.25, 25.35], [78.12, 25.52], [78.00, 25.68],
  // W — Rajasthan / MP border heading NW
  [77.88, 25.85], [77.78, 26.00], [77.68, 26.15], [77.58, 26.30],
  [77.48, 26.48], [77.40, 26.62],
  // W — Rajasthan border
  [77.35, 26.78], [77.32, 26.92], [77.38, 27.08], [77.42, 27.22],
  [77.48, 27.38],
  // W — Haryana border
  [77.55, 27.52], [77.58, 27.65], [77.52, 27.78], [77.45, 27.90],
  [77.38, 28.02], [77.30, 28.15], [77.22, 28.28], [77.18, 28.42],
  [77.15, 28.55],
  // NCR notch (Delhi/Haryana indent)
  [77.10, 28.62], [77.08, 28.72], [77.12, 28.82], [77.18, 28.92],
  [77.25, 29.02],
  // NW — Haryana border back up to Saharanpur
  [77.30, 29.15], [77.35, 29.30], [77.32, 29.45], [77.28, 29.58],
  [77.30, 29.72], [77.35, 29.85], [77.40, 29.98], [77.45, 30.10],
  [77.50, 30.22], [77.57, 30.40],
];

export const SPECIALTIES = [
  "Cardiology",
  "Oncology",
  "Neurology",
  "Orthopedics",
  "Kidney & Urology",
  "Gastroenterology",
  "Gynecology",
  "General Surgery & Burns",
  "Pediatrics",
] as const;

export type Specialty = (typeof SPECIALTIES)[number];

// Major UP cities with approximate [lat, lng] and specialty strengths (0-1)
// Higher = more hospitals / better coverage for that specialty
interface CityData {
  name: string;
  lat: number;
  lng: number;
  strengths: Record<Specialty, number>;
}

export const UP_CITIES: CityData[] = [
  {
    name: "Lucknow",
    lat: 26.85,
    lng: 80.95,
    strengths: {
      Cardiology: 1.0, Oncology: 0.9, Neurology: 0.95, Orthopedics: 0.9,
      "Kidney & Urology": 0.85, Gastroenterology: 0.9, Gynecology: 0.95,
      "General Surgery & Burns": 1.0, Pediatrics: 0.95,
    },
  },
  {
    name: "Noida",
    lat: 28.57,
    lng: 77.35,
    strengths: {
      Cardiology: 0.95, Oncology: 0.85, Neurology: 0.9, Orthopedics: 0.85,
      "Kidney & Urology": 0.8, Gastroenterology: 0.85, Gynecology: 0.9,
      "General Surgery & Burns": 0.9, Pediatrics: 0.85,
    },
  },
  {
    name: "Kanpur",
    lat: 26.45,
    lng: 80.35,
    strengths: {
      Cardiology: 0.75, Oncology: 0.5, Neurology: 0.6, Orthopedics: 0.8,
      "Kidney & Urology": 0.65, Gastroenterology: 0.6, Gynecology: 0.75,
      "General Surgery & Burns": 0.85, Pediatrics: 0.7,
    },
  },
  {
    name: "Varanasi",
    lat: 25.32,
    lng: 83.0,
    strengths: {
      Cardiology: 0.7, Oncology: 0.65, Neurology: 0.6, Orthopedics: 0.7,
      "Kidney & Urology": 0.55, Gastroenterology: 0.55, Gynecology: 0.7,
      "General Surgery & Burns": 0.75, Pediatrics: 0.7,
    },
  },
  {
    name: "Prayagraj",
    lat: 25.43,
    lng: 81.85,
    strengths: {
      Cardiology: 0.6, Oncology: 0.45, Neurology: 0.5, Orthopedics: 0.65,
      "Kidney & Urology": 0.5, Gastroenterology: 0.5, Gynecology: 0.6,
      "General Surgery & Burns": 0.7, Pediatrics: 0.6,
    },
  },
  {
    name: "Agra",
    lat: 27.18,
    lng: 78.02,
    strengths: {
      Cardiology: 0.6, Oncology: 0.4, Neurology: 0.45, Orthopedics: 0.7,
      "Kidney & Urology": 0.5, Gastroenterology: 0.45, Gynecology: 0.6,
      "General Surgery & Burns": 0.65, Pediatrics: 0.55,
    },
  },
  {
    name: "Meerut",
    lat: 28.98,
    lng: 77.7,
    strengths: {
      Cardiology: 0.55, Oncology: 0.35, Neurology: 0.45, Orthopedics: 0.6,
      "Kidney & Urology": 0.4, Gastroenterology: 0.4, Gynecology: 0.55,
      "General Surgery & Burns": 0.6, Pediatrics: 0.5,
    },
  },
  {
    name: "Gorakhpur",
    lat: 26.76,
    lng: 83.37,
    strengths: {
      Cardiology: 0.45, Oncology: 0.3, Neurology: 0.35, Orthopedics: 0.5,
      "Kidney & Urology": 0.35, Gastroenterology: 0.35, Gynecology: 0.5,
      "General Surgery & Burns": 0.55, Pediatrics: 0.6,
    },
  },
  {
    name: "Bareilly",
    lat: 28.37,
    lng: 79.42,
    strengths: {
      Cardiology: 0.4, Oncology: 0.25, Neurology: 0.3, Orthopedics: 0.5,
      "Kidney & Urology": 0.3, Gastroenterology: 0.3, Gynecology: 0.45,
      "General Surgery & Burns": 0.5, Pediatrics: 0.45,
    },
  },
  {
    name: "Aligarh",
    lat: 27.88,
    lng: 78.08,
    strengths: {
      Cardiology: 0.45, Oncology: 0.3, Neurology: 0.4, Orthopedics: 0.5,
      "Kidney & Urology": 0.4, Gastroenterology: 0.35, Gynecology: 0.45,
      "General Surgery & Burns": 0.5, Pediatrics: 0.45,
    },
  },
  {
    name: "Jhansi",
    lat: 25.45,
    lng: 78.57,
    strengths: {
      Cardiology: 0.3, Oncology: 0.2, Neurology: 0.2, Orthopedics: 0.4,
      "Kidney & Urology": 0.25, Gastroenterology: 0.2, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Moradabad",
    lat: 28.83,
    lng: 78.78,
    strengths: {
      Cardiology: 0.35, Oncology: 0.2, Neurology: 0.25, Orthopedics: 0.4,
      "Kidney & Urology": 0.25, Gastroenterology: 0.25, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Ghaziabad",
    lat: 28.67,
    lng: 77.42,
    strengths: {
      Cardiology: 0.7, Oncology: 0.55, Neurology: 0.6, Orthopedics: 0.7,
      "Kidney & Urology": 0.6, Gastroenterology: 0.6, Gynecology: 0.7,
      "General Surgery & Burns": 0.75, Pediatrics: 0.65,
    },
  },
  {
    name: "Mathura",
    lat: 27.49,
    lng: 77.67,
    strengths: {
      Cardiology: 0.3, Oncology: 0.15, Neurology: 0.2, Orthopedics: 0.45,
      "Kidney & Urology": 0.2, Gastroenterology: 0.25, Gynecology: 0.45,
      "General Surgery & Burns": 0.5, Pediatrics: 0.45,
    },
  },
  {
    name: "Firozabad",
    lat: 27.15,
    lng: 78.39,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.35,
      "Kidney & Urology": 0.15, Gastroenterology: 0.15, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Saharanpur",
    lat: 29.97,
    lng: 77.55,
    strengths: {
      Cardiology: 0.35, Oncology: 0.2, Neurology: 0.25, Orthopedics: 0.45,
      "Kidney & Urology": 0.25, Gastroenterology: 0.25, Gynecology: 0.4,
      "General Surgery & Burns": 0.5, Pediatrics: 0.4,
    },
  },
  {
    name: "Muzaffarnagar",
    lat: 29.47,
    lng: 77.7,
    strengths: {
      Cardiology: 0.3, Oncology: 0.15, Neurology: 0.2, Orthopedics: 0.4,
      "Kidney & Urology": 0.2, Gastroenterology: 0.2, Gynecology: 0.4,
      "General Surgery & Burns": 0.45, Pediatrics: 0.4,
    },
  },
  {
    name: "Shahjahanpur",
    lat: 27.88,
    lng: 79.91,
    strengths: {
      Cardiology: 0.25, Oncology: 0.1, Neurology: 0.15, Orthopedics: 0.35,
      "Kidney & Urology": 0.15, Gastroenterology: 0.15, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Lakhimpur Kheri",
    lat: 27.95,
    lng: 80.78,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.1, Gastroenterology: 0.1, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Faizabad/Ayodhya",
    lat: 26.77,
    lng: 82.14,
    strengths: {
      Cardiology: 0.3, Oncology: 0.15, Neurology: 0.2, Orthopedics: 0.4,
      "Kidney & Urology": 0.2, Gastroenterology: 0.2, Gynecology: 0.4,
      "General Surgery & Burns": 0.45, Pediatrics: 0.4,
    },
  },
  {
    name: "Sultanpur",
    lat: 26.26,
    lng: 82.07,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.1, Gastroenterology: 0.1, Gynecology: 0.3,
      "General Surgery & Burns": 0.35, Pediatrics: 0.3,
    },
  },
  {
    name: "Azamgarh",
    lat: 26.07,
    lng: 83.19,
    strengths: {
      Cardiology: 0.25, Oncology: 0.1, Neurology: 0.15, Orthopedics: 0.35,
      "Kidney & Urology": 0.15, Gastroenterology: 0.15, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Mirzapur",
    lat: 25.15,
    lng: 82.57,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.15, Gastroenterology: 0.1, Gynecology: 0.3,
      "General Surgery & Burns": 0.35, Pediatrics: 0.3,
    },
  },
  {
    name: "Etawah",
    lat: 26.78,
    lng: 79.02,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.15, Gastroenterology: 0.1, Gynecology: 0.3,
      "General Surgery & Burns": 0.35, Pediatrics: 0.3,
    },
  },
  {
    name: "Rampur",
    lat: 28.81,
    lng: 79.03,
    strengths: {
      Cardiology: 0.25, Oncology: 0.1, Neurology: 0.15, Orthopedics: 0.35,
      "Kidney & Urology": 0.15, Gastroenterology: 0.15, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Sitapur",
    lat: 27.57,
    lng: 80.68,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.1, Gastroenterology: 0.1, Gynecology: 0.35,
      "General Surgery & Burns": 0.4, Pediatrics: 0.35,
    },
  },
  {
    name: "Unnao",
    lat: 26.55,
    lng: 80.49,
    strengths: {
      Cardiology: 0.25, Oncology: 0.1, Neurology: 0.15, Orthopedics: 0.35,
      "Kidney & Urology": 0.15, Gastroenterology: 0.15, Gynecology: 0.4,
      "General Surgery & Burns": 0.45, Pediatrics: 0.4,
    },
  },
  {
    name: "Basti",
    lat: 26.80,
    lng: 82.76,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.1, Gastroenterology: 0.1, Gynecology: 0.3,
      "General Surgery & Burns": 0.35, Pediatrics: 0.35,
    },
  },
  {
    name: "Deoria",
    lat: 26.50,
    lng: 83.78,
    strengths: {
      Cardiology: 0.2, Oncology: 0.1, Neurology: 0.1, Orthopedics: 0.3,
      "Kidney & Urology": 0.1, Gastroenterology: 0.1, Gynecology: 0.3,
      "General Surgery & Burns": 0.35, Pediatrics: 0.35,
    },
  },
];

// --- Utility functions ---

/** Ray-casting point-in-polygon test */
export function isInsidePolygon(
  point: [number, number],
  polygon: [number, number][]
): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const [xi, yi] = polygon[i];
    const [xj, yj] = polygon[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) {
      inside = !inside;
    }
  }
  return inside;
}

/** Haversine distance in km */
export function haversineKm(
  lat1: number,
  lng1: number,
  lat2: number,
  lng2: number
): number {
  const R = 6371;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLng = ((lng2 - lng1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Compute coverage score (0-1) for a grid cell based on nearby city hospitals */
export function computeCoverage(
  lat: number,
  lng: number,
  specialty: Specialty
): number {
  let maxScore = 0;
  for (const city of UP_CITIES) {
    const dist = haversineKm(lat, lng, city.lat, city.lng);
    const strength = city.strengths[specialty];
    // Exponential decay: 50km half-distance
    const score = strength * Math.exp(-dist / 50);
    if (score > maxScore) maxScore = score;
  }
  return Math.min(1, maxScore);
}

/** Coverage score → fill color (red→yellow→green) */
export function coverageColor(score: number): string {
  if (score > 0.8) return "#1a9850";
  if (score > 0.6) return "#66bd63";
  if (score > 0.4) return "#a6d96a";
  if (score > 0.25) return "#fee08b";
  if (score > 0.12) return "#fc8d59";
  return "#d73027";
}
