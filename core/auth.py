"""
Control de acceso por clave compartida.

La app se publica en internet, asi que la pantalla de ingreso es lo primero que
se ejecuta. La clave no vive en el codigo: se lee de `st.secrets`, que en
Streamlit Cloud se configura desde el panel de la aplicacion y en local vive en
`.streamlit/secrets.toml` (archivo que nunca se sube al repositorio).
"""

from __future__ import annotations

import hmac

import streamlit as st

CLAVE_SESION = "acceso_concedido"


def _clave_configurada() -> str | None:
    """Lee la clave de los secretos. Devuelve None si no hay ninguna configurada."""
    try:
        valor = st.secrets["app"]["clave"]
    except Exception:
        return None
    valor = str(valor).strip()
    return valor or None


def _pantalla_sin_clave() -> None:
    """
    Aviso para quien despliega, no para el usuario final.

    Si la app llegara a publicarse sin clave quedaria abierta a cualquiera, asi
    que se bloquea el paso en lugar de dejarla pasar por omision.
    """
    st.title("Falta configurar la clave de acceso")
    st.error(
        "La aplicacion no tiene clave y no puede abrirse asi, porque quedaria "
        "visible para cualquiera con el enlace."
    )
    st.markdown(
        "**Para configurarla en Streamlit Cloud:** entra a la aplicacion, "
        "abre *Settings → Secrets* y pega estas dos lineas:"
    )
    st.code('[app]\nclave = "la-clave-que-elijas"', language="toml")
    st.markdown(
        "**Para configurarla en esta computadora:** crea el archivo "
        "`.streamlit/secrets.toml` dentro de la carpeta `dashboard` con el mismo contenido."
    )


def _pantalla_ingreso() -> None:
    """Pantalla de ingreso: lo minimo indispensable, sin distracciones."""
    izq, centro, der = st.columns([1, 1.4, 1])
    with centro:
        st.markdown("## Dashboard de Ventas")
        st.caption("Ingresa la clave para continuar.")
        with st.form("ingreso"):
            clave = st.text_input("Clave", type="password", label_visibility="collapsed",
                                  placeholder="Clave de acceso")
            enviar = st.form_submit_button("Entrar", use_container_width=True, type="primary")

        if enviar:
            # compare_digest evita filtrar informacion por el tiempo de comparacion.
            if hmac.compare_digest(clave, _clave_configurada() or ""):
                st.session_state[CLAVE_SESION] = True
                st.rerun()
            else:
                st.error("Clave incorrecta.")


def exigir_acceso() -> bool:
    """
    Bloquea la app hasta que se ingrese la clave correcta.

    Devuelve True cuando el acceso esta concedido. Llamar al inicio de `main()`
    y salir de inmediato si devuelve False.
    """
    if st.session_state.get(CLAVE_SESION):
        return True

    if _clave_configurada() is None:
        _pantalla_sin_clave()
        return False

    _pantalla_ingreso()
    return False


def boton_salir() -> None:
    """Cierra la sesion. Se muestra al pie de la barra lateral."""
    if st.button("Cerrar sesion", use_container_width=True):
        st.session_state.pop(CLAVE_SESION, None)
        st.rerun()
