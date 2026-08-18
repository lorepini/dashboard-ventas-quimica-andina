"""
Dashboard de ventas del grupo.

El usuario sube los tres reporteadores semanales, la app los procesa en memoria
y muestra los indicadores. Los datos no se guardan: cada sesion parte de los
archivos que se suban. Lo unico que persiste son las metas anuales, que se
escriben una vez y quedan disponibles en las siguientes sesiones.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from core import auth
from core import metas as metas_mod
from core import metrics as m
from core.loader import (
    EMPRESAS,
    ORDEN_EMPRESAS,
    aplicar_filtros,
    cargar_reporteador,
    combinar,
    detectar_empresa,
)
from ui import componentes as c
from ui import tab_empresa, tab_grupo

st.set_page_config(
    page_title="Ventas | Grupo Química Andina",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Carga de archivos
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _procesar(archivos: list[tuple[str, bytes]]) -> tuple[pd.DataFrame, list[dict]]:
    """
    Procesa los archivos subidos. Se cachea por contenido para que cambiar de
    pestaña o mover un filtro no vuelva a leer los Excel.
    """
    from io import BytesIO

    resultados, diagnostico = [], []
    for nombre, contenido in archivos:
        empresa = detectar_empresa(nombre)
        if empresa is None:
            diagnostico.append({
                "archivo": nombre,
                "empresa": None,
                "error": "No se pudo identificar la empresa por el nombre del archivo.",
            })
            continue
        try:
            resultado = cargar_reporteador(BytesIO(contenido), empresa)
        except Exception as exc:  # el mensaje se le muestra al usuario tal cual
            diagnostico.append({"archivo": nombre, "empresa": empresa, "error": str(exc)})
            continue

        resultados.append(resultado)
        diagnostico.append({
            "archivo": nombre,
            "empresa": empresa,
            "error": None,
            "filas": resultado.filas_validas,
            "desde": resultado.fecha_min,
            "hasta": resultado.fecha_max,
            "advertencias": resultado.advertencias,
        })

    return combinar(resultados), diagnostico


def _pantalla_carga() -> None:
    """Pantalla inicial: explica en dos lineas que hay que hacer."""
    st.title("Dashboard de Ventas")
    st.markdown(
        "#### Sube los tres reporteadores de la semana para ver los indicadores actualizados."
    )
    st.info(
        "Arrastra los archivos **REPORTEADOR INDUSTRIAL**, **REPORTEADOR SOCIEDAD MINERA** "
        "y **REPORTEADOR YESO LA LIMEÑA** en el recuadro de la barra lateral. "
        "La app identifica sola a que empresa corresponde cada uno.",
        icon="⬅️",
    )
    st.caption(
        "Los archivos no se guardan en ningun lado: se procesan en el momento y se "
        "descartan al cerrar. Las metas que cargues si quedan guardadas."
    )


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------

def _formulario_metas(anio: int, df: pd.DataFrame) -> None:
    """
    Formulario de metas anuales. Se escribe una vez y queda guardado para las
    siguientes sesiones, sin necesidad de subir ni descargar ningun archivo.
    """
    guardadas = metas_mod.cargar_metas()
    with st.form("form_metas"):
        st.caption(f"Meta de venta anual {anio}, en soles y sin IGV.")
        valores: dict[str, float] = {}
        for empresa in ORDEN_EMPRESAS:
            actual = metas_mod.obtener_meta(anio, empresa)
            valores[empresa] = st.number_input(
                EMPRESAS[empresa]["nombre"],
                min_value=0.0,
                value=float(actual) if actual else 0.0,
                step=100_000.0,
                format="%.0f",
                key=f"meta_{anio}_{empresa}",
            )
        if st.form_submit_button("Guardar metas", use_container_width=True, type="primary"):
            metas_mod.guardar_metas_anio(anio, valores)
            st.success("Metas guardadas. Quedan disponibles la proxima vez que abras la app.")
            st.rerun()

    cargados = sorted(a for a in guardadas if int(a) != anio)
    if cargados:
        st.caption("Años con meta guardada: " + ", ".join(str(a) for a in cargados))


def _pedir_archivos() -> list:
    """Primer bloque de la barra lateral: la carga semanal."""
    with st.sidebar:
        st.markdown("### Datos de la semana")
        return st.file_uploader(
            "Reporteadores (.xls)",
            type=["xls", "xlsx"],
            accept_multiple_files=True,
            help="Puedes subir los tres a la vez.",
        )


def _controles(df: pd.DataFrame) -> dict:
    """
    Resto de la barra lateral, una vez que hay datos cargados.

    Va despues del procesamiento porque el selector de año depende de lo que
    traigan los archivos.
    """
    with st.sidebar:
        st.divider()
        st.markdown("### Periodo")
        anio = st.selectbox("Año a analizar", m.anios_disponibles(df), index=0)

        st.divider()
        st.markdown("### Que se incluye")
        servicios = st.checkbox(
            "Incluir servicios (fletes, alquileres)",
            value=False,
            help="Los codigos SER corresponden a fletes, alquileres y servicios varios. "
            "Apagado, el ranking muestra solo productos.",
        )
        intercompany = st.checkbox(
            "Incluir ventas entre las empresas del grupo",
            value=False,
            help="Las tres empresas se facturan entre si. Apagado, el consolidado "
            "muestra la venta real a clientes externos.",
        )

        st.divider()
        st.markdown("### Metas")
        _formulario_metas(anio, df)

        st.divider()
        auth.boton_salir()

    return {"anio": anio, "servicios": servicios, "intercompany": intercompany}


# ---------------------------------------------------------------------------
# Principal
# ---------------------------------------------------------------------------

def main() -> None:
    c.aplicar_estilos()

    # La app es publica en internet: nada se muestra antes de la clave.
    if not auth.exigir_acceso():
        return

    archivos = _pedir_archivos()

    if not archivos:
        _pantalla_carga()
        return

    with st.spinner("Procesando los reporteadores..."):
        df, diagnostico = _procesar([(a.name, a.getvalue()) for a in archivos])

    for d in [d for d in diagnostico if d["error"]]:
        st.error(f"**{d['archivo']}**: {d['error']}")

    if df.empty:
        st.warning("No se pudo leer ningun archivo valido. Revisa que sean los reporteadores.")
        return

    opciones = _controles(df)
    anio = opciones["anio"]

    df_filtrado = aplicar_filtros(
        df,
        incluir_intercompany=opciones["intercompany"],
        incluir_servicios=opciones["servicios"],
    )
    corte = m.fecha_corte(df)

    cargadas = [d for d in diagnostico if not d["error"]]
    faltantes = [
        EMPRESAS[e]["nombre"] for e in ORDEN_EMPRESAS
        if e not in {d["empresa"] for d in cargadas}
    ]

    encabezado = st.container()
    with encabezado:
        izq, der = st.columns([3, 1])
        izq.title("Dashboard de Ventas")
        der.metric("Datos actualizados al", corte.strftime("%d/%m/%Y"))
        if faltantes:
            st.warning(
                "Falta subir el reporteador de: " + ", ".join(faltantes) +
                ". Las cifras del grupo estan incompletas.",
                icon="⚠️",
            )
    # Los ajustes de limpieza son informacion de respaldo, no de decision:
    # viven en la barra lateral para no gastar espacio en la pantalla principal.
    if any(d.get("advertencias") for d in cargadas):
        with st.sidebar:
            with st.expander("Ajustes aplicados a los datos"):
                for d in cargadas:
                    for aviso in d.get("advertencias", []):
                        st.caption(f"**{EMPRESAS[d['empresa']]['nombre']}**: {aviso}")

    nombres = [EMPRESAS[e]["nombre"] for e in ORDEN_EMPRESAS if e in set(df["EMPRESA"])]
    pestanas = st.tabs(["Resumen del Grupo"] + nombres)

    with pestanas[0]:
        tab_grupo.render(df_filtrado, anio, corte)

    presentes = [e for e in ORDEN_EMPRESAS if e in set(df["EMPRESA"])]
    for pestana, empresa in zip(pestanas[1:], presentes):
        with pestana:
            tab_empresa.render(df_filtrado, empresa, anio, corte)


if __name__ == "__main__":
    main()
