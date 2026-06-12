import zipfile
import tempfile
import os
from datetime import datetime

import streamlit as st
import geopandas as gpd
import folium
from folium import plugins
from streamlit_folium import st_folium
import pandas as pd

st.set_page_config(page_title="Generador de Mapas Automáticos", layout="wide")

LOGO_DEFAULT = os.path.join(os.path.dirname(__file__), "logo_default.png")

BASEMAPS = {
    "ESRI Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "Google Satellite": "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
    "Google Hybrid": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "ESRI Topo": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    "CartoDB Positron": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    "ESRI Gray": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
}

BASEMAP_ATTRS = {
    "ESRI Satellite": "Esri",
    "Google Satellite": "Google",
    "Google Hybrid": "Google",
    "OpenStreetMap": "OpenStreetMap",
    "ESRI Topo": "Esri",
    "CartoDB Positron": "CartoDB",
    "ESRI Gray": "Esri",
}

BASEMAP_SWITCHER = ["ESRI Satellite", "Google Satellite", "Google Hybrid", "OpenStreetMap"]


LABEL_COLUMNS = ["name", "nombre", "Name", "NOMBRE", "label", "etiqueta", "desc", "descripcion", "Descripcion"]

NATURA_ADDRESS = "Ingeniero López 236, Torre 2, Piso 6-A · Córdoba, Argentina (CP 5000)"
NATURA_WEB = "naturainternational.org"


def _get_geom_type(gdf):
    types = gdf.geometry.geom_type.unique()
    if any(t in ("Polygon", "MultiPolygon") for t in types):
        return "polygon"
    elif any(t in ("LineString", "MultiLineString") for t in types):
        return "line"
    elif any(t in ("Point", "MultiPoint") for t in types):
        return "point"
    return "polygon"


