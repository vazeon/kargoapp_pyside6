import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets'
import { buildInvoicePdfBlob, calculateInvoicePagePlan } from './pdfmake_export.js'
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core'
import UniverPresetSheetsCoreEnUS from '@univerjs/preset-sheets-core/locales/en-US'
import '@univerjs/preset-sheets-core/lib/index.css'

// Optional open-source Univer Sheets presets. These extend the native ribbon,
// menus and context menus; Kargo does not recreate their UI.
import { UniverSheetsFilterPreset } from '@univerjs/preset-sheets-filter'
import UniverPresetSheetsFilterEnUS from '@univerjs/preset-sheets-filter/locales/en-US'
import '@univerjs/preset-sheets-filter/lib/index.css'

import { UniverSheetsSortPreset } from '@univerjs/preset-sheets-sort'
import UniverPresetSheetsSortEnUS from '@univerjs/preset-sheets-sort/locales/en-US'
import '@univerjs/preset-sheets-sort/lib/index.css'

import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation'
import UniverPresetSheetsDataValidationEnUS from '@univerjs/preset-sheets-data-validation/locales/en-US'
import '@univerjs/preset-sheets-data-validation/lib/index.css'

import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting'
import UniverPresetSheetsConditionalFormattingEnUS from '@univerjs/preset-sheets-conditional-formatting/locales/en-US'
import '@univerjs/preset-sheets-conditional-formatting/lib/index.css'

import { UniverSheetsFindReplacePreset } from '@univerjs/preset-sheets-find-replace'
import UniverPresetSheetsFindReplaceEnUS from '@univerjs/preset-sheets-find-replace/locales/en-US'
import '@univerjs/preset-sheets-find-replace/lib/index.css'

import { UniverSheetsHyperLinkPreset } from '@univerjs/preset-sheets-hyper-link'
import UniverPresetSheetsHyperLinkEnUS from '@univerjs/preset-sheets-hyper-link/locales/en-US'
import '@univerjs/preset-sheets-hyper-link/lib/index.css'

import { UniverSheetsTablePreset } from '@univerjs/preset-sheets-table'
import UniverPresetSheetsTableEnUS from '@univerjs/preset-sheets-table/locales/en-US'
import '@univerjs/preset-sheets-table/lib/index.css'

import { UniverSheetsDrawingPreset } from '@univerjs/preset-sheets-drawing'
import UniverPresetSheetsDrawingEnUS from '@univerjs/preset-sheets-drawing/locales/en-US'
import '@univerjs/preset-sheets-drawing/lib/index.css'

import { UniverSheetsNotePreset } from '@univerjs/preset-sheets-note'
import UniverPresetSheetsNoteEnUS from '@univerjs/preset-sheets-note/locales/en-US'
import '@univerjs/preset-sheets-note/lib/index.css'

import { UniverSheetsThreadCommentPreset } from '@univerjs/preset-sheets-thread-comment'
import UniverPresetSheetsThreadCommentEnUS from '@univerjs/preset-sheets-thread-comment/locales/en-US'
import '@univerjs/preset-sheets-thread-comment/lib/index.css'

let univer = null
let univerAPI = null
let workbook = null
let worksheet = null
let bridge = null
let locked = false
let programmaticChange = false
let snapshotTimer = null
let eventDisposables = []
let lastColumnKeys = []
// Preserve Kargo row identity when native Univer sorting moves spreadsheet rows.
let lastBridgeRows = []

// Kargo Page Break Preview. The same pagination calculator is shared with
// pdfmake so editor guides and the generated PDF use one layout definition.
let currentPageSetup = {
  paper_size: 'NCR', orientation: 'landscape', width_mm: 139.7, height_mm: 241.3,
  margins: { top: 4, bottom: 4, left: 4, right: 4 }, scaling: 'actual',
  repeat_header_rows: 1, page_order: 'down_then_over', show_page_breaks: true,
}
let currentInvoicePdfData = { layout_type: 'standard' }
let pageBreakPlan = null
let pageBreakOverlay = null
let pageBreakDrawFrame = 0
let pageBreakResizeObserver = null
let pageBreakObservedCanvas = null
let pageBreakListenersReady = false
let kargoPageSetupMenuObserver = null

const APP_VERSION = '1.6.1'

// Spreadsheet viewport: blank cells stay available like a conventional sheet.
// Only rows/columns with model metadata or user-entered content are bridged to Python.
const MIN_SHEET_ROWS = 100
const MIN_SHEET_COLUMNS = 26

function safeCall(name, ...args) {
  // Invoke the QWebChannel proxy as a property call so its receiver remains
  // exactly the registered QObject proxy expected by Qt WebChannel.
  try {
    if (!bridge) {
      console.error(`[Kargo] Bridge ${name} unavailable: channel not initialized`)
      return false
    }
    if (typeof bridge[name] !== 'function') {
      console.error(`[Kargo] Bridge method ${name} unavailable`)
      return false
    }
    bridge[name](...args)
    return true
  } catch (error) {
    console.error(`[Kargo] Bridge ${name} failed`, error)
    return false
  }
}

function newId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replaceAll('-', '')
  return `kargo_${Date.now()}_${Math.random().toString(36).slice(2, 12)}`
}

function columnName(index) {
  let n = index + 1
  let result = ''
  while (n > 0) {
    const rem = (n - 1) % 26
    result = String.fromCharCode(65 + rem) + result
    n = Math.floor((n - 1) / 26)
  }
  return result
}

function getPageBreakCanvas() {
  const root = document.getElementById('univer-app')
  if (!root) return null

  // Prefer Univer's stable primary worksheet canvas over selection/header canvases.
  const mainCanvas = root.querySelector('#univer-sheet-main-canvas')
    || document.getElementById('univer-sheet-main-canvas')
  if (mainCanvas instanceof HTMLCanvasElement) {
    const rect = mainCanvas.getBoundingClientRect()
    if (rect.width > 180 && rect.height > 140) return mainCanvas
  }

  const candidates = [...root.querySelectorAll('canvas')].map((canvas) => {
    const rect = canvas.getBoundingClientRect()
    const style = window.getComputedStyle(canvas)
    return {
      canvas,
      rect,
      area: rect.width * rect.height,
      visible: style.display !== 'none' && style.visibility !== 'hidden',
    }
  }).filter((item) => item.visible && item.rect.width > 180 && item.rect.height > 140)
  candidates.sort((a, b) => b.area - a.area)
  return candidates[0]?.canvas || null
}

function ensurePageBreakOverlay() {
  const root = document.getElementById('univer-app')
  if (!root) return false

  // createUniver/React may clear the mount node after initialization. Reattach
  // this node on every draw so it cannot remain detached after the first render.
  if (!pageBreakOverlay) {
    pageBreakOverlay = document.createElement('div')
    pageBreakOverlay.className = 'kargo-page-break-overlay'
    Object.assign(pageBreakOverlay.style, {
      position: 'absolute', display: 'none', overflow: 'hidden', pointerEvents: 'none',
      zIndex: '20', boxSizing: 'border-box',
    })
  }

  if (window.getComputedStyle(root).position === 'static') root.style.position = 'relative'
  if (pageBreakOverlay.parentElement !== root) root.appendChild(pageBreakOverlay)
  return true
}

