# ui.py
# sculptr.ai — Modern Dark UI (PySide6)
#fawadtest

from __future__ import annotations

# ---- hotfix: make Key_Shift_L/R exist even if renderer asks for them ----
from PySide6.QtCore import Qt
if not hasattr(Qt, "Key_Shift_L"):
    Qt.Key_Shift_L = Qt.Key_Shift
if not hasattr(Qt, "Key_Shift_R"):
    Qt.Key_Shift_R = Qt.Key_Shift
# -------------------------------------------------------------------------
import os
OBJ_PATH = os.path.join(os.path.dirname(__file__), "cube.obj")  # or rename to your file

from renderer import SimpleGLViewport
import sys
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QFrame, QLabel, QLineEdit, QPushButton, QStackedWidget,
    QGraphicsDropShadowEffect, QToolBar
)


# Theme
ACCENT  = "#7C4DFF"     # purple accent
BG      = "#1b1b1f"     # window bg (near-black)
PANEL_BG= "#222228"     # side panel bg
MID     = "#2a2a31"     # mid tone (splitter / cards)
TEXT    = "#E6E6EA"     # primary text
SUBTLE  = "#a8a8b3"     # secondary text
BORDER  = "#3a3a44"     # outlines

# Global StyleSheet (use .format with escaped braces)
STYLE = """
* {{
  color: {TEXT};
  font-family: 'Segoe UI', 'Inter', 'SF Pro Text', 'Roboto', sans-serif;
  font-size: 14px;
}}

QMainWindow {{
  background: {BG};
}}

QSplitter::handle {{
  background: {MID};
  width: 4px;
}}
QSplitter::handle:hover {{
  background: {ACCENT};
}}

#RightPanel {{
  background: {PANEL_BG};
  border-left: 2px solid {BORDER};
}}

#Card {{
  background: {MID};
  border: 1px solid {BORDER};
  border-radius: 14px;
}}

#ViewportBar {{
  background: {MID};
  border: 1px solid {BORDER};
  border-radius: 12px;
  padding: 8px 10px;
}}
#ViewportBar QLabel {{
  color: {SUBTLE};
}}

#Field {{
  background: #26262d;
  border: 1px solid {BORDER};
  border-radius: 10px;
  padding: 6px 10px;
}}
#SmallBtn {{
  background: rgba(124,77,255,0.18);
  border: 1px solid rgba(124,77,255,0.35);
  border-radius: 10px;
  padding: 6px 10px;
  color: {TEXT};
}}

#TabButton {{
  background: transparent;
  border: none;
  color: {SUBTLE};
  padding: 8px 10px;
  border-radius: 10px;
}}
#TabButton[active="true"] {{
  color: {TEXT};
  background: rgba(124,77,255,0.18);
  border: 1px solid rgba(124,77,255,0.35);
}}
#TabButton:hover {{
  color: {TEXT};
}}

#PromptWrap {{
  background: transparent;
}}
#PromptField {{
  background: {MID};
  border: 1px solid {BORDER};
  border-radius: 14px;
  padding: 12px 16px;
  color: {TEXT};
}}
#GoButton {{
  background: {ACCENT};
  border: none;
  border-radius: 12px;
  padding: 10px 16px;
  color: white;
  font-weight: 600;
}}
#GoButton:hover {{ filter: brightness(1.05); }}
#GoButton:pressed {{ filter: brightness(0.92); }}

.Separator {{
  background: {BORDER};
  max-height: 1px;
  min-height: 1px;
}}

QMenuBar {{
  background: {MID};
  color: {TEXT};
}}
QMenuBar::item {{
  padding: 6px 10px;
  background: transparent;
}}
QMenuBar::item:selected {{
  background: rgba(124,77,255,0.18);
  border-radius: 6px;
}}

QMenu {{
  background: {PANEL_BG};
  border: 1px solid {BORDER};
  color: {TEXT};
}}
QMenu::item {{ padding: 6px 12px; }}
QMenu::item:selected {{ background: rgba(124,77,255,0.18); }}
QMenu::separator {{
  height: 1px;
  background: {BORDER};
  margin: 6px 4px;
}}
""".format(TEXT=TEXT, BG=BG, MID=MID, ACCENT=ACCENT, PANEL_BG=PANEL_BG, BORDER=BORDER, SUBTLE=SUBTLE)