def _build_interactive_template(
    layers, project_name, map_name, logo_path=None,
):
    legend_items = ""
    total_area_ha = 0.0
    total_area_km2 = 0.0
    has_polygon = False
    for gdf, layer_name, fill_color, edge_color in layers:
        if gdf.empty:
            continue
        geom_type = _get_geom_type(gdf)
        if geom_type == "polygon":
            legend_items += f'''
            <li><div class="legend-color" style="background:{fill_color}; border:1px solid {edge_color};"></div> <span>{layer_name}</span></li>'''
            has_polygon = True
        elif geom_type == "line":
            legend_items += f'''
            <li><div class="legend-line" style="background:{edge_color};"></div> <span>{layer_name}</span></li>'''
        elif geom_type == "point":
            legend_items += f'''
            <li><div class="circle-marker" style="background:{fill_color}; border-color:{edge_color};"></div> <span>{layer_name}</span></li>'''

    area_ha_str, area_km2_str = "", ""
    center_lat, center_lng = "", ""
    try:
        all_gdfs = []
        for gdf, _name, _fc, _ec in layers:
            if gdf.empty:
                continue
            g = gdf.copy()
            if g.crs is None:
                g = g.set_crs("EPSG:4326")
            if not g.empty:
                g3857 = g.to_crs("EPSG:3857")
                area_m2 = g3857.area.sum()
                total_area_ha += area_m2 / 10000
                total_area_km2 += area_m2 / 1_000_000
            all_gdfs.append(g.to_crs("EPSG:4326"))
        if all_gdfs:
            merged = gpd.pd.concat(all_gdfs, ignore_index=True)
            bounds = merged.total_bounds
            center_lat = f"{(bounds[1] + bounds[3]) / 2:.4f}"
            center_lng = f"{(bounds[0] + bounds[2]) / 2:.4f}"
    except Exception:
        pass

    if total_area_ha >= 100:
        area_ha_str = f"{total_area_ha:,.0f}"
        area_km2_str = f"{total_area_km2:,.0f}"
    else:
        area_ha_str = f"{total_area_ha:,.2f}"
        area_km2_str = f"{total_area_km2:,.2f}"

    logo_html = ""
    if logo_path and os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                import base64
                b64 = base64.b64encode(f.read()).decode()
            logo_html = f'<img class="header-logo" src="data:image/png;base64,{b64}" alt="Logo">'
        except Exception:
            pass

    title_display = map_name or "Mapa"
    project_display = project_name or ""
    today_str = datetime.now().strftime("%d/%m/%Y")

    area_info = ""
    if has_polygon and area_ha_str:
        area_info = f'<p><span class="info-label">Superficie:</span><span class="info-value">{area_ha_str} ha ({area_km2_str} km²)</span></p>'

    location_info = ""
    if center_lat and center_lng:
        location_info = f'<p><span class="info-label">Coordenadas:</span><span class="info-value">Lat {center_lat} / Lon {center_lng}</span></p>'

    header_title_text = title_display
    if has_polygon and area_ha_str:
        header_title_text += f" · {area_ha_str} ha"
    if project_display:
        header_title_text += f" · {project_display}"

    template = f'''
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Montserrat', 'Segoe UI', Roboto, Helvetica, sans-serif; background: #eef2f0; color: #1e2a1e; }}
        .info-card {{ position: absolute; bottom: 20px; right: 20px; width: 280px; max-width: calc(100% - 40px); background: rgba(255, 255, 255, 0.96); backdrop-filter: blur(10px); border-radius: 20px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); padding: 0.9rem 1.1rem; border-left: 5px solid #4c9f70; z-index: 10; font-size: 0.78rem; pointer-events: auto; }}
        .info-card h3 {{ font-size: 1rem; font-weight: 700; margin: 0 0 0.4rem 0; color: #1e3b2a; border-bottom: 2px solid #e0e7cf; display: inline-block; padding-right: 1rem; }}
        .info-card p {{ margin: 0.4rem 0; line-height: 1.4; display: flex; gap: 0.4rem; align-items: baseline; flex-wrap: wrap; }}
        .info-label {{ font-weight: 700; color: #2c6e3c; min-width: 65px; font-size: 0.7rem; }}
        .info-value {{ font-weight: 500; color: #1c2c1a; }}
        .info-footer {{ margin-top: 8px; font-size: 0.65rem; color: #4f6b4a; border-top: 1px solid #ddd9c5; padding-top: 6px; text-align: center; }}
        .legend-card {{ position: absolute; bottom: 20px; left: 20px; width: 240px; max-width: calc(100% - 60px); background: rgba(255, 255, 248, 0.97); backdrop-filter: blur(8px); border-radius: 20px; box-shadow: 0 8px 20px rgba(0,0,0,0.15); padding: 0.8rem 0.9rem; border-right: 3px solid #8bb56a; z-index: 10; font-size: 0.75rem; pointer-events: auto; max-height: 50vh; overflow-y: auto; }}
        .legend-card h4 {{ font-size: 0.85rem; font-weight: 700; margin: 0 0 6px 0; color: #2d4a26; display: flex; align-items: center; gap: 6px; border-bottom: 1px solid #ccdbb8; padding-bottom: 4px; }}
        .legend-list {{ list-style: none; margin: 0; padding: 0; }}
        .legend-list li {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 0.7rem; line-height: 1.3; }}
        .legend-color {{ width: 24px; height: 12px; border-radius: 3px; display: inline-block; flex-shrink: 0; }}
        .legend-line {{ width: 24px; height: 3px; display: inline-block; border-radius: 2px; flex-shrink: 0; }}
        .circle-marker {{ width: 10px; height: 10px; border-radius: 50%; border: 1.5px solid; display: inline-block; flex-shrink: 0; }}
        .legend-footer-small {{ font-size: 0.6rem; margin-top: 8px; text-align: center; color: #5b6e53; border-top: 1px solid #e0e2d4; padding-top: 5px; }}
        .compass-rose {{
            position: absolute; bottom: 80px; right: 24px; z-index: 1000;
            width: 56px; height: 62px; pointer-events: none;
            display: flex; flex-direction: column; align-items: center;
            font-family: 'Montserrat', sans-serif;
        }}
        .compass-rose svg {{ width: 44px; height: 44px; }}
        .compass-label {{ font-size: 11px; font-weight: 700; color: #333; line-height: 1; margin-top: -2px; }}
        .footer-credits {{ position: fixed; bottom: 0; left: 0; right: 0; z-index: 10000; background: #eaf2e5; font-size: 0.6rem; text-align: center; padding: 4px; color: #2b482f; border-top: 1px solid #c7dcb4; font-family: monospace; min-height: 22px; }}
    </style>
    <div class="compass-rose">
        <svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">
            <circle cx="22" cy="22" r="20" fill="none" stroke="#bbb" stroke-width="0.5"/>
            <circle cx="22" cy="22" r="19" fill="none" stroke="#ddd" stroke-width="0.3"/>
            <polygon points="22,2 17,16 22,14 27,16" fill="#c0392b"/>
            <polygon points="22,2 22,14 27,16" fill="#e74c3c"/>
            <polygon points="22,42 17,28 22,30 27,28" fill="#bbb"/>
            <polygon points="22,42 22,30 27,28" fill="#ddd"/>
            <polygon points="2,22 16,17 14,22 16,27" fill="#bbb"/>
            <polygon points="2,22 14,22 16,27" fill="#ddd"/>
            <polygon points="42,22 28,17 30,22 28,27" fill="#bbb"/>
            <polygon points="42,22 30,22 28,27" fill="#ddd"/>
            <circle cx="22" cy="22" r="2.5" fill="none" stroke="#999" stroke-width="0.8"/>
            <text x="22" y="6" text-anchor="middle" fill="#c0392b" font-size="5" font-weight="700" font-family="Montserrat,sans-serif">N</text>
            <text x="22" y="41" text-anchor="middle" fill="#888" font-size="4" font-weight="600" font-family="Montserrat,sans-serif">S</text>
            <text x="4" y="23.5" text-anchor="middle" fill="#888" font-size="4" font-weight="600" font-family="Montserrat,sans-serif">O</text>
            <text x="40" y="23.5" text-anchor="middle" fill="#888" font-size="4" font-weight="600" font-family="Montserrat,sans-serif">E</text>
        </svg>
    </div>
    <div class="legend-card">
        <h4>Referencias cartográficas</h4>
        <ul class="legend-list">
            {legend_items}
        </ul>
        <div class="legend-footer-small">
            Escala gráfica: ver control inferior izquierdo<br>
            Base: OpenStreetMap · Capas temáticas ajustables
        </div>
    </div>
    <div class="info-card" id="infoCard">
        <h3>Información del área</h3>
        <p><span class="info-label">Ubicación:</span><span class="info-value">{project_display if project_display else "Área de interés"}</span></p>
        {area_info}
        <p><span class="info-label">Referencia:</span><span class="info-value">{title_display}</span></p>
        <p><span class="info-label">Fecha:</span><span class="info-value">{today_str}</span></p>
        {location_info}
        <div class="info-footer">
            Datos técnicos de campo · Relevamiento Natura Argentina
        </div>
    </div>
    '''
    return template


