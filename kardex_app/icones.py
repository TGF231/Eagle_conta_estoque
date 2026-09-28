# -*- coding: utf-8 -*-
"""Ícones desenhados em runtime para a folha de estilo (PySide6).

O Qt Style Sheets não aceita data URI, e estilizar os botões de spin do
QDateEdit/QTimeEdit descarta as setas nativas. Em vez de arrastar .png pelo
projeto, desenhamos os poucos ícones necessários e gravamos numa pasta
temporária, referenciada pelo QSS. Os arquivos são nomeados pela paleta, para
que trocar de tema não reaproveite um ícone com a cor anterior.
"""
from __future__ import annotations

import os
import tempfile

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF

_cache: dict[str, dict[str, str]] = {}


def _pasta() -> str:
    caminho = os.path.join(tempfile.gettempdir(), "kardex_icones")
    os.makedirs(caminho, exist_ok=True)
    return caminho


def _gravar(nome: str, pixmap: QPixmap) -> str:
    caminho = os.path.join(_pasta(), nome)
    pixmap.save(caminho, "PNG")
    return caminho.replace("\\", "/")


def _chevron(larg: int, alt: int, cor: str, para_cima: bool) -> QPixmap:
    pixmap = QPixmap(larg, alt)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    caneta = QPen(QColor(cor))
    caneta.setWidthF(1.5)
    caneta.setCapStyle(Qt.PenCapStyle.RoundCap)
    caneta.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(caneta)
    if para_cima:
        pontos = [
            QPointF(larg * 0.24, alt * 0.62),
            QPointF(larg * 0.50, alt * 0.36),
            QPointF(larg * 0.76, alt * 0.62),
        ]
    else:
        pontos = [
            QPointF(larg * 0.24, alt * 0.38),
            QPointF(larg * 0.50, alt * 0.64),
            QPointF(larg * 0.76, alt * 0.38),
        ]
    p.drawPolyline(QPolygonF(pontos))
    p.end()
    return pixmap


def caminhos(paleta) -> dict[str, str]:
    """Gera (uma vez por paleta) e devolve os caminhos dos ícones."""
    guardado = _cache.get(paleta.nome)
    if guardado is not None:
        return guardado

    suf = paleta.nome
    art = {
        "cima": _gravar(f"cima_{suf}.png", _chevron(12, 12, paleta.ink_2, True)),
        "baixo": _gravar(f"baixo_{suf}.png", _chevron(12, 12, paleta.ink_2, False)),
    }
    _cache[paleta.nome] = art
    return art
