"""
FATROCU DB  v17 | QUANTUM ENGINE
defterbeyan.gov.tr RPA — React-aware otomasyon
"""
import sys, json, datetime
from pathlib import Path

import pyperclip
import pandas as pd
from playwright.sync_api import sync_playwright, Page

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLabel, QTextEdit, QGroupBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QSpinBox, QSplitter, QFrame
)
from PySide6.QtCore  import Qt, QThread, Signal, QWaitCondition, QMutex, QDateTime
from PySide6.QtGui   import QFont, QColor

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════
PORTAL_URL   = "https://portal.defterbeyan.gov.tr/"
SESSION_FILE = Path("session.json")
LOG_FILE     = Path("fatrocu.log")

# Kolon alias haritası — sağdaki listedeki ilk eşleşen kullanılır
COL_MAP = {
    "fatura_no" : ["alan fatura numarası","fatura numarası","belge no","sıra no","no"],
    "tarih"     : ["fatura tarihi","belge tarihi","tarih"],
    "vkn"       : ["alıcı vkn/tckn","satıcı vkn/tckn","vkn","tckn"],
    "unvan"     : ["alıcı ünvan","satıcı ünvan","unvan","ad soyad","ad"],
    "matrah"    : ["kdv matrahı","matrah","tutar","kdv hariç tutar"],
    "stopaj"    : ["stopaj","stopaj tutarı","stopaj oranı"],
}

STYLE = """
QMainWindow,QWidget{background:#080c14;color:#c9d1d9;font-family:'Consolas',monospace;font-size:11px;}
QGroupBox{color:#58a6ff;font-weight:bold;border:1px solid #21262d;border-radius:6px;
          background:#0d1117;margin-top:12px;padding:12px 10px 10px;}
QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}
QPushButton{border-radius:5px;padding:8px 14px;font-weight:bold;border:none;}
QPushButton:disabled{background:#21262d!important;color:#484f58!important;}
QTableWidget{background:#0d1117;color:#c9d1d9;border:1px solid #21262d;gridline-color:#161b22;}
QHeaderView::section{background:#161b22;color:#58a6ff;border:none;padding:4px;font-weight:bold;}
QTextEdit{background:#010409;color:#3fb950;font-family:'Consolas';font-size:10px;
          border:1px solid #21262d;border-radius:4px;}
QProgressBar{background:#161b22;border:1px solid #21262d;border-radius:4px;
             height:6px;text-align:center;color:transparent;}
QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1f6feb,stop:1 #388bfd);border-radius:4px;}
QSpinBox{background:#161b22;color:#c9d1d9;border:1px solid #30363d;
         border-radius:4px;padding:4px;}
QScrollBar:vertical{background:#0d1117;width:8px;}
QScrollBar::handle:vertical{background:#30363d;border-radius:4px;}
"""

BTN = {
    "yellow" : "background:#e3b341;color:#0d1117;",
    "blue"   : "background:#1f6feb;color:#fff;",
    "orange" : "background:#d97706;color:#fff;",
    "green"  : "background:#238636;color:#fff;",
    "red"    : "background:#da3633;color:#fff;",
    "gray"   : "background:#21262d;color:#c9d1d9;",
    "teal"   : "background:#0e7490;color:#fff;",
    "fire"   : "background:#b91c1c;color:#fff;",
}

# ══════════════════════════════════════════════════════════
#  DATA UTILS
# ══════════════════════════════════════════════════════════
def resolve(row: dict, key: str) -> str:
    """COL_MAP üzerinden alias-tolerant kolon okuma."""
    lmap = {k.lower().strip(): v for k, v in row.items()}
    for alias in COL_MAP.get(key, []):
        v = lmap.get(alias)
        if v is not None and str(v).strip() not in ("", "nan"):
            return str(v).strip()
    return ""

def fmt_date(val: str) -> str:
    try:
        s = str(val).strip().replace("-",".").replace("/",".")
        p = s.split(".")
        return f"{p[0].zfill(2)}.{p[1].zfill(2)}.{p[2]}" if len(p)==3 else s
    except:
        return str(val)

def fmt_money(val) -> str:
    if pd.isna(val) or str(val).strip() in ("","nan","0","0,00"):
        return "0,00"
    v = str(val).replace("TL","").replace("%","").replace(" ","").replace(".","").strip()
    return v if "," in v else v+",00"

