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
import matplotlib.pyplot as plt
import contextily as ctx
from shapely.geometry import box
from PIL import Image
import numpy as np
import matplotlib.patches as mpatches

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


def create_interactive_map(gdf, basemap_name, project_name, map_name):
    if gdf.crs is None:
        gdf.set_crs("EPSG:4326", inplace=True)
    if gdf.crs.to_string() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    bounds = gdf.total_bounds
    center = [(bounds[1] + bounds[3]) / 2, (bounds[0] + bounds[2]) / 2]

    tile_url = BASEMAPS[basemap_name]
    attr = BASEMAP_ATTRS.get(basemap_name, "")

    m = folium.Map(
        location=center,
        zoom_start=10,
        tiles=tile_url,
        attr=attr,
    )

    style = {
        "fillColor": "#4CAF50",
        "color": "#2E7D32",
        "weight": 2,
        "fillOpacity": 0.35,
    }

    geo_json = folium.GeoJson(
        gdf.to_json(),
        style_function=lambda x: style,
        name=map_name or "Polígono",
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


def draw_coordinate_grid(ax, extent_4326, line_kw=None):
    if line_kw is None:
        line_kw = {"linewidth": 0.4, "color": "#555555", "alpha": 0.5, "linestyle": "--"}

    west, east, south, north = extent_4326
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()

    lon_interval = _nice_interval(east - west)
    lat_interval = _nice_interval(north - south)
    lon_interval = max(lon_interval, 0.0001)
    lat_interval = max(lat_interval, 0.0001)

    lon_start = np.floor(west / lon_interval) * lon_interval
    lat_start = np.floor(south / lat_interval) * lat_interval

    lons = np.arange(lon_start, east + lon_interval, lon_interval)
    lats = np.arange(lat_start, north + lat_interval, lat_interval)

    for lon in lons:
        x1, y1 = _deg_to_3857(lon, south)
        x2, y2 = _deg_to_3857(lon, east)
        ax.plot([x1, x2], [y1, y2], zorder=2, **line_kw)
    for lat in lats:
        x1, y1 = _deg_to_3857(west, lat)
        x2, y2 = _deg_to_3857(east, lat)
        ax.plot([x1, x2], [y1, y2], zorder=2, **line_kw)

    lon_lbls = [l for l in lons if west <= l <= east]
    lat_lbls = [l for l in lats if south <= l <= north]

    for lon in lon_lbls:
        x_data, _ = _deg_to_3857(lon, (south + north) / 2)
        ew = "E" if lon >= 0 else "W"
        label = f"{abs(lon):.4f}°{ew}" if abs(lon) < 10 else f"{abs(lon):.2f}°{ew}"
        ax.annotate(label, xy=(x_data, ymin), xytext=(0, -8),
                    textcoords="offset points", ha="center", va="top",
                    fontsize=7, zorder=7,
                    annotation_clip=False)
        ax.annotate(label, xy=(x_data, ymax), xytext=(0, 6),
                    textcoords="offset points", ha="center", va="bottom",
                    fontsize=7, zorder=7,
                    annotation_clip=False)
    for lat in lat_lbls:
        _, y_data = _deg_to_3857((west + east) / 2, lat)
        ns = "S" if lat < 0 else "N"
        label = f"{abs(lat):.4f}°{ns}" if abs(lat) < 10 else f"{abs(lat):.2f}°{ns}"
        ax.annotate(label, xy=(xmin, y_data), xytext=(-8, 0),
                    textcoords="offset points", ha="right", va="center",
                    fontsize=7, zorder=7,
                    annotation_clip=False)
        ax.annotate(label, xy=(xmax, y_data), xytext=(6, 0),
                    textcoords="offset points", ha="left", va="center",
                    fontsize=7, zorder=7,
                    annotation_clip=False)


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
        fontsize=18, fontweight="bold", fontfamily="sans-serif",
        va="top", ha="center",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="black", alpha=0.85),
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
        [0.015, 0.01, logo_w_in / fig_w, logo_h_in / fig_h],
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


def add_legend(fig, ax, gdf_m):
    """Add a legend box in the bottom-right section."""
    legend_text = "Área de interés"
    from matplotlib.lines import Line2D
    legend_elem = [
        Line2D([0], [0], marker="s", color="w", markerfacecolor="#4CAF50",
               markeredgecolor="#2E7D32", markersize=10, label=legend_text),
    ]
    leg = ax.legend(
        handles=legend_elem,
        loc="lower right",
        fontsize=9,
        framealpha=0.9,
        edgecolor="black",
        facecolor="white",
        title="Leyenda",
        title_fontsize=10,
    )
    leg.get_title().set_fontweight("bold")


def add_info_box(fig, project_name, map_name, gdf):
    area_3857 = gdf.to_crs("EPSG:3857")
    total_area_km2 = area_3857.area.sum() / 1_000_000
    perimeter_m = area_3857.length.sum()
    perimeter_km = perimeter_m / 1000

    lines = []
    lines.append(f"Proyecto: {project_name}")
    lines.append(f"Mapa: {map_name}")
    lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y')}")
    lines.append(f"Superficie: {total_area_km2:,.2f} km²")
    lines.append(f"Perímetro: {perimeter_km:,.2f} km")
    info_text = "\n".join(lines)

    fig.text(
        0.78, 0.07, info_text,
        fontsize=10, fontfamily="sans-serif",
        va="bottom", ha="left",
        bbox=dict(boxstyle="round,pad=0.6", facecolor="white", edgecolor="black", alpha=0.9),
    )


