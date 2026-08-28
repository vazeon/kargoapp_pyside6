# themes/components/inputs.py

def get_global_focus_qss() -> str:
    """
    Mengembalikan QSS tambahan untuk memberikan outline biru (highlight)
    pada semua jenis input saat sedang aktif (fokus) di seluruh modul.
    """
    warna_highlight = "#0081db"  # Warna primary biru, sesuaikan dengan paletmu jika perlu

    return f"""
        /* Targetkan semua widget input teks dan angka */
        QLineEdit:focus, 
        QDateEdit:focus, 
        QTimeEdit:focus, 
        QDateTimeEdit:focus, 
        QSpinBox:focus, 
        QDoubleSpinBox:focus, 
        QTextEdit:focus, 
        QPlainTextEdit:focus {{
            border: 1px solid {warna_highlight};
            border-radius: 4px;
        }}

        
        /* 
           --- ALTERNATIF: SAPU BERSIH SISA BORDER --- 
           Memaksa mesin Qt untuk membersihkan border saat kehilangan fokus 
           sehingga tidak ada artefak garis biru yang tertinggal.
        */
        
        
        QComboBox:focus {{
            border: 1px solid {warna_highlight};
            border-radius: 4px;
        }}
        
        /* Opsional: Untuk item di dalam list/tabel/dropdown saat di-fokus */
        QAbstractItemView::item:focus {{
            border: 1px solid {warna_highlight};
            background-color: transparent;
        }}
    """