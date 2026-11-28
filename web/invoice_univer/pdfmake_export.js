// web/invoice_univer/pdfmake_export.js

import pdfMake from 'pdfmake/build/pdfmake'
import pdfFonts from 'pdfmake/build/vfs_fonts'

// pdfmake 0.3 keeps browser fonts in a virtual file system that is registered
// explicitly. The bundled Roboto family matches the application's default font.
pdfMake.addVirtualFileSystem(pdfFonts)

const PT_PER_MM = 72 / 25.4
const PT_PER_PX = 72 / 96
const DEFAULT_FONT_SIZE = 9

function asNumber(value, fallback) {
  const result = Number(value)
  return Number.isFinite(result) ? result : fallback
}

function getColor(color, fallback = undefined) {
  if (!color) return fallback
  const raw = typeof color === 'string' ? color : color.rgb
  if (!raw) return fallback
  const value = String(raw).trim()
  const rgb = value.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i)
  if (rgb) {
    return `#${rgb.slice(1).map((part) => Number(part).toString(16).padStart(2, '0')).join('')}`
  }
  return value
}

function resolveStyle(styleRef, styles) {
  if (!styleRef) return {}
  if (typeof styleRef === 'string') return styles?.[styleRef] || {}
  return typeof styleRef === 'object' ? styleRef : {}
}

function composeCellStyle(workbookStyles, sheet, row, column, cell) {
  // Workbook/worksheet defaults are lowest priority. Row and column styles
  // provide their usual fallbacks, while explicit cell formatting wins.
  return Object.assign(
    {},
    resolveStyle(workbookStyles?.defaultStyle, workbookStyles?.styles),
    resolveStyle(sheet?.defaultStyle, workbookStyles?.styles),
    resolveStyle(sheet?.columnData?.[column]?.s, workbookStyles?.styles),
    resolveStyle(sheet?.rowData?.[row]?.s, workbookStyles?.styles),
    resolveStyle(cell?.s, workbookStyles?.styles),
  )
}

function cellText(cell) {
  if (cell?.v !== undefined && cell?.v !== null) return String(cell.v)
  const stream = cell?.p?.body?.dataStream
  if (typeof stream === 'string') {
    // Univer rich-text streams end with paragraph/control sentinels. Keep
    // authored line breaks while removing only trailing control characters.
    return stream.replace(/[\r\u0000]+$/g, '').replace(/\u000b/g, '\n')
  }
  return ''
}

function borderEnabled(border) {
  return Boolean(border && Number(border.s) !== 0)
}

function cellBorders(style, gridlines) {
  const source = style?.bd || {}
  const left = gridlines || borderEnabled(source.l)
  const top = gridlines || borderEnabled(source.t)
  const right = gridlines || borderEnabled(source.r)
  const bottom = gridlines || borderEnabled(source.b)
  const color = (side) => getColor(source[side]?.cl, '#9AA0A6')
  return {
    border: [left, top, right, bottom],
    borderColor: [color('l'), color('t'), color('r'), color('b')],
  }
}

function displayCellValue(cell, style) {
  const value = cell?.v
  if (value === undefined || value === null) return cellText(cell)
  if (typeof value !== 'number' || !style?.n?.pattern) return cellText(cell)
  const pattern = String(style.n.pattern)
  const formatter = new Intl.NumberFormat('id-ID', {
    maximumFractionDigits: /0\.0+/.test(pattern) ? 2 : 0,
  })
  if (/\bRp\b|\\"Rp\\"/i.test(pattern)) return `Rp ${formatter.format(value)}`
  if (pattern.includes('%')) return `${formatter.format(value * 100)}%`
  if (pattern.includes('#,##0') || pattern.includes('0')) return formatter.format(value)
  return String(value)
}

function convertCell(cell, styles, gridlines, scaleFactor, rowHeightPx) {
  const style = resolveStyle(cell?.s, styles)
  const text = displayCellValue(cell, style)
  const fontSize = Math.max(4, asNumber(style.fs, DEFAULT_FONT_SIZE) * scaleFactor)
  const verticalPadding = Math.max(1, ((asNumber(rowHeightPx, 22) * PT_PER_PX) - fontSize * 1.35) / 2)
  const output = {
    text: text || ' ',
    font: 'Roboto',
    fontSize,
    margin: [2 * scaleFactor, verticalPadding * scaleFactor, 2 * scaleFactor, verticalPadding * scaleFactor],
    ...cellBorders(style, gridlines),
  }

  if (style.bl) output.bold = true
  if (style.it) output.italics = true
  if (style.ul?.s) output.decoration = 'underline'
  if (style.st?.s) output.decoration = 'lineThrough'

  const color = getColor(style.cl)
  const fill = getColor(style.bg)
  if (color) output.color = color
  if (fill) output.fillColor = fill

  const horizontal = Number(style.ht)
  if (horizontal === 2) output.alignment = 'center'
  else if (horizontal === 3) output.alignment = 'right'
  else if (horizontal === 4 || horizontal === 5) output.alignment = 'justify'
  else if (horizontal === 1) output.alignment = 'left'

  const vertical = Number(style.vt)
  if (vertical === 2) output.verticalAlignment = 'middle'
  else if (vertical === 3) output.verticalAlignment = 'bottom'
  else output.verticalAlignment = 'top'

  if (style.tb === 2) output.noWrap = true
  return output
}

