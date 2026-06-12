import io
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
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager
import contextily as ctx
from PIL import Image
import matplotlib.patches as mpatches

FONT_PATH = os.path.join(os.path.dirname(__file__), "Montserrat.ttf")
if os.path.exists(FONT_PATH):
    fontManager.addfont(FONT_PATH)
    plt.rcParams["font.family"] = "Montserrat"
    FONT_FAMILY = "Montserrat"
else:
    plt.rcParams["font.family"] = "sans-serif"
    FONT_FAMILY = "sans-serif"

FP12 = FontProperties(family=FONT_FAMILY, size=12)

st.set_page_config(page_title="Generador de Mapas Automáticos", layout="wide")

LOGO_DEFAULT = os.path.join(os.path.dirname(__file__), "logo_default.png")

BASEMAPS = {
    "ESRI Satellite": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "Google Hybrid": "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    "ESRI Topo": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
    "CartoDB Positron": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    "ESRI Gray": "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
}

BASEMAP_ATTRS = {
    "ESRI Satellite": "Esri",
    "OpenStreetMap": "OpenStreetMap",
    "Google Hybrid": "Google",
    "ESRI Topo": "Esri",
    "CartoDB Positron": "CartoDB",
    "ESRI Gray": "Esri",
}

ctx_providers = {
    "ESRI Satellite": ctx.providers.Esri.WorldImagery,
    "OpenStreetMap": ctx.providers.OpenStreetMap.Mapnik,
    "Google Hybrid": ctx.providers.Esri.WorldImagery,
    "ESRI Topo": ctx.providers.Esri.WorldTopoMap,
    "CartoDB Positron": ctx.providers.CartoDB.Positron,
    "ESRI Gray": ctx.providers.Esri.WorldGrayCanvas,
}


LABEL_COLUMNS = ["name", "nombre", "Name", "NOMBRE", "label", "etiqueta", "desc", "descripcion", "Descripcion"]

