# -*- coding: utf-8 -*-
"""Paleta e folha de estilo (QSS), inspiradas no SPED Tables / Backup Maximus.

Mesmo acento **cobre** da família de ferramentas. As cores semânticas
(ok/aviso/erro) são separadas do acento de propósito, para que "atenção" nunca
se confunda com "isto é clicável". O tema escuro não é uma inversão automática:
os neutros mantêm o viés azulado e o acento sobe de saturação para continuar
legível sobre fundo escuro.
"""
from __future__ import annotations

from dataclasses import dataclass

FONT_UI = '"Segoe UI", "Noto Sans", sans-serif'
FONT_MONO = '"Cascadia Mono", "Consolas", monospace'


@dataclass(frozen=True)
class Paleta:
    nome: str
    bg: str
    surface: str
    surface_2: str
    sunken: str
    ink: str
    ink_2: str
    ink_3: str
    border: str
    border_2: str
    accent: str
    accent_hover: str
    accent_soft: str
    on_accent: str
    ok: str
    warn: str
    bad: str
    info: str


CLARO = Paleta(
    nome="claro",
    bg="#F4F6F8",
    surface="#FFFFFF",
    surface_2="#E9EDF1",
    sunken="#FBFCFD",
    ink="#16202A",
    ink_2="#4A5A6A",
    ink_3="#74848F",
    border="#D2DAE2",
    border_2="#BAC5D0",
    accent="#C2410C",
    accent_hover="#9A3412",
    accent_soft="#FBEBE2",
    on_accent="#FFFFFF",
    ok="#15803D",
    warn="#A16207",
    bad="#B4232B",
    info="#1565C0",
)

ESCURO = Paleta(
    nome="escuro",
    bg="#0F1620",
    surface="#18212C",
    surface_2="#212C39",
    sunken="#131C25",
    ink="#E3E9EF",
    ink_2="#94A4B5",
    ink_3="#6E7F91",
    border="#2B3745",
    border_2="#3A4857",
    accent="#F97316",
    accent_hover="#FB923C",
    accent_soft="#2E1B10",
    on_accent="#1A1005",
    ok="#4ADE80",
    warn="#FBBF24",
    bad="#F87171",
    info="#60A5FA",
)

_ativa = CLARO


def atual() -> Paleta:
    return _ativa


def definir_escuro(escuro: bool) -> Paleta:
    """Troca a paleta ativa e devolve a nova."""
    global _ativa
    _ativa = ESCURO if escuro else CLARO
    return _ativa


def e_escuro() -> bool:
    return _ativa is ESCURO