function viewportScrollPixels() {
  try {
    const scroll = worksheet?.getScrollState?.() || {}
    const skeleton = worksheet?.getSkeleton?.()
    const startRow = Math.max(0, Number(scroll.sheetViewStartRow || 0))
    const startColumn = Math.max(0, Number(scroll.sheetViewStartColumn || 0))
    const startCell = skeleton?.getCellWithCoordByIndex?.(startRow, startColumn, false) || {}
    return {
      x: Number(startCell.startX || 0) + Number(scroll.offsetX || 0),
      y: Number(startCell.startY || 0) + Number(scroll.offsetY || 0),
    }
  } catch (error) {
    console.debug('[Kargo] Unable to calculate viewport scroll for page breaks', error)
    return { x: 0, y: 0 }
  }
}

function worksheetCellPosition(rowIndex, columnIndex, scroll) {
  try {
    const address = `${columnName(Math.max(0, Number(columnIndex) || 0))}${Math.max(0, Number(rowIndex) || 0) + 1}`
    const rect = worksheet.getRange(address).getCellRect()
    return { left: Number(rect.left) - scroll.x, top: Number(rect.top) - scroll.y }
  } catch (_) {
    return null
  }
}

function addPageBreakLine(parent, direction, position, start, length) {
  if (!Number.isFinite(position) || !Number.isFinite(start) || !Number.isFinite(length) || length <= 0) return
  const line = document.createElement('div')
  Object.assign(line.style, {
    position: 'absolute', boxSizing: 'border-box', pointerEvents: 'none',
    // Keep page guides subtle like spreadsheet print-break indicators.
    // A single CSS pixel and no shadow prevents the guide from obscuring cells.
    borderColor: 'rgba(37,99,235,.68)', borderStyle: 'dashed', borderWidth: '0',
  })
  if (direction === 'horizontal') {
    line.style.left = `${Math.max(0, start)}px`
    line.style.top = `${position}px`
    line.style.width = `${length}px`
    line.style.height = '0'
    line.style.borderTopWidth = '1px'
  } else {
    line.style.left = `${position}px`
    line.style.top = `${Math.max(0, start)}px`
    line.style.width = '0'
    line.style.height = `${length}px`
    line.style.borderLeftWidth = '1px'
  }
  parent.appendChild(line)
}

function drawPageBreakOverlay() {
  pageBreakDrawFrame = 0
  if (!ensurePageBreakOverlay()) return
  const enabled = currentPageSetup?.show_page_breaks !== false
  if (!worksheet || !pageBreakPlan) {
    pageBreakOverlay.style.display = 'none'
    return
  }
  const root = document.getElementById('univer-app')
  const canvas = getPageBreakCanvas()
  if (!root || !canvas) {
    pageBreakOverlay.style.display = 'none'
    return
  }
  const rootRect = root.getBoundingClientRect()
  const canvasRect = canvas.getBoundingClientRect()
  if (canvasRect.width < 120 || canvasRect.height < 100) {
    pageBreakOverlay.style.display = 'none'
    return
  }

  const left = canvasRect.left - rootRect.left
  const top = canvasRect.top - rootRect.top
  pageBreakOverlay.style.left = `${left}px`
  pageBreakOverlay.style.top = `${top}px`
  pageBreakOverlay.style.width = `${canvasRect.width}px`
  pageBreakOverlay.style.height = `${canvasRect.height}px`
  pageBreakOverlay.style.display = 'block'
  // Replace old guides but keep the status badge as the first child.
  while (pageBreakOverlay.children.length > 0) pageBreakOverlay.removeChild(pageBreakOverlay.lastChild)

  const scroll = viewportScrollPixels()
  const scrollState = worksheet?.getScrollState?.() || {}
  const visibleRange = worksheet?.getVisibleRange?.() || {}
  const visibleRow = Math.max(0, Number(visibleRange.startRow ?? scrollState.sheetViewStartRow ?? 0))
  const visibleColumn = Math.max(0, Number(visibleRange.startColumn ?? scrollState.sheetViewStartColumn ?? 0))
  const gridOrigin = worksheetCellPosition(visibleRow, visibleColumn, scroll)
  const skeleton = worksheet?.getSkeleton?.()
  // Univer's main sheet canvas includes the column-letter and row-number
  // headers. Page-break guides must be clipped to the cell viewport only.
  const rowHeaderWidth = Math.max(0, Number(
    skeleton?.rowHeaderWidthAndMarginLeft ?? skeleton?.rowHeaderWidth ?? 0
  ))
  const columnHeaderHeight = Math.max(0, Number(
    skeleton?.columnHeaderHeightAndMarginTop ?? skeleton?.columnHeaderHeight ?? 0
  ))
  const gridLeft = gridOrigin ? Math.max(rowHeaderWidth, gridOrigin.left) : rowHeaderWidth
  const gridTop = gridOrigin ? Math.max(columnHeaderHeight, gridOrigin.top) : columnHeaderHeight
  const width = canvasRect.width
  const height = canvasRect.height

  // Clip the overlay away from both header bands. This prevents the guides
  // from crossing column letters (A, B, C...) or row numbers.
  pageBreakOverlay.style.clipPath = `inset(${columnHeaderHeight}px 0 0 ${rowHeaderWidth}px)`
  // Page-break lines are drawn only over the grid; no page-count badge is shown.
  if (enabled && gridOrigin) {
    for (const rawRowIndex of (pageBreakPlan.rowBreaks || [])) {
      const rowIndex = Math.max(0, Number(rawRowIndex) || 0)
      // A break before the first visible row is drawn directly below the
      // column-header band; breaks already scrolled above the viewport vanish.
      if (rowIndex < visibleRow) continue
      const point = worksheetCellPosition(rowIndex, visibleColumn, scroll)
      if (!point) continue
      const lineTop = rowIndex === visibleRow
        ? Math.max(columnHeaderHeight, point.top)
        : point.top
      if (lineTop < columnHeaderHeight || lineTop > height) continue
      addPageBreakLine(pageBreakOverlay, 'horizontal', lineTop, gridLeft, width - gridLeft)
    }
    for (const rawColumnIndex of (pageBreakPlan.columnBreaks || [])) {
      const columnIndex = Math.max(0, Number(rawColumnIndex) || 0)
      if (columnIndex < visibleColumn) continue
      const point = worksheetCellPosition(visibleRow, columnIndex, scroll)
      if (!point) continue
      const lineLeft = columnIndex === visibleColumn
        ? Math.max(rowHeaderWidth, point.left)
        : point.left
      if (lineLeft < rowHeaderWidth || lineLeft > width) continue
      addPageBreakLine(pageBreakOverlay, 'vertical', lineLeft, gridTop, height - gridTop)
    }
  }

  if (pageBreakResizeObserver && pageBreakObservedCanvas !== canvas) {
    try { pageBreakResizeObserver.disconnect() } catch (_) { /* Ignore. */ }
    pageBreakObservedCanvas = canvas
    try { pageBreakResizeObserver.observe(canvas) } catch (_) { /* Ignore. */ }
  }
}

