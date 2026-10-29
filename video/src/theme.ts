import { loadFont as loadSans } from "@remotion/google-fonts/Geist";
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";

const sans = loadSans("normal", { weights: ["400", "500", "600", "700", "800"], subsets: ["latin"] });
const mono = loadMono("normal", { weights: ["400", "500", "600"], subsets: ["latin"] });

export const FONT = sans.fontFamily;
export const MONO = mono.fontFamily;

export const C = {
  ink: "#111512",
  muted: "#5c645e",
  faint: "#8a918c",
  line: "#e4e6e2",
  soft: "#f6f8f6",
  g1: "#0a4a29",
  g2: "#0d5c33",
  g3: "#12814a",
  bright: "#4ade80",
  gsoft: "#edf5f0",
  red: "#c22f2f",
  redsoft: "#fbeeee",
  blue: "#2563eb",
  night: "#07110b",
};

export const BAND = `radial-gradient(1400px 700px at 85% 0%, rgba(74, 222, 128, 0.30), transparent 70%), linear-gradient(135deg, ${C.g1}, ${C.g2} 55%, ${C.g3})`;

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
