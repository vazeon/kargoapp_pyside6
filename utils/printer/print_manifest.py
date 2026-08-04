# utils/printer/print_manifest.py
from __future__ import annotations

import html
import re
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from config import DATA_CLIENT
from utils.number_formatters import (
    angka_indonesia_to_decimal,
    format_angka_indonesia,
    format_decimal_indonesia,
    jumlahkan_angka_dari_teks,
)
from utils.typography import get_master_font

from .common import (
    JENIS_MANIFEST,
    JendelaPreviewCustom,
    buat_dokumen_html,
    buat_printer,
)

_KUNCI_ITEM = (
    "no_resi",
    "pengirim",
    "penerima",
    "kota_tujuan",
    "nama_barang",
    "koli",
    "berat",
    "cbm",
    "total_ongkir",
    "ket_manifest",
)


def _esc(value: Any) -> str:
    return html.escape(
        str(value if value is not None else "")
    )


def _nilai_row(
        row: Iterable[Any],
        index: int,
        default: Any = "",
) -> Any:
    if isinstance(row, dict):
        try:
            return row.get(
                _KUNCI_ITEM[index],
                default,
            )
        except IndexError:
            return default

    try:
        return row[index]
    except (
            IndexError,
            KeyError,
            TypeError,
    ):
        return default


def _teks_koli(nilai: Any) -> str:
    """Menampilkan nilai KOLI sebagai teks bebas."""
    if nilai is None:
        return ""
    return str(nilai).strip().upper()


def _format_desimal(
        nilai: Any,
        maksimum_desimal: int = 2,
) -> str:
    return format_angka_indonesia(
        nilai,
        maksimum_desimal=maksimum_desimal,
        kosong_jika_nol=True,
        nilai_kosong="-",
    )