function schedulePageBreakDraw() {
  if (pageBreakDrawFrame) return
  pageBreakDrawFrame = window.requestAnimationFrame(() => drawPageBreakOverlay())
}

function refreshPageBreakPlan(snapshot = null) {
  if (!worksheet) return
  try {
    const saved = snapshot || currentSnapshot()
    if (!saved) return
    const source = {
      ...saved,
      custom: { ...(saved.custom || {}), kargoActiveSheetId: worksheet.getSheetId() },
    }
    pageBreakPlan = calculateInvoicePagePlan(source, currentPageSetup || {}, currentInvoicePdfData || null)
  } catch (error) {
    pageBreakPlan = null
    console.warn('[Kargo] Page break calculation failed', error)
  }
  schedulePageBreakDraw()
}

function initializePageBreakOverlay() {
  if (pageBreakListenersReady) return
  pageBreakListenersReady = true
  if (typeof ResizeObserver !== 'undefined') {
    pageBreakResizeObserver = new ResizeObserver(() => schedulePageBreakDraw())
  }
  window.addEventListener('resize', schedulePageBreakDraw, { passive: true })
  window.addEventListener('wheel', schedulePageBreakDraw, { passive: true, capture: true })
  window.addEventListener('scroll', schedulePageBreakDraw, { passive: true, capture: true })
  window.addEventListener('pointerup', schedulePageBreakDraw, { passive: true, capture: true })
  ensurePageBreakOverlay()
}

function parseNumber(value, type) {
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (type === 'currency' || type === 'integer') return Math.round(value)
    return value
  }
  let text = String(value ?? '').trim()
  if (!text || text === '-') return ''
  if (type === 'text' || type === 'date') return text
  text = text.replace(/^Rp\s*/i, '').replace(/\s/g, '')
  if (text.includes(',')) {
    text = text.replace(/\./g, '').replace(',', '.')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(text)) {
    text = text.replace(/\./g, '')
  }
  const parsed = Number(text)
  if (!Number.isFinite(parsed)) return String(value ?? '')
  if (type === 'currency' || type === 'integer') return Math.round(parsed)
  return parsed
}

function cellDataValue(cell, type) {
  if (!cell) return ''
  let value = cell.v
  if (value === undefined || value === null) value = ''
  if (type === 'currency' && typeof value === 'number') return Math.round(value)
  if (type === 'integer' && typeof value === 'number') return Math.round(value)
  return value
}

function setCellValue(sheet, row, column, value, type, formula = '') {
  const address = `${columnName(column)}${row + 1}`
  const range = sheet.getRange(address)
  if (formula) {
    range.setFormula(formula)
  } else {
    const parsed = parseNumber(value, type)
    range.setValue(parsed)
  }
  if (type === 'currency') range.setNumberFormat('"Rp" #,##0')
  else if (type === 'decimal') range.setNumberFormat('#,##0.##')
  else if (type === 'integer') range.setNumberFormat('#,##0')
}

function clearEvents() {
  for (const disposable of eventDisposables) {
    try { disposable?.dispose?.() } catch (_) { /* Ignore disposed listeners. */ }
  }
  eventDisposables = []
}

function registerEvents() {
  clearEvents()
  const events = univerAPI?.Event || {}
  const syncEvents = ['SheetValueChanged', 'SheetSkeletonChanged', 'CommandExecuted', 'SheetZoomChanged']
  for (const name of syncEvents) {
    if (events[name]) {
      eventDisposables.push(univerAPI.addEvent(events[name], () => {
        scheduleSnapshot()
        if (name === 'SheetZoomChanged') schedulePageBreakDraw()
      }))
    }
  }
  if (events.Scroll) {
    eventDisposables.push(univerAPI.addEvent(events.Scroll, () => schedulePageBreakDraw()))
  }
  if (events.SelectionChanged) {
    eventDisposables.push(univerAPI.addEvent(events.SelectionChanged, (params) => {
      const selected = []
      for (const item of (params?.selections || [])) {
        const range = item?.range || item
        if (!range) continue
        const top = Number(range.startRow ?? range.start?.row ?? range.startRowIndex ?? 0)
        const bottom = Number(range.endRow ?? range.end?.row ?? top)
        const left = Number(range.startColumn ?? range.start?.column ?? range.startColumnIndex ?? 0)
        const right = Number(range.endColumn ?? range.end?.column ?? left)
        if ([top, bottom, left, right].every(Number.isFinite) && Math.max(top, bottom) >= 1) {
          selected.push({ top: Math.min(top, bottom), bottom: Math.max(top, bottom), left: Math.min(left, right), right: Math.max(left, right) })
        }
      }
      safeCall('selectionChanged', JSON.stringify(selected))
    }))
  }
  if (events.BeforeSheetEditStart) {
    eventDisposables.push(univerAPI.addEvent(events.BeforeSheetEditStart, (event) => {
      if (locked) {
        event.cancel = true
        return
      }
      const row = Number(event?.row ?? event?.range?.startRow ?? -1)
      const column = Number(event?.column ?? event?.range?.startColumn ?? -1)
    }))
  }
  if (events.BeforeCommandExecute) {
    eventDisposables.push(univerAPI.addEvent(events.BeforeCommandExecute, (event) => {
      if (!locked) return
      const id = String(event?.id || '').toLowerCase()
      if (id.includes('sheet.command') || id.includes('sheet.command.')) event.cancel = true
    }))
  }
}

function scheduleSnapshot() {
  if (programmaticChange || locked) return
  if (snapshotTimer) clearTimeout(snapshotTimer)
  snapshotTimer = setTimeout(() => {
    snapshotTimer = null
    emitSnapshot()
  }, 140)
}

function currentSnapshot() {
  if (!workbook || !worksheet) return null
  try {
    const saved = workbook.save()
    return saved && typeof saved === 'object' ? saved : null
  } catch (error) {
    console.error('[Kargo] Unable to save Univer snapshot', error)
    return null
  }
}

