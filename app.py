import io
import zipfile
import tempfile
import os

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


def load_polygon(uploaded_file):
    file_bytes = uploaded_file.getvalue()
    fname = uploaded_file.name.lower()

    if fname.endswith(".kml") or fname.endswith(".kmz"):
        return read_kml(file_bytes)
    elif fname.endswith(".zip"):
        return read_shapefile_zip(file_bytes)
    elif fname.endswith(".shp"):
        with tempfile.TemporaryDirectory() as tmpdir:
            shp_path = os.path.join(tmpdir, uploaded_file.name)
            with open(shp_path, "wb") as f:
                f.write(file_bytes)
            os.environ["SHAPE_RESTORE_SHX"] = "YES"
            return gpd.read_file(shp_path)
    elif fname.endswith(".geojson") or fname.endswith(".json"):
        with tempfile.NamedTemporaryFile(suffix=".geojson", delete=False) as f:
            f.write(file_bytes)
            f.flush()
            path = f.name
        try:
            return gpd.read_file(path)
        finally:
            os.unlink(path)
    else:
        raise ValueError(
            "Formato no soportado. Usa .kml, .kmz, .zip (con .shp), .shp, .geojson"
        )


def create_interactive_map(gdf, basemap_name, project_name, map_name):
    if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
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


def add_scale_bar(ax, gdf_m):
    bounds = gdf_m.total_bounds
    width_m = bounds[2] - bounds[0]
    height_m = bounds[3] - bounds[1]

    target_len = width_m / 5
    order = 10 ** (int(np.log10(target_len)))
    scale_len = round(target_len / order) * order

    x_min = bounds[0] + width_m * 0.06
    y_min = bounds[1] + height_m * 0.06

    ax.plot(
        [x_min, x_min + scale_len],
        [y_min, y_min],
        color="black",
        linewidth=2.5,
        transform=ax.transData,
    )
    tick_size = height_m * 0.015
    ax.plot(
        [x_min, x_min],
        [y_min - tick_size, y_min + tick_size],
        color="black",
        linewidth=2,
        transform=ax.transData,
    )
    ax.plot(
        [x_min + scale_len, x_min + scale_len],
        [y_min - tick_size, y_min + tick_size],
        color="black",
        linewidth=2,
        transform=ax.transData,
    )

    km_val = scale_len / 1000
    label = f"{km_val:.0f} km" if km_val >= 1 else f"{scale_len:.0f} m"
    ax.text(
        x_min + scale_len / 2,
        y_min - height_m * 0.03,
        label,
        ha="center",
        va="top",
        fontsize=10,
        fontweight="bold",
    )


def add_north_arrow(ax, gdf_m):
    bounds = gdf_m.total_bounds
    width_m = bounds[2] - bounds[0]
    height_m = bounds[3] - bounds[1]

    nx = bounds[0] + width_m * 0.06
    ny = bounds[1] + height_m * 0.15

    arrow_length = height_m * 0.06
    ax.annotate(
        "",
        xy=(nx, ny + arrow_length),
        xytext=(nx, ny),
        ha="center",
        va="bottom",
        fontsize=14,
        fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="black", lw=2.5),
    )
    ax.text(
        nx,
        ny + arrow_length + height_m * 0.01,
        "N",
        ha="center",
        va="bottom",
        fontsize=13,
        fontweight="bold",
    )


def create_static_map(
    gdf, basemap_name, project_name, map_name, logo_path=None,
    include_scale=True, include_north=True
):
    if gdf.crs is None or gdf.crs.to_string() != "EPSG:3857":
        gdf_m = gdf.to_crs("EPSG:3857")
    else:
        gdf_m = gdf

    if logo_path and os.path.exists(logo_path):
        logo_img = Image.open(logo_path)
    else:
        logo_img = None

    fig, ax = plt.subplots(1, 1, figsize=(12, 10))

    try:
        ctx.add_basemap(
            ax,
            crs=gdf_m.crs.to_string(),
            source=ctx_providers[basemap_name],
        )
    except Exception:
        try:
            ctx.add_basemap(ax, crs=gdf_m.crs.to_string(), source=ctx.providers.OpenStreetMap.Mapnik)
        except Exception:
            pass

    gdf_m.plot(
        ax=ax,
        facecolor="#4CAF50",
        edgecolor="#2E7D32",
        linewidth=1.5,
        alpha=0.4,
    )

    ctx.add_attribution(ax, "")

    bounds = gdf_m.total_bounds
    margin = 0.05
    x_margin = (bounds[2] - bounds[0]) * margin
    y_margin = (bounds[3] - bounds[1]) * margin
    ax.set_xlim(bounds[0] - x_margin, bounds[2] + x_margin)
    ax.set_ylim(bounds[1] - y_margin, bounds[3] + y_margin)

    ax.axis("off")

    if logo_img:
        logo_aspect = logo_img.width / logo_img.height
        logo_width_inches = 1.8
        logo_height_inches = logo_width_inches / logo_aspect
        fig_w, fig_h = fig.get_size_inches()
        ax_logo = fig.add_axes(
            [0.03, 0.03, logo_width_inches / fig_w, logo_height_inches / fig_h],
            zorder=10,
        )
        ax_logo.imshow(logo_img)
        ax_logo.axis("off")

    title_lines = []
    if map_name:
        title_lines.append(map_name)
    if project_name:
        title_lines.append(project_name)

    if title_lines:
        title_text = "\n".join(title_lines)
        ax.set_title(
            title_text,
            fontsize=14,
            fontweight="bold",
            pad=12,
            loc="center",
            family="sans-serif",
        )

    if include_scale:
        add_scale_bar(ax, gdf_m)

    if include_north:
        add_north_arrow(ax, gdf_m)

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
            include_scale = st.checkbox("Incluir barra de escala", value=True)
            include_north = st.checkbox("Incluir norte", value=True)

        with col_b:
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