# Viewport Stuff (mostly temp until proper renderer made)
class Viewport(QWidget):
    """Placeholder viewport. Replace with your GL/Qt3D/three.js view later."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumSize(640, 400)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(QColor(0,0,0,120))
        self.setGraphicsEffect(shadow)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(24,24,-24,-24)

        p.setPen(QPen(QColor(BORDER), 1))
        p.drawRoundedRect(rect, 12, 12)

        # Wireframe cube
        size = min(rect.width(), rect.height()) * 0.35
        cx, cy = rect.center().x(), rect.center().y()
        offset, depth = size * 0.5, size * 0.35
        front = [(cx - offset, cy - offset), (cx + offset, cy - offset),
                 (cx + offset, cy + offset), (cx - offset, cy + offset)]
        back = [(x + depth, y - depth) for (x, y) in front]
        pen = QPen(QColor(210,210,220,200)); pen.setWidth(2)
        p.setPen(pen)

        def poly(pts):
            for i in range(len(pts)):
                x1,y1=pts[i]; x2,y2=pts[(i+1)%len(pts)]
                p.drawLine(int(x1),int(y1),int(x2),int(y2))
        poly(front); poly(back)
        for i in range(4):
            p.drawLine(int(front[i][0]),int(front[i][1]),int(back[i][0]),int(back[i][1]))

        # Watermark
        p.setPen(QColor(SUBTLE))
        f=QFont(); f.setPointSize(10); p.setFont(f)
        p.drawText(rect.adjusted(8,8,-8,-8), Qt.AlignBottom|Qt.AlignLeft, "Viewport • drop your renderer here later")

# Viewport Top Bar (fields above viewport)
class ViewportBar(QWidget):
    """Compact control strip that sits above the viewport (no logic yet)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ViewportBar")
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)

        name  = QLineEdit(); name.setObjectName("Field"); name.setPlaceholderText("Model name…")
        view  = QLineEdit(); view.setObjectName("Field"); view.setPlaceholderText("View: Perspective")
        shade = QLineEdit(); shade.setObjectName("Field"); shade.setPlaceholderText("Shading: Solid")
        reset = QPushButton("Reset View"); reset.setObjectName("SmallBtn")

        h.addWidget(QLabel("Scene:"))
        h.addWidget(name, 1)
        h.addSpacing(6)
        h.addWidget(view)
        h.addWidget(shade)
        h.addStretch(1)
        h.addWidget(reset)