function buildBridgePayload() {
  if (!worksheet) return null
  const previousProgrammaticState = programmaticChange
  programmaticChange = true
  try {
  const sheetSnapshot = worksheet.getSheet().getSnapshot()
  const physicalRowCount = Math.max(1, Number(sheetSnapshot.rowCount || 1))
  const physicalColumnCount = Math.max(1, Number(sheetSnapshot.columnCount || 1))
  const hasCellContent = (cell) => {
    if (!cell) return false
    if (String(cell.f || '').trim()) return true
    const value = cell.v
    return value !== undefined && value !== null && String(value).trim() !== ''
  }

  // Ignore the empty canvas when syncing to Python. A column becomes part of
  // the invoice model when it has a model key, a header, or cell content.
  let lastActiveColumn = -1
  for (let column = 0; column < physicalColumnCount; column += 1) {
    const meta = worksheet.getColumnCustomMetadata(column) || {}
    let active = Boolean(meta.kargoKey)
      || hasCellContent(sheetSnapshot.cellData?.[0]?.[column])
    if (!active) {
      for (let row = 1; row < physicalRowCount; row += 1) {
        if (hasCellContent(sheetSnapshot.cellData?.[row]?.[column])) {
          active = true
          break
        }
      }
    }
    if (active) lastActiveColumn = column
  }
  const columnCount = Math.max(1, lastActiveColumn + 1)

  // Keep model rows (row metadata) and rows containing user data/formulas.
  // Blank viewport rows below the used range are not written into the invoice.
  let lastActiveRow = 0
  for (let row = 1; row < physicalRowCount; row += 1) {
    const rowMeta = worksheet.getRowCustomMetadata(row) || {}
    let active = Boolean(rowMeta.kargoRowId)
    if (!active) {
      for (let column = 0; column < physicalColumnCount; column += 1) {
        if (hasCellContent(sheetSnapshot.cellData?.[row]?.[column])) {
          active = true
          break
        }
      }
    }
    if (active) lastActiveRow = row
  }
  const rowCount = Math.max(2, lastActiveRow + 1)

  // Column custom metadata follows a column when it is moved. A duplicated
  // custom key means a newly inserted column inherited its neighbour's meta.
  const columns = []
  const keys = new Set()
  for (let column = 0; column < columnCount; column += 1) {
    let meta = worksheet.getColumnCustomMetadata(column) || {}
    let key = String(meta.kargoKey || '')
    if (!key || keys.has(key)) {
      key = `custom_${newId()}`
      meta = { kargoKey: key, kargoType: 'text', kargoTitle: `KOLOM ${column + 1}` }
      worksheet.setColumnCustomMetadata(column, meta)
    }
    keys.add(key)
    const headerCell = sheetSnapshot.cellData?.[0]?.[column]
    const titleValue = headerCell?.v
    const title = String(titleValue ?? meta.kargoTitle ?? `KOLOM ${column + 1}`).trim() || `KOLOM ${column + 1}`
    const type = ['text', 'integer', 'decimal', 'currency', 'date'].includes(meta.kargoType) ? meta.kargoType : 'text'
    const width = Number(worksheet.getColumnWidth(column) || meta.kargoWidth || 110)
    columns.push({ key, title, type, width, stretch: Boolean(meta.kargoStretch) })
    if (meta.kargoTitle !== title || meta.kargoType !== type || meta.kargoWidth !== width) {
      worksheet.setColumnCustomMetadata(column, { ...meta, kargoKey: key, kargoTitle: title, kargoType: type, kargoWidth: width })
    }
  }
  lastColumnKeys = columns.map((item) => item.key)

  const rows = []
  const rowTokens = []
  const seenRows = new Set()
  const rowRecords = []
  const resiColumnIndex = columns.findIndex((column) => column.key === 'resi')

  // Capture row signatures before building the bridge payload. A stable Resi
  // is preferred; manual rows without Resi use their complete visible content.
  for (let row = 1; row < rowCount; row += 1) {
    const rowCells = []
    for (let column = 0; column < columnCount; column += 1) {
      const cell = sheetSnapshot.cellData?.[row]?.[column]
      rowCells.push({
        value: cellDataValue(cell, columns[column].type),
        formula: String(cell?.f || ''),
      })
    }
    const resiValue = resiColumnIndex >= 0
      ? String(rowCells[resiColumnIndex]?.value ?? '').trim().toUpperCase()
      : ''
    const signature = resiValue
      ? `resi:${resiValue}`
      : `row:${JSON.stringify(rowCells)}`
    rowRecords.push({ row, signature })
  }

  // Reassign row tokens only when current rows form an unambiguous permutation
  // of the previous snapshot. This protects Resi source metadata during a
  // native Sort operation without guessing after an actual cell edit.
  if (lastBridgeRows.length === rowRecords.length && rowRecords.length > 0) {
    const previousBySignature = new Map()
    let previousUnique = true
    for (const record of lastBridgeRows) {
      if (previousBySignature.has(record.signature)) {
        previousUnique = false
        break
      }
      previousBySignature.set(record.signature, record.id)
    }
    const currentSignatures = new Set(rowRecords.map((record) => record.signature))
    const currentUnique = currentSignatures.size === rowRecords.length
    const sameMembers = previousUnique && currentUnique
      && rowRecords.every((record) => previousBySignature.has(record.signature))
    if (sameMembers) {
      for (const record of rowRecords) {
        const expectedId = previousBySignature.get(record.signature)
        const currentMeta = worksheet.getRowCustomMetadata(record.row) || {}
        if (expectedId && currentMeta.kargoRowId !== expectedId) {
          worksheet.setRowCustomMetadata(record.row, {
            ...currentMeta,
            kargoRowId: expectedId,
          })
        }
      }
    }
  }

  const nextBridgeRows = []
  for (const record of rowRecords) {
    const row = record.row
    let meta = worksheet.getRowCustomMetadata(row) || {}
    let id = String(meta.kargoRowId || '')
    if (!id || seenRows.has(id)) {
      id = newId()
      meta = { ...meta, kargoRowId: id }
      worksheet.setRowCustomMetadata(row, meta)
    }
    seenRows.add(id)
    rowTokens.push(id)
    const cells = {}
    for (let column = 0; column < columnCount; column += 1) {
      const key = columns[column].key
      const cell = sheetSnapshot.cellData?.[row]?.[column]
      let value = cellDataValue(cell, columns[column].type)
      const formula = String(cell?.f || '')
      if (formula && (value === '' || value === null)) {
        try { value = worksheet.getRange(`${columnName(column)}${row + 1}`).getValue() ?? '' } catch (_) { /* Keep empty result. */ }
      }
      cells[key] = { value, formula }
    }
    rows.push({ id, cells })
    nextBridgeRows.push({ id, signature: record.signature })
  }
  lastBridgeRows = nextBridgeRows
  let saved = currentSnapshot()
  return {
    columns,
    rows,
    rowTokens,
    workbook: saved,
  }
  } finally {
    programmaticChange = previousProgrammaticState
  }
}

