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

    if fname.endswith(".kml") or fname.endswith(".kmz"):
        return ensure_crs(read_kml(file_bytes))
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


def create_interactive_map(layers, basemap_name, project_name, map_name, include_labels=False):
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

    for gdf, layer_name, fill_color, edge_color in layers:
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
        geo_json = folium.GeoJson(
            gdf.to_json(),
            style_function=lambda x, s=style: s,
            name=layer_name,
            tooltip=tooltip,
        )
        geo_json.add_to(m)

    if map_name:
        title_html = f"""
        <div style="position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
                    z-index: 9999; background: white; padding: 8px 24px;
                    border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                    font-family: sans-serif; font-size: 18px; font-weight: bold;
                    text-align: center; pointer-events: none;">
            {map_name}
        </div>
        """
        m.get_root().html.add_child(folium.Element(title_html))

    if project_name:
        subtitle_html = f"""
        <div style="position: fixed; top: 52px; left: 50%; transform: translateX(-50%);
                    z-index: 9999; background: rgba(255,255,255,0.9); padding: 4px 16px;
                    border-radius: 4px; box-shadow: 0 1px 4px rgba(0,0,0,0.2);
                    font-family: sans-serif; font-size: 13px; color: #555;
                    text-align: center; pointer-events: none;">
            {project_name}
        </div>
        """
        m.get_root().html.add_child(folium.Element(subtitle_html))

    plugins.Fullscreen(position="topright").add_to(m)
    plugins.MousePosition(position="bottomright").add_to(m)
    plugins.MeasureControl(position="topleft").add_to(m)

    m.fit_bounds([[bounds[1], bounds[0]], [bounds[3], bounds[2]]])

    return m


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


def add_title_box(fig, map_name, project_name):
    """Add title box at the top-left of the figure."""
    text_lines = []
    if map_name:
        text_lines.append(map_name)
    if project_name:
        text_lines.append(project_name)
    if not text_lines:
        return

    title_text = "\n".join(text_lines)
    fig.text(
        0.5, 0.97, title_text,
        fontsize=20, fontweight="bold", color="#111111",
        va="top", ha="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="black", alpha=0.85),
    )


def add_logo_box(fig, logo_img):
    """Add logo at the bottom-left of the figure."""
    if logo_img is None:
        return
    logo_aspect = logo_img.width / logo_img.height
    logo_w_in = 2.0
    logo_h_in = logo_w_in / logo_aspect
    fig_w, fig_h = fig.get_size_inches()
    ax_logo = fig.add_axes(
        [0.015, 0.015, logo_w_in / fig_w, logo_h_in / fig_h],
        zorder=10,
    )
    ax_logo.imshow(logo_img)
    ax_logo.axis("off")


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


def add_legend(fig, ax, layers):
    from matplotlib.lines import Line2D
    legend_elem = []
    for gdf, layer_name, fill_color, edge_color in layers:
        label = layer_name or "Capa"
        legend_elem.append(
            Line2D([0], [0], marker="s", color="w", markerfacecolor=fill_color,
                   markeredgecolor=edge_color, markersize=10, label=label),
        )
    leg = fig.legend(
        handles=legend_elem,
        loc="upper left",
        bbox_to_anchor=(0.02, 0.65),
        fontsize=10,
        framealpha=0.9,
        edgecolor="black",
        facecolor="white",
        title="Leyenda",
        title_fontsize=11,
    )
    leg.get_title().set_fontweight("bold")


def add_info_box(fig, project_name, map_name, layers):
    NATURA_GREEN = "#2D6A4F"
    DARK = "#222222"

    lines = []
    lines.append(f"Proyecto: {project_name}")
    lines.append(f"Mapa: {map_name}")

    total_area = 0
    total_perim = 0
    for gdf, layer_name, _fc, _ec in layers:
        area_3857 = gdf.to_crs("EPSG:3857")
        area_km2 = area_3857.area.sum() / 1_000_000
        perim_m = area_3857.length.sum()
        perim_km = perim_m / 1000
        total_area += area_km2
        total_perim += perim_km
        lines.append(f"{layer_name}: {area_km2:,.2f} km² / {perim_km:,.2f} km")

    if len(layers) > 1:
        lines.append(f"Total: {total_area:,.2f} km² / {total_perim:,.2f} km")

    data_text = "\n".join(lines)

    fig.text(
        0.02, 0.87, "Departamento Técnico",
        fontsize=12, fontweight="bold", fontproperties=FontProperties(family=FONT_FAMILY, size=12), color=NATURA_GREEN,
        va="top", ha="left",
    )
    fig.text(
        0.02, 0.84, data_text,
        fontsize=12, fontproperties=FontProperties(family=FONT_FAMILY, size=12, weight="bold"), color=DARK,
        va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="white", edgecolor=NATURA_GREEN, alpha=0.95, linewidth=1.2),
    )


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

    fig = plt.figure(figsize=(16, 12))

    map_left = 0.28
    map_bottom = 0.08
    map_w = 0.69
    map_h = 0.70

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

    if include_legend:
        add_legend(fig, ax, layers)

    if include_scale:
        add_scale_bar_map(ax, merged_3857)

    if include_north:
        add_north_arrow_map(ax, merged_3857)

    if logo_path and os.path.exists(logo_path):
        logo_img = Image.open(logo_path)
    else:
        logo_img = None

    add_title_box(fig, map_name, project_name)
    add_logo_box(fig, logo_img)

    if include_infobox:
        add_info_box(fig, project_name, map_name, layers)

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
                        m = create_interactive_map(
                            layers, basemap_name, project_name, map_name,
                            include_labels=True,
                        )
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
            if st.button("Generar HTML"):
                html_layers = []
                for gdf, layer_name, fc, ec in layers:
                    if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
                        gdf_html = gdf.to_crs("EPSG:4326")
                    else:
                        gdf_html = gdf
                    html_layers.append((gdf_html, layer_name, fc, ec))
                m = create_interactive_map(
                    html_layers,
                    basemap_name,
                    project_name,
                    map_name,
                    include_labels=include_labels,
                )
                html_bytes = m._repr_html_().encode("utf-8")
                st.download_button(
                    label="Descargar HTML",
                    data=html_bytes,
                    file_name=f"{map_name.replace(' ', '_')}.html",
                    mime="text/html",
                )


if __name__ == "__main__":
    main()
