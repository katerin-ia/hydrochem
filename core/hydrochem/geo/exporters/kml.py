"""Generacion de KML sin dependencias externas.

El notebook usaba ``simplekml``, que en el equipo de destino no se puede
instalar. KML es XML con una estructura muy acotada, asi que se escribe con la
libreria estandar y se evita la dependencia.

Detalles de KML que es facil equivocar y que aqui quedan resueltos:

- **El color va en ``aabbggrr``**, no en ``#rrggbb``: alfa, azul, verde, rojo.
  Un ``#0e6b75`` se escribe ``ff756b0e``.
- Las coordenadas van **``lon,lat,alt``**, en ese orden.
- El separador decimal tiene que ser el punto **siempre**, con independencia de
  la configuracion regional. El manual del propio libro PiperStiff documenta
  este mismo fallo, corregido en su version 7.
- La descripcion HTML va envuelta en ``CDATA``, y cualquier texto que venga del
  dato del usuario se escapa antes.
- La leyenda se hace con un ``ScreenOverlay``, no con marcadores en (0,0). El
  notebook los ponia ahi y aparecian flotando en el golfo de Guinea.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape

#: Carpeta interna del KMZ donde van las imagenes.
FILES_DIR = "files"


def hex_to_kml_color(hex_color: str, alpha: int = 255) -> str:
    """``#rrggbb`` -> ``aabbggrr``, que es el orden que espera KML."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"Color no valido: {hex_color!r}. Usa el formato #rrggbb.")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"{alpha:02x}{b}{g}{r}".lower()


def num(value, decimals: int = 8) -> str:
    """Numero con punto decimal, sin depender de la configuracion regional."""
    if value is None:
        return ""
    return f"{float(value):.{decimals}f}".rstrip("0").rstrip(".") or "0"


def cdata(html: str) -> str:
    """Envuelve HTML en CDATA, cerrando cualquier ``]]>`` que trajera dentro."""
    return "<![CDATA[" + html.replace("]]>", "]]]]><![CDATA[>") + "]]>"


@dataclass
class Placemark:
    """Un punto del mapa."""

    name: str
    lon: float
    lat: float
    description_html: str = ""
    style_id: str = ""
    #: Campos para la ventana de atributos de Google Earth (pestana de datos).
    data: dict[str, object] = field(default_factory=dict)

    def to_xml(self, indent: str = "      ") -> str:
        parts = [f"{indent}<Placemark>"]
        parts.append(f"{indent}  <name>{escape(str(self.name))}</name>")
        if self.style_id:
            parts.append(f"{indent}  <styleUrl>#{escape(self.style_id)}</styleUrl>")
        if self.description_html:
            parts.append(f"{indent}  <description>{cdata(self.description_html)}</description>")
        if self.data:
            parts.append(f"{indent}  <ExtendedData>")
            for key, value in self.data.items():
                if value is None:
                    continue
                parts.append(
                    f'{indent}    <Data name="{escape(str(key))}">'
                    f"<value>{escape(str(value))}</value></Data>"
                )
            parts.append(f"{indent}  </ExtendedData>")
        parts.append(f"{indent}  <Point>")
        parts.append(
            f"{indent}    <coordinates>{num(self.lon)},{num(self.lat)},0</coordinates>"
        )
        parts.append(f"{indent}  </Point>")
        parts.append(f"{indent}</Placemark>")
        return "\n".join(parts)