async function emitSnapshot() {
  if (!worksheet || programmaticChange) return
  try {
    // Do not wait for onCalculationResultApplied() here: that API waits for a
    // future formula-result event. Snapshot serialization is also triggered
    // by non-formula changes, so waiting can stall the bridge indefinitely.
    // Univer has already applied the visible result for committed edits; the
    // bridge reads current cell values from the worksheet below.
    if (!worksheet || programmaticChange) return
    const payload = buildBridgePayload()
    if (!payload) return
    const json = JSON.stringify(payload)
    safeCall('sheetSnapshotChanged', json)
    safeCall('snapshotAvailable', json)
    refreshPageBreakPlan(payload.workbook)
  } catch (error) {
    console.error('[Kargo] Failed to serialize sheet', error)
    safeCall('webError', String(error?.stack || error))
  }
}

function registerColumnMetadata(sheet, columns) {
  const metadata = {}
  columns.forEach((column, index) => {
    metadata[index] = {
      kargoKey: String(column.key),
      kargoTitle: String(column.title),
      kargoType: String(column.type || 'text'),
      kargoWidth: Number(column.width || 110),
      kargoStretch: Boolean(column.stretch),
    }
  })
  sheet.setColumnCustom(metadata)
}

function registerRowMetadata(sheet, rows) {
  const metadata = {}
  rows.forEach((row, index) => {
    metadata[index + 1] = { kargoRowId: String(row.id || newId()) }
  })
  sheet.setRowCustom(metadata)
  sheet.setRowCustomMetadata(0, { kargoHeader: true })
}

function createWorkbookFromModel(payload) {
  programmaticChange = true
  lastBridgeRows = []
  try {
    if (workbook?.getId?.()) {
      try { univerAPI.disposeUnit(workbook.getId()) } catch (_) { /* Ignore old workbook. */ }
    }
    const id = `kargo_invoice_${newId()}`
    workbook = univerAPI.createWorkbook({ id, name: 'Invoice Kargo' })
    worksheet = workbook.getActiveSheet()
    const columns = Array.isArray(payload.columns) ? payload.columns : []
    const rows = Array.isArray(payload.rows) ? payload.rows : []
    const modelColumnCount = Math.max(1, columns.length)
    const modelRowCount = Math.max(2, rows.length + 1)
    const columnCount = Math.max(MIN_SHEET_COLUMNS, modelColumnCount)
    const rowCount = Math.max(MIN_SHEET_ROWS, modelRowCount)
    worksheet.setRowCount(rowCount)
    worksheet.setColumnCount(columnCount)

    const matrix = [columns.map((column) => String(column.title || column.key || ''))]
    for (const row of rows) {
      const values = columns.map((column) => {
        const cell = row.cells?.[column.key] || {}
        return parseNumber(cell.value, column.type)
      })
      matrix.push(values)
    }
    worksheet.getRange(`A1:${columnName(modelColumnCount - 1)}${modelRowCount}`).setValues(matrix)
    registerColumnMetadata(worksheet, columns)
    registerRowMetadata(worksheet, rows)
    worksheet.setFrozenRows(1)
    workbook.setNumfmtLocal?.('id')
    columns.forEach((column, index) => {
      worksheet.setColumnWidth(index, Number(column.width || 110))
      if (column.type === 'currency') {
        worksheet.getRange(`${columnName(index)}2:${columnName(index)}${rowCount}`).setNumberFormat('"Rp" #,##0')
      } else if (column.type === 'decimal') {
        worksheet.getRange(`${columnName(index)}2:${columnName(index)}${rowCount}`).setNumberFormat('#,##0.##')
      } else if (column.type === 'integer') {
        worksheet.getRange(`${columnName(index)}2:${columnName(index)}${rowCount}`).setNumberFormat('#,##0')
      }
    })
    if (columnCount > 0) {
      const header = worksheet.getRange(`A1:${columnName(columnCount - 1)}1`)
      header.setFontWeight('bold')
      header.setHorizontalAlignment('center')
      header.setBackgroundColor('#e7ebf0')
    }
    rows.forEach((row, rowIndex) => {
      columns.forEach((column, columnIndex) => {
        const formula = String(row.cells?.[column.key]?.formula || '')
        if (formula) {
          const address = `${columnName(columnIndex)}${rowIndex + 2}`
          worksheet.getRange(address).setFormula(formula)
        }
      })
    })
    locked = Boolean(payload.locked)
    registerEvents()
    if (locked) document.body.classList.add('kargo-locked')
    else document.body.classList.remove('kargo-locked')
    safeCall('gridReady')
    const snapshotPayload = buildBridgePayload()
    if (snapshotPayload) {
      safeCall('snapshotAvailable', JSON.stringify(snapshotPayload))
      refreshPageBreakPlan(snapshotPayload.workbook)
    }
  } finally {
    programmaticChange = false
  }
}

function syncWorkbookFromModel(payload) {
  if (!worksheet) {
    createWorkbookFromModel(payload)
    return
  }
  const columns = Array.isArray(payload.columns) ? payload.columns : []
  const rows = Array.isArray(payload.rows) ? payload.rows : []
  const oldData = worksheet.getSheet().getSnapshot()
  const oldColumns = Number(oldData.columnCount || 0)
  const oldRows = Number(oldData.rowCount || 0)
  const keys = columns.map((column) => String(column.key))
  const sameKeys = keys.length === lastColumnKeys.length && keys.every((key, index) => key === lastColumnKeys[index])
  const targetColumns = Math.max(MIN_SHEET_COLUMNS, columns.length)
  if (!sameKeys || oldColumns !== targetColumns) {
    createWorkbookFromModel(payload)
    return
  }
  const metadataMismatch = columns.some((column, columnIndex) => {
    const meta = worksheet.getColumnCustomMetadata(columnIndex) || {}
    return meta.kargoKey !== column.key
  })
  if (metadataMismatch) {
    createWorkbookFromModel(payload)
    return
  }
  programmaticChange = true
  try {
    // A Python-side row count change is uncommon (the normal insert/delete
    // path is performed inside Univer). Resize without replacing the
    // workbook so existing merge ranges and formatting are retained.
    const targetRows = Math.max(MIN_SHEET_ROWS, rows.length + 1)
    if (oldRows !== targetRows) worksheet.setRowCount(targetRows)
    columns.forEach((column, columnIndex) => {
      const headerAddress = `${columnName(columnIndex)}1`
      const currentHeader = oldData.cellData?.[0]?.[columnIndex]?.v ?? ''
      const desiredHeader = String(column.title || column.key)
      if (String(currentHeader) !== desiredHeader) worksheet.getRange(headerAddress).setValue(desiredHeader)
      for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
        const cell = rows[rowIndex].cells?.[column.key] || {}
        const currentCell = oldData.cellData?.[rowIndex + 1]?.[columnIndex] || {}
        const currentFormula = String(currentCell.f || '')
        const desiredFormula = String(cell.formula || '')
        const desiredValue = parseNumber(cell.value, column.type)
        const sameValue = (currentCell.v ?? '') === (desiredValue ?? '')
          || (typeof currentCell.v === 'number' && typeof desiredValue === 'number' && currentCell.v === desiredValue)
        if (currentFormula !== desiredFormula || (!desiredFormula && !sameValue)) {
          setCellValue(worksheet, rowIndex + 1, columnIndex, cell.value, column.type, desiredFormula)
        }
      }
    })
    rows.forEach((row, rowIndex) => {
      const current = worksheet.getRowCustomMetadata(rowIndex + 1) || {}
      if (current.kargoRowId !== row.id) worksheet.setRowCustomMetadata(rowIndex + 1, { kargoRowId: row.id })
    })
    locked = Boolean(payload.locked)
    if (locked) document.body.classList.add('kargo-locked')
    else document.body.classList.remove('kargo-locked')
    const snapshotPayload = buildBridgePayload()
    if (snapshotPayload) {
      safeCall('snapshotAvailable', JSON.stringify(snapshotPayload))
      refreshPageBreakPlan(snapshotPayload.workbook)
    }
  } finally {
    programmaticChange = false
  }
}

