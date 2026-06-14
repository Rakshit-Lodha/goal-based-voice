import { useRTVIClientEvent } from "@pipecat-ai/client-react";

// client-react@1.6 ships a bundled .d.ts whose RTVIEvent enum is nominally
// distinct from @pipecat-ai/client-js's (they're the same single instance at
// runtime). Re-type the hook by the stable RTVI event-name strings so callers
// don't trip over the duplicated enum identity.
export type RtviEventName = "serverMessage" | "transportStateChanged";

export const useRtviEvent = useRTVIClientEvent as unknown as (
  event: RtviEventName,
  handler: (data: unknown) => void,
) => void;