def is_stopajli(row: dict) -> bool:
    v = resolve(row, "stopaj")
    return bool(v) and fmt_money(v) != "0,00"

def row_tip(row: dict) -> tuple[str,str]:
    """(label, hex_color)"""
    if is_stopajli(row):
        return "STOPAJLI 🔴", "#ff7b72"
    return "NORMAL 🟢", "#3fb950"

def ts() -> str:
    return QDateTime.currentDateTime().toString("hh:mm:ss")

# ══════════════════════════════════════════════════════════
#  REACT-AWARE WRITE  (3-tier fallback)
# ══════════════════════════════════════════════════════════
_JS_INJECT = """(args) => {
    const el = document.querySelector(args.sel);
    if (!el) return null;
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value')
          .set.call(el, args.val);
    ['input','change','blur'].forEach(t =>
        el.dispatchEvent(new Event(t,{bubbles:true,cancelable:true})));
    return el.value;
}"""

def react_write(page: Page, selector: str, value: str, log) -> bool:
    value = str(value)
    el = page.locator(selector).first

    # ── Tier 1: nativeInputValueSetter + event cascade ──
    try:
        el.scroll_into_view_if_needed()
        el.click(force=True)
        page.wait_for_timeout(100)
        result = page.evaluate(_JS_INJECT, {"sel": selector, "val": value})
        page.wait_for_timeout(200)
        if result == value:
            log(f"  ✓ inject   {selector} ← {value}")
            return True
    except Exception as e:
        log(f"  ! inject   {str(e)[:60]}")

    # ── Tier 2: clipboard paste (isTrusted events) ──
    try:
        pyperclip.copy(value)
        el.click(force=True)
        page.wait_for_timeout(80)
        page.keyboard.press("Control+A")
        page.keyboard.press("Control+V")
        page.wait_for_timeout(250)
        page.keyboard.press("Tab")
        page.wait_for_timeout(150)
        log(f"  ✓ clipboard {selector} ← {value}")
        return True
    except Exception as e:
        log(f"  ! clipboard {str(e)[:60]}")

    # ── Tier 3: mechanical keystroke ──
    try:
        el.click(force=True)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        el.type(value, delay=55)
        page.keyboard.press("Tab")
        page.wait_for_timeout(200)
        log(f"  ✓ mechanic  {selector} ← {value}")
        return True
    except Exception as e:
        log(f"  ✗ ALL FAILED {selector}: {str(e)[:60]}")
        return False

# ══════════════════════════════════════════════════════════
#  SESSION
# ══════════════════════════════════════════════════════════
def session_save(excel: str, idx: int):
    SESSION_FILE.write_text(json.dumps({"excel": excel, "idx": idx}))

def session_load() -> dict:
    try:
        return json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}
    except:
        return {}