function getRestoredSheetRowCount(sheetSnapshot) {
  const physicalRowCount = Math.max(1, Number(sheetSnapshot?.rowCount || 1))
  const cellData = sheetSnapshot?.cellData || {}
  let lastUsedRow = 0

  // Keep rows that contain an actual value or formula. Do not mistake the
  // old 1,000-row blank canvas for user data when restoring older snapshots.
  for (const [rowKey, rowCells] of Object.entries(cellData)) {
    const rowIndex = Number(rowKey)
    if (!Number.isInteger(rowIndex) || rowIndex < 0 || rowIndex >= physicalRowCount) continue
    if (Object.values(rowCells || {}).some((cell) => {
      if (!cell) return false
      const value = cell.v
      return String(cell.f || '').trim() !== ''
        || (value !== undefined && value !== null && String(value).trim() !== '')
    })) {
      lastUsedRow = Math.max(lastUsedRow, rowIndex)
    }
  }

  // Preserve merged ranges that extend below the default 100-row canvas.
  for (const merge of (sheetSnapshot?.mergeData || [])) {
    const endRow = Number(merge?.endRow ?? merge?.startRow ?? -1)
    if (Number.isInteger(endRow) && endRow >= 0) {
      lastUsedRow = Math.max(lastUsedRow, endRow)
    }
  }

  // Preserve rows carrying Kargo row identity metadata, including intentionally
  // created blank rows that belong to the invoice model.
  if (typeof worksheet?.getRowCustomMetadata === 'function') {
    for (let row = 1; row < physicalRowCount; row += 1) {
      const metadata = worksheet.getRowCustomMetadata(row) || {}
      if (metadata.kargoRowId) lastUsedRow = Math.max(lastUsedRow, row)
    }
  }

  return Math.max(MIN_SHEET_ROWS, lastUsedRow + 1)
}

function restoreWorkbook(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return
  programmaticChange = true
  lastBridgeRows = []
  try {
    if (workbook?.getId?.()) {
      try { univerAPI.disposeUnit(workbook.getId()) } catch (_) { /* Ignore old workbook. */ }
    }
    workbook = univerAPI.createWorkbook(snapshot)
    worksheet = workbook.getActiveSheet()
    const restoredSheet = worksheet.getSheet().getSnapshot()
    const targetRows = getRestoredSheetRowCount(restoredSheet)
    const restoredRows = Math.max(1, Number(restoredSheet.rowCount || 1))
    const restoredColumns = Math.max(1, Number(restoredSheet.columnCount || 1))
    if (restoredRows !== targetRows) worksheet.setRowCount(targetRows)
    if (restoredColumns < MIN_SHEET_COLUMNS) worksheet.setColumnCount(MIN_SHEET_COLUMNS)
    workbook.setNumfmtLocal?.('id')
    registerEvents()
    safeCall('gridReady')
    const payload = buildBridgePayload()
    if (payload) {
      safeCall('snapshotAvailable', JSON.stringify(payload))
      refreshPageBreakPlan(payload.workbook)
    }
  } catch (error) {
    console.error('[Kargo] Restore snapshot failed', error)
    safeCall('webError', `Gagal memulihkan tampilan spreadsheet: ${error?.message || error}`)
  } finally {
    programmaticChange = false
  }
}

function setModelCell(row, key, value, formula) {
  if (!worksheet) return
  const columnIndex = lastColumnKeys.indexOf(String(key))
  if (columnIndex < 0) return
  const previousProgrammaticState = programmaticChange
  programmaticChange = true
  try {
    const columnMeta = worksheet.getColumnCustomMetadata(columnIndex) || {}
    setCellValue(worksheet, Number(row) + 1, columnIndex, value, columnMeta.kargoType || 'text', formula)
    const snapshotPayload = buildBridgePayload()
    if (snapshotPayload) {
      safeCall('snapshotAvailable', JSON.stringify(snapshotPayload))
      refreshPageBreakPlan(snapshotPayload.workbook)
    }
  } finally {
    programmaticChange = previousProgrammaticState
  }
}

function setModelSelection(row, key) {
  if (!worksheet) return
  const columnIndex = lastColumnKeys.indexOf(String(key))
  if (columnIndex < 0) return
  try {
    worksheet.getRange(`${columnName(columnIndex)}${Number(row) + 2}`).activate()
  } catch (error) {
    console.debug('[Kargo] Could not move active selection', error)
  }
}

function applyTheme(theme) {
  if (!theme || typeof theme !== 'object') return
  document.documentElement.style.setProperty('--kargo-font-family', theme.fontFamily || 'Roboto')
  document.documentElement.style.setProperty('--kargo-font-size', `${Number(theme.fontSize || 9.5) * 1.333}px`)
  document.documentElement.style.setProperty('--kargo-bg', theme.bg || '#ffffff')
  document.documentElement.style.setProperty('--kargo-text', theme.text || '#202124')
  document.documentElement.style.setProperty('--kargo-border', theme.border || '#d8dde5')
  document.body.classList.toggle('kargo-dark', Boolean(theme.dark))
  try { univerAPI?.toggleDarkMode?.(Boolean(theme.dark)) } catch (error) {
    console.debug('[Kargo] Could not switch Univer dark mode', error)
  }
}

function getKargoNativeRibbonTabList() {
  const root = document.getElementById('univer-app')
  if (!root) return null

  // Kargo configures ribbonType: 'classic'. In Univer 1.6.1 that menu is
  // rendered by ClassicMenu, which has role="tablist" but deliberately does
  // NOT carry the data-u-comp="ribbon-grid-menu" marker (that marker belongs
  // to RibbonGridMenu / ribbonType: 'grid'). Identify the actual main tab row
  // by its native labels instead of relying on the grid-only marker.
  const candidates = [...root.querySelectorAll('[role="tablist"]')]
  return candidates.find((list) => {
    const labels = [...list.querySelectorAll('button[role="tab"]')]
      .map((tab) => (tab.textContent || '').normalize('NFKC').trim().toLowerCase())
    return labels.includes('view') && labels.includes('start') && labels.includes('insert')
  }) || null
}