function visibleIndexes(data, count, key) {
  const result = []
  for (let index = 0; index < count; index += 1) {
    if (Number(data?.[index]?.hd) === 1) continue
    result.push(index)
  }
  return result.length ? result : [0]
}

function findUsedRange(sheet) {
  const cellData = sheet?.cellData || {}
  let lastRow = 0
  let lastColumn = 0
  let found = false

  // Kargo row/column metadata is the most accurate used-range signal for the
  // initial Invoice template. It avoids printing the empty 100x26 viewport.
  for (const [rowKey, rowInfo] of Object.entries(sheet?.rowData || {})) {
    const row = Number(rowKey)
    if (Number.isInteger(row) && row >= 0 && rowInfo?.custom?.kargoRowId) {
      lastRow = Math.max(lastRow, row)
      found = true
    }
  }
  for (const [columnKey, columnInfo] of Object.entries(sheet?.columnData || {})) {
    const column = Number(columnKey)
    if (Number.isInteger(column) && column >= 0 && columnInfo?.custom?.kargoKey) {
      lastColumn = Math.max(lastColumn, column)
      found = true
    }
  }

  // Also include manual cells which do not carry Kargo metadata, formulas,
  // rich-text cells, and their styled content.
  for (const [rowKey, cells] of Object.entries(cellData)) {
    const row = Number(rowKey)
    if (!Number.isInteger(row) || row < 0) continue
    for (const [columnKey, cell] of Object.entries(cells || {})) {
      const column = Number(columnKey)
      if (!Number.isInteger(column) || column < 0 || !cell) continue
      const hasValue = cell.v !== undefined && cell.v !== null && String(cell.v) !== ''
      const hasFormula = Boolean(String(cell.f || '').trim())
      const hasRichText = Boolean(cell.p)
      if (!hasValue && !hasFormula && !hasRichText) continue
      lastRow = Math.max(lastRow, row)
      lastColumn = Math.max(lastColumn, column)
      found = true
    }
  }

  for (const merge of sheet?.mergeData || []) {
    const endRow = asNumber(merge?.endRow, -1)
    const endColumn = asNumber(merge?.endColumn, -1)
    if (endRow >= 0 && endColumn >= 0) {
      lastRow = Math.max(lastRow, endRow)
      lastColumn = Math.max(lastColumn, endColumn)
      found = true
    }
  }

  return found ? { startRow: 0, endRow: lastRow, startColumn: 0, endColumn: lastColumn } : {
    startRow: 0, endRow: 0, startColumn: 0, endColumn: 0,
  }
}

function makeMergeLookup(merges, rowMap, columnMap) {
  const starts = new Map()
  const covered = new Set()
  for (const merge of merges || []) {
    const startRow = asNumber(merge.startRow, -1)
    const endRow = asNumber(merge.endRow, startRow)
    const startColumn = asNumber(merge.startColumn, -1)
    const endColumn = asNumber(merge.endColumn, startColumn)
    if (startRow < 0 || startColumn < 0 || endRow < startRow || endColumn < startColumn) continue

    const visibleRows = []
    const visibleColumns = []
    for (let row = startRow; row <= endRow; row += 1) {
      if (rowMap.has(row)) visibleRows.push(rowMap.get(row))
    }
    for (let column = startColumn; column <= endColumn; column += 1) {
      if (columnMap.has(column)) visibleColumns.push(columnMap.get(column))
    }
    if (!visibleRows.length || !visibleColumns.length) continue
    const outputRow = Math.min(...visibleRows)
    const outputColumn = Math.min(...visibleColumns)
    const key = `${outputRow}:${outputColumn}`
    starts.set(key, {
      rowSpan: visibleRows.length,
      colSpan: visibleColumns.length,
    })

    for (const row of visibleRows) {
      for (const column of visibleColumns) {
        if (row === outputRow && column === outputColumn) continue
        covered.add(`${row}:${column}`)
      }
    }
  }
  return { starts, covered }
}

