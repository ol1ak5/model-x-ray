import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from "remotion";
import { C, FONT } from "./theme";
import { SCENES } from "./timeline";
import type { Scene, SceneName } from "./timeline";
import { CameraStyle, clamp } from "./parts";
import type { Camera } from "./parts";
import { Ai, Open, Stakes, Who } from "./scenes/Story";
import { Close, Demo, Engine, Proof, Reveal } from "./scenes/Product";

const VIEWS: Record<SceneName, (props: { scene: Scene }) => JSX.Element> = { open: Open, stakes: Stakes, who: Who, ai: Ai, reveal: Reveal, demo: Demo, engine: Engine, proof: Proof, close: Close };

const CUT = 10;

function Caption({ text, frames, dark }: { text: string; frames: number; dark: boolean }) {
  const frame = useCurrentFrame();
  const p = Math.min(clamp(frame, 0, 6), clamp(frame, frames - 4, frames + 4, 1, 0));
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 30, pointerEvents: "none" }}>
      <div
        style={{
          maxWidth: 1500,
          textAlign: "center",
          fontFamily: FONT,
          fontWeight: 500,
          fontSize: 34,
          lineHeight: 1.3,
          color: dark ? "#fff" : C.ink,
          opacity: p,
          textShadow: dark ? "0 2px 12px rgba(0,0,0,0.9), 0 0 2px rgba(0,0,0,0.9)" : "0 0 10px #fff, 0 0 4px #fff, 0 0 2px #fff",
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
}

export function Film({ camera }: { camera: Camera }) {
  return (
    <CameraStyle.Provider value={camera}>
    <AbsoluteFill style={{ background: "#000" }}>
      <Audio src={staticFile("music.wav")} volume={0.3} />
      {SCENES.map((scene) => {
        const View = VIEWS[scene.name];
        return (
          <Sequence key={scene.name} from={scene.from} durationInFrames={scene.duration} name={scene.name}>
            <SceneFrame scene={scene}>
              <View scene={scene} />
            </SceneFrame>
          </Sequence>
        );
      })}
      {SCENES.flatMap((scene) =>
        scene.lines.map((line) => (
          <Sequence key={line.id} from={scene.from + line.start} durationInFrames={line.frames + 8} name={line.id}>
            <Audio src={staticFile(`voice/${line.id}.wav`)} />
            <Caption text={line.text} frames={line.frames + 4} dark={scene.dark} />
          </Sequence>
        )),
      )}
    </AbsoluteFill>
    </CameraStyle.Provider>
  );
}

function SceneFrame({ scene, children }: { scene: Scene; children: JSX.Element }) {
  const frame = useCurrentFrame();
  const enter = clamp(frame, 0, CUT);
  const zoom = 1.04 - 0.04 * enter;
  return <AbsoluteFill style={{ transform: `scale(${zoom})`, opacity: scene.name === "open" ? clamp(frame, 0, 20) : 1 }}>{children}</AbsoluteFill>;
}
