import React, { useEffect, useRef, useState } from "react";
import maplibregl, { Map as MapLibre, StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import MapboxDraw from "@mapbox/mapbox-gl-draw";
import "@mapbox/mapbox-gl-draw/dist/mapbox-gl-draw.css";

type LiveAnalyzeResponse = {
  parcel_acres: number;
  carve_out_acres: number;
  restore_acres: number;
  buildable_acres: number;
  breakdown: Record<string, number>;
  parcel_geojson: GeoJSON.Geometry | null;
  carve_outs_geojson: GeoJSON.Geometry[];
  buildable_geojson?: GeoJSON.Geometry;
};

const MAP_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: { type: "raster", tiles: ["https://a.tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: '© OSM contributors' },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

const DRAW_STYLES = [
  { 'id': 'gl-draw-polygon-fill-inactive', 'type': 'fill', 'filter': ['all', ['==', 'active', 'false'], ['==', '$type', 'Polygon'], ['!=', 'mode', 'static']], 'paint': { 'fill-color': '#3bb2d0', 'fill-outline-color': '#3bb2d0', 'fill-opacity': 0.1 } },
  { 'id': 'gl-draw-polygon-fill-active', 'type': 'fill', 'filter': ['all', ['==', 'active', 'true'], ['==', '$type', 'Polygon']], 'paint': { 'fill-color': '#fbb03b', 'fill-outline-color': '#fbb03b', 'fill-opacity': 0.1 } },
  { 'id': 'gl-draw-polygon-stroke-active', 'type': 'line', 'filter': ['all', ['==', 'active', 'true'], ['==', '$type', 'Polygon']], 'layout': { 'line-cap': 'round', 'line-join': 'round' }, 'paint': { 'line-color': '#fbb03b', 'line-width': 2 } },
  { 'id': 'gl-draw-polygon-and-line-vertex-active', 'type': 'circle', 'filter': ['all', ['==', 'meta', 'vertex'], ['==', '$type', 'Point'], ['!=', 'mode', 'static']], 'paint': { 'circle-radius': 5, 'circle-color': '#fbb03b' } }
];

function getBBox(geometry: GeoJSON.Geometry): [[number, number], [number, number]] {
    let coords: number[][] = [];
    if (geometry.type === "Polygon") coords = geometry.coordinates[0];
    else if (geometry.type === "MultiPolygon") coords = geometry.coordinates.flatMap(p => p[0]);
    if (!coords || coords.length === 0) return [[-180, -90], [180, 90]];
    let minX = coords[0][0], minY = coords[0][1], maxX = coords[0][0], maxY = coords[0][1];
    for (const [x, y] of coords) {
        if (x < minX) minX = x; if (y < minY) minY = y;
        if (x > maxX) maxX = x; if (y > maxY) maxY = y;
    }
    return [[minX, minY], [maxX, maxY]];
}

export default function MapGL() {
  const mapContainer = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibre | null>(null);
  const drawRef = useRef<MapboxDraw | null>(null);

  const [parcelId, setParcelId] = useState<string>("0");
  const [parcelIdInput, setParcelIdInput] = useState<string>("0");
  const [loading, setLoading] = useState<boolean>(false);
  const [mapReady, setMapReady] = useState<boolean>(false);
  const [analysis, setAnalysis] = useState<LiveAnalyzeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drawMode, setDrawMode] = useState<"carve" | "restore">("carve");

  const drawModeRef = useRef(drawMode);
  useEffect(() => { drawModeRef.current = drawMode; }, [drawMode]);

  const [buffers, setBuffers] = useState({ wetlands: 30, floodzones: 0, transmission: 20, buildings: 5 });

  const to3857 = (lng: number, lat: number): [number, number] => {
    const x = (lng * 20037508.34) / 180;
    let y = Math.log(Math.tan(((90 + lat) * Math.PI) / 360)) / (Math.PI / 180);
    y = (y * 20037508.34) / 180;
    return [x, y];
  };

  const recalculate = async () => {
    if (!drawRef.current || !analysis?.parcel_geojson) return;
    const features = drawRef.current.getAll().features;
    const parcelRing3857 = (analysis.parcel_geojson as any).coordinates[0].map((pt: any) => to3857(pt[0], pt[1]));
    const body = {
        parcel_id: parcelId,
        parcel: { ring: parcelRing3857 },
        carve_outs: features.filter(f => f.properties?.mode !== "restore").map(f => ({ ring: (f.geometry as any).coordinates[0].map((pt: any) => to3857(pt[0], pt[1])) })),
        restores: features.filter(f => f.properties?.mode === "restore").map(f => ({ ring: (f.geometry as any).coordinates[0].map((pt: any) => to3857(pt[0], pt[1])) })),
        wetland_buffer_m: buffers.wetlands, flood_buffer_m: buffers.floodzones, transmission_buffer_m: buffers.transmission, building_buffer_m: buffers.buildings
    };
    try {
      const resp = await fetch("/api/buildable-area", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const result = await resp.json();
      setAnalysis(prev => prev ? { ...prev, ...result } : null);
    } catch (e) {}
  };

  const recalculateRef = useRef(recalculate);
  useEffect(() => { recalculateRef.current = recalculate; });

  useEffect(() => {
    if (!mapContainer.current) return;
    const map = new maplibregl.Map({ container: mapContainer.current, style: MAP_STYLE, center: [-97.7431, 30.2672], zoom: 12 });
    const draw = new MapboxDraw({ displayControlsDefault: false, controls: { polygon: true, trash: true }, styles: DRAW_STYLES });
    map.addControl(draw);
    mapRef.current = map;
    drawRef.current = draw;
    map.on("load", () => setMapReady(true));

    map.on("draw.create", (e) => {
        const feature = e.features[0];
        if (feature) draw.setFeatureProperty(feature.id as string, "mode", drawModeRef.current);
        recalculateRef.current();
    });
    map.on("draw.update", () => recalculateRef.current());
    map.on("draw.delete", () => recalculateRef.current());

    return () => map.remove();
  }, []);

  const loadAnalysis = async () => {
    if (!mapReady || !mapRef.current || !parcelId) return;
    setLoading(true);
    setError(null);
    try {
      const url = `/api/live-analyze/${parcelId}?wetland_buffer_m=${buffers.wetlands}&flood_buffer_m=${buffers.floodzones}&transmission_buffer_m=${buffers.transmission}&building_buffer_m=${buffers.buildings}`;
      const resp = await fetch(url);
      const data: LiveAnalyzeResponse = await resp.json();
      if (!data.parcel_geojson) { setError(`Parcel ID "${parcelId}" not found.`); setAnalysis(null); return; }
      setAnalysis(data);
      renderData(data);
      mapRef.current.fitBounds(getBBox(data.parcel_geojson), { padding: 80, maxZoom: 17 });
    } catch (e) { setError("Connection failed."); } finally { setLoading(false); }
  };

  useEffect(() => { loadAnalysis(); }, [parcelId, mapReady, buffers]);

  // Clear any manually-drawn carve-out/restore shapes whenever the parcel
  // changes — otherwise old shapes drawn relative to a previous parcel's
  // location get sent along with the new parcel and never spatially overlap
  // it, silently producing zero carve-out/restore area.
  useEffect(() => {
    if (drawRef.current) {
      drawRef.current.deleteAll();
    }
  }, [parcelId]);

  const renderData = (data: LiveAnalyzeResponse) => {
    if (!mapRef.current || !mapReady || !data.parcel_geojson) return;
    addGeoJSONLayer("parcel-base", data.parcel_geojson, "rgba(74, 144, 226, 0.1)", 1, "#4A90E2", 3);
    const exSource: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: (data.carve_outs_geojson || []).map(g => ({ type: "Feature", geometry: g, properties: {} })) };
    if (exSource.features.length > 0) addGeoJSONLayer("constraints", exSource, "rgba(231, 76, 60, 0.3)", 1, "#E74C3C", 1);
    else removeLayer("constraints");
    if (data.buildable_geojson) addGeoJSONLayer("buildable-result", data.buildable_geojson, "rgba(39, 174, 96, 0.5)", 1, "#1e8449", 2);
    else removeLayer("buildable-result");
  };

  const removeLayer = (id: string) => {
    const map = mapRef.current; if (!map || !mapReady) return;
    try { if (map.getLayer(id)) map.removeLayer(id); if (map.getLayer(`${id}-stroke`)) map.removeLayer(`${id}-stroke`); if (map.getSource(`${id}-source`)) map.removeSource(`${id}-source`); } catch (e) {}
  };

  const addGeoJSONLayer = (id: string, data: any, color: string, opacity: number, strokeColor?: string, strokeWidth?: number) => {
    const map = mapRef.current; if (!map || !mapReady) return;
    const sourceId = `${id}-source`;
    removeLayer(id);
    map.addSource(sourceId, { type: "geojson", data });
    map.addLayer({ id, type: "fill", source: sourceId, paint: { 'fill-color': color, 'fill-opacity': opacity } });
    if (strokeColor) map.addLayer({ id: `${id}-stroke`, type: "line", source: sourceId, paint: { 'line-color': strokeColor, 'line-width': strokeWidth || 1 } });
  };

  useEffect(() => {
    if (analysis) renderData(analysis);
  }, [analysis?.buildable_geojson, analysis?.carve_outs_geojson]);

  return (
    <div style={{ width: "100%", height: "85vh", position: "relative", borderRadius: "16px", overflow: "hidden", border: "1px solid #333", boxShadow: "0 20px 50px rgba(0,0,0,0.5)" }}>
      <div ref={mapContainer} style={{ width: "100%", height: "100%" }} />
      <div style={{ position: "absolute", top: "20px", left: "20px", width: "360px", background: "rgba(10, 10, 20, 0.98)", padding: "24px", borderRadius: "16px", color: "#fff", zIndex: 1, maxHeight: "90%", overflowY: "auto", border: "1px solid rgba(255,255,255,0.1)", backdropFilter: "blur(10px)" }}>
        <h2 style={{ margin: "0 0 5px 0", fontSize: "1.4rem" }}>Land Analysis Panel</h2>
        <div style={{ fontSize: "0.8rem", color: "#888", marginBottom: "20px" }}>Web Mercator (EPSG:3857) Planar Formula</div>
        <div style={{ display: "flex", gap: "8px", marginBottom: "25px" }}>
          <input value={parcelIdInput} onChange={e => setParcelIdInput(e.target.value)} placeholder="Parcel ID" style={{ flex: 1, padding: "12px", borderRadius: "10px", background: "#000", color: "#fff", border: "1px solid #444" }} />
          <button onClick={() => setParcelId(parcelIdInput)} style={{ padding: "12px 20px", borderRadius: "10px", background: "#4A90E2", color: "#fff", border: "none", fontWeight: "bold", cursor: "pointer" }}>Analyze</button>
        </div>
        {analysis ? (
          <div style={{ background: "rgba(255,255,255,0.05)", padding: "20px", borderRadius: "14px", marginBottom: "25px" }}>
             {Object.entries(analysis.breakdown).map(([label, val]) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", fontSize: label.includes("Final") ? "1.2rem" : "0.95rem", fontWeight: label.includes("Final") ? 800 : 400 }}>
                    <span style={{ color: label.includes("Removed") ? "#E74C3C" : "#aaa" }}>{label}:</span>
                    <span style={{ color: label.includes("Final") ? "#27AE60" : "#fff" }}>{val} ac</span>
                </div>
             ))}
          </div>
        ) : (
          <div style={{ padding: "20px", textAlign: "center", color: "#666", background: "rgba(0,0,0,0.2)", borderRadius: "12px", marginBottom: "25px" }}>{loading ? "Analyzing..." : "Enter Parcel ID to see metrics"}</div>
        )}
        <div style={{ marginBottom: "25px" }}>
            <div style={{ fontWeight: "bold", color: "#4A90E2", marginBottom: "12px", fontSize: "0.9rem" }}>Regulatory Setbacks (meters):</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "15px" }}>
                <div>Wetlands <input type="number" value={buffers.wetlands} onChange={e => setBuffers({...buffers, wetlands: Number(e.target.value)})} style={inputStyle} /></div>
                <div>Floodplain <input type="number" value={buffers.floodzones} onChange={e => setBuffers({...buffers, floodzones: Number(e.target.value)})} style={inputStyle} /></div>
                <div>Electric <input type="number" value={buffers.transmission} onChange={e => setBuffers({...buffers, transmission: Number(e.target.value)})} style={inputStyle} /></div>
                <div>Buildings <input type="number" value={buffers.buildings} onChange={e => setBuffers({...buffers, buildings: Number(e.target.value)})} style={inputStyle} /></div>
            </div>
        </div>
        <div style={{ marginBottom: "10px" }}>
            <div style={{ fontWeight: "bold", color: "#4A90E2", marginBottom: "12px", fontSize: "0.9rem" }}>Manual Adjustments:</div>
            <div style={{ display: "flex", gap: "10px" }}>
                <button onClick={() => setDrawMode("carve")} style={{ flex: 1, padding: "12px", borderRadius: "10px", background: drawMode === "carve" ? "#E74C3C" : "#222", border: "none", color: "#fff", cursor: "pointer", fontWeight: "bold" }}>Exclude Area</button>
                <button onClick={() => setDrawMode("restore")} style={{ flex: 1, padding: "12px", borderRadius: "10px", background: drawMode === "restore" ? "#27AE60" : "#222", border: "none", color: "#fff", cursor: "pointer", fontWeight: "bold" }}>Restore Area</button>
            </div>
            <div style={{ marginTop: "15px", fontSize: "0.75rem", color: "#888" }}>Use the polygon tool on the top-right to adjust the buildable area. Metrics update live.</div>
        </div>
        {error && <div style={{ color: "#ff4757", fontSize: "0.85rem", marginTop: "15px", textAlign: "center", padding: "10px", background: "rgba(255,71,87,0.1)", borderRadius: "8px" }}>{error}</div>}
      </div>
      <div style={{ position: "absolute", bottom: "25px", right: "25px", background: "rgba(0,0,0,0.85)", padding: "12px 18px", borderRadius: "10px", color: "#fff", fontSize: "0.8rem", border: "1px solid rgba(255,255,255,0.1)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}><div style={{ width: 14, height: 14, background: "#27AE60", borderRadius: 3 }} /> Buildable Result</div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "6px" }}><div style={{ width: 14, height: 14, background: "#E74C3C", borderRadius: 3 }} /> Excluded Constraints</div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}><div style={{ width: 14, height: 14, border: "2.5px solid #4A90E2", borderRadius: 3 }} /> Parcel Boundary</div>
      </div>
    </div>
  );
}

const inputStyle = { width: "100%", background: "#000", color: "#fff", border: "1px solid #333", borderRadius: "6px", padding: "8px", marginTop: "6px", fontSize: "0.9rem" };