def create_static_map(
    gdf, basemap_name, project_name, map_name, logo_path=None,
    include_scale=True, include_north=True, include_grid=True,
    include_legend=True, include_infobox=True, include_border=True,
):
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf_4326 = gdf.to_crs("EPSG:4326")
    gdf_3857 = gdf.to_crs("EPSG:3857")

    bounds_4326 = gdf_4326.total_bounds
    margin = 0.06
    xm = (bounds_4326[2] - bounds_4326[0]) * margin
    ym = (bounds_4326[3] - bounds_4326[1]) * margin

    extent_4326 = [
        bounds_4326[0] - xm, bounds_4326[2] + xm,
        bounds_4326[1] - ym, bounds_4326[3] + ym,
    ]

    fig = plt.figure(figsize=(16, 11))

    left = 0.1
    bottom = 0.14
    map_w = 0.75
    map_h = 0.72

    ax = fig.add_axes([left, bottom, map_w, map_h])

    bounds_3857 = gdf_3857.total_bounds
    margin_3857 = 0.06
    xm_3857 = (bounds_3857[2] - bounds_3857[0]) * margin_3857
    ym_3857 = (bounds_3857[3] - bounds_3857[1]) * margin_3857
    ax.set_xlim(bounds_3857[0] - xm_3857, bounds_3857[2] + xm_3857)
    ax.set_ylim(bounds_3857[1] - ym_3857, bounds_3857[3] + ym_3857)

    try:
        ctx.add_basemap(
            ax,
            crs=gdf_3857.crs.to_string(),
            source=ctx_providers[basemap_name],
            zoom="auto",
        )
    except Exception:
        try:
            ctx.add_basemap(ax, crs=gdf_3857.crs.to_string(),
                          source=ctx.providers.OpenStreetMap.Mapnik,
                          zoom="auto")
        except Exception:
            pass

    gdf_3857.plot(
        ax=ax,
        facecolor="#4CAF50",
        edgecolor="#2E7D32",
        linewidth=1.5,
        alpha=0.4,
        zorder=3,
    )

    ctx.add_attribution(ax, "")

    if include_border:
        add_map_border(ax)

    if include_grid:
        draw_coordinate_grid(ax, extent_4326)

    if include_legend:
        add_legend(fig, ax, gdf_3857)

    if include_scale:
        add_scale_bar_map(ax, gdf_3857)

    if include_north:
        add_north_arrow_map(ax, gdf_3857)

    if logo_path and os.path.exists(logo_path):
        logo_img = Image.open(logo_path)
    else:
        logo_img = None

    add_title_box(fig, map_name, project_name)
    add_logo_box(fig, logo_img)

    if include_infobox:
        add_info_box(fig, project_name, map_name, gdf_4326)

    return fig


def main():
    st.title("Mapas Automáticos")
    st.markdown("Sube un polígono (KML, SHP, GeoJSON) y genera mapas con formato estandarizado.")

    if "file_key" not in st.session_state:
        st.session_state["file_key"] = 0
        st.session_state["gdf"] = None

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Datos del mapa")
        project_name = st.text_input("Nombre del proyecto", value="Proyecto Ejemplo")
        map_name = st.text_input("Nombre del mapa", value="Mapa de Área de Interés")

        uploaded_file = st.file_uploader(
            "Cargar archivo del polígono",
            type=["kml", "kmz", "zip", "shp", "geojson", "json"],
            help="KML, KMZ, ZIP (con SHP), SHP, o GeoJSON",
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

        if uploaded_file is None:
            st.session_state["gdf"] = None
            st.info("Carga un archivo para ver la vista previa")
        else:
            with st.spinner("Leyendo archivo..."):
                try:
                    gdf = load_polygon(uploaded_file)

                    if gdf.empty:
                        st.error("El archivo no contiene geometrías válidas.")
                        st.session_state["gdf"] = None
                    else:
                        st.success(f"Polígono cargado: {len(gdf)} geometría(s)")
                        st.session_state["gdf"] = gdf

                        if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
                            gdf_plot = gdf.to_crs("EPSG:4326")
                        else:
                            gdf_plot = gdf

                        m = create_interactive_map(
                            gdf_plot, basemap_name, project_name, map_name
                        )
                        st_folium(m, width=None, height=500)

                except Exception as e:
                    st.error(f"Error al leer el archivo: {str(e)}")
                    st.session_state["gdf"] = None

    if st.session_state["gdf"] is not None:
        gdf = st.session_state["gdf"]

        if st.button("Nuevo mapa", type="secondary"):
            st.session_state["gdf"] = None
            st.session_state["file_key"] += 1
            st.rerun()

        st.divider()
        st.subheader("Exportar mapa estático")

        col_a, col_b = st.columns([1, 1])

        with col_a:
            export_dpi = st.selectbox("Resolución de exportación", [150, 200, 300], index=1)
            include_grid = st.checkbox("Marco de coordenadas", value=True)
            include_border = st.checkbox("Recuadro del mapa", value=True)

        with col_b:
            include_scale = st.checkbox("Barra de escala", value=True)
            include_north = st.checkbox("Flecha de norte", value=True)
            include_infobox = st.checkbox("Caja de información", value=True)

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
                        gdf,
                        basemap_name,
                        project_name,
                        map_name,
                        logo_path=logo_path,
                        include_scale=include_scale,
                        include_north=include_north,
                        include_grid=include_grid,
                        include_border=include_border,
                        include_infobox=include_infobox,
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
                if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
                    gdf_html = gdf.to_crs("EPSG:4326")
                else:
                    gdf_html = gdf
                m = create_interactive_map(
                    gdf_html,
                    basemap_name,
                    project_name,
                    map_name,
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
