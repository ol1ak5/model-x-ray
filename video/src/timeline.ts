import pace from "./pace.json";
import voice from "./voice.json";
import { FPS } from "./theme";

export type SceneName = "open" | "stakes" | "who" | "ai" | "reveal" | "demo" | "engine" | "proof" | "close";

export type Line = { id: string; text: string; start: number; frames: number };

export type Scene = { name: SceneName; from: number; duration: number; lines: Line[]; dark: boolean };

const PACE = pace.scenes as Record<SceneName, { lead: number; gap: number; tail: number; dark: boolean }>;

export const ORDER = pace.order as SceneName[];

function build(): Scene[] {
  let cursor = 0;
  return ORDER.map((name) => {
    const pace = PACE[name];
    let at = pace.lead;
    const lines = voice.lines
      .filter((line) => line.scene === name)
      .map((line) => {
        const frames = Math.ceil(line.seconds * FPS);
        const placed = { id: line.id, text: line.text, start: at, frames };
        at += frames + pace.gap;
        return placed;
      });
    const duration = at - pace.gap + pace.tail;
    const scene = { name, from: cursor, duration, lines, dark: pace.dark };
    cursor += duration;
    return scene;
  });
}

export const SCENES = build();

export const TOTAL = SCENES.reduce((sum, scene) => sum + scene.duration, 0);

export function lineOf(scene: Scene, index: number): Line {
  return scene.lines[index];
}