function getPageGeometry(pageSetup) {
  const setup = pageSetup || {}
  const paper = String(setup.paper_size || 'NCR').toUpperCase()
  const orientation = String(setup.orientation || (paper === 'NCR' ? 'landscape' : 'portrait')).toLowerCase()
  let pageSize
  let widthMm
  let heightMm

  if (paper === 'A3') {
    pageSize = 'A3'
    widthMm = 297
    heightMm = 420
  } else if (paper === 'A4') {
    pageSize = 'A4'
    widthMm = 210
    heightMm = 297
  } else if (paper === 'NCR') {
    widthMm = 139.7
    heightMm = 241.3
  } else {
    widthMm = asNumber(setup.width_mm, 210)
    heightMm = asNumber(setup.height_mm, 297)
  }

  if (orientation === 'landscape' && widthMm < heightMm) {
    ;[widthMm, heightMm] = [heightMm, widthMm]
  } else if (orientation !== 'landscape' && widthMm > heightMm) {
    ;[widthMm, heightMm] = [heightMm, widthMm]
  }

  if (pageSize) {
    return { pageSize, pageOrientation: orientation, widthPt: widthMm * PT_PER_MM, heightPt: heightMm * PT_PER_MM }
  }
  return {
    pageSize: { width: widthMm * PT_PER_MM, height: heightMm * PT_PER_MM },
    pageOrientation: undefined,
    widthPt: widthMm * PT_PER_MM,
    heightPt: heightMm * PT_PER_MM,
  }
}

function makeInvoiceContent(invoiceData) {
  if (!invoiceData || typeof invoiceData !== 'object') return []
  const content = []
  const companyName = String(invoiceData.company_name || 'PT KARGO EKSPEDISI')
  const logoText = String(invoiceData.logo_text || companyName)
  const address = String(invoiceData.company_address || '')
  const phone = String(invoiceData.company_phone || '')
  const addressText = [address, phone ? `Telp. ${phone}` : ''].filter(Boolean).join('\n')

  content.push({
    columns: [
      {
        width: '55%',
        stack: [
          { text: logoText, fontSize: 14, bold: true, color: '#1747A6', margin: [0, 0, 0, 2] },
          { text: companyName, fontSize: 8.5, bold: true },
        ],
      },
      {
        width: '45%',
        text: addressText,
        alignment: 'right',
        fontSize: 7.5,
        lineHeight: 1.15,
      },
    ],
    columnGap: 8,
    margin: [0, 0, 0, 5],
  })

  content.push({
    table: {
      widths: ['*'],
      body: [[{
        stack: [
          { text: 'INVOICE', fontSize: 10.5, bold: true, alignment: 'center' },
          { text: `No. ${String(invoiceData.invoice_number || 'DRAFT')}`, fontSize: 8, alignment: 'center' },
        ],
        margin: [3, 3, 3, 3],
      }]],
    },
    layout: {
      hLineWidth: () => 0.7,
      vLineWidth: () => 0.7,
      hLineColor: () => '#202124',
      vLineColor: () => '#202124',
      paddingLeft: () => 0,
      paddingRight: () => 0,
      paddingTop: () => 0,
      paddingBottom: () => 0,
    },
    margin: [0, 0, 0, 5],
  })

  if (String(invoiceData.layout_type || 'standard') === 'logistics') {
    content.push({
      table: {
        widths: [48, '*'],
        body: [[
          { text: 'TO :', bold: true, fontSize: 8.5, margin: [4, 3, 4, 3] },
          { text: String(invoiceData.client || '-'), bold: true, fontSize: 9, margin: [4, 3, 4, 3] },
        ]],
      },
      layout: {
        hLineWidth: () => 0.6,
        vLineWidth: () => 0.6,
        hLineColor: () => '#202124',
        vLineColor: () => '#202124',
      },
      margin: [0, 0, 0, 5],
    })
  } else {
    content.push({
      table: {
        widths: ['*', '*'],
        headerRows: 1,
        body: [
          [
            { text: 'BILL TO', bold: true, alignment: 'center', fontSize: 8, margin: [4, 3, 4, 3], fillColor: '#F2F4F7' },
            { text: 'SHIP TO', bold: true, alignment: 'center', fontSize: 8, margin: [4, 3, 4, 3], fillColor: '#F2F4F7' },
          ],
          [
            { text: String(invoiceData.client || '-'), alignment: 'center', fontSize: 8.5, margin: [4, 4, 4, 4] },
            { text: String(invoiceData.ship_to || '-'), alignment: 'center', fontSize: 8.5, margin: [4, 4, 4, 4] },
          ],
        ],
      },
      layout: {
        hLineWidth: () => 0.6,
        vLineWidth: () => 0.6,
        hLineColor: () => '#202124',
        vLineColor: () => '#202124',
      },
      margin: [0, 0, 0, 0],
    })
  }
  return content
}