def _build_print_template(fig_map_html, layers, project_name, map_name, logo_path=None, basemap_variants=None, basemap_name=None):
    """Build a self-contained print-layout HTML with left panel + map + layer toggles + export."""
    total_area_ha = 0.0
    total_area_km2 = 0.0
    center_lat = ""
    center_lng = ""
    legend_items_html = ""

    for i, (gdf, layer_name, fill_color, edge_color) in enumerate(layers):
        if gdf.empty:
            layer_id = f"layer_{i}"
            legend_items_html += f'''
            <label class="legend-item" data-layer="{layer_id}">
                <span class="legend-swatch" style="background:{fill_color};border:1px solid {edge_color};width:16px;height:10px;display:inline-block;border-radius:2px;"></span>
                <span>{layer_name}</span>
            </label>'''
            continue
        geom_type = _get_geom_type(gdf)
        layer_id = f"layer_{i}"
        if geom_type == "polygon":
            swatch = f'<span class="legend-swatch" style="background:{fill_color};border:1px solid {edge_color};width:26px;height:14px;display:inline-block;border-radius:3px;"></span>'
        elif geom_type == "line":
            swatch = f'<span class="legend-swatch" style="background:{edge_color};width:26px;height:3px;display:inline-block;border-radius:2px;vertical-align:middle;"></span>'
        else:
            swatch = f'<span class="legend-swatch" style="background:{fill_color};border:1.5px solid {edge_color};width:12px;height:12px;display:inline-block;border-radius:50%;"></span>'

        legend_items_html += f'''
        <label class="legend-item" data-layer="{layer_id}">
            <input type="checkbox" checked onchange="toggleLayer('{layer_id}', this.checked)">
            {swatch}
            <span>{layer_name}</span>
        </label>'''

        g = gdf.copy()
        if g.crs is None:
            g = g.set_crs("EPSG:4326")
        if not g.empty:
            g3857 = g.to_crs("EPSG:3857")
            area_m2 = g3857.area.sum()
            total_area_ha += area_m2 / 10000
            total_area_km2 += area_m2 / 1_000_000

    if total_area_ha >= 100:
        area_ha_str = f"{total_area_ha:,.0f}"
        area_km2_str = f"{total_area_km2:,.0f}"
    else:
        area_ha_str = f"{total_area_ha:,.2f}"
        area_km2_str = f"{total_area_km2:,.2f}"

    try:
        all_gdfs = []
        for gdf, _name, _fc, _ec in layers:
            if gdf.empty:
                continue
            g = gdf.copy()
            if g.crs is None:
                g = g.set_crs("EPSG:4326")
            all_gdfs.append(g.to_crs("EPSG:4326"))
        if all_gdfs:
            merged = gpd.pd.concat(all_gdfs, ignore_index=True)
            bounds = merged.total_bounds
            center_lat = f"{(bounds[1] + bounds[3]) / 2:.4f}"
            center_lng = f"{(bounds[0] + bounds[2]) / 2:.4f}"
    except Exception:
        pass

    logo_html = ""
    if logo_path and os.path.exists(logo_path):
        try:
            with open(logo_path, "rb") as f:
                import base64
                b64 = base64.b64encode(f.read()).decode()
            logo_html = f'<img src="data:image/png;base64,{b64}" class="panel-logo" alt="Logo">'
        except Exception:
            pass

    title_display = map_name or "Mapa"
    project_display = project_name or ""
    today_str = datetime.now().strftime("%d/%m/%Y")

    area_info = ""
    if area_ha_str:
        area_info = f'<p><span class="il">Superficie:</span><span class="iv">{area_ha_str} ha ({area_km2_str} km²)</span></p>'

    location_info = ""
    if center_lat and center_lng:
        location_info = f'<p><span class="il">Coordenadas:</span><span class="iv">Lat {center_lat} / Lon {center_lng}</span></p>'

    # Build list of layer data for JS
    layers_meta = []
    for i, (gdf, layer_name, fill_color, edge_color) in enumerate(layers):
        layers_meta.append({
            "id": f"layer_{i}",
            "name": layer_name,
        })

    L = len(layers)
    import json

    import json as _json
    # Escape the folium HTML for embedding in JS template literal
    folium_json_str = _json.dumps(fig_map_html).replace('</script>', '<\\/script>')

    basemap_variants_escaped = basemap_variants or {basemap_name: fig_map_html}
    _capture_script = '<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script><script>window.addEventListener("message",async function(e){if(e.data==="captureMap"){try{var d=document.querySelector("[id^=\\"map_\\"]");var c=await html2canvas(d,{scale:2,useCORS:true,allowTaint:false,backgroundColor:"#e8ece8"});e.source.postMessage({type:"mapCapture",dataUrl:c.toDataURL("image/png")},"*")}catch(err){e.source.postMessage({type:"mapCaptureError",message:err.message},"*")}}});</script>'
    for k in list(basemap_variants_escaped.keys()):
        basemap_variants_escaped[k] = basemap_variants_escaped[k].replace('</body>', _capture_script + '</body>')
    basemap_variants_json = _json.dumps(basemap_variants_escaped, ensure_ascii=False).replace('</script>', '<\\/script>')

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Print Layout - {title_display}</title>
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/utif/3.1.0/UTIF.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Montserrat','Segoe UI',Roboto,sans-serif; background:#eef2f0; }}

.print-layout {{
    width: 1200px; height: 900px;
    margin: 20px auto; display: flex;
    box-shadow: 0 4px 20px rgba(0,0,0,0.15);
    background: white; position: relative;
}}