def cetak_manifest_ke_printer(
        data: dict,
        parent_window=None,
        tipe_kertas: str = "A4",
) -> None:
    """Membuat preview dan mencetak dokumen Manifest."""
    if not isinstance(data, dict):
        raise TypeError(
            "Data manifest harus berupa dictionary."
        )

    # Memaksa tipe kertas selalu menjadi A4
    tipe_kertas = "A4"

    printer = buat_printer(
        JENIS_MANIFEST,
        tipe_kertas=tipe_kertas,
    )

    comp_name = str(
        DATA_CLIENT.get("nama_perusahaan")
        or "EKSPEDISI"
    ).strip()
    list_items = data.get("items", [])
    if not isinstance(list_items, (list, tuple)):
        list_items = []

    baris_tabel: list[str] = []
    total_berat = Decimal("0")
    total_cbm = Decimal("0")
    total_seluruh_ongkir = Decimal("0")

    for index, row in enumerate(list_items):
        nomor = index + 1
        no_resi = _nilai_row(row, 0)
        pengirim = _nilai_row(row, 1)
        penerima = _nilai_row(row, 2)
        kota_raw = str(
            _nilai_row(row, 3, "")
        )
        nama_barang = _nilai_row(row, 4)
        nilai_koli = _nilai_row(row, 5, "")
        nilai_berat = _nilai_row(row, 6, 0)
        nilai_cbm = _nilai_row(row, 7, 0)
        total_ongkir = _nilai_row(row, 8, "-")
        ket_manifest = _nilai_row(row, 9, "-")

        total_berat += angka_indonesia_to_decimal(
            nilai_berat
        )
        total_cbm += angka_indonesia_to_decimal(
            nilai_cbm
        )

        # Mengekstrak angka dari format Rupiah untuk dijumlahkan
        angka_ongkir_bersih = re.sub(r'[^\d]', '', str(total_ongkir))
        if angka_ongkir_bersih:
            total_seluruh_ongkir += Decimal(angka_ongkir_bersih)

        kota_cetak = (
            kota_raw.split(" - ")[-1].strip()
            if " - " in kota_raw
            else kota_raw.strip()
        )

        baris_tabel.append(
            "<tr>"
            f'<td align="center">{nomor}</td>'
            f"<td>{_esc(no_resi)}</td>"
            f"<td>{_esc(pengirim)}</td>"
            f"<td>{_esc(penerima)}</td>"
            f"<td>{_esc(kota_cetak)}</td>"
            f"<td>{_esc(nama_barang)}</td>"
            f'<td align="right">{_esc(_teks_koli(nilai_koli))}</td>'
            f'<td align="right">{_format_desimal(nilai_berat)}</td>'
            f'<td align="right">{_format_desimal(nilai_cbm)}</td>'
            f'<td align="right">{_esc(total_ongkir)}</td>'
            f"<td>{_esc(ket_manifest)}</td>"
            "</tr>"
        )

    if not baris_tabel:
        baris_tabel.append(
            '<tr><td colspan="11" align="center" '
            'style="padding:18px;color:#64748b;">'
            "Tidak ada muatan pada manifest."
            "</td></tr>"
        )

    total_koli = jumlahkan_angka_dari_teks(
        _nilai_row(row, 5, "")
        for row in list_items
    )
    total_koli_cetak = (
        format_decimal_indonesia(total_koli)
        if total_koli != 0
        else "-"
    )
    total_berat_cetak = _format_desimal(
        total_berat,
        maksimum_desimal=2,
    )
    total_cbm_cetak = _format_desimal(
        total_cbm,
        maksimum_desimal=2,
    )

    # Format hasil akhir perhitungan seluruh ongkir
    if total_seluruh_ongkir > 0:
        total_ongkir_cetak = format_angka_indonesia(
            total_seluruh_ongkir,
            maksimum_desimal=0,
        )
    else:
        total_ongkir_cetak = "-"

    nomor_manifest = str(
        data.get("no_manifest", "")
        or "MANIFEST"
    ).strip().upper()
    truk = str(
        data.get("truk")
        or data.get("armada")
        or ""
    ).strip().upper()
    note_manifest = str(
        data.get("note_manifest", "")
        or ""
    ).strip().upper()
    nama_kapal = str(
        data.get("nama_kapal", "")
        or ""
    ).strip().upper()
    tanggal = str(
        data.get("tanggal", "")
        or ""
    ).strip()

    armada_atau_note = truk if (truk and truk != "-") else (note_manifest or "")
    if armada_atau_note and nama_kapal:
        detail_gabungan = f"{armada_atau_note} - {nama_kapal}"
    else:
        detail_gabungan = armada_atau_note or nama_kapal or "-"

    font_dokumen = get_master_font()

    root_project = Path(__file__).resolve().parents[2]
    logo_path = (
            root_project
            / "assets"
            / "logo"
            / "logo_mahkota_kargo.png"
    )
    logo_html = ""
    if logo_path.is_file():
        logo_html = (
            f'<img src="{_esc(logo_path.as_uri())}" '
            'width="18" height="18" alt="Logo">'
        )

    tanggal_cetak = tanggal or "-"

    html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{
                font-family: "{font_dokumen}";
                font-size: 4pt;
                margin: 0;
                padding: 0;
                color: #000000;
            }}
            .document-header {{
                width: 100%;
                border-collapse: collapse;
                table-layout: fixed;
                margin: 0 0 4px 0;
            }}
            .document-header td {{
                border: none;
                padding: 0 4px 4px 4px;
                vertical-align: middle;
            }}
            .company-block {{
                width: 100%;
                border-collapse: collapse;
            }}
            .company-block td {{
                padding: 0;
            }}
            .logo-cell {{
                width: 22px;
                text-align: left;
                vertical-align: middle;
            }}
            .company-name {{
                font-size: 7pt;
                line-height: 1.15;
                font-weight: bold;
                color: #d71920;
                white-space: nowrap;
            }}
            .center-detail {{
                text-align: center;
                font-size: 7pt;
                line-height: 1.35;
                font-weight: bold;
            }}
            .right-detail {{
                text-align: right;
                font-size: 5pt;
                line-height: 1.35;
                font-weight: bold;
                white-space: nowrap;
            }}
            .right-detail .manifest-number {{
                margin-top: 2px;
            }}
            .table-data {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 0;
                table-layout: fixed;
            }}
            .table-data th {{
                border: 1px solid #94a3b8;
                padding: 3px 2px;
                background-color: #dbeafe;
                font-size: 4pt;
                line-height: 1.15;
                font-weight: bold;
            }}
            .table-data td {{
                border: 1px solid #94a3b8;
                padding: 4px 3px;
                font-size: 4pt;
                line-height: 1.2;
                word-wrap: break-word;
            }}
            .total-row {{
                font-weight: bold;
                background-color: #f8fafc;
            }}
        </style>
    </head>
    <body>
        <table class="document-header">
            <tr>
                <td width="30%">
                    <table class="company-block">
                        <tr>
                            <td class="logo-cell">
                                {logo_html}
                            </td>
                            <td class="company-name">
                                {_esc(comp_name.upper())}
                            </td>
                        </tr>
                    </table>
                </td>

                <td width="48%" class="center-detail">
                    <div>
                        {_esc(detail_gabungan)}
                    </div>
                </td>

                <td width="22%" class="right-detail">
                    <div>{_esc(tanggal_cetak)}</div>
                    <div class="manifest-number">
                        No. : {_esc(nomor_manifest)}
                    </div>
                </td>
            </tr>
        </table>

        <table class="table-data">
            <thead>
                <tr>
                    <th width="3%">NO</th>
                    <th width="7%">RESI</th>
                    <th width="12%">PENGIRIM</th>
                    <th width="12%">PENERIMA</th>
                    <th width="10%">KOTA TUJUAN</th>
                    <th width="18%">NAMA BARANG</th>
                    <th width="5%">KOLI</th>
                    <th width="5%">BERAT (kg)</th>
                    <th width="5%">KUBIK (m3)</th>
                    <th width="11%">ONGKIR (Rp)</th>
                    <th width="12%">KETERANGAN</th>
                </tr>
            </thead>
            <tbody>
                {''.join(baris_tabel)}
                <tr class="total-row">
                    <td colspan="6" align="right"
                        style="padding-right: 15px;">
                        TOTAL MUATAN :
                    </td>
                    <td align="right"><b>{total_koli_cetak}</b></td>
                    <td align="right"><b>{total_berat_cetak}</b></td>
                    <td align="right"><b>{total_cbm_cetak}</b></td>
                    <td align="right"><b>{total_ongkir_cetak}</b></td>
                </tr>
            </tbody>
        </table>
    </body>
    </html>
    """

    document = buat_dokumen_html(
        html_content,
        printer,
        margin=0,
    )

    preview = JendelaPreviewCustom(
        printer,
        document,
        parent_window,
        jenis_dokumen=JENIS_MANIFEST,
        tipe_kertas=tipe_kertas,
        nomor_dokumen=nomor_manifest,
    )
    preview.exec()