function makeInvoiceFooterContent(invoiceData) {
  if (!invoiceData || typeof invoiceData !== 'object') return []
  const paymentStack = [{ text: 'PAYMENT INFO', bold: true, fontSize: 8, margin: [0, 0, 0, 2] }]
  paymentStack.push({ text: String(invoiceData.payment || '-'), fontSize: 7.5, lineHeight: 1.15 })
  if (String(invoiceData.notes || '').trim()) {
    paymentStack.push({
      table: {
        widths: ['*'],
        body: [[{
          text: `Catatan: ${String(invoiceData.notes).trim()}`,
          fontSize: 7,
          margin: [3, 3, 3, 3],
        }]],
      },
      layout: {
        hLineWidth: () => 0.45,
        vLineWidth: () => 0.45,
        hLineColor: () => '#9AA0A6',
        vLineColor: () => '#9AA0A6',
        paddingLeft: () => 0,
        paddingRight: () => 0,
        paddingTop: () => 0,
        paddingBottom: () => 0,
      },
      margin: [0, 4, 0, 0],
    })
  }

  return [
    {
      columns: [
        { width: '65%', stack: paymentStack },
        {
          width: '35%',
          table: {
            widths: ['*', 'auto'],
            body: [
              [
                { text: 'SUB TOTAL', bold: true, alignment: 'right', fontSize: 8, margin: [3, 3, 3, 3] },
                { text: String(invoiceData.subtotal_text || 'Rp 0'), alignment: 'right', fontSize: 8, margin: [3, 3, 3, 3] },
              ],
              [
                { text: String(invoiceData.tax_name || 'PAJAK'), bold: true, alignment: 'right', fontSize: 8, margin: [3, 3, 3, 3] },
                { text: String(invoiceData.tax_text || 'Rp 0'), alignment: 'right', fontSize: 8, margin: [3, 3, 3, 3] },
              ],
              [
                { text: 'TOTAL', bold: true, alignment: 'right', fontSize: 9.5, margin: [3, 3, 3, 3] },
                { text: String(invoiceData.total_text || 'Rp 0'), bold: true, alignment: 'right', fontSize: 9.5, margin: [3, 3, 3, 3] },
              ],
            ],
          },
          layout: {
            hLineWidth: () => 0.6,
            vLineWidth: () => 0.6,
            hLineColor: () => '#202124',
            vLineColor: () => '#202124',
          },
        },
      ],
      columnGap: 8,
      margin: [0, 2, 0, 0],
    },
    {
      text: String(invoiceData.place_date || invoiceData.date_text || ''),
      alignment: 'right',
      fontSize: 8,
      margin: [0, 7, 8, 0],
    },
    {
      text: String(invoiceData.signer || ''),
      bold: true,
      decoration: 'underline',
      alignment: 'right',
      fontSize: 8.5,
      margin: [0, 28, 8, 0],
    },
  ]
}

function estimateRowHeights(snapshot, sheet, sourceRows, sourceColumns, columnWidths, rowMap, columnMap, scaleFactor) {
  const styles = snapshot.styles || {}
  const merges = sheet.mergeData || []
  const mergeWidth = new Map()
  for (const merge of merges) {
    const startColumn = asNumber(merge?.startColumn, -1)
    const endColumn = asNumber(merge?.endColumn, startColumn)
    if (startColumn < 0 || endColumn < startColumn) continue
    const visible = sourceColumns.filter((column) => column >= startColumn && column <= endColumn)
    if (visible.length < 2) continue
    const key = `${asNumber(merge.startRow, -1)}:${startColumn}`
    mergeWidth.set(key, visible.reduce((sum, column) => sum + columnWidths[columnMap.get(column)], 0))
  }

  return sourceRows.map((sourceRow) => {
    const rowInfo = sheet.rowData?.[sourceRow] || {}
    const basePx = asNumber(Number(rowInfo.ia) === 1 ? rowInfo.ah : rowInfo.h, sheet.defaultRowHeight || 23)
    let estimated = Math.max(4, basePx * PT_PER_PX * scaleFactor)

    for (const sourceColumn of sourceColumns) {
      const cell = sheet.cellData?.[sourceRow]?.[sourceColumn] || null
      const style = composeCellStyle(snapshot, sheet, sourceRow, sourceColumn, cell)
      const text = displayCellValue(cell, style)
      if (!text) continue
      const outputColumn = columnMap.get(sourceColumn)
      let width = columnWidths[outputColumn] || 48
      const mergeKey = `${sourceRow}:${sourceColumn}`
      if (mergeWidth.has(mergeKey)) width = mergeWidth.get(mergeKey)
      const fontSize = Math.max(4, asNumber(style.fs, DEFAULT_FONT_SIZE) * scaleFactor)
      const available = Math.max(8, width - 5 * scaleFactor)
      const averageGlyph = fontSize * 0.52
      const explicitLines = String(text).split(/\r?\n/)
      let lineCount = 0
      for (const line of explicitLines) {
        if (style.tb === 2) {
          lineCount += 1
        } else {
          lineCount += Math.max(1, Math.ceil(Array.from(line).length * averageGlyph / available))
        }
      }
      const required = lineCount * fontSize * 1.24 + 4 * scaleFactor + 1
      estimated = Math.max(estimated, required)
    }
    return estimated
  })
}