.left-panel {{
    width: 27%; height: 100%;
    background: #fafaf8;
    display: flex; flex-direction: column;
    padding: 22px 16px 14px 18px;
    border-right: 1px solid #d4ddd0;
    overflow: hidden;
}}
.panel-logo {{ max-width: 120px; max-height: 60px; object-fit: contain; display: block; margin: 0 0 4px 0; }}
.panel-title {{ font-size: 21px; font-weight: 800; color: #1f3b2c; margin-bottom: 1px; line-height: 1.2; }}
.panel-project {{ font-size: 14px; font-weight: 500; color: #4d6b4d; margin-bottom: 3px; }}
.panel-area {{ font-size: 12px; color: #3c6e3f; margin-bottom: 6px; }}
.panel-sep {{ border: none; border-top: 1.5px solid #c0d4b0; margin: 7px 0; }}

.legend-title {{ font-size: 15px; font-weight: 700; color: #2d4a26; margin-bottom: 6px; }}
.legend-item {{
    display: flex; align-items: center; gap: 8px;
    font-size: 12px; color: #1e2a1e; margin-bottom: 3px;
    cursor: pointer; user-select: none;
}}
.legend-item input[type="checkbox"] {{ accent-color: #4c9f70; width: 16px; height: 16px; cursor: pointer; }}

.info-title {{ font-size: 15px; font-weight: 700; color: #2d4a26; margin: 3px 0 3px; }}
.info-card-print {{ font-size: 11px; }}
.info-card-print p {{ margin: 2px 0; line-height: 1.3; }}
.il {{ font-weight: 600; color: #3c6e3f; }}
.iv {{ color: #1c2c1a; }}

.scale-section {{ margin-top: auto; padding-top: 6px; }}
.scale-title {{ font-size: 12px; font-weight: 600; color: #3c6e3f; }}
.dept-title {{ font-size: 12px; font-weight: 700; color: #3c6e3f; margin-top: 6px; }}
.scale-bar-wrap {{ display: flex; align-items: center; gap: 6px; }}
.compass-mini {{ display: flex; flex-direction: column; align-items: center; margin-right: 6px; }}
.compass-mini svg {{ width: 32px; height: 32px; }}
.scale-bar-line {{ height: 3px; background: black; width: 140px; position: relative; }}
.scale-bar-line::before, .scale-bar-line::after {{
    content: ''; position: absolute; top: -5px;
    width: 2.5px; height: 12px; background: black;
}}
.scale-bar-line::before {{ left: 0; }}
.scale-bar-line::after {{ right: 0; }}
.scale-label {{ font-size: 10px; font-weight: 700; color: #333; }}

.credits {{
    margin-top: 5px; font-size: 7.5px; color: #7a8f7a; line-height: 1.4;
}}

.map-area {{
    width: 73%; height: 100%; position: relative;
    background: #e8ece8; overflow: hidden;
}}
.map-area iframe {{ width: 100%; height: 100%; border: none; }}

.export-bar {{
    max-width: 1200px; margin: 0 auto 10px;
    padding: 8px 0; display: flex; gap: 6px;
    justify-content: center; flex-wrap: wrap;
}}
.export-btn {{
    padding: 7px 14px; border: none; border-radius: 6px;
    font-family: 'Montserrat', sans-serif; font-weight: 600; font-size: 12px;
    cursor: pointer; color: white; transition: opacity 0.2s;
}}
.export-btn:hover {{ opacity: 0.85; }}
.btn-png {{ background: #2d6a2b; }}
.btn-jpg {{ background: #e87c1f; }}
.btn-tiff {{ background: #4a2a1a; }}
.btn-webp {{ background: #1565C0; }}
.btn-pdf {{ background: #c22d2d; }}
.btn-print {{ background: #555; }}
.basemap-title {{ font-size: 15px; font-weight: 700; color: #2d4a26; margin-bottom: 4px; }}
.basemap-group {{ display: flex; flex-direction: column; gap: 2px; }}
.basemap-item {{ font-size: 11px; color: #333; cursor: pointer; font-family: 'Montserrat', sans-serif; }}
.basemap-item input {{ accent-color: #4c9f70; margin-right: 4px; }}

@media print {{
    .export-bar {{ display: none !important; }}
    .print-layout {{ margin: 0; box-shadow: none; width: 100%; height: 100vh; }}
}}
</style>
</head>
<body>

<div class="export-bar" id="exportBar">
    <button class="export-btn btn-png" onclick="exportFormat('png')">PNG</button>
    <button class="export-btn btn-jpg" onclick="exportFormat('jpeg')">JPEG</button>
    <button class="export-btn btn-tiff" onclick="exportFormat('tiff')">TIFF</button>
    <button class="export-btn btn-webp" onclick="exportFormat('webp')">WEBP</button>
    <button class="export-btn btn-pdf" onclick="exportFormat('pdf')">PDF</button>
    <button class="export-btn btn-print" onclick="window.print()">Imprimir</button>
</div>

<div class="print-layout" id="printLayout">
    <div class="left-panel">
        <div class="panel-title">{title_display}</div>
        {f'<div class="panel-project">{project_display}</div>' if project_display else ''}
        {f'<div class="panel-area">Superficie: {area_ha_str} ha</div>' if area_ha_str else ''}
        <hr class="panel-sep">

        <div class="basemap-title">Mapa base</div>
        <div class="basemap-group">
            <label class="basemap-item"><input type="radio" name="basemap" value="ESRI Satellite" checked onchange="switchBasemap(this.value)"> Esri Satélite</label>
            <label class="basemap-item"><input type="radio" name="basemap" value="Google Satellite" onchange="switchBasemap(this.value)"> Google Satélite</label>
            <label class="basemap-item"><input type="radio" name="basemap" value="Google Hybrid" onchange="switchBasemap(this.value)"> Google Híbrido</label>
            <label class="basemap-item"><input type="radio" name="basemap" value="OpenStreetMap" onchange="switchBasemap(this.value)"> OpenStreetMap</label>
        </div>
        <hr class="panel-sep">

        <div class="legend-title">Capas</div>
        <div id="legendContainer">
        {legend_items_html}
        </div>
        <hr class="panel-sep">

        <div class="info-title">Información del área</div>
        <div class="info-card-print">
            <p><span class="il">Ubicación:</span><span class="iv">{project_display or "Área de interés"}</span></p>
            {area_info}
            <p><span class="il">Referencia:</span><span class="iv">{title_display}</span></p>
            <p><span class="il">Fecha:</span><span class="iv">{today_str}</span></p>
            {location_info}
        </div>
        <hr class="panel-sep">

        <div class="scale-section">
            <div class="scale-title">Escala gráfica</div>
            <div class="scale-bar-wrap">
                <div class="compass-mini">
                    <svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg">
                        <polygon points="22,2 17,16 22,14 27,16" fill="#c0392b"/>
                        <polygon points="22,2 22,14 27,16" fill="#e74c3c"/>
                        <polygon points="22,42 17,28 22,30 27,28" fill="#bbb"/>
                        <polygon points="22,42 22,30 27,28" fill="#ddd"/>
                        <polygon points="2,22 16,17 14,22 16,27" fill="#bbb"/>
                        <polygon points="2,22 14,22 16,27" fill="#ddd"/>
                        <polygon points="42,22 28,17 30,22 28,27" fill="#bbb"/>
                        <polygon points="42,22 30,22 28,27" fill="#ddd"/>
                        <circle cx="22" cy="22" r="2" fill="none" stroke="#999" stroke-width="0.6"/>
                        <text x="22" y="5.5" text-anchor="middle" fill="#c0392b" font-size="4.5" font-weight="700" font-family="Montserrat,sans-serif">N</text>
                        <text x="22" y="40.5" text-anchor="middle" fill="#888" font-size="3.5" font-weight="600" font-family="Montserrat,sans-serif">S</text>
                        <text x="4.5" y="23.5" text-anchor="middle" fill="#888" font-size="3.5" font-weight="600" font-family="Montserrat,sans-serif">O</text>
                        <text x="39.5" y="23.5" text-anchor="middle" fill="#888" font-size="3.5" font-weight="600" font-family="Montserrat,sans-serif">E</text>
                    </svg>
                </div>
                <div class="scale-bar-line"></div>
                <span class="scale-label">10 km</span>
            </div>
            <div class="dept-title">Departamento Técnico</div>
        </div>
        <div class="credits">
            {logo_html}
            &copy; Natura Argentina<br>
            www.{NATURA_WEB}<br>
            {NATURA_ADDRESS}
        </div>
    </div>

    <div class="map-area" id="mapArea">
        <iframe id="mapIframe" sandbox="allow-scripts allow-same-origin allow-popups" style="width:100%;height:100%;border:none;"></iframe>
    </div>
</div>

<script>
var basemapHtml = {basemap_variants_json};
var foliumHtml = basemapHtml[Object.keys(basemapHtml)[0]];
document.getElementById('mapIframe').srcdoc = foliumHtml;

function toggleLayer(layerId, visible) {{
    var iframe = document.getElementById('mapIframe');
    if (iframe && iframe.contentWindow) {{
        iframe.contentWindow.postMessage({{type:'toggleLayer', layerId:layerId, visible:visible}}, '*');
    }}
}}

function switchBasemap(name) {{
    var iframe = document.getElementById('mapIframe');
    if (iframe) {{
        iframe.srcdoc = basemapHtml[name] || foliumHtml;
    }}
}}

async function captureLayout() {{
    var layout = document.getElementById('printLayout');
    var iframe = document.getElementById('mapIframe');
    if (!layout || !iframe) return null;
    var sc = 2;
    try {{
        var layoutCanvas = await html2canvas(layout, {{
            scale: sc, useCORS: true, allowTaint: false,
            backgroundColor: '#ffffff', logging: false,
        }});
        var ctx = layoutCanvas.getContext('2d');
        try {{
            var mapDataUrl = await new Promise(function(resolve, reject) {{
                var t = setTimeout(function() {{ reject(new Error('timeout')); }}, 20000);
                var handler = function(e) {{
                    if (e.data && e.data.type === 'mapCapture') {{ clearTimeout(t); window.removeEventListener('message', handler); resolve(e.data.dataUrl); }}
                    if (e.data && e.data.type === 'mapCaptureError') {{ clearTimeout(t); window.removeEventListener('message', handler); reject(new Error(e.data.message)); }}
                }};
                window.addEventListener('message', handler);
                iframe.contentWindow.postMessage('captureMap', '*');
            }});
            var img = new Image();
            img.src = mapDataUrl;
            await new Promise(function(resolve, reject) {{ img.onload = resolve; img.onerror = reject; }});
            var lr = layout.getBoundingClientRect();
            var ir = iframe.getBoundingClientRect();
            ctx.drawImage(img, (ir.left - lr.left) * sc, (ir.top - lr.top) * sc, ir.width * sc, ir.height * sc);
        }} catch(e2) {{
            console.warn('iframe capture via postMessage failed:', e2);
        }}
        return layoutCanvas;
    }} catch(e) {{ throw e; }}
}}
async function exportFormat(format) {{
    var layout = document.getElementById('printLayout');
    if (!layout) return;
    try {{
        var canvas = await captureLayout();
        if (!canvas) return;
        var fn = '{title_display}';
        if (format === 'pdf') {{
            var imgData = canvas.toDataURL('image/png');
            var pdf = new jspdf.jsPDF('landscape', 'px', [canvas.width, canvas.height]);
            pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
            pdf.save(fn + '.pdf');
        }} else if (format === 'tiff') {{
            try {{
                var ctx2 = canvas.getContext('2d');
                var imgData = ctx2.getImageData(0, 0, canvas.width, canvas.height);
                var tiffData = UTIF.encodeImage(imgData.data, canvas.width, canvas.height);
                var blob = new Blob([tiffData], {{type: 'image/tiff'}});
                var link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                link.download = fn + '.tiff';
                link.click();
                URL.revokeObjectURL(link.href);
            }} catch(et) {{
                alert('TIFF no disponible, se descargó PNG como alternativa');
                var link = document.createElement('a');
                link.download = fn + '.png';
                link.href = canvas.toDataURL('image/png');
                link.click();
            }}
        }} else {{
            var mime = {{png:'image/png',jpeg:'image/jpeg',webp:'image/webp'}}[format] || 'image/png';
            var ext = {{png:'png',jpeg:'jpg',webp:'webp'}}[format] || 'png';
            var qual = format === 'jpeg' ? 0.95 : (format === 'webp' ? 0.9 : undefined);
            var link = document.createElement('a');
            link.download = fn + '.' + ext;
            link.href = canvas.toDataURL(mime, qual);
            link.click();
        }}
    }} catch(e) {{ alert('Error al exportar: ' + e.message); }}
}};
</script>

</body>
</html>'''

    return html


LAYER_COLORS = [
    ("#FF1744", "#C62828"),  # Rojo
    ("#FF9100", "#E65100"),  # Naranja
    ("#2979FF", "#1565C0"),  # Azul
    ("#FFEA00", "#8C6B00"),  # Amarillo
    ("#D500F9", "#6A1B9A"),  # Púrpura
    ("#00E5FF", "#00838F"),  # Cian
    ("#FF4081", "#C2185B"),  # Rosa
    ("#00E676", "#2E7D32"),  # Verde
    ("#FF3D00", "#BF360C"),  # Naranja intenso
    ("#651FFF", "#311B92"),  # Púrpura intenso
]


def read_kml(file_bytes):
    with tempfile.NamedTemporaryFile(suffix=".kml", delete=False) as f:
        f.write(file_bytes)
        f.flush()
        path = f.name
    try:
        gdf = gpd.read_file(path, driver="KML")
        return gdf
    except Exception:
        gdf = gpd.read_file(path)
        return gdf
    finally:
        os.unlink(path)


def read_kmz(file_bytes):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "doc.kmz")
        with open(zip_path, "wb") as f:
            f.write(file_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        kml_files = []
        for root, _dirs, files in os.walk(tmpdir):
            for f in files:
                if f.endswith(".kml"):
                    kml_files.append(os.path.join(root, f))
        if not kml_files:
            raise ValueError("No se encontró un archivo .kml dentro del KMZ")
        gdf = gpd.read_file(kml_files[0], driver="KML")
        return gdf


def read_shapefile_zip(file_bytes):
    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, "upload.zip")
        with open(zip_path, "wb") as f:
            f.write(file_bytes)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmpdir)
        shp_files = []
        for root, _dirs, files in os.walk(tmpdir):
            for f in files:
                if f.endswith(".shp"):
                    shp_files.append(os.path.join(root, f))
        if not shp_files:
            raise ValueError("No se encontró un archivo .shp en el ZIP")
        os.environ["SHAPE_RESTORE_SHX"] = "YES"
        gdf = gpd.read_file(shp_files[0])
        return gdf


def ensure_crs(gdf):
    if gdf.crs is None:
        st.warning("El archivo no tiene un sistema de coordenadas definido. Se asume WGS84 (EPSG:4326).")
        gdf.set_crs("EPSG:4326", inplace=True)
    return gdf


def load_polygon(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    fname = uploaded_file.name.lower()

    if fname.endswith(".kml"):
        return ensure_crs(read_kml(file_bytes))
    elif fname.endswith(".kmz"):
        return ensure_crs(read_kmz(file_bytes))
    elif fname.endswith(".zip"):
        return ensure_crs(read_shapefile_zip(file_bytes))
    elif fname.endswith(".shp"):
        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, uploaded_file.name)
            with open(shp_path, "wb") as f:
                f.write(file_bytes)
            os.environ["SHAPE_RESTORE_SHX"] = "YES"
            return ensure_crs(gpd.read_file(shp_path))
    elif fname.endswith(".geojson") or fname.endswith(".json"):
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as f:
            f.write(file_bytes)
            f.flush()
            path = f.name
        try:
            return ensure_crs(gpd.read_file(path))
        finally:
            os.unlink(path)
    else:
        raise ValueError(
            "Formato no soportado. Usa .kml, .kmz, .zip (con .shp), .shp, .geojson"
        )


def load_shapefile_set(files):
    """Load a shapefile from a list of component files (.shp, .shx, .dbf, .prj, .cpg, etc.)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base_name = None
        for uf in files:
            name = uf.name
            ext = os.path.splitext(name)[1].lower()
            if ext == ".shp":
                base_name = os.path.splitext(name)[0]
            fpath = os.path.join(tmpdir, name)
            with open(fpath, "wb") as f:
                f.write(uf.getvalue())
        if not base_name:
            raise ValueError("No se encontró un archivo .shp en el grupo")
        os.environ["SHAPE_RESTORE_SHX"] = "YES"
        shp_path = os.path.join(tmpdir, base_name + ".shp")
        return ensure_crs(gpd.read_file(shp_path))


def create_interactive_map(layers, basemap_name, project_name, map_name, include_labels=False, logo_path=None):
    if not layers:
        return None

    merged = []
    for gdf, _name, _fc, _ec in layers:
        if gdf.crs is None:
            gdf.set_crs("EPSG:4326", inplace=True)
        if gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        merged.append(gdf)

    merged_gdf = gpd.pd.concat(merged, ignore_index=True)
    bounds = merged_gdf.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    tile_url = BASEMAPS[basemap_name]
    attr = BASEMAP_ATTRS.get(basemap_name, "")

    m = folium.Map(
        location=center,
        zoom_start=10,
        tiles=tile_url,
        attr=attr,
    )

    for i, (gdf, layer_name, fill_color, edge_color) in enumerate(layers):
        if gdf.crs.to_string() != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")
        style = {
            "fillColor": fill_color,
            "color": edge_color,
            "weight": 2,
            "fillOpacity": 0.6,
        }
        tooltip = None
        if include_labels:
            label_col = _detect_label_column(gdf)
            if label_col is not None:
                tooltip = folium.GeoJsonTooltip(fields=[label_col], labels=False, sticky=True)
        geo_json = folium.GeoJson(
            gdf.to_json(),
            style_function=lambda x, s=style: s,
            name=layer_name,
            tooltip=tooltip,
            layer_id=f"layer_{i}",
            marker=folium.CircleMarker(
                radius=6,
                color=edge_color,
                fill_color=fill_color,
                weight=2,
                fill_opacity=0.6,
            ),
        )
        geo_json.add_to(m)

    custom_template = _build_interactive_template(
        layers, project_name, map_name, logo_path=logo_path,
    )
    m.get_root().html.add_child(folium.Element(custom_template))

    # Inject toggle-layer listener for print template
    toggle_js = """
<script>
window.__layers = {};
(function() {
    try {
        var m = null;
        for (var k in window) {
            if (k.indexOf('map_') === 0 && window[k] && window[k].eachLayer) {
                m = window[k]; break;
            }
        }
        if (!m) return;
        m.eachLayer(function(layer) {
            if (layer.options && layer.options.layerId) {
                window.__layers[layer.options.layerId] = layer;
            }
        });
    } catch(e) { console.warn('init layers:', e); }
})();
window.__toggleLayer = function(layerId, visible) {
    try {
        var layer = window.__layers[layerId];
        if (!layer) return;
        var m = null;
        for (var k in window) {
            if (k.indexOf('map_') === 0 && window[k] && window[k].eachLayer) {
                m = window[k]; break;
            }
        }
        if (!m) return;
        if (visible) m.addLayer(layer);
        else m.removeLayer(layer);
    } catch(e) { console.warn('toggle:', e); }
};
window.addEventListener('message', function(e) {
    if (e.data && e.data.type === 'toggleLayer') {
        window.__toggleLayer(e.data.layerId, e.data.visible);
    }
});
</script>"""
    m.get_root().html.add_child(folium.Element(toggle_js))

    plugins.Fullscreen(position="topright").add_to(m)
    plugins.MousePosition(position="bottomright").add_to(m)
    plugins.MeasureControl(position="topleft").add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    return m


def generate_print_template(layers, basemap_name, project_name, map_name, include_labels=False, logo_path=None):
    """Generate a self-contained print layout HTML with map, legend toggles, and export buttons."""
    folium_map = create_interactive_map(layers, basemap_name, project_name, map_name,
                                        include_labels=include_labels, logo_path=logo_path)
    if folium_map is None:
        return None
    folium_html = folium_map.get_root().render()
    basemap_variants = {}
    for bm in BASEMAP_SWITCHER:
        fm = create_interactive_map(layers, bm, project_name, map_name,
                                    include_labels=include_labels, logo_path=logo_path)
        if fm:
            basemap_variants[bm] = fm.get_root().render()
    print_html = _build_print_template(folium_html, layers, project_name, map_name, logo_path=logo_path,
                                       basemap_variants=basemap_variants, basemap_name=basemap_name)
    return print_html

def _detect_label_column(gdf):
    for col in LABEL_COLUMNS:
        if col in gdf.columns:
            return col
    return None


def main():
    st.title("Mapas Automáticos")
    st.markdown("Sube un polígono (KML, SHP, GeoJSON) y genera mapas con formato estandarizado.")

    if "file_key" not in st.session_state:
        st.session_state["file_key"] = 0
        st.session_state["layers"] = []

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Datos del mapa")
        project_name = st.text_input("Nombre del proyecto", value="Proyecto Ejemplo")
        map_name = st.text_input("Nombre del mapa", value="Mapa de Área de Interés")

        uploaded_files = st.file_uploader(
            "Cargar archivos (capas)",
            type=["kml", "kmz", "zip", "shp", "geojson", "json"],
            accept_multiple_files=True,
            help="KML, KMZ, ZIP (con SHP), SHP o GeoJSON. Múltiples archivos = múltiples capas.",
            key=f"file_uploader_{st.session_state.file_key}",
        )

        basemap_name = st.selectbox(
            "Mapa base",
            list(BASEMAPS.keys()),
            index=0,
        )

        uploaded_logo = st.file_uploader(
            "Logo personalizado (opcional)",
            type=["png", "jpg", "jpeg"],
            help="Si no subes uno, se usará el logo por defecto",
        )

    with col2:
        st.subheader("Vista previa")

        if not uploaded_files:
            st.session_state["layers"] = []
            st.info("Carga archivos para ver la vista previa")
        else:
            with st.spinner("Leyendo archivos..."):
                try:
                    SHP_EXTS = {".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}
                    shp_groups = {}
                    non_shp = []
                    for uf in uploaded_files:
                        ext = os.path.splitext(uf.name)[1].lower()
                        if ext in SHP_EXTS:
                            base = os.path.splitext(uf.name)[0]
                            shp_groups.setdefault(base, []).append(uf)
                        else:
                            non_shp.append(uf)

                    layers = []
                    color_idx = 0

                    for base, group in shp_groups.items():
                        has_shp = any(os.path.splitext(uf.name)[1].lower() == ".shp" for uf in group)
                        has_companions = len(group) > 1
                        if has_shp and has_companions:
                            try:
                                gdf = load_shapefile_set(group)
                                if gdf.empty:
                                    st.warning(f"'{base}.shp' no contiene geometrías válidas, se omite.")
                                    continue
                                fc, ec = LAYER_COLORS[color_idx % len(LAYER_COLORS)]
                                color_idx += 1
                                layers.append((gdf, base, fc, ec))
                                st.success(f"✓ {base}: {len(gdf)} geometría(s)")
                            except Exception as e:
                                st.warning(f"Error al cargar shapefile '{base}': {e}")
                        elif has_shp:
                            for uf in group:
                                non_shp.append(uf)
                        else:
                            for uf in group:
                                non_shp.append(uf)

                    for uf in non_shp:
                        try:
                            gdf = load_polygon(uf)
                            if gdf.empty:
                                st.warning(f"'{uf.name}' no contiene geometrías válidas, se omite.")
                                continue
                            fc, ec = LAYER_COLORS[color_idx % len(LAYER_COLORS)]
                            color_idx += 1
                            layers.append((gdf, os.path.splitext(uf.name)[0], fc, ec))
                            st.success(f"✓ {uf.name}: {len(gdf)} geometría(s)")
                        except Exception as e:
                            st.warning(f"Error al cargar '{uf.name}': {e}")

                    if layers:
                        st.session_state["layers"] = layers
                        preview_logo_path = None
                        if uploaded_logo:
                            logo_ext = uploaded_logo.name.split(".")[-1]
                            tmp_logo = tempfile.NamedTemporaryFile(suffix=f".{logo_ext}", delete=False)
                            tmp_logo.write(uploaded_logo.getvalue())
                            tmp_logo.close()
                            preview_logo_path = tmp_logo.name
                        elif os.path.exists(LOGO_DEFAULT):
                            preview_logo_path = LOGO_DEFAULT
                        m = create_interactive_map(
                            layers, basemap_name, project_name, map_name,
                            include_labels=True, logo_path=preview_logo_path,
                        )
                        if preview_logo_path and preview_logo_path != LOGO_DEFAULT:
                            try:
                                os.unlink(preview_logo_path)
                            except Exception:
                                pass
                        if m:
                            st_folium(m, width=None, height=500)
                    else:
                        st.error("No se pudo cargar ninguna capa.")
                        st.session_state["layers"] = []

                except Exception as e:
                    st.error(f"Error al leer archivos: {str(e)}")
                    st.session_state["layers"] = []

    if st.session_state["layers"]:
        layers = st.session_state["layers"]

        if st.button("Nuevo mapa", type="secondary"):
            st.session_state["layers"] = []
            st.session_state["file_key"] += 1
            st.rerun()

        st.divider()
        include_labels = st.checkbox("Etiquetas en el mapa", value=False)

        st.subheader("Plantilla de impresión")
        st.markdown("Genera un HTML con panel izquierdo, checkboxes de capas y exportación a PNG, JPEG, TIFF, WEBP y PDF.")

        if st.button("Generar plantilla de impresión", type="primary", use_container_width=True):
            with st.spinner("Generando plantilla..."):
                html_layers = []
                for gdf, layer_name, fc, ec in layers:
                    if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
                        gdf_html = gdf.to_crs("EPSG:4326")
                    else:
                        gdf_html = gdf
                    html_layers.append((gdf_html, layer_name, fc, ec))
                export_logo_path = None
                if uploaded_logo:
                    logo_ext = uploaded_logo.name.split(".")[-1]
                    tmp_logo = tempfile.NamedTemporaryFile(suffix=f".{logo_ext}", delete=False)
                    tmp_logo.write(uploaded_logo.getvalue())
                    tmp_logo.close()
                    export_logo_path = tmp_logo.name
                elif os.path.exists(LOGO_DEFAULT):
                    export_logo_path = LOGO_DEFAULT
                try:
                    print_html = generate_print_template(
                        html_layers, basemap_name, project_name, map_name,
                        include_labels=include_labels, logo_path=export_logo_path,
                    )
                    if print_html:
                        st.success("Plantilla generada correctamente")
                        st.download_button(
                            label="Descargar plantilla de impresión (HTML)",
                            data=print_html.encode("utf-8"),
                            file_name=f"{map_name.replace(' ', '_')}_print.html",
                            mime="text/html",
                            use_container_width=True,
                        )
                        st.info("Abrí el HTML en tu navegador. Usá los checkboxes para mostrar/ocultar capas y los botones para exportar a PNG, JPEG, TIFF, WEBP o PDF.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                finally:
                    if export_logo_path and export_logo_path != LOGO_DEFAULT:
                        try:
                            os.unlink(export_logo_path)
                        except Exception:
                            pass


if __name__ == "__main__":
    main()