@dataclass
class IconStyle:
    """Estilo de marcador. ``icon_href`` puede ser una imagen del propio KMZ."""

    style_id: str
    icon_href: str | None = None
    color_hex: str | None = None
    scale: float = 1.1
    highlight_scale: float = 1.6
    label_scale: float = 0.8

    def _style(self, style_id: str, scale: float, indent: str) -> str:
        lines = [f'{indent}<Style id="{escape(style_id)}">', f"{indent}  <IconStyle>"]
        if self.color_hex:
            lines.append(f"{indent}    <color>{hex_to_kml_color(self.color_hex)}</color>")
        lines.append(f"{indent}    <scale>{num(scale, 3)}</scale>")
        if self.icon_href:
            lines.append(f"{indent}    <Icon><href>{escape(self.icon_href)}</href></Icon>")
            # Sin hotSpot, Google Earth ancla la imagen por su esquina inferior
            # izquierda y el diagrama queda descolocado respecto al punto.
            lines.append(
                f'{indent}    <hotSpot x="0.5" y="0.5" '
                f'xunits="fraction" yunits="fraction"/>'
            )
        lines.append(f"{indent}  </IconStyle>")
        lines.append(
            f"{indent}  <LabelStyle><scale>{num(self.label_scale, 2)}</scale></LabelStyle>"
        )
        lines.append(f"{indent}  <BalloonStyle><text>$[description]</text></BalloonStyle>")
        lines.append(f"{indent}</Style>")
        return "\n".join(lines)

    def to_xml(self, indent: str = "    ") -> str:
        """Dos estilos y un StyleMap: Google Earth agranda el icono al pasar el
        raton por encima solo si se le da el par normal/highlight."""
        normal_id = f"{self.style_id}-n"
        highlight_id = f"{self.style_id}-h"
        return "\n".join([
            self._style(normal_id, self.scale, indent),
            self._style(highlight_id, self.highlight_scale, indent),
            f'{indent}<StyleMap id="{escape(self.style_id)}">',
            f"{indent}  <Pair><key>normal</key>"
            f"<styleUrl>#{escape(normal_id)}</styleUrl></Pair>",
            f"{indent}  <Pair><key>highlight</key>"
            f"<styleUrl>#{escape(highlight_id)}</styleUrl></Pair>",
            f"{indent}</StyleMap>",
        ])


@dataclass
class Folder:
    name: str
    placemarks: list[Placemark] = field(default_factory=list)
    open: bool = False
    description: str = ""

    def to_xml(self, indent: str = "    ") -> str:
        parts = [f"{indent}<Folder>", f"{indent}  <name>{escape(self.name)}</name>"]
        if self.description:
            parts.append(f"{indent}  <description>{cdata(self.description)}</description>")
        parts.append(f"{indent}  <open>{1 if self.open else 0}</open>")
        for pm in self.placemarks:
            parts.append(pm.to_xml(indent + "  "))
        parts.append(f"{indent}</Folder>")
        return "\n".join(parts)


@dataclass
class ScreenOverlay:
    """Imagen fija sobre la pantalla. Es lo correcto para una leyenda.

    Se ancla por su esquina inferior izquierda a una posicion de la pantalla, de
    modo que no se mueve al desplazar el mapa ni ensucia el mapa con puntos
    ficticios.
    """

    name: str
    href: str
    x: float = 0.02
    y: float = 0.02

    def to_xml(self, indent: str = "    ") -> str:
        return "\n".join([
            f"{indent}<ScreenOverlay>",
            f"{indent}  <name>{escape(self.name)}</name>",
            f"{indent}  <Icon><href>{escape(self.href)}</href></Icon>",
            f'{indent}  <overlayXY x="0" y="0" xunits="fraction" yunits="fraction"/>',
            f'{indent}  <screenXY x="{num(self.x, 3)}" y="{num(self.y, 3)}" '
            f'xunits="fraction" yunits="fraction"/>',
            f'{indent}  <size x="0" y="0" xunits="fraction" yunits="fraction"/>',
            f"{indent}</ScreenOverlay>",
        ])


@dataclass
class Document:
    """Un documento KML completo."""

    name: str = "HydroChem"
    description: str = ""
    styles: list[IconStyle] = field(default_factory=list)
    folders: list[Folder] = field(default_factory=list)
    overlays: list[ScreenOverlay] = field(default_factory=list)

    def to_xml(self) -> str:
        parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<kml xmlns="http://www.opengis.net/kml/2.2">',
            "  <Document>",
            f"    <name>{escape(self.name)}</name>",
        ]
        if self.description:
            parts.append(f"    <description>{cdata(self.description)}</description>")
        parts.append("    <open>1</open>")
        for style in self.styles:
            parts.append(style.to_xml())
        for overlay in self.overlays:
            parts.append(overlay.to_xml())
        for folder in self.folders:
            parts.append(folder.to_xml())
        parts.append("  </Document>")
        parts.append("</kml>")
        return "\n".join(parts) + "\n"

    @property
    def n_placemarks(self) -> int:
        return sum(len(f.placemarks) for f in self.folders)