NATURA_ADDRESS = "Ingeniero López 236, Torre 2, Piso 6-A · Córdoba, Argentina (CP 5000)"
NATURA_WEB = "www.naturainternational.org"


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
    <link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Inter', 'Segoe UI', Roboto, Helvetica, sans-serif; background: #eef2f0; color: #1e2a1e; }}
        .top-header {{
            position: fixed; top: 0; left: 0; right: 0; z-index: 10000;
            background: #1f3b2c; color: white;
            padding: 0.55rem 1.5rem;
            display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center;
            gap: 0.8rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1);
            border-bottom: 3px solid #b7b87b;
            min-height: 48px;
        }}
        .brand {{ display: flex; align-items: baseline; gap: 0.5rem; flex-wrap: wrap; }}
        .header-logo {{ height: 28px; width: auto; object-fit: contain; margin-right: 2px; }}
        .brand .logo {{ font-weight: 800; font-size: 1.1rem; letter-spacing: -0.3px; background: #e6b42220; padding: 0.15rem 0.5rem; border-radius: 40px; border-left: 3px solid #e9c46a; }}
        .brand .logo a {{ color: #f5e7b2; text-decoration: none; }}
        .institution-name {{ font-weight: 500; font-size: 0.75rem; background: #2a4b37; padding: 0.15rem 0.6rem; border-radius: 30px; }}
        .map-title-header {{ background: #00000033; backdrop-filter: blur(4px); padding: 0.2rem 0.8rem; border-radius: 40px; font-weight: 600; font-size: 0.8rem; letter-spacing: 0.3px; border: 1px solid #cee2b0; text-align: center; }}
        .departamento-tech {{ font-size: 0.6rem; background: #2c5a3b; padding: 0.15rem 0.7rem; border-radius: 20px; display: inline-flex; align-items: center; gap: 4px; }}
        .map-wrapper {{ flex: 1; position: relative; background: #cbdcd0; }}
        #map {{ height: 100%; width: 100%; z-index: 1; }}
        .folium-map {{ margin-top: 52px !important; margin-bottom: 24px !important; }}
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
        .footer-credits {{ position: fixed; bottom: 0; left: 0; right: 0; z-index: 10000; background: #eaf2e5; font-size: 0.6rem; text-align: center; padding: 4px; color: #2b482f; border-top: 1px solid #c7dcb4; font-family: monospace; min-height: 22px; }}
        .leaflet-control-layers {{ margin-top: 56px !important; margin-left: 8px !important; border-radius: 16px !important; box-shadow: 0 2px 8px rgba(0,0,0,0.2) !important; }}
        .leaflet-control-scale {{ background: rgba(255,255,245,0.9) !important; border-radius: 12px !important; padding: 2px 8px !important; font-size: 10px !important; font-weight: 500 !important; box-shadow: 0 1px 4px rgba(0,0,0,0.2) !important; }}
        @media (max-width: 700px) {{ .top-header {{ padding: 0.4rem 0.8rem; flex-direction: column; align-items: flex-start; min-height: 40px; }} .info-card, .legend-card {{ position: relative !important; bottom: auto; left: auto; right: auto; margin: 8px; width: auto; max-width: none; }} .folium-map {{ margin-top: 88px !important; }} .leaflet-control-layers {{ margin-top: 90px !important; }} }}
    </style>
    <header class="top-header">
        <div class="brand">
            {logo_html}
            <div class="logo"><a href="https://{NATURA_WEB}" target="_blank">NaturaArgentina</a></div>
            <div class="institution-name">Conservación · Investigación · Territorios</div>
        </div>
        <div class="map-title-header" id="dynamicMapTitle">
            {header_title_text}
        </div>
        <div class="departamento-tech">
            Dpto. Técnico | {NATURA_ADDRESS}
        </div>
    </header>
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
    <div class="footer-credits">
        www.{NATURA_WEB} | {NATURA_ADDRESS} | Map template v2.0 - generación automática
    </div>
    '''
    return template


def _build_print_template(fig_map_html, layers, project_name, map_name, logo_path=None):
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
    folium_json_str = _json.dumps(fig_map_html)

    html = f'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Print Layout - {title_display}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400;14..32,500;14..32,600;14..32,700;14..32,800&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/utif/3.1.0/UTIF.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:'Inter','Segoe UI',Roboto,sans-serif; background:#eef2f0; }}

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
.panel-logo {{ max-width: 90%; max-height: 55px; object-fit: contain; margin-bottom: 10px; }}
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
.scale-title {{ font-size: 12px; font-weight: 600; color: #3c6e3f; margin-bottom: 3px; }}
.scale-bar-wrap {{ display: flex; align-items: center; gap: 6px; }}
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
    font-family: 'Inter', sans-serif; font-weight: 600; font-size: 12px;
    cursor: pointer; color: white; transition: opacity 0.2s;
}}
.export-btn:hover {{ opacity: 0.85; }}
.btn-png {{ background: #2d6a2b; }}
.btn-jpg {{ background: #e87c1f; }}
.btn-tiff {{ background: #4a2a1a; }}
.btn-webp {{ background: #1565C0; }}
.btn-pdf {{ background: #c22d2d; }}
.btn-print {{ background: #555; }}

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
        {logo_html}
        <div class="panel-title">{title_display}</div>
        {f'<div class="panel-project">{project_display}</div>' if project_display else ''}
        {f'<div class="panel-area">Superficie: {area_ha_str} ha</div>' if area_ha_str else ''}
        <hr class="panel-sep">

        <div class="legend-title">Referencias</div>
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
                <div class="scale-bar-line"></div>
                <span class="scale-label">10 km</span>
            </div>
        </div>
        <div class="credits">
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
var foliumHtml = {folium_json_str};
document.getElementById('mapIframe').srcdoc = foliumHtml;

function toggleLayer(layerId, visible) {{
    var iframe = document.getElementById('mapIframe');
    if (iframe && iframe.contentWindow) {{
        iframe.contentWindow.postMessage({{type:'toggleLayer', layerId:layerId, visible:visible}}, '*');
    }}
}}

async function exportFormat(format) {{
    var layout = document.getElementById('printLayout');
    if (!layout) return;
    try {{
        var canvas = await html2canvas(layout, {{
            scale: 2, useCORS: true, allowTaint: false,
            backgroundColor: '#ffffff', logging: false,
            width: layout.scrollWidth, height: layout.scrollHeight,
        }});
        var fn = '{title_display}';
        if (format === 'pdf') {{
            var imgData = canvas.toDataURL('image/png');
            var pdf = new jspdf.jsPDF('landscape', 'px', [canvas.width, canvas.height]);
            pdf.addImage(imgData, 'PNG', 0, 0, canvas.width, canvas.height);
            pdf.save(fn + '.pdf');
        }} else if (format === 'tiff') {{
            var ctx = canvas.getContext('2d');
            var imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            var tiffData = UTIF.encode(imgData.data, canvas.width, canvas.height);
            var blob = new Blob([tiffData], {{type: 'image/tiff'}});
            var link = document.createElement('a');
            link.href = URL.createObjectURL(blob);
            link.download = fn + '.tiff';
            link.click();
            URL.revokeObjectURL(link.href);
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
}}
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
            "fillOpacity": 0.35,
        }
        tooltip = None
        if include_labels:
            label_col = _detect_label_column(gdf)
            if label_col is not None:
                tooltip = folium.GeoJsonTooltip(fields=[label_col], labels=False, sticky=True)
        fg = folium.FeatureGroup(name=f"layer_{i}", show=True)
        geo_json = folium.GeoJson(
            gdf.to_json(),
            style_function=lambda x, s=style: s,
            name=layer_name,
            tooltip=tooltip,
        )
        geo_json.add_to(fg)
        fg.add_to(m)

    custom_template = _build_interactive_template(
        layers, project_name, map_name, logo_path=logo_path,
    )
    m.get_root().html.add_child(folium.Element(custom_template))

    # Inject toggle-layer listener for print template
    toggle_js = """
<script>
window.__toggleLayer = function(layerId, visible) {
    try {
        var m = null;
        for (var k in window) {
            if (k.indexOf('map_') === 0 && window[k] && window[k].eachLayer) {
                m = window[k]; break;
            }
        }
        if (!m) return;
        m.eachLayer(function(layer) {
            if (layer.options && layer.options.name === layerId) {
                if (visible) m.addLayer(layer);
                else m.removeLayer(layer);
            }
        });
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
    print_html = _build_print_template(folium_html, layers, project_name, map_name, logo_path=logo_path)
    return print_html


def _deg_to_3857(x, y):
    from pyproj import Transformer
    t = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    return t.transform(x, y)


def _nice_interval(span, target_count=6):
    if span <= 0:
        return 0.5
    interval = span / target_count
    magnitude = 10 ** np.floor(np.log10(interval))
    residual = interval / magnitude
    for nice in [1, 2, 5, 10]:
        if residual <= nice:
            return nice * magnitude
    return 10 * magnitude


def _fmt_coord(deg, is_lon=True):
    """Format coordinate in degrees/minutes for cleaner labels."""
    d = abs(deg)
    degrees = int(d)
    minutes = (d - degrees) * 60
    if abs(minutes - round(minutes)) < 0.01:
        minutes = round(minutes)
    suffix = ("E" if deg >= 0 else "W") if is_lon else ("N" if deg >= 0 else "S")
    if minutes == 0:
        return f"{degrees}°{suffix}"
    elif isinstance(minutes, int):
        return f"{degrees}°{minutes}'{suffix}"
    else:
        return f"{degrees}°{minutes:.1f}'{suffix}"


def draw_coordinate_grid(ax, extent_4326):
    west, east, south, north = extent_4326
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    lon_interval = _nice_interval(east - west)
    lat_interval = _nice_interval(north - south)
    lon_interval = max(lon_interval, 0.0001)
    lat_interval = max(lat_interval, 0.0001)

    lon_start = np.floor(west / lon_interval) * lon_interval
    lat_start = np.floor(south / lat_interval) * lat_interval

    lons = np.arange(lon_start, east + lon_interval * 0.5, lon_interval)
    lats = np.arange(lat_start, north + lat_interval * 0.5, lat_interval)

    gl_kw = {"linewidth": 0.3, "color": "#666666", "alpha": 0.4, "linestyle": "--", "zorder": 2}
    for lon in lons:
        if west <= lon <= east:
            x1, y1 = _deg_to_3857(lon, south)
            x2, y2 = _deg_to_3857(lon, north)
            ax.plot([x1, x2], [y1, y2], **gl_kw)
    for lat in lats:
        if south <= lat <= north:
            x1, y1 = _deg_to_3857(west, lat)
            x2, y2 = _deg_to_3857(east, lat)
            ax.plot([x1, x2], [y1, y2], **gl_kw)

    lbl_kw = {"fontsize": 7.5, "color": "#111111", "zorder": 7, "fontweight": "bold"}

    for lon in lons:
        if west <= lon <= east:
            x_data, _ = _deg_to_3857(lon, (south + north) / 2)
            label = _fmt_coord(lon, is_lon=True)
            ax.annotate(label, xy=(x_data, ymin), xytext=(0, -9),
                        textcoords="offset points", ha="center", va="top",
                        annotation_clip=False, **lbl_kw)
            ax.annotate(label, xy=(x_data, ymax), xytext=(0, 7),
                        textcoords="offset points", ha="center", va="bottom",
                        annotation_clip=False, **lbl_kw)
    for lat in lats:
        if south <= lat <= north:
            _, y_data = _deg_to_3857((west + east) / 2, lat)
            label = _fmt_coord(lat, is_lon=False)
            ax.annotate(label, xy=(xmin, y_data), xytext=(-9, 0),
                        textcoords="offset points", ha="right", va="center",
                        annotation_clip=False, **lbl_kw)
            ax.annotate(label, xy=(xmax, y_data), xytext=(7, 0),
                        textcoords="offset points", ha="left", va="center",
                        annotation_clip=False, **lbl_kw)


def add_map_border(ax):
    """Add a black border frame around the map."""
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    rect = mpatches.Rectangle(
        (xmin, ymin), xmax - xmin, ymax - ymin,
        linewidth=1.5, edgecolor="black", facecolor="none", zorder=5
    )
    ax.add_patch(rect)


def add_scale_bar_map(ax, gdf_m):
    """Add a scale bar in the bottom-center of the map."""
    bounds = gdf_m.total_bounds
    width_m = bounds[2] - bounds[0]
    height_m = bounds[3] - bounds[1]

    target_len = width_m / 5
    order = 10 ** (int(np.log10(target_len)))
    scale_len = round(target_len / order) * order
    if scale_len < 1:
        scale_len = order

    x_center = (bounds[0] + bounds[2]) / 2
    x_start = x_center - scale_len / 2
    y_pos = bounds[1] + height_m * 0.06

    ax.plot([x_start, x_start + scale_len], [y_pos, y_pos],
            color="black", linewidth=2.5, zorder=6)
    tick = height_m * 0.015
    ax.plot([x_start, x_start], [y_pos - tick, y_pos + tick],
            color="black", linewidth=2, zorder=6)
    ax.plot([x_start + scale_len, x_start + scale_len], [y_pos - tick, y_pos + tick],
            color="black", linewidth=2, zorder=6)

    km_val = scale_len / 1000
    label = f"{km_val:.0f} km" if km_val >= 1 else f"{scale_len:.0f} m"
    ax.text(x_center, y_pos - height_m * 0.03, label,
            ha="center", va="top", fontsize=9, fontweight="bold", zorder=6)


def add_north_arrow_map(ax, gdf_m):
    """Add a north arrow on the bottom-right of the map."""
    bounds = gdf_m.total_bounds
    width_m = bounds[2] - bounds[0]
    height_m = bounds[3] - bounds[1]

    x_pos = bounds[2] - width_m * 0.08
    y_pos = bounds[1] + height_m * 0.06
    arrow_len = height_m * 0.05

    ax.annotate(
        "", xy=(x_pos, y_pos + arrow_len), xytext=(x_pos, y_pos),
        ha="center", va="bottom",
        arrowprops=dict(arrowstyle="->", color="black", lw=2.5), zorder=6
    )
    ax.text(x_pos, y_pos + arrow_len + height_m * 0.01, "N",
            ha="center", va="bottom", fontsize=11, fontweight="bold", zorder=6)


def _draw_left_panel(fig, logo_img, map_name, project_name, layers, total_area_ha, total_area_km2, center_lat, center_lng):
    from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
    PANEL_W = 0.27
    ax = fig.add_axes([0, 0, PANEL_W, 1], zorder=5)
    ax.set_facecolor('#fafaf8')
    ax.axis('off')

    y = 0.97

    # ---- LOGO ----
    if logo_img:
        logo_aspect = logo_img.width / logo_img.height
        logo_h_fig = 0.07
        logo_w_fig = logo_h_fig * logo_aspect * (fig.get_size_inches()[1] / fig.get_size_inches()[0])
        ax_logo = fig.add_axes([0.03, y - logo_h_fig, logo_w_fig, logo_h_fig], zorder=6)
        ax_logo.imshow(logo_img)
        ax_logo.axis('off')
        y -= logo_h_fig + 0.025

    # ---- TITLE SECTION ----
    ax.text(0.06, y, (map_name or "Mapa"), fontsize=22, fontweight='800', color='#1f3b2c', va='top')
    y -= 0.065

    if project_name:
        ax.text(0.06, y, project_name, fontsize=14, fontweight='500', color='#4d6b4d', va='top')
        y -= 0.045

    if total_area_ha > 0:
        area_h = f"{total_area_ha:,.0f}" if total_area_ha >= 100 else f"{total_area_ha:,.2f}"
        ax.text(0.06, y, f"Superficie: {area_h} ha", fontsize=11, color='#3c6e3f', va='top')
        y -= 0.035

    y -= 0.015
    ax.plot([0.06, 0.93], [y, y], color='#c0d4b0', linewidth=1.5, transform=ax.transAxes, clip_on=False)
    y -= 0.04

    # ---- LEGEND SECTION ----
    ax.text(0.06, y, 'Referencias', fontsize=16, fontweight='700', color='#2d4a26', va='top')
    y -= 0.045

    for gdf, layer_name, fill_color, edge_color in layers:
        if gdf.empty:
            continue
        geom_type = _get_geom_type(gdf)
        sy = y - 0.02
        if geom_type == 'polygon':
            r = Rectangle((0.06, sy), 0.06, 0.035, facecolor=fill_color, edgecolor=edge_color,
                          linewidth=1, transform=ax.transAxes, zorder=7)
            ax.add_patch(r)
        elif geom_type == 'line':
            ax.plot([0.06, 0.12], [y, y], color=edge_color, linewidth=4,
                    transform=ax.transAxes, zorder=7, clip_on=False)
        elif geom_type == 'point':
            c = Circle((0.09, y), 0.018, facecolor=fill_color, edgecolor=edge_color,
                       linewidth=1, transform=ax.transAxes, zorder=7)
            ax.add_patch(c)
        ax.text(0.13, y, layer_name, fontsize=12, color='#1e2a1e', va='center')
        y -= 0.042

    y -= 0.01
    ax.plot([0.06, 0.93], [y, y], color='#c0d4b0', linewidth=1.5, transform=ax.transAxes, clip_on=False)
    y -= 0.035

    # ---- INFO SECTION ----
    ax.text(0.06, y, 'Información del área', fontsize=16, fontweight='700', color='#2d4a26', va='top')
    y -= 0.045

    info_lines = []
    info_lines.append(('Ubicación:', project_name or 'Área de interés'))
    if total_area_ha > 0:
        area_h = f"{total_area_ha:,.0f}" if total_area_ha >= 100 else f"{total_area_ha:,.2f}"
        area_k = f"{total_area_km2:,.0f}" if total_area_km2 >= 100 else f"{total_area_km2:,.2f}"
        info_lines.append(('Superficie:', f"{area_h} ha ({area_k} km²)"))
    info_lines.append(('Referencia:', map_name or '—'))
    info_lines.append(('Fecha:', datetime.now().strftime("%d/%m/%Y")))
    if center_lat and center_lng:
        info_lines.append(('Coordenadas:', f"Lat {center_lat} / Lon {center_lng}"))

    for label, value in info_lines:
        ax.text(0.06, y, label, fontsize=10, fontweight='600', color='#3c6e3f', va='top')
        ax.text(0.06, y - 0.024, str(value), fontsize=10, color='#1c2c1a', va='top')
        y -= 0.048

    y -= 0.01
    ax.plot([0.06, 0.93], [y, y], color='#c0d4b0', linewidth=1.5, transform=ax.transAxes, clip_on=False)
    y -= 0.035

    # ---- SCALE BAR ----
    ax.text(0.06, y, 'Escala gráfica', fontsize=12, fontweight='600', color='#3c6e3f', va='top')
    y -= 0.03
    bar_len = 0.2
    bar_x = 0.12
    ax.plot([bar_x, bar_x + bar_len], [y, y], color='black', linewidth=4, transform=ax.transAxes, clip_on=False)
    ax.plot([bar_x, bar_x], [y - 0.015, y + 0.015], color='black', linewidth=2.5, transform=ax.transAxes, clip_on=False)
    ax.plot([bar_x + bar_len, bar_x + bar_len], [y - 0.015, y + 0.015], color='black', linewidth=2.5, transform=ax.transAxes, clip_on=False)
    scale_label = '10 km'
    ax.text(bar_x + bar_len / 2, y - 0.035, scale_label, fontsize=10, ha='center', va='top', color='#333', fontweight='bold')
    y -= 0.055

    # ---- CREDITS ----
    ax.text(0.06, 0.02,
            f"© Natura Argentina\nwww.{NATURA_WEB}\n{NATURA_ADDRESS}",
            fontsize=8, color='#7a8f7a', va='bottom', linespacing=1.5)


def _detect_label_column(gdf):
    for col in LABEL_COLUMNS:
        if col in gdf.columns:
            return col
    return None


def create_static_map(
    layers, basemap_name, project_name, map_name, logo_path=None,
    include_scale=True, include_north=True, include_grid=False,
    include_legend=True, include_infobox=True, include_border=True,
    include_labels=False,
):
    if not layers:
        return None

    gdfs_4326 = []
    gdfs_3857 = []
    for gdf, _name, _fc, _ec in layers:
        if gdf.empty:
            continue
        g = gdf.copy()
        if g.crs is None:
            g = g.set_crs("EPSG:4326")
        g_4326 = g.to_crs("EPSG:4326")
        g_3857 = g.to_crs("EPSG:3857")
        if g_4326.empty or g_3857.empty:
            continue
        gdfs_4326.append(g_4326)
        gdfs_3857.append(g_3857)

    if not gdfs_4326:
        raise ValueError("Ninguna capa contiene geometrías válidas después de la reproyección.")

    merged_4326 = gpd.pd.concat(gdfs_4326, ignore_index=True)
    merged_3857 = gpd.pd.concat(gdfs_3857, ignore_index=True)

    bounds_4326 = merged_4326.total_bounds
    if not np.all(np.isfinite(bounds_4326)):
        raise ValueError("Los límites geográficos calculados contienen valores inválidos (NaN/Inf). Revisa la proyección de tus archivos.")

    margin = 0.06
    xm = (bounds_4326[2] - bounds_4326[0]) * margin
    ym = (bounds_4326[3] - bounds_4326[1]) * margin

    extent_4326 = [
        bounds_4326[0] - xm, bounds_4326[2] + xm,
        bounds_4326[1] - ym, bounds_4326[3] + ym,
    ]

    # Calculate area and centroid
    total_area_ha = 0.0
    total_area_km2 = 0.0
    center_lat = ""
    center_lng = ""
    for gdf, _name, _fc, _ec in layers:
        if gdf.empty:
            continue
        g = gdf.copy()
        if g.crs is None:
            g = g.set_crs("EPSG:4326")
        g3857 = g.to_crs("EPSG:3857")
        area_m2 = g3857.area.sum()
        total_area_ha += area_m2 / 10000
        total_area_km2 += area_m2 / 1_000_000
    try:
        center_lat = f"{(bounds_4326[1] + bounds_4326[3]) / 2:.2f}"
        center_lng = f"{(bounds_4326[0] + bounds_4326[2]) / 2:.2f}"
    except Exception:
        pass

    fig = plt.figure(figsize=(16, 11))

    # LEFT PANEL (27% width)
    if logo_path and os.path.exists(logo_path):
        logo_img = Image.open(logo_path)
    else:
        logo_img = None
    _draw_left_panel(fig, logo_img, map_name, project_name, layers,
                     total_area_ha, total_area_km2, center_lat, center_lng)

    # MAP AXES (right side, ~70% width)
    PANEL_W = 0.27
    map_left = PANEL_W + 0.01
    map_bottom = 0.035
    map_w = 1.0 - map_left - 0.01
    map_h = 1.0 - map_bottom - 0.01

    ax = fig.add_axes([map_left, map_bottom, map_w, map_h])

    bounds_3857 = merged_3857.total_bounds
    if not np.all(np.isfinite(bounds_3857)):
        raise ValueError("Los límites del mapa en proyección Mercator contienen valores inválidos. Revisa la proyección de tus archivos.")

    margin_3857 = 0.05
    xm_3857 = (bounds_3857[2] - bounds_3857[0]) * margin_3857
    ym_3857 = (bounds_3857[3] - bounds_3857[1]) * margin_3857
    ax.set_xlim(bounds_3857[0] - xm_3857, bounds_3857[2] + xm_3857)
    ax.set_ylim(bounds_3857[1] - ym_3857, bounds_3857[3] + ym_3857)

    try:
        ctx.add_basemap(
            ax,
            crs=merged_3857.crs.to_string(),
            source=ctx_providers[basemap_name],
            zoom="auto",
        )
    except Exception:
        try:
            ctx.add_basemap(ax, crs=merged_3857.crs.to_string(),
                          source=ctx.providers.OpenStreetMap.Mapnik,
                          zoom="auto")
        except Exception:
            pass

    for gdf_3857, layer_name, fill_color, edge_color in layers:
        g = gdf_3857.to_crs("EPSG:3857")
        g.plot(
            ax=ax,
            facecolor=fill_color,
            edgecolor=edge_color,
            linewidth=1.5,
            alpha=0.4,
            zorder=3,
        )

        if include_labels:
            label_col = _detect_label_column(g)
            if label_col is not None:
                for _, row in g.iterrows():
                    if pd.isna(row[label_col]):
                        continue
                    geom = row.geometry
                    if geom is None or geom.is_empty:
                        continue
                    if geom.geom_type in ("Point", "MultiPoint"):
                        if geom.geom_type == "MultiPoint":
                            xy = geom.centroid
                        else:
                            xy = geom
                    else:
                        xy = geom.representative_point()
                    ax.annotate(
                        str(row[label_col]),
                        xy=(xy.x, xy.y),
                        fontsize=6,
                        color="black",
                        weight="bold",
                        ha="center",
                        va="bottom",
                        zorder=10,
                        bbox=dict(boxstyle="round,pad=0.15", facecolor="white",
                                  edgecolor="none", alpha=0.7),
                    )

    ctx.add_attribution(ax, "")
    ax.tick_params(left=False, labelleft=False, bottom=False, labelbottom=False)

    if include_border:
        add_map_border(ax)

    if include_grid:
        draw_coordinate_grid(ax, extent_4326)

    if include_scale:
        add_scale_bar_map(ax, merged_3857)

    if include_north:
        add_north_arrow_map(ax, merged_3857)

    return fig


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
                    layers = []
                    for i, uf in enumerate(uploaded_files):
                        gdf = load_polygon(uf)
                        if gdf.empty:
                            st.warning(f"'{uf.name}' no contiene geometrías válidas, se omite.")
                            continue
                        layer_name = os.path.splitext(uf.name)[0]
                        fc, ec = LAYER_COLORS[i % len(LAYER_COLORS)]
                        layers.append((gdf, layer_name, fc, ec))
                        st.success(f"✓ {layer_name}: {len(gdf)} geometría(s)")

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
        st.subheader("Exportar mapa estático")

        col_a, col_b = st.columns([1, 1])

        with col_a:
            export_dpi = st.selectbox("Resolución de exportación", [150, 200, 300], index=1)
            include_grid = st.checkbox("Marco de coordenadas", value=False)
            include_border = st.checkbox("Recuadro del mapa", value=True)

        with col_b:
            include_scale = st.checkbox("Barra de escala", value=True)
            include_north = st.checkbox("Flecha de norte", value=True)
            include_infobox = st.checkbox("Caja de información", value=True)
            include_labels = st.checkbox("Etiquetas", value=False)

        if st.button("Generar mapa estático (PNG)", type="primary", use_container_width=True):
            with st.spinner("Generando mapa estático..."):
                try:
                    logo_path = None
                    if uploaded_logo:
                        logo_ext = uploaded_logo.name.split(".")[-1]
                        tmp_logo = tempfile.NamedTemporaryFile(
                            suffix=f".{logo_ext}", delete=False
                        )
                        tmp_logo.write(uploaded_logo.getvalue())
                        tmp_logo.close()
                        logo_path = tmp_logo.name
                    elif os.path.exists(LOGO_DEFAULT):
                        logo_path = LOGO_DEFAULT

                    fig = create_static_map(
                        layers,
                        basemap_name,
                        project_name,
                        map_name,
                        logo_path=logo_path,
                        include_scale=include_scale,
                        include_north=include_north,
                        include_grid=include_grid,
                        include_border=include_border,
                        include_infobox=include_infobox,
                        include_labels=include_labels,
                    )

                    buf = io.BytesIO()
                    fig.savefig(
                        buf,
                        format="png",
                        dpi=export_dpi,
                        bbox_inches="tight",
                        facecolor="white",
                        edgecolor="none",
                    )
                    plt.close(fig)

                    if uploaded_logo and logo_path and os.path.exists(logo_path):
                        os.unlink(logo_path)

                    st.success("Mapa generado correctamente")
                    st.download_button(
                        label="Descargar PNG",
                        data=buf.getvalue(),
                        file_name=f"{map_name.replace(' ', '_')}.png",
                        mime="image/png",
                        use_container_width=True,
                    )

                    buf.seek(0)
                    st.image(buf, caption="Vista previa del mapa estático")

                except Exception as e:
                    st.error(f"Error al generar mapa estático: {str(e)}")

        with st.expander("Exportar mapa interactivo (HTML)"):
            if st.button("Generar HTML", key="gen_html"):
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
                m = create_interactive_map(
                    html_layers,
                    basemap_name,
                    project_name,
                    map_name,
                    include_labels=include_labels,
                    logo_path=export_logo_path,
                )
                if export_logo_path and export_logo_path != LOGO_DEFAULT:
                    try:
                        os.unlink(export_logo_path)
                    except Exception:
                        pass
                html_bytes = m._repr_html_().encode("utf-8")
                st.download_button(
                    label="Descargar HTML",
                    data=html_bytes,
                    file_name=f"{map_name.replace(' ', '_')}.html",
                    mime="text/html",
                )

            st.markdown("---")
            st.subheader("Plantilla de impresión")
            if st.button("Generar plantilla de impresión", key="gen_print"):
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
                        st.download_button(
                            label="Descargar plantilla de impresión (HTML)",
                            data=print_html.encode("utf-8"),
                            file_name=f"{map_name.replace(' ', '_')}_print.html",
                            mime="text/html",
                            use_container_width=True,
                        )
                        st.info("Abrí el HTML en tu navegador para usar los controles de capas y exportar a PNG/JPEG/PDF.")
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