function pageHeaderReserve(invoiceData) {
  if (!invoiceData || typeof invoiceData !== 'object') return 0
  return String(invoiceData.layout_type || 'standard') === 'logistics' ? 72 : 98
}

function pageFooterReserve(invoiceData) {
  if (!invoiceData || typeof invoiceData !== 'object') return 0
  const noteLines = Math.max(0, Math.ceil(String(invoiceData.notes || '').length / 75))
  const paymentLines = Math.max(1, Math.ceil(String(invoiceData.payment || '').length / 85))
  return 100 + noteLines * 9 + Math.max(0, paymentLines - 1) * 9
}

function breakInsideMergedRegion(candidate, currentStart, sourceRows, merges, axis) {
  let adjusted = candidate
  for (const merge of merges || []) {
    const start = asNumber(axis === 'row' ? merge?.startRow : merge?.startColumn, -1)
    const end = asNumber(axis === 'row' ? merge?.endRow : merge?.endColumn, start)
    if (start < 0 || end < start) continue
    const startIndex = sourceRows.indexOf(start)
    const endIndex = sourceRows.indexOf(end)
    if (startIndex < 0 || endIndex < 0) continue
    if (startIndex < adjusted && endIndex >= adjusted) {
      // Prefer moving the break before the merged range. If the merge itself
      // occupies a whole page, keep it together on the next page instead.
      if (startIndex > currentStart) adjusted = startIndex
      else adjusted = Math.max(adjusted, endIndex + 1)
    }
  }
  return adjusted
}

function makeColumnPages(sourceColumns, columnWidths, availableWidth, scaleMode, merges) {
  if (!sourceColumns.length) return [{ start: 0, end: 1 }]
  const total = columnWidths.reduce((sum, width) => sum + width, 0)
  if (scaleMode === 'fit_width' || total <= availableWidth) {
    return [{ start: 0, end: sourceColumns.length }]
  }

  const pages = []
  let cursor = 0
  while (cursor < sourceColumns.length) {
    let end = cursor
    let used = 0
    while (end < sourceColumns.length) {
      const nextWidth = columnWidths[end] || 0
      if (end > cursor && used + nextWidth > availableWidth) break
      used += nextWidth
      end += 1
    }
    if (end <= cursor) end = cursor + 1
    end = breakInsideMergedRegion(end, cursor, sourceColumns, merges, 'column')
    if (end <= cursor) {
      // A merged range wider than the printable width remains indivisible.
      const containing = (merges || []).find((merge) => {
        const start = asNumber(merge?.startColumn, -1)
        const finish = asNumber(merge?.endColumn, start)
        return start <= sourceColumns[cursor] && finish >= sourceColumns[cursor]
      })
      if (containing) {
        const mergeEnd = sourceColumns.indexOf(asNumber(containing.endColumn, containing.startColumn))
        end = Math.max(cursor + 1, mergeEnd + 1)
      } else {
        end = cursor + 1
      }
    }
    pages.push({ start: cursor, end: Math.min(sourceColumns.length, end) })
    cursor = Math.min(sourceColumns.length, end)
  }
  return pages
}

