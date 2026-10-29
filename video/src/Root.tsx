import { Composition } from "remotion";
import { Film } from "./Film";
import { FPS, HEIGHT, WIDTH } from "./theme";
import { TOTAL } from "./timeline";

export function Root() {
  return <Composition id="Film" component={Film} durationInFrames={TOTAL} fps={FPS} width={WIDTH} height={HEIGHT} defaultProps={{ camera: "path" as const }} />;
}