function ensureKargoPageSetupRibbonButton() {
  const root = document.getElementById('univer-app')
  if (!root) return false

  // The current app uses Univer's ClassicMenu. Keep all native tabs intact and
  // add one normal button immediately after View.
  const tabList = getKargoNativeRibbonTabList()
  if (!tabList) return false

  const current = tabList.querySelector('[data-kargo-page-setup="true"]')
  if (current) return true

  const nativeTabs = [...tabList.querySelectorAll('button[role="tab"]')]
  if (!nativeTabs.length) return false

  const referenceTab = nativeTabs.find((tab) =>
    (tab.textContent || '').normalize('NFKC').trim().toLowerCase() === 'view'
  )
  if (!referenceTab) return false

  const button = document.createElement('button')
  button.type = 'button'
  button.dataset.kargoPageSetup = 'true'
  button.textContent = 'Page Setup'
  button.title = 'Atur ukuran kertas, orientasi, margin, dan scaling Invoice'
  button.setAttribute('aria-label', 'Page Setup Invoice')
  button.setAttribute('aria-haspopup', 'dialog')
  button.tabIndex = 0

  // Reuse the native ClassicMenu tab styling, but force the non-selected state
  // even if View happens to be the active tab when the button is inserted.
  button.className = referenceTab.className
  button.classList.remove(
    'univer-bg-primary-50',
    'univer-font-semibold',
    'univer-text-primary-600',
    'univer-shadow-sm',
    'dark:!univer-bg-primary-900',
    'dark:!univer-text-primary-300',
    'univer-border-primary-600',
    'univer-text-primary-700',
  )
  button.classList.add(
    'univer-bg-transparent',
    'univer-text-gray-700',
    'dark:!univer-text-gray-200',
  )
  button.style.marginLeft = '3px'
  button.style.flex = '0 0 auto'
  button.addEventListener('click', (event) => {
    event.preventDefault()
    event.stopPropagation()
    if (!safeCall('openPageSetup')) {
      console.error('[Kargo] Page Setup dialog could not be opened: Qt bridge is unavailable.')
    }
  })

  referenceTab.insertAdjacentElement('afterend', button)
  return true
}

function initializeKargoPageSetupRibbonButton() {
  const root = document.getElementById('univer-app')
  if (!root) return

  if (!kargoPageSetupMenuObserver) {
    kargoPageSetupMenuObserver = new MutationObserver(() => {
      ensureKargoPageSetupRibbonButton()
    })
    kargoPageSetupMenuObserver.observe(root, { childList: true, subtree: true })
  }
  // First attempt covers a ribbon which already exists; the observer handles
  // React mount/re-render and contextual ribbon updates afterwards.
  ensureKargoPageSetupRibbonButton()
}

function initializeBridge() {
  if (typeof QWebChannel === 'undefined' || !window.qt?.webChannelTransport) {
    safeCall('webError', 'QWebChannel tidak tersedia pada Qt WebEngine.')
    return
  }
  new QWebChannel(window.qt.webChannelTransport, (channel) => {
    bridge = channel.objects.kargoBridge
    safeCall('webReady')
  })
}

window.kargoLoadModel = (payload) => {
  if (!univerAPI) return
  createWorkbookFromModel(payload || {})
}
window.kargoSyncModel = (payload) => syncWorkbookFromModel(payload || {})
window.kargoCaptureCurrentModel = () => {
  if (!worksheet || programmaticChange) return null
  try {
    const payload = buildBridgePayload()
    if (!payload) return null
    // The Python model is about to receive this exact snapshot. Cancel the
    // pending debounced duplicate so it cannot race with the template rebuild.
    if (snapshotTimer) {
      window.clearTimeout(snapshotTimer)
      snapshotTimer = null
    }
    return JSON.stringify(payload)
  } catch (error) {
    console.error('[Kargo] Unable to capture current model before template switch', error)
    return null
  }
}
window.kargoRestoreSnapshot = (snapshot) => restoreWorkbook(snapshot)
window.kargoSetPageSetup = (pageSetup = {}, invoiceData = null) => {
  currentPageSetup = { ...(currentPageSetup || {}), ...(pageSetup || {}) }
  if (invoiceData && typeof invoiceData === 'object') currentInvoicePdfData = { ...invoiceData }
  refreshPageBreakPlan()
}
// Python checks this marker before dispatching a request. It prevents an old
// vendor bundle from accepting a call but never returning a correlated result.
function withTimeout(promise, timeoutMs, message) {
  let timer = null
  return new Promise((resolve, reject) => {
    timer = window.setTimeout(() => reject(new Error(message)), timeoutMs)
    Promise.resolve(promise).then(
      (value) => { if (timer !== null) window.clearTimeout(timer); resolve(value) },
      (error) => { if (timer !== null) window.clearTimeout(timer); reject(error) },
    )
  })
}