function makeRowPages(sourceRows, rowHeights, availableHeight, repeatRows, invoiceData, merges) {
  const count = sourceRows.length
  if (!count) return [{ start: 0, end: 1 }]
  const repeatedCount = Math.max(0, Math.min(count, repeatRows))
  const repeatedHeight = rowHeights.slice(0, repeatedCount).reduce((sum, height) => sum + height, 0)
  const firstHeader = pageHeaderReserve(invoiceData)
  const footer = pageFooterReserve(invoiceData)
  const pages = []
  let cursor = 0

  while (cursor < count) {
    const first = pages.length === 0
    const prefixHeight = first ? firstHeader : repeatedHeight
    const capacity = Math.max(12, availableHeight - prefixHeight)
    const remainingHeight = rowHeights.slice(cursor).reduce((sum, height) => sum + height, 0)
    const footerFits = remainingHeight + prefixHeight + footer <= availableHeight

    if (footerFits) {
      pages.push({ start: cursor, end: count, first, repeat: !first })
      break
    }

    let used = 0
    let end = cursor
    while (end < count && used + rowHeights[end] <= capacity) {
      used += rowHeights[end]
      end += 1
    }
    if (end <= cursor) end = cursor + 1

    // If all rows fit without the final invoice footer but not with it, reserve
    // a final page for the footer by moving one or more trailing rows forward.
    if (end >= count && footer > 0) {
      const lastPageCapacity = Math.max(12, availableHeight - (first ? firstHeader : repeatedHeight) - footer)
      let tailStart = count
      let tailHeight = 0
      while (tailStart > cursor + 1 && tailHeight + rowHeights[tailStart - 1] <= lastPageCapacity) {
        tailStart -= 1
        tailHeight += rowHeights[tailStart]
      }
      if (tailStart > cursor && tailStart < count) end = tailStart
      else if (count - cursor > 1) end = count - 1
    }

    const safeEnd = breakInsideMergedRegion(end, cursor, sourceRows, merges, 'row')
    end = safeEnd > cursor ? Math.min(count, safeEnd) : end
    if (end <= cursor) end = Math.min(count, cursor + 1)
    pages.push({ start: cursor, end, first, repeat: !first })
    cursor = end
  }

  return pages.length ? pages : [{ start: 0, end: count, first: true, repeat: false }]
}

function buildInvoiceLayout(workbookSnapshot, pageSetup = {}, invoiceData = null) {
  if (!workbookSnapshot || typeof workbookSnapshot !== 'object') {
    throw new Error('Snapshot workbook Univer tidak tersedia.')
  }

  const sheetId = workbookSnapshot.custom?.kargoActiveSheetId
    || workbookSnapshot.sheetOrder?.[0]
    || Object.keys(workbookSnapshot.sheets || {})[0]
  const sheet = sheetId ? workbookSnapshot.sheets?.[sheetId] : null
  if (!sheet) throw new Error('Worksheet aktif Univer tidak ditemukan.')

  const range = findUsedRange(sheet)
  const rowCount = range.endRow - range.startRow + 1
  const columnCount = range.endColumn - range.startColumn + 1
  const sourceRows = visibleIndexes(sheet.rowData, rowCount, 'row').map((row) => row + range.startRow)
  const sourceColumns = visibleIndexes(sheet.columnData, columnCount, 'column').map((column) => column + range.startColumn)
  const rowMap = new Map(sourceRows.map((row, index) => [row, index]))
  const columnMap = new Map(sourceColumns.map((column, index) => [column, index]))
  const styles = workbookSnapshot.styles || {}
  const gridlines = Boolean(pageSetup.print_gridlines)
  const scaleMode = String(pageSetup.scaling || 'actual')

  const baseColumnWidths = sourceColumns.map((column) => {
    const widthPx = asNumber(sheet.columnData?.[column]?.w, sheet.defaultColumnWidth || 73)
    return Math.max(12, widthPx * PT_PER_PX)
  })
  const geometry = getPageGeometry(pageSetup)
  const margins = pageSetup.margins || {}
  const marginPt = [
    asNumber(margins.left, 4) * PT_PER_MM,
    asNumber(margins.top, 4) * PT_PER_MM,
    asNumber(margins.right, 4) * PT_PER_MM,
    asNumber(margins.bottom, 4) * PT_PER_MM,
  ]
  const availableWidth = Math.max(36, geometry.widthPt - marginPt[0] - marginPt[2])
  const availableHeight = Math.max(36, geometry.heightPt - marginPt[1] - marginPt[3])
  const totalWidth = baseColumnWidths.reduce((sum, width) => sum + width, 0)
  const scaleFactor = scaleMode === 'fit_width' && totalWidth > availableWidth
    ? availableWidth / totalWidth
    : 1
  const finalWidths = baseColumnWidths.map((width) => width * scaleFactor)
  const rowHeights = estimateRowHeights(
    workbookSnapshot,
    sheet,
    sourceRows,
    sourceColumns,
    finalWidths,
    rowMap,
    columnMap,
    scaleFactor,
  )

  const mergeLookup = makeMergeLookup(sheet.mergeData, rowMap, columnMap)
  const mergeData = sheet.mergeData || []
  const repeatedRows = Math.max(0, Math.min(sourceRows.length, Math.floor(asNumber(pageSetup.repeat_header_rows, 1))))
  const columnPages = makeColumnPages(sourceColumns, finalWidths, availableWidth, scaleMode, mergeData)
  const rowPages = makeRowPages(sourceRows, rowHeights, availableHeight, repeatedRows, invoiceData, mergeData)

  const body = sourceRows.map((sourceRow, outputRow) => {
    return sourceColumns.map((sourceColumn, outputColumn) => {
      const position = `${outputRow}:${outputColumn}`
      if (mergeLookup.covered.has(position)) return {}
      const cell = sheet.cellData?.[sourceRow]?.[sourceColumn] || null
      const effectiveStyle = composeCellStyle(workbookSnapshot, sheet, sourceRow, sourceColumn, cell)
      const heightPx = (rowHeights[outputRow] || 17) / PT_PER_PX
      const converted = convertCell(cell ? { ...cell, s: effectiveStyle } : { s: effectiveStyle }, styles, gridlines, scaleFactor, heightPx)
      const merge = mergeLookup.starts.get(position)
      if (merge) {
        if (merge.colSpan > 1) converted.colSpan = merge.colSpan
        if (merge.rowSpan > 1) converted.rowSpan = merge.rowSpan
      }
      return converted
    })
  })

  const pageOrder = String(pageSetup.page_order || 'down_then_over')
  const pages = []
  if (pageOrder === 'over_then_down') {
    for (let rowIndex = 0; rowIndex < rowPages.length; rowIndex += 1) {
      for (let columnIndex = 0; columnIndex < columnPages.length; columnIndex += 1) {
        pages.push({ rowIndex, columnIndex })
      }
    }
  } else {
    for (let columnIndex = 0; columnIndex < columnPages.length; columnIndex += 1) {
      for (let rowIndex = 0; rowIndex < rowPages.length; rowIndex += 1) {
        pages.push({ rowIndex, columnIndex })
      }
    }
  }

  return {
    sheet,
    sourceRows,
    sourceColumns,
    rowHeights,
    finalWidths,
    body,
    rowPages,
    columnPages,
    pages,
    repeatedRows,
    geometry,
    marginPt,
    scaleFactor,
    availableWidth,
    availableHeight,
    gridlines,
    pageOrder,
  }
}

