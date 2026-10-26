"""
Contextual PDF Reader — desktop app (PySide6 + PyMuPDF, no JavaScript)

This is the frontend UI skeleton from the wireframe: sidebar search,
page-number + highlight toggle in the top bar, page viewer in the middle.

Search here ranks page chunks by term frequency — a stand-in for a real
embeddings-based context search you can swap in later (see run_search()).
Everything else — page jump, highlight rendering, result list, PDF
rendering — is the real interaction, wired end to end.

Install:
    pip install PySide6 PyMuPDF

Run:
    python main.py
"""

import sys
from dataclasses import dataclass
from typing import Optional

import fitz  # PyMuPDF
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QFileDialog, QScrollArea, QCheckBox, QFrame
)

ZOOM = 1.6              # render scale for page -> pixmap
CHUNK_SIZE = 220        # characters per search chunk
MAX_RESULTS = 8


@dataclass
class Chunk:
    page: int           # 0-indexed
    text: str
    score: int = 0


class PdfReader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Contextual PDF Reader")
        self.resize(1180, 780)

        self.doc: Optional[fitz.Document] = None
        self.chunks: list[Chunk] = []
        self.current_page = 0
        self.active_terms: list[str] = []

        self._build_ui()
        self._apply_style()

    # ---------------------------------------------------------- UI build
    def _build_ui(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_viewer(), 1)
        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(300)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Brand
        brand = QWidget()
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(18, 20, 18, 14)
        title = QLabel("Marginale")
        title.setObjectName("brandTitle")
        sub = QLabel("Search what a page means, not just what it says")
        sub.setObjectName("brandSub")
        sub.setWordWrap(True)
        brand_layout.addWidget(title)
        brand_layout.addWidget(sub)
        layout.addWidget(brand)
        layout.addWidget(self._hline())

        # Search box
        search_wrap = QWidget()
        search_layout = QVBoxLayout(search_wrap)
        search_layout.setContentsMargins(18, 14, 18, 14)
        row = QHBoxLayout()
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Ask for a topic, table, or figure…")
        self.query_input.setEnabled(False)
        self.query_input.returnPressed.connect(self.run_search)
        self.search_btn = QPushButton("Search")
        self.search_btn.setEnabled(False)
        self.search_btn.clicked.connect(self.run_search)
        row.addWidget(self.query_input)
        row.addWidget(self.search_btn)
        search_layout.addLayout(row)
        hint = QLabel("Ranks pages by term relevance across the whole "
                       "document and jumps you straight to the match.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        search_layout.addWidget(hint)
        layout.addWidget(search_wrap)
        layout.addWidget(self._hline())

        # Results
        self.results_head = QLabel("Results")
        self.results_head.setObjectName("resultsHead")
        self.results_head.setContentsMargins(18, 10, 18, 6)
        layout.addWidget(self.results_head)

        self.results_list = QListWidget()
        self.results_list.setObjectName("resultsList")
        self.results_list.itemClicked.connect(self._on_result_clicked)
        layout.addWidget(self.results_list, 1)
        layout.addWidget(self._hline())

        open_btn = QPushButton("Open a PDF")
        open_btn.setObjectName("openBtn")
        open_btn.clicked.connect(self.open_pdf)
        open_wrap = QWidget()
        open_layout = QVBoxLayout(open_wrap)
        open_layout.setContentsMargins(18, 14, 18, 16)
        open_layout.addWidget(open_btn)
        layout.addWidget(open_wrap)

        return sidebar

    def _build_viewer(self) -> QWidget:
        main = QWidget()
        layout = QVBoxLayout(main)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(52)
        top_layout = QHBoxLayout(topbar)
        top_layout.setContentsMargins(18, 0, 18, 0)

        self.doc_title = QLabel("No document open")
        self.doc_title.setObjectName("docTitle")
        top_layout.addWidget(self.doc_title)
        top_layout.addStretch(1)

        self.prev_btn = QPushButton("◀")
        self.prev_btn.setFixedWidth(28)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.prev_page)
        self.page_readout = QLabel("— / —")
        self.page_readout.setObjectName("pageReadout")
        self.page_readout.setFixedWidth(70)
        self.page_readout.setAlignment(Qt.AlignCenter)
        self.next_btn = QPushButton("▶")
        self.next_btn.setFixedWidth(28)
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.next_page)
        top_layout.addWidget(self.prev_btn)
        top_layout.addWidget(self.page_readout)
        top_layout.addWidget(self.next_btn)
        top_layout.addStretch(1)

        self.highlight_check = QCheckBox("Highlight matches")
        self.highlight_check.setChecked(True)
        self.highlight_check.stateChanged.connect(lambda _: self.render_page())
        top_layout.addWidget(self.highlight_check)

        layout.addWidget(topbar)

        # Page viewer
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("viewport")
        self.page_label = QLabel("Open a PDF from the sidebar to begin.")
        self.page_label.setObjectName("pageLabel")
        self.page_label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.page_label)
        layout.addWidget(self.scroll, 1)

        # Status bar
        self.status = QLabel("Open a PDF to begin indexing")
        self.status.setObjectName("status")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setFixedHeight(26)
        layout.addWidget(self.status)

        return main

    def _hline(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("hline")
        return line

    # ------------------------------------------------------------- style
    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow { background: #2a271e; }
            #sidebar { background: #18160f; }
            #brandTitle { color: #faf7ef; font-size: 17px; font-style: italic; }
            #brandSub { color: #8b8570; font-size: 11px; margin-top: 3px; }
            #hint { color: #75705d; font-size: 10.5px; margin-top: 8px; }
            #resultsHead { color: #79735e; font-size: 10.5px; }
            #hline { background: #3a362a; max-height: 1px; border: none; }
            QLineEdit {
                background: #232016; border: 1px solid #45402f; color: #faf7ef;
                padding: 7px 9px; border-radius: 3px; font-size: 13px;
            }
            QLineEdit:focus { border-color: #e9c98f; }
            QPushButton {
                background: #a8632a; color: #1c130a; border: none;
                padding: 7px 12px; border-radius: 3px; font-weight: 600; font-size: 12.5px;
            }
            QPushButton:hover:!disabled { background: #b96f31; }
            QPushButton:disabled { background: #4a4232; color: #7a7460; }
            #openBtn { padding: 10px; font-size: 13px; }
            QListWidget#resultsList {
                background: #18160f; border: none; color: #c9c2ac; font-size: 12px;
            }
            QListWidget#resultsList::item { padding: 8px 14px; border-left: 2px solid transparent; }
            QListWidget#resultsList::item:selected { background: #262112; border-left: 2px solid #e9c98f; color: #faf7ef; }
            #topbar { background: #18160f; border-bottom: 1px solid #3a362a; }
            #docTitle { color: #c9c2ac; font-size: 12.5px; }
            #pageReadout { color: #c9c2ac; font-family: monospace; font-size: 12px; }
            QCheckBox { color: #c9c2ac; font-size: 12px; }
            #viewport { background: #2a271e; border: none; }
            #pageLabel { color: #736e5b; font-size: 13px; padding: 60px; }
            #status { background: #18160f; color: #736e5b; font-size: 11px; border-top: 1px solid #3a362a; }
        """)

    # --------------------------------------------------------- PDF logic
    def open_pdf(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF files (*.pdf)")
        if not path:
            return
        self.doc = fitz.open(path)
        self.current_page = 0
        self.active_terms = []
        print(self.current_page)
        print(self.active_terms)
        self.results_list.clear()
        self.doc_title.setText(path.split("/")[-1])
        self.query_input.setEnabled(True)
        self.search_btn.setEnabled(True)
        self.prev_btn.setEnabled(True)
        self.next_btn.setEnabled(True)
        self._index_document()
        self.render_page()

    def _index_document(self):
        """Build the search index. Replace this with a call to your real
        ingestion pipeline (embeddings, table-aware extraction, etc.)."""
        self.chunks = []
        for i, page in enumerate(self.doc):
            text = " ".join(page.get_text("text").split())
            for start in range(0, len(text), CHUNK_SIZE):
                piece = text[start:start + CHUNK_SIZE].strip()
                if piece:
                    self.chunks.append(Chunk(page=i, text=piece))
        self.status.setText(f"Indexed {self.doc.page_count} pages. Ready to search.")

    def run_search(self):
        """Placeholder relevance search — swap this scoring step for a real
        embeddings-similarity lookup against your backend when it's ready."""
        query = self.query_input.text().strip()
        if not query or not self.chunks:
            return
        terms = [t for t in query.lower().split() if len(t) > 1]
        self.active_terms = terms

        scored = []
        for chunk in self.chunks:
            lower = chunk.text.lower()
            score = sum(lower.count(t) for t in terms)
            if score > 0:
                scored.append(Chunk(page=chunk.page, text=chunk.text, score=score))
        scored.sort(key=lambda c: c.score, reverse=True)
        top = scored[:MAX_RESULTS]

        self.results_list.clear()
        self.results_head.setText(
            f"{len(top)} match{'es' if len(top) != 1 else ''}" if top else "No matches"
        )

        if not top:
            item = QListWidgetItem(
                "Nothing matched. Try different words — this scores by term "
                "relevance, not true semantic meaning."
            )
            item.setFlags(Qt.NoItemFlags)
            self.results_list.addItem(item)
            return

        for chunk in top:
            snippet = chunk.text[:150] + ("…" if len(chunk.text) > 150 else "")
            item = QListWidgetItem(f"Page {chunk.page + 1}  ·  relevance {chunk.score}\n{snippet}")
            item.setData(Qt.UserRole, chunk.page)
            self.results_list.addItem(item)

        self.results_list.setCurrentRow(0)
        self.current_page = top[0].page
        self.render_page()

    def _on_result_clicked(self, item: QListWidgetItem):
        page = item.data(Qt.UserRole)
        if page is None:
            return
        self.current_page = page
        self.render_page()

    def prev_page(self):
        if self.doc and self.current_page > 0:
            self.current_page -= 1
            self.render_page()

    def next_page(self):
        if self.doc and self.current_page < self.doc.page_count - 1:
            self.current_page += 1
            self.render_page()

    def render_page(self):
        if not self.doc:
            return
        page = self.doc[self.current_page]
        matrix = fitz.Matrix(ZOOM, ZOOM)
        pix = page.get_pixmap(matrix=matrix)

        image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(image)

        if self.highlight_check.isChecked() and self.active_terms:
            pixmap = pixmap.copy()
            painter = QPainter(pixmap)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(233, 201, 143, 130))  # translucent highlight
            for term in self.active_terms:
                for rect in page.search_for(term):
                    r = rect * matrix
                    painter.drawRect(QRectF(r.x0, r.y0, r.x1 - r.x0, r.y1 - r.y0))
            painter.end()

        self.page_label.setPixmap(pixmap)
        self.page_label.resize(pixmap.size())
        self.page_readout.setText(f"{self.current_page + 1} / {self.doc.page_count}")
        self.prev_btn.setEnabled(self.current_page > 0)
        self.next_btn.setEnabled(self.current_page < self.doc.page_count - 1)
        self.status.setText(f"Viewing page {self.current_page + 1} of {self.doc.page_count}")


def main():
    app = QApplication(sys.argv)
    window = PdfReader()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