window.kargoPdfRequestProtocol = 1
window.kargoPdfBridgeDiagnostics = () => ({
  bridgeReady: Boolean(bridge),
  pdfProgressAvailable: typeof bridge?.pdfProgress === 'function',
  pdfReadyAvailable: typeof bridge?.pdfReady === 'function',
  pdfErrorAvailable: typeof bridge?.pdfError === 'function',
  workbookReady: Boolean(workbook && worksheet),
})
window.kargoGeneratePdf = async (pageSetup = {}, invoiceData = null, requestId = '') => {
  const pdfRequestId = String(requestId || '')
  const sendPdfEvent = (method, data) => {
    const envelope = JSON.stringify({ request_id: pdfRequestId, ...data })
    if (!safeCall(method, envelope)) {
      console.error(`[Kargo] Could not deliver ${method} through Qt WebChannel`, pdfRequestId)
      return false
    }
    return true
  }
  try {
    currentPageSetup = { ...(currentPageSetup || {}), ...(pageSetup || {}) }
    if (invoiceData && typeof invoiceData === 'object') currentInvoicePdfData = { ...invoiceData }
    if (!workbook || !worksheet) throw new Error('Workbook Univer belum siap.')
    sendPdfEvent('pdfProgress', { stage: 'snapshot', message: 'Membaca data worksheet Univer...' })

    // Page Setup changes do not trigger formula calculation. Calling
    // onCalculationResultApplied() here would wait for a future formula event
    // and could leave the Live Preview stuck forever. Read the current workbook
    // snapshot directly; formula cells are refreshed from worksheet.getValue()
    // immediately below before they are passed to pdfmake.

    const snapshot = currentSnapshot()
    if (!snapshot) throw new Error('Gagal mengambil snapshot workbook Univer.')
    sendPdfEvent('pdfProgress', { stage: 'layout', message: 'Menghitung layout halaman...' })
    refreshPageBreakPlan(snapshot)
    snapshot.custom = {
      ...(snapshot.custom || {}),
      kargoActiveSheetId: worksheet.getSheetId(),
    }

    // Some formula cells store the source expression separately from the
    // displayed result. Resolve their current calculated values before handing
    // the snapshot to pdfmake, so printed values match the visible worksheet.
    const activeSheetId = snapshot.custom?.kargoActiveSheetId || snapshot.sheetOrder?.[0]
    const activeSheet = activeSheetId ? snapshot.sheets?.[activeSheetId] : null
    for (const [rowKey, rowCells] of Object.entries(activeSheet?.cellData || {})) {
      const rowIndex = Number(rowKey)
      if (!Number.isInteger(rowIndex) || rowIndex < 0) continue
      for (const [columnKey, cell] of Object.entries(rowCells || {})) {
        if (!cell || !String(cell.f || '').trim()) continue
        const columnIndex = Number(columnKey)
        if (!Number.isInteger(columnIndex) || columnIndex < 0) continue
        try {
          cell.v = worksheet.getRange(`${columnName(columnIndex)}${rowIndex + 1}`).getValue() ?? ''
        } catch (_) { /* Preserve the cached value if formula lookup fails. */ }
      }
    }

    sendPdfEvent('pdfProgress', { stage: 'render', message: 'pdfmake sedang merender halaman PDF...' })
    const blob = await withTimeout(
      buildInvoicePdfBlob(snapshot, pageSetup || {}, invoiceData || null),
      45000,
      'pdfmake tidak menyelesaikan rendering dalam 45 detik.'
    )
    sendPdfEvent('pdfProgress', { stage: 'encode', message: 'PDF selesai dirender; menyiapkan data untuk Preview...' })
    const bytes = new Uint8Array(await withTimeout(
      blob.arrayBuffer(),
      15000,
      'PDF selesai dirender tetapi proses konversi datanya melewati 15 detik.'
    ))
    let binary = ''
    const chunkSize = 0x8000
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize))
    }
    sendPdfEvent('pdfReady', { payload: btoa(binary) })
  } catch (error) {
    console.error('[Kargo] PDFMake export failed', error)
    sendPdfEvent('pdfError', { message: String(error?.message || error) })
  }
}
window.kargoSetModelCell = (row, key, value, formula = '') => setModelCell(row, key, value, formula)
window.kargoSetModelSelection = (row, key) => setModelSelection(row, key)
window.kargoSetLocked = (value) => {
  locked = Boolean(value)
  document.body.classList.toggle('kargo-locked', locked)
}
window.kargoApplyTheme = (theme) => applyTheme(theme)
window.kargoSetColumnWidth = (column, width) => {
  try { worksheet?.setColumnWidth(Number(column), Number(width)) } catch (_) { /* Ignore. */ }
}
window.kargoAdjustZoom = (direction) => {
  try {
    const activeSheet = univerAPI?.getActiveWorkbook?.()?.getActiveSheet?.() || worksheet
    if (!activeSheet) return null
    const current = Number(activeSheet.getZoom?.() || 1)
    const step = Number(direction) > 0 ? 0.1 : -0.1
    const next = Math.max(0.1, Math.min(4, Math.round((current + step) * 100) / 100))
    activeSheet.zoom(next)
    return next
  } catch (error) {
    console.warn('[Kargo] Ctrl+Scroll zoom failed', error)
    return null
  }
}

window.kargoDebugPageBreaks = () => ({
  overlayConnected: Boolean(pageBreakOverlay?.isConnected),
  overlayParent: pageBreakOverlay?.parentElement?.id || null,
  mainCanvasFound: Boolean(getPageBreakCanvas()),
  hasWorksheet: Boolean(worksheet),
  hasPlan: Boolean(pageBreakPlan),
  showPageBreaks: currentPageSetup?.show_page_breaks !== false,
  pageSetupMenuTabListFound: Boolean(getKargoNativeRibbonTabList()),
  pageSetupMenuButtonFound: Boolean(document.querySelector('[data-kargo-page-setup="true"]')) ,
  rowBreaks: pageBreakPlan?.rowBreaks || [],
  columnBreaks: pageBreakPlan?.columnBreaks || [],
})

function initializeUniver() {
  try {
    initializePageBreakOverlay()
    const result = createUniver({
      locale: LocaleType.EN_US,
      locales: {
        [LocaleType.EN_US]: mergeLocales(
          UniverPresetSheetsCoreEnUS,
          UniverPresetSheetsFilterEnUS,
          UniverPresetSheetsSortEnUS,
          UniverPresetSheetsDataValidationEnUS,
          UniverPresetSheetsConditionalFormattingEnUS,
          UniverPresetSheetsFindReplaceEnUS,
          UniverPresetSheetsHyperLinkEnUS,
          UniverPresetSheetsTableEnUS,
          UniverPresetSheetsDrawingEnUS,
          UniverPresetSheetsNoteEnUS,
          UniverPresetSheetsThreadCommentEnUS,
        ),
      },
      presets: [
        UniverSheetsCorePreset({
        // Keep the original Univer desktop spreadsheet interface. The Kargo
        // layer only supplies invoice data and application-specific actions.
        container: 'univer-app',
        header: true,
        toolbar: true,
        ribbonType: 'classic',
        contextMenu: true,
        formulaBar: true,
        footer: {
          sheetBar: true,
          statisticBar: true,
          menus: true,
          zoomSlider: true,
          addSheetButtonConfig: {
            show: true,
            defaultRowCount: MIN_SHEET_ROWS,
            defaultColumnCount: MIN_SHEET_COLUMNS,
          },
        },
        sheets: {
          // Native Excel-like fill handle and overwrite warning.
          enableFillHandle: true,
          warnBeforeDragOverwrite: true,
          selectionAnimation: true,
          // Merged text can grow its row; arrow keys do not wrap at sheet edge.
          autoHeightForMergedCells: true,
          allowArrowKeyWrapOnSheetBoundary: false,
        },
        }),
        // Data handling: AutoFilter, single/multi-column sorting, validation,
        // conditional formatting, Find & Replace, hyperlinks and Tables.
        UniverSheetsFilterPreset(),
        UniverSheetsSortPreset(),
        UniverSheetsDataValidationPreset({
          showEditOnDropdown: true,
          showSearchOnDropdown: true,
        }),
        UniverSheetsConditionalFormattingPreset(),
        UniverSheetsFindReplacePreset(),
        UniverSheetsHyperLinkPreset(),
        UniverSheetsTablePreset(),
        // Cell notes, threaded comments and floating/in-cell images.
        UniverSheetsDrawingPreset({ allowImageSize: 5 * 1024 * 1024 }),
        UniverSheetsNotePreset(),
        UniverSheetsThreadCommentPreset(),
      ],
    })
    univer = result.univer
    univerAPI = result.univerAPI
    initializeBridge()
    initializeKargoPageSetupRibbonButton()
  } catch (error) {
    console.error('[Kargo] Univer initialization failed', error)
    safeCall('webError', `Univer gagal diinisialisasi: ${error?.stack || error}`)
  }
}

initializeUniver()