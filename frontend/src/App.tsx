import React from "react";
import MapGL from "./components/MapGL";

export default function App() {
  return (
    <div
      style={{
        fontFamily: `"Inter", sans-serif`,
        minHeight: "100vh",
        background: "linear-gradient(135deg, #1e1e2f, #2a2a3d)",
        color: "#e0e0e0",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "flex-start",
        padding: "2rem",
      }}
    >
      <h1 style={{ fontSize: "2.2rem", marginBottom: "0.75rem" }}>Buildable Land Analysis</h1>
      <p style={{ marginBottom: "1.5rem", maxWidth: 760, textAlign: "center", opacity: 0.9 }}>
        Draw a parcel, then carve out excluded areas and restore added-back areas. The buildable total and breakdown update live.
      </p>
      <div style={{ width: "100%", maxWidth: "1200px" }}>
        <MapGL />
      </div>

    </div>
  );
}