#Generate and Edit Tab Right Panel
class RightPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("RightPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        #Top tabs
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(10)

        self.btn_ai = QPushButton("AI Generate"); self.btn_ai.setObjectName("TabButton")
        self.btn_edit = QPushButton("Edit Tools"); self.btn_edit.setObjectName("TabButton")

        self.btn_ai.setProperty("active", True)
        self.btn_edit.setProperty("active", False)
        self.btn_ai.clicked.connect(lambda: self._activate_tab(0))
        self.btn_edit.clicked.connect(lambda: self._activate_tab(1))

        #Stretches on both sides keep the buttons centered as the panel resizes
        tabs_row.addStretch(1)
        tabs_row.addWidget(self.btn_ai)
        tabs_row.addSpacing(6)   # small gap between the two buttons
        tabs_row.addWidget(self.btn_edit)
        tabs_row.addStretch(1)

        root.addLayout(tabs_row)


        # Separator
        sep = QFrame(); sep.setObjectName("Separator"); sep.setFixedHeight(1)
        root.addWidget(sep)

        # Stacked content
        self.stack = QStackedWidget()
        self.stack.addWidget(self._placeholder_tab("Prompt → Mesh"))
        self.stack.addWidget(self._placeholder_tab("Quick Edit Tools"))
        root.addWidget(self.stack, 1)

        # Prompt bar
        root.addWidget(self._build_prompt_bar())

    def _activate_tab(self, idx: int):
        self.stack.setCurrentIndex(idx)
        for btn,active in [(self.btn_ai,idx==0),(self.btn_edit,idx==1)]:
            btn.setProperty("active", active)
            btn.style().unpolish(btn); btn.style().polish(btn)

    def _placeholder_tab(self, title: str) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(12)
        t = QLabel(f"{title} (placeholder)"); t.setStyleSheet(f"color:{TEXT}; font-weight:600;")
        t2= QLabel("Wire functionality later."); t2.setStyleSheet(f"color:{SUBTLE};")
        card = QFrame(); card.setObjectName("Card")
        lay = QVBoxLayout(card); lay.setContentsMargins(14,14,14,14); lay.addWidget(t); lay.addWidget(t2)
        v.addWidget(card); v.addStretch(1)
        return w

    def _build_prompt_bar(self) -> QWidget:
        wrap = QWidget(); wrap.setObjectName("PromptWrap")
        h = QHBoxLayout(wrap); h.setContentsMargins(0,4,0,0); h.setSpacing(10)
        self.prompt = QLineEdit(); self.prompt.setObjectName("PromptField")
        self.prompt.setPlaceholderText("Type what you want to generate…")
        self.go = QPushButton("→"); self.go.setObjectName("GoButton"); self.go.setFixedWidth(56)
        h.addWidget(self.prompt, 1); h.addWidget(self.go, 0)
        return wrap

# Main Window
class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("sculptr.ai")
        self.resize(1200, 720)

        # Main layout: viewport (left) | right panel
        splitter = QSplitter(Qt.Horizontal)

        viewport_wrap = QVBoxLayout()
        viewport_wrap.setContentsMargins(16, 16, 16, 16)
        viewport_container = QWidget()
        viewport_container.setLayout(viewport_wrap)

        self.viewport_top_bar = ViewportBar()
        self.viewport_widget = SimpleGLViewport(bg_hex=BG, line_hex=TEXT, obj_path=OBJ_PATH)
        viewport_wrap.addWidget(self.viewport_top_bar, 0)
        viewport_wrap.addWidget(self.viewport_widget, 1)

        # hook Reset View button to renderer
        reset_btn = self.viewport_top_bar.findChild(QPushButton, "SmallBtn")
        if reset_btn:
            reset_btn.clicked.connect(self.viewport_widget.reset_view)

        right = RightPanel(); right.setMinimumWidth(360)
        self._right_panel = right  

        splitter.addWidget(viewport_container)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(splitter)
        self.setCentralWidget(central)

        # Apply stylesheet
        self.setStyleSheet(STYLE)

        # Menubar + actions
        self._build_menubar()
        self._connect_menu_actions()

    def _build_menubar(self):
        mb = self.menuBar()

        # File
        m_file = mb.addMenu("&File")
        act_new     = m_file.addAction("New")
        act_open    = m_file.addAction("Open…")
        act_save    = m_file.addAction("Save")
        act_saveas  = m_file.addAction("Save As…")
        m_file.addSeparator()
        act_export  = m_file.addAction("Export GLB/OBJ…")
        m_file.addSeparator()
        act_exit    = m_file.addAction("Exit")
        act_new.setShortcut("Ctrl+N")
        act_open.setShortcut("Ctrl+O")
        act_save.setShortcut("Ctrl+S")
        act_saveas.setShortcut("Ctrl+Shift+S")
        act_exit.setShortcut("Alt+F4")

        # Edit
        m_edit = mb.addMenu("&Edit")
        act_undo   = m_edit.addAction("Undo");  act_undo.setShortcut("Ctrl+Z")
        act_redo   = m_edit.addAction("Redo");  act_redo.setShortcut("Ctrl+Y")
        m_edit.addSeparator()
        act_cut    = m_edit.addAction("Cut");   act_cut.setShortcut("Ctrl+X")
        act_copy   = m_edit.addAction("Copy");  act_copy.setShortcut("Ctrl+C")
        act_paste  = m_edit.addAction("Paste"); act_paste.setShortcut("Ctrl+V")
        m_edit.addSeparator()
        act_prefs  = m_edit.addAction("Preferences…")

        # Properties
        m_props = mb.addMenu("&Properties")
        act_scene     = m_props.addAction("Scene Settings…")
        act_material  = m_props.addAction("Material Settings…")
        act_viewport  = m_props.addAction("Viewport Settings…")

        # Window
        m_window = mb.addMenu("&Window")
        act_toggle_right   = m_window.addAction("Toggle Right Panel")
        act_toggle_toolbar = m_window.addAction("Toggle Toolbar")
        m_window.addSeparator()
        act_reset_layout   = m_window.addAction("Reset Layout")

        # Help
        m_help = mb.addMenu("&Help")
        act_docs   = m_help.addAction("Documentation")
        act_about  = m_help.addAction("About Sculptr.ai")

        # Stash actions
        self._menu_actions = dict(
            new=act_new, open=act_open, save=act_save, saveas=act_saveas, export=act_export, exit=act_exit,
            undo=act_undo, redo=act_redo, cut=act_cut, copy=act_copy, paste=act_paste, prefs=act_prefs,
            scene=act_scene, material=act_material, viewport=act_viewport,
            toggle_right=act_toggle_right, toggle_toolbar=act_toggle_toolbar, reset_layout=act_reset_layout,
            docs=act_docs, about=act_about
        )

    def _connect_menu_actions(self):
        a = self._menu_actions
        a["exit"].triggered.connect(self.close)

        # Toggle Right Panel
        if hasattr(self, "_right_panel"):
            a["toggle_right"].triggered.connect(
                lambda: self._right_panel.setVisible(not self._right_panel.isVisible())
            )

        # Toggle Toolbar
        if hasattr(self, "toolBar"):
            a["toggle_toolbar"].triggered.connect(
                lambda: self.toolBar.setVisible(not self.toolBar.isVisible())
            )

        # About dialog
        def _show_about():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "About Sculptr.ai",
                "Sculptr.ai — AI 3D Modeler UI (PySide6)\nMVP UI scaffold"
            )
        a["about"].triggered.connect(_show_about)

# Run
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Main()
    win.show()
    sys.exit(app.exec())
