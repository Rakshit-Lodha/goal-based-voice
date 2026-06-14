import { useMemo } from "react";
import { PipecatClientProvider, PipecatClientAudio } from "@pipecat-ai/client-react";
import { createClient } from "./pcClient";
import Dashboard from "./Dashboard";

export default function App() {
  const client = useMemo(() => createClient(), []);
  return (
    // client-react's bundled .d.ts declares its own PipecatClient class, nominally
    // distinct from the one we construct though identical at runtime — cast here.
    <PipecatClientProvider client={client as never}>
      <Dashboard />
      {/* Plays Maya's TTS audio coming back from the bot. */}
      <PipecatClientAudio />
    </PipecatClientProvider>
  );
}