# ══════════════════════════════════════════════════════════
#  WORKER
# ══════════════════════════════════════════════════════════
class Worker(QThread):
    log_sig      = Signal(str)
    row_sig      = Signal(dict)
    states_sig   = Signal(str, str, str, str, str)  # p_lbl,p_clr, c_lbl,c_clr, n_lbl,n_clr  — packed as 5 str
    # actually let's use a dict signal
    state_sig    = Signal(dict)   # {prev:(lbl,clr), curr:(lbl,clr), next:(lbl,clr)}
    status_sig   = Signal(str)
    pause_sig    = Signal(bool)
    progress_sig = Signal(int, int)
    done_sig     = Signal()

    def __init__(self, excel: str, start_idx: int = 0):
        super().__init__()
        self.excel      = excel
        self.idx        = start_idx
        self.running    = True
        self.trigger    = False
        self.action     = "NEXT"
        self._mutex     = QMutex()
        self._wait      = QWaitCondition()

    # ── internal log ──────────────────────────
    def _log(self, msg: str):
        full = f"[{ts()}] {msg}"
        self.log_sig.emit(full)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] {msg}\n")

    # ── entry point ───────────────────────────
    def run(self):
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                args=["--start-maximized","--disable-blink-features=AutomationControlled"]
            )
            ctx  = browser.new_context(no_viewport=True)
            page = ctx.new_page()
            page.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
            )
            page.goto(PORTAL_URL)
            self._log("Hazır ✦  Login → fatura sayfasına git → BAŞLAT'a bas")

            while self.running:
                if self.trigger:
                    self.trigger = False
                    self._flow(page)
                self.msleep(80)

            browser.close()

    # ── main flow ────────────────────────────
    def _flow(self, page: Page):
        try:
            df = pd.read_excel(self.excel, dtype=str)
            df.columns = [c.strip() for c in df.columns]
        except Exception as e:
            self._log(f"EXCEL HATA: {e}"); return

        total = len(df)

        while 0 <= self.idx < total and self.running:
            row = df.iloc[self.idx].to_dict()
            self.row_sig.emit(row)
            self.progress_sig.emit(self.idx + 1, total)
            session_save(self.excel, self.idx)

            # state panel
            def safe_tip(i):
                if i < 0 or i >= total: return ("—", "#484f58")
                return row_tip(df.iloc[i].to_dict())

            p = safe_tip(self.idx - 1)
            c = row_tip(row)
            n = safe_tip(self.idx + 1) if self.idx + 1 < total else ("BİTTİ 🏁", "#d29922")

            self.state_sig.emit({"prev": p, "curr": c, "next": n})
            self.status_sig.emit(f"{c[0]}  ·  {self.idx+1} / {total}  ({int((self.idx+1)/total*100)}%)")

            # field values
            f_no   = resolve(row, "fatura_no")
            f_tar  = fmt_date(resolve(row, "tarih"))
            vkn    = resolve(row, "vkn")
            unvan  = resolve(row, "unvan")
            matrah = fmt_money(resolve(row, "matrah") or "0")

            self._log(f"━ [{self.idx+1}/{total}] {f_no} | {f_tar} | {c[0]}")

            try:
                react_write(page, "#kayitTarihi", f_tar, self._log)
                react_write(page, "#belgeTarihi", f_tar, self._log)
                react_write(page, "#siraNo",      f_no,  self._log)

                if vkn in ("11111111111","","nan") or not vkn:
                    page.locator("#nihaiTuketici").click()
                    page.wait_for_timeout(100)
                    react_write(page, "#ad", unvan, self._log)
                else:
                    react_write(page, "#tcknVkn", vkn, self._log)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(600)

                m_el = page.locator("input.text-right.form-control").first
                if m_el.is_visible():
                    react_write(page, "input.text-right.form-control", matrah, self._log)

                self._log(f"✅ {f_no} | {f_tar} | {matrah} TL")

            except Exception as e:
                self._log(f"⚠ Satır {self.idx+1} hata: {str(e)[:120]}")

            # pause — kullanıcı kaydetsin
            self.pause_sig.emit(True)
            self._mutex.lock()
            self._wait.wait(self._mutex)
            self._mutex.unlock()
            self.pause_sig.emit(False)

            if   self.action == "NEXT": self.idx += 1
            elif self.action == "PREV": self.idx = max(0, self.idx - 1)
            elif self.action == "STOP": self.running = False

        if self.idx >= total:
            self._log("🏁 Tüm satırlar tamamlandı!")
            self.done_sig.emit()

    def control(self, cmd: str):
        self.action = cmd
        self._wait.wakeAll()

    def jump(self, idx: int):
        self.idx = idx

# ══════════════════════════════════════════════════════════
#  STATE CARD  (önceki / şu an / sonraki)
# ══════════════════════════════════════════════════════════
class StateCard(QFrame):
    def __init__(self, title: str, large: bool = False):
        super().__init__()
        self._base_border = "#388bfd" if large else "#21262d"
        self.setStyleSheet(
            f"background:#0d1117;border:{'2' if large else '1'}px solid "
            f"{self._base_border};border-radius:6px;"
        )
        vl = QVBoxLayout(self); vl.setContentsMargins(8,6,8,8); vl.setSpacing(2)
        t = QLabel(title); t.setAlignment(Qt.AlignCenter)
        t.setStyleSheet("color:#484f58;font-size:10px;font-weight:bold;border:none;")
        self.val = QLabel("—"); self.val.setAlignment(Qt.AlignCenter)
        fs = "20px" if large else "14px"
        self.val.setStyleSheet(f"font-size:{fs};font-weight:bold;color:#484f58;border:none;")
        vl.addWidget(t); vl.addWidget(self.val)

    def update(self, label: str, color: str):
        self.val.setText(label)
        self.val.setStyleSheet(
            f"font-size:{'20px' if '●' in self.parent().__class__.__name__ else '14px'};"
            f"font-weight:bold;color:{color};border:none;"
        )