export function calculateInvoicePagePlan(workbookSnapshot, pageSetup = {}, invoiceData = null) {
  const layout = buildInvoiceLayout(workbookSnapshot, pageSetup, invoiceData)
  const sheet = layout.sheet
  const fullRowCount = Math.max(
    asNumber(sheet.rowCount, 0),
    (layout.sourceRows[layout.sourceRows.length - 1] ?? 0) + 1,
  )
  const fullColumnCount = Math.max(
    asNumber(sheet.columnCount, 0),
    (layout.sourceColumns[layout.sourceColumns.length - 1] ?? 0) + 1,
  )

  // Page-break guides extend beyond the currently filled cells. This lets a
  // user see where the next page ends while building a short invoice, just as
  // Excel shows the page boundary before the sheet has been filled.
  const previewRows = visibleIndexes(sheet.rowData, fullRowCount, 'row')
  const actualRowHeights = new Map(layout.sourceRows.map((row, index) => [row, layout.rowHeights[index]]))
  const defaultRowHeight = asNumber(sheet.defaultRowHeight, 23)
  const previewRowHeights = previewRows.map((row) => {
    if (actualRowHeights.has(row)) return actualRowHeights.get(row)
    const info = sheet.rowData?.[row] || {}
    const rowPx = asNumber(Number(info.ia) === 1 ? info.ah : info.h, defaultRowHeight)
    return Math.max(4, rowPx * PT_PER_PX * layout.scaleFactor)
  })
  const previewRowPages = makeRowPages(
    previewRows,
    previewRowHeights,
    layout.availableHeight,
    layout.repeatedRows,
    invoiceData,
    sheet.mergeData || [],
  )

  const previewColumns = visibleIndexes(sheet.columnData, fullColumnCount, 'column')
  const actualColumnWidths = new Map(layout.sourceColumns.map((column, index) => [column, layout.finalWidths[index]]))
  const defaultColumnWidth = asNumber(sheet.defaultColumnWidth, 73)
  const previewColumnWidths = previewColumns.map((column) => {
    if (actualColumnWidths.has(column)) return actualColumnWidths.get(column)
    const info = sheet.columnData?.[column] || {}
    const widthPx = asNumber(info.w, defaultColumnWidth)
    return Math.max(12, widthPx * PT_PER_PX * layout.scaleFactor)
  })
  const previewColumnPages = makeColumnPages(
    previewColumns,
    previewColumnWidths,
    layout.availableWidth,
    String(pageSetup.scaling || 'actual'),
    sheet.mergeData || [],
  )

  return {
    // Guides use the full worksheet grid; page totals and actual page ranges
    // remain based on the populated/used range printed by pdfmake.
    rowBreaks: previewRowPages.slice(1).map((page) => previewRows[page.start]).filter(Number.isInteger),
    columnBreaks: previewColumnPages.slice(1).map((page) => previewColumns[page.start]).filter(Number.isInteger),
    rowPages: layout.rowPages.map((page) => ({
      startRow: layout.sourceRows[page.start],
      endRow: layout.sourceRows[Math.max(page.start, page.end - 1)],
    })),
    columnPages: layout.columnPages.map((page) => ({
      startColumn: layout.sourceColumns[page.start],
      endColumn: layout.sourceColumns[Math.max(page.start, page.end - 1)],
    })),
    horizontalPages: layout.columnPages.length,
    verticalPages: layout.rowPages.length,
    pageCount: layout.pages.length,
    scaleFactor: layout.scaleFactor,
    pageOrder: layout.pageOrder,
  }
}

