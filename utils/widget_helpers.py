# utils/widget_helpers.py

from contextlib import contextmanager
from typing import Any, Iterator, Optional

from PySide6.QtCore import QEvent, QObject, QPoint, QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QWidget


@contextmanager
def blokir_signal_sementara(
    widget: Any,
) -> Iterator[None]:
    """
    Memblokir signal widget untuk sementara.

    Status signal sebelumnya akan dikembalikan setelah proses
    selesai, termasuk apabila terjadi exception.
    """
    status_sebelumnya = widget.blockSignals(True)

    try:
        yield
    finally:
        widget.blockSignals(status_sebelumnya)


@contextmanager
def blokir_signal_opsional(
    widget: Any,
    aktif: bool = True,
) -> Iterator[None]:
    """Memblokir signal hanya ketika ``aktif`` bernilai True."""
    if aktif:
        with blokir_signal_sementara(widget):
            yield
    else:
        yield

# Alias kompatibilitas untuk modul lama yang masih memakai nama internal.
_blokir_signal_sementara = blokir_signal_sementara
_blokir_signal_opsional = blokir_signal_opsional


def _refresh_style_widget(
    widget: QWidget,
) -> None:
    """
    Meminta Qt mengevaluasi ulang dynamic property pada stylesheet.

    Pengaman re-entrancy mencegah pemanggilan berulang ketika proses
    ``polish()`` sendiri memicu event atau helper placeholder lain.
    """
    if widget is None:
        return

    if bool(getattr(widget, "_refresh_style_aktif", False)):
        return

    widget._refresh_style_aktif = True

    try:
        style = widget.style()

        if style is not None:
            style.unpolish(widget)
            style.polish(widget)

        widget.update()
    except RuntimeError:
        # Wrapper Python dapat tertinggal ketika objek C++ sudah dihapus.
        return
    finally:
        try:
            widget._refresh_style_aktif = False
        except RuntimeError:
            pass


def paksa_kapital_lineedit(
    edit_widget: QLineEdit,
) -> None:
    """
    Slot atau fungsi global untuk memaksa isi QLineEdit
    menjadi huruf kapital melalui signal textChanged.
    """
    teks_lama = edit_widget.text()
    teks_baru = teks_lama.upper()

    if teks_baru == teks_lama:
        return

    pos_lama = edit_widget.cursorPosition()

    with blokir_signal_sementara(edit_widget):
        edit_widget.setText(teks_baru)

        edit_widget.setCursorPosition(
            min(
                pos_lama,
                len(teks_baru),
            )
        )


class _FilterPopupComboBoxBawah(QObject):
    """
    Event filter internal untuk menjaga popup QComboBox tetap muncul
    tepat di bawah kotak ComboBox.

    Objek ini disimpan sebagai atribut pada QComboBox supaya tidak
    dihapus oleh garbage collector selama widget masih digunakan.
    """

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Show:
            # Tunggu sampai Qt selesai menghitung ukuran popup bawaan.
            QTimer.singleShot(0, self._posisikan_popup)

        return super().eventFilter(watched, event)

    def _posisikan_popup(self) -> None:
        combo = self._combo

        if combo is None or not combo.isVisible():
            return

        view = combo.view()
        if view is None:
            return

        popup = view.window()
        if popup is None or not popup.isVisible():
            return

        posisi_bawah = combo.mapToGlobal(QPoint(0, combo.height()))

        screen = QApplication.screenAt(
            combo.mapToGlobal(combo.rect().center())
        )
        if screen is None:
            screen = QApplication.primaryScreen()
        if screen is None:
            popup.move(posisi_bawah)
            return

        area = screen.availableGeometry()

        # Lebar minimal mengikuti ComboBox, tetapi tetap memakai ukuran
        # popup bawaan jika daftar item membutuhkan ruang lebih besar.
        lebar_popup = max(popup.width(), combo.width())
        lebar_popup = min(lebar_popup, area.width())

        x = posisi_bawah.x()
        x = max(area.left(), min(x, area.right() - lebar_popup + 1))

        # Popup tetap dibuka ke bawah. Bila ruang terbatas, tingginya
        # diperkecil sehingga QListView menampilkan scrollbar.
        ruang_bawah = max(1, area.bottom() - posisi_bawah.y() + 1)
        tinggi_popup = min(popup.height(), ruang_bawah)

        popup.setGeometry(
            x,
            posisi_bawah.y(),
            lebar_popup,
            tinggi_popup,
        )


def pasang_popup_combobox_bawah(combo: QComboBox) -> bool:
    """
    Memasang perilaku popup-bawah pada satu QComboBox.

    Fungsi bersifat idempoten: aman dipanggil berulang kali pada widget
    yang sama. Mengembalikan True jika widget valid dan helper terpasang.
    """
    if not isinstance(combo, QComboBox):
        return False

    filter_lama: Optional[_FilterPopupComboBoxBawah] = getattr(
        combo,
        "_filter_popup_combobox_bawah",
        None,
    )
    if filter_lama is not None:
        return True

    view = combo.view()
    if view is None:
        return False

    popup = view.window()
    if popup is None:
        return False

    filter_popup = _FilterPopupComboBoxBawah(combo)
    popup.installEventFilter(filter_popup)

    # Wajib disimpan agar objek filter tidak terhapus oleh Python.
    combo._filter_popup_combobox_bawah = filter_popup
    return True


def terapkan_popup_combobox_bawah(container_widget: QWidget) -> int:
    """
    Menerapkan helper popup-bawah ke seluruh QComboBox dalam container.

    Contoh penggunaan:
        terapkan_popup_combobox_bawah(self)

    Fungsi juga menerima QComboBox secara langsung. Nilai kembali adalah
    jumlah ComboBox yang berhasil dipasang atau sudah memiliki helper.
    """
    if container_widget is None:
        return 0

    daftar_combo = []
    if isinstance(container_widget, QComboBox):
        daftar_combo.append(container_widget)

    daftar_combo.extend(container_widget.findChildren(QComboBox))

    jumlah_terpasang = 0
    combo_sudah_diproses = set()

    for combo in daftar_combo:
        identitas = id(combo)
        if identitas in combo_sudah_diproses:
            continue

        combo_sudah_diproses.add(identitas)
        if pasang_popup_combobox_bawah(combo):
            jumlah_terpasang += 1

    return jumlah_terpasang