def folha_estilo() -> str:
    from kardex_app import icones

    p = _ativa
    art = icones.caminhos(p)
    seta_cima = art["cima"]
    seta_baixo = art["baixo"]
    return f"""
QWidget {{
    background: {p.bg};
    color: {p.ink};
    font-family: {FONT_UI};
    font-size: 10pt;
}}
QDialog, QMainWindow {{ background: {p.bg}; }}

QLabel {{ background: transparent; color: {p.ink}; }}
QLabel[role="titulo"] {{ font-size: 16pt; font-weight: 700; color: {p.ink}; }}
QLabel[role="secao"] {{ font-weight: 700; letter-spacing: 1px; color: {p.ink_2}; }}
QLabel[role="dica"] {{ color: {p.ink_3}; }}
QLabel[role="ok"] {{ color: {p.ok}; font-weight: bold; }}
QLabel[role="aviso"] {{ color: {p.warn}; }}
QLabel[role="erro"] {{ color: {p.bad}; font-weight: bold; }}

QGroupBox {{
    background: transparent;
    border: 1px solid {p.border};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {p.ink_2};
    font-weight: 600;
}}

QPushButton {{
    background: {p.surface};
    color: {p.ink_2};
    border: 1px solid {p.border_2};
    border-radius: 4px;
    padding: 6px 14px;
    min-height: 16px;
}}
QPushButton:hover {{ background: {p.surface_2}; color: {p.ink}; }}
QPushButton:pressed {{ background: {p.border}; }}
QPushButton:disabled {{
    background: {p.bg}; color: {p.ink_3}; border-color: {p.border};
}}
QPushButton[role="accent"] {{
    background: {p.accent};
    color: {p.on_accent};
    border: 1px solid {p.accent};
    font-weight: 600;
    padding: 7px 18px;
}}
QPushButton[role="accent"]:hover {{
    background: {p.accent_hover}; border-color: {p.accent_hover};
}}
QPushButton[role="accent"]:disabled {{
    background: {p.border_2}; border-color: {p.border_2}; color: {p.bg};
}}

QLineEdit, QDateEdit, QTimeEdit, QSpinBox, QPlainTextEdit {{
    background: {p.sunken};
    color: {p.ink};
    border: 1px solid {p.border_2};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {p.accent_soft};
    selection-color: {p.ink};
}}
QLineEdit:focus, QDateEdit:focus, QTimeEdit:focus, QSpinBox:focus,
QPlainTextEdit:focus {{
    border-color: {p.accent};
}}
QLineEdit:read-only {{ background: {p.surface_2}; }}
QPlainTextEdit {{ font-family: {FONT_MONO}; }}

QDateEdit::drop-down, QTimeEdit::drop-down {{
    border: none; width: 18px;
}}

QDateEdit::up-button, QTimeEdit::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid {p.border_2};
    border-top-right-radius: 4px;
    background: {p.surface_2};
}}
QDateEdit::down-button, QTimeEdit::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid {p.border_2};
    border-bottom-right-radius: 4px;
    background: {p.surface_2};
}}
QDateEdit::up-button:hover, QTimeEdit::up-button:hover,
QDateEdit::down-button:hover, QTimeEdit::down-button:hover {{
    background: {p.border};
}}
QDateEdit::up-button:pressed, QTimeEdit::up-button:pressed,
QDateEdit::down-button:pressed, QTimeEdit::down-button:pressed {{
    background: {p.accent_soft};
}}
QDateEdit::up-arrow, QTimeEdit::up-arrow {{
    image: url("{seta_cima}"); width: 12px; height: 12px;
}}
QDateEdit::down-arrow, QTimeEdit::down-arrow {{
    image: url("{seta_baixo}"); width: 12px; height: 12px;
}}

QCalendarWidget QWidget {{ alternate-background-color: {p.surface_2}; }}
QCalendarWidget QAbstractItemView:enabled {{
    background: {p.surface};
    color: {p.ink};
    selection-background-color: {p.accent};
    selection-color: {p.on_accent};
}}
QCalendarWidget QToolButton {{
    background: transparent; color: {p.ink};
}}
QCalendarWidget QToolButton:hover {{ background: {p.surface_2}; }}
QCalendarWidget QMenu {{ background: {p.surface}; color: {p.ink}; }}
QCalendarWidget QSpinBox {{
    background: {p.sunken}; color: {p.ink};
    border: 1px solid {p.border_2};
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{ background: {p.surface_2}; }}

QComboBox {{
    background: {p.surface};
    color: {p.ink};
    border: 1px solid {p.border_2};
    border-radius: 4px;
    padding: 5px 8px;
}}
QComboBox:focus {{ border-color: {p.accent}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox::down-arrow {{ image: url("{seta_baixo}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {p.surface};
    color: {p.ink};
    border: 1px solid {p.border_2};
    selection-background-color: {p.accent_soft};
    selection-color: {p.ink};
    outline: none;
    padding: 2px;
}}

QTableWidget, QTableView {{
    background: {p.surface};
    alternate-background-color: {p.surface_2};
    color: {p.ink};
    gridline-color: {p.border};
    border: 1px solid {p.border_2};
    border-radius: 4px;
    outline: none;
}}
QTableWidget::item, QTableView::item {{ padding: 2px 6px; }}
QHeaderView::section {{
    background: {p.surface_2};
    color: {p.ink_2};
    border: none;
    border-right: 1px solid {p.border};
    border-bottom: 1px solid {p.border_2};
    padding: 5px 6px;
    font-weight: 600;
}}
QHeaderView::section:vertical {{
    color: {p.ink_3}; font-weight: 400;
}}
QTableCornerButton::section {{
    background: {p.surface_2}; border: none;
    border-bottom: 1px solid {p.border_2};
}}

QDialogButtonBox {{ background: transparent; }}

QScrollBar:vertical {{ background: {p.bg}; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {p.border_2}; border-radius: 5px; min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {p.ink_3}; }}
QScrollBar:horizontal {{ background: {p.bg}; height: 11px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {p.border_2}; border-radius: 5px; min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{ background: {p.ink_3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QToolTip {{
    background: {p.ink}; color: {p.surface}; border: none; padding: 5px 7px;
}}
QMessageBox {{ background: {p.bg}; }}
QMessageBox QLabel {{ color: {p.ink}; }}

QFrame[role="divisor"] {{ background: {p.border}; max-height: 1px; border: none; }}
"""