class StatePanel(QWidget):
    def __init__(self):
        super().__init__()
        h = QHBoxLayout(self); h.setSpacing(6); h.setContentsMargins(0,0,0,0)
        self.prev = StateCard("◀  ÖNCEKİ")
        self.curr = StateCard("●  ŞU AN",  large=True)
        self.curr.val.setStyleSheet("font-size:22px;font-weight:bold;color:#484f58;border:none;")
        self.next = StateCard("▶  SONRAKİ")
        h.addWidget(self.prev)
        h.addWidget(self.curr, 2)
        h.addWidget(self.next)

    def update(self, data: dict):
        p, c, n = data["prev"], data["curr"], data["next"]
        self._set(self.prev, *p)
        self._set(self.curr, *c, large=True)
        self._set(self.next, *n)

    def _set(self, card: StateCard, label: str, color: str, large: bool = False):
        fs = "22px" if large else "14px"
        card.val.setText(label)
        card.val.setStyleSheet(f"font-size:{fs};font-weight:bold;color:{color};border:none;")

# ══════════════════════════════════════════════════════════
#  MAIN WINDOW
# ══════════════════════════════════════════════════════════
class FatrocuDB(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FATROCU DB  v17 | QUANTUM ENGINE")
        self.showMaximized()
        self.setStyleSheet(STYLE)
        self.worker: Worker | None = None
        self.excel  = ""
        self._pending_idx = 0
        self._build()
        self._restore_session()

    # ── build ──────────────────────────────────
    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        main = QHBoxLayout(root); main.setSpacing(8); main.setContentsMargins(8,8,8,8)

        left = QVBoxLayout(); left.setSpacing(6)

        # kurulum
        g1 = QGroupBox("⚙  KURULUM"); v1 = QVBoxLayout(g1)
        h_f = QHBoxLayout()
        self.lbl_file = QLabel("— dosya seçilmedi —")
        self.lbl_file.setStyleSheet("color:#8b949e;")
        self.btn_file   = self._btn("📂 EXCEL SEÇ",        "yellow", self._pick)
        self.btn_launch = self._btn("🚀 TARAYICIYI BAŞLAT", "blue",   self._launch)
        self.btn_launch.setEnabled(False)
        h_f.addWidget(self.lbl_file,3); h_f.addWidget(self.btn_file,1)
        v1.addLayout(h_f); v1.addWidget(self.btn_launch)
        left.addWidget(g1)

        # state panel
        self.states = StatePanel()
        left.addWidget(self.states)

        # status + progress
        self.lbl_status = QLabel("BEKLEMEDE")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet("color:#8b949e;")
        self.progress = QProgressBar(); self.progress.setFormat("")
        left.addWidget(self.lbl_status)
        left.addWidget(self.progress)

        # mevcut satır
        g2 = QGroupBox("📋  MEVCUT SATIR"); v2 = QVBoxLayout(g2)
        self.table = QTableWidget(0,2)
        self.table.setHorizontalHeaderLabels(["ALAN","DEĞER"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        v2.addWidget(self.table)
        left.addWidget(g2,1)

        # operasyon
        g3 = QGroupBox("⚡  OPERASYON"); v3 = QVBoxLayout(g3)
        self.btn_start = self._btn("▶  YAZMAYA BAŞLAT","orange",self._fire)
        self.btn_start.setEnabled(False); self.btn_start.setMinimumHeight(46)
        v3.addWidget(self.btn_start)

        h_nav = QHBoxLayout()
        self.btn_prev = self._btn("⏪ ÖNCEKİ", "gray",  lambda: self.worker.control("PREV"))
        self.btn_stop = self._btn("🛑 DURDUR",  "red",   lambda: self.worker.control("STOP"))
        self.btn_next = self._btn("✅ SIRADAKİ","green", lambda: self.worker.control("NEXT"))
        self.btn_next.setMinimumHeight(52)
        for b in (self.btn_prev,self.btn_stop,self.btn_next): b.setEnabled(False)
        h_nav.addWidget(self.btn_prev); h_nav.addWidget(self.btn_stop); h_nav.addWidget(self.btn_next,2)
        v3.addLayout(h_nav)

        h_j = QHBoxLayout()
        self.spin = QSpinBox(); self.spin.setMinimum(1); self.spin.setMaximum(99999)
        h_j.addWidget(QLabel("Satıra atla:")); h_j.addWidget(self.spin)
        h_j.addWidget(self._btn("GİT","teal",self._jump))
        v3.addLayout(h_j)
        left.addWidget(g3)

        # log
        g4 = QGroupBox("📟  LOG"); v4 = QVBoxLayout(g4)
        self.log_box = QTextEdit(); self.log_box.setReadOnly(True)
        v4.addWidget(self.log_box)
        v4.addWidget(self._btn("🗑 TEMİZLE","gray",self.log_box.clear), 0, Qt.AlignRight)

        sp = QSplitter(Qt.Horizontal)
        lw = QWidget(); lw.setLayout(left)
        sp.addWidget(lw); sp.addWidget(g4)
        sp.setStretchFactor(0,2); sp.setStretchFactor(1,1)
        main.addWidget(sp)

    def _btn(self, txt, style, slot) -> QPushButton:
        b = QPushButton(txt); b.setStyleSheet(BTN[style]); b.clicked.connect(slot)
        return b

    # ── slots ──────────────────────────────────
    def _log(self, msg): self.log_box.append(msg)

    def _update_row(self, data: dict):
        self.table.setRowCount(0)
        for k,v in data.items():
            r = self.table.rowCount(); self.table.insertRow(r)
            ki = QTableWidgetItem(str(k)); ki.setForeground(QColor("#58a6ff"))
            self.table.setItem(r,0,ki); self.table.setItem(r,1,QTableWidgetItem(str(v)))

    def _set_pause(self, p: bool):
        self.btn_next.setEnabled(p)
        self.btn_prev.setEnabled(p)
        self.btn_stop.setEnabled(p)

    def _set_progress(self, cur: int, tot: int):
        self.progress.setMaximum(tot); self.progress.setValue(cur)

    def _on_done(self):
        self.states.curr.val.setText("🏁 BİTTİ")
        self.states.curr.val.setStyleSheet("font-size:22px;font-weight:bold;color:#d29922;border:none;")

    # ── actions ────────────────────────────────
    def _pick(self):
        f,_ = QFileDialog.getOpenFileName(self,"Excel Seç","","Excel (*.xlsx *.xls)")
        if f:
            self.excel = f
            self.lbl_file.setText(Path(f).name)
            self.lbl_file.setStyleSheet("color:#3fb950;")
            self.btn_launch.setEnabled(True)
            self._log(f"[{ts()}] Excel: {Path(f).name}")

    def _launch(self):
        self.worker = Worker(self.excel, self._pending_idx)
        self.worker.log_sig     .connect(self._log)
        self.worker.row_sig     .connect(self._update_row)
        self.worker.state_sig   .connect(self.states.update)
        self.worker.status_sig  .connect(self.lbl_status.setText)
        self.worker.pause_sig   .connect(self._set_pause)
        self.worker.progress_sig.connect(self._set_progress)
        self.worker.done_sig    .connect(self._on_done)
        self.worker.start()
        self.btn_launch.setEnabled(False)
        self.btn_start.setEnabled(True)
        self._log(f"[{ts()}] Tarayıcı açıldı. Login → BAŞLAT")

    def _fire(self):
        self.worker.trigger = True
        self.btn_start.setEnabled(False)
        self.btn_start.setText("🔥 MOTOR AKTİF")
        self.btn_start.setStyleSheet(BTN["fire"])

    def _jump(self):
        if self.worker:
            self.worker.jump(self.spin.value()-1)
            self._log(f"[{ts()}] → Satır {self.spin.value()}")

    def _restore_session(self):
        s = session_load()
        if s.get("excel") and Path(s["excel"]).exists():
            self.excel = s["excel"]
            self._pending_idx = s.get("idx",0)
            self.lbl_file.setText(f"♻ {Path(s['excel']).name}  (satır {self._pending_idx+1}'den)")
            self.lbl_file.setStyleSheet("color:#d29922;")
            self.btn_launch.setEnabled(True)
            self._log(f"[{ts()}] Oturum geri yüklendi — satır {self._pending_idx+1}")

# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Consolas",10))
    FatrocuDB().show()
    sys.exit(app.exec())
