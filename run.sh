#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$DIR/venv"

if [ ! -d "$VENV" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv "$VENV"
    source "$VENV/bin/activate"
    pip install "numpy<2" "pandas<2.2" geopandas folium streamlit streamlit-folium contextily matplotlib shapely Pillow
else
    source "$VENV/bin/activate"
fi

echo "Iniciando Mapas Automáticos..."
xdg-open "http://localhost:8501" 2>/dev/null || open "http://localhost:8501" 2>/dev/null || true
streamlit run "$DIR/app.py" --server.port 8501