export function buildInvoicePdfDefinition(workbookSnapshot, pageSetup = {}, invoiceData = null) {
  const layout = buildInvoiceLayout(workbookSnapshot, pageSetup, invoiceData)
  const repeatedRows = layout.repeatedRows
  const tableLayout = {
    hLineWidth: () => 0.35,
    vLineWidth: () => 0.35,
    hLineColor: () => '#9AA0A6',
    vLineColor: () => '#9AA0A6',
    paddingLeft: () => 0,
    paddingRight: () => 0,
    paddingTop: () => 0,
    paddingBottom: () => 0,
  }

  const content = []
  let firstPage = true
  if (invoiceData) content.push(...makeInvoiceContent(invoiceData))

  layout.pages.forEach((page, pageIndex) => {
    const rowPage = layout.rowPages[page.rowIndex]
    const columnPage = layout.columnPages[page.columnIndex]
    const rowIndexes = []
    if (rowPage.repeat && repeatedRows > 0) {
      for (let index = 0; index < repeatedRows; index += 1) rowIndexes.push(index)
    }
    for (let index = rowPage.start; index < rowPage.end; index += 1) rowIndexes.push(index)

    const columnIndexes = []
    for (let index = columnPage.start; index < columnPage.end; index += 1) columnIndexes.push(index)
    const pageBody = rowIndexes.map((rowIndex) => columnIndexes.map((columnIndex) => {
      const cell = layout.body[rowIndex]?.[columnIndex]
      return cell === undefined ? {} : cell
    }))
    const pageHeights = rowIndexes.map((rowIndex) => layout.rowHeights[rowIndex] || 17)
    const pageWidths = columnIndexes.map((columnIndex) => layout.finalWidths[columnIndex] || 48)
    const tableNode = {
      table: {
        headerRows: repeatedRows,
        widths: pageWidths,
        body: pageBody,
        heights: pageHeights,
      },
      layout: tableLayout,
      dontBreakRows: true,
      keepWithHeaderRows: repeatedRows,
      margin: [0, pageIndex === 0 && invoiceData ? 2 : 0, 0, 0],
    }
    if (!firstPage) tableNode.pageBreak = 'before'
    content.push(tableNode)
    firstPage = false
  })

  if (invoiceData) content.push(...makeInvoiceFooterContent(invoiceData))

  const defaultStyle = {
    font: 'Roboto',
    fontSize: DEFAULT_FONT_SIZE * layout.scaleFactor,
    color: '#202124',
  }
  return {
    info: {
      title: String(workbookSnapshot.name || 'Invoice Kargo'),
      subject: 'Invoice Kargo - Univer Spreadsheet',
      creator: 'Kargo Desktop',
    },
    pageSize: layout.geometry.pageSize,
    ...(layout.geometry.pageOrientation ? { pageOrientation: layout.geometry.pageOrientation } : {}),
    pageMargins: layout.marginPt,
    defaultStyle,
    footer: (currentPage, pageCount) => ({
      text: `Halaman ${currentPage} / ${pageCount}`,
      alignment: 'right',
      fontSize: 7,
      color: '#6B7280',
      margin: [0, 0, 10, 4],
    }),
    content,
  }
}

export async function buildInvoicePdfBlob(workbookSnapshot, pageSetup = {}, invoiceData = null) {
  const definition = buildInvoicePdfDefinition(workbookSnapshot, pageSetup, invoiceData)
  return pdfMake.createPdf(definition).getBlob()
}