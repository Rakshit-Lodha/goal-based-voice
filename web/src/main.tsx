import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";

// No StrictMode: its dev double-mount would dispose/recreate the WebRTC client.
createRoot(document.getElementById("root")!).render(<App />);
