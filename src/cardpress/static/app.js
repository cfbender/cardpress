const $ = (selector) => document.querySelector(selector)

const SUGGESTIONS = ["Treasure", "Food", "Clue", "Blood", "Map", "Zombie", "Soldier", "Goblin", "Spirit", "Saproling", "Monarch", "Initiative"]
const KINDS = {
  tokens: { noun: "tokens", placeholder: "Search tokens: zombie, treasure, monarch…" },
  cards: { noun: "cards", placeholder: "Search cards by name, or use Scryfall syntax" },
  all: { noun: "cards or tokens", placeholder: "Search every card and token" },
}
const SEARCH_DEBOUNCE_MS = 400
const TOAST_MS = 4000
const MAX_COPIES = 20

const searchForm = $("#search-form")
const queryInput = $("#query")
const results = $("#results")
const resultCount = $("#result-count")
const notice = $("#notice")
const cardDialog = $("#card-dialog")
const previewWell = $("#preview-well")
const previewImage = $("#card-preview")
const copiesInput = $("#copies")
const printButton = $("#print")
const settingsDialog = $("#settings-dialog")
const settingsForm = $("#settings-form")
const toasts = $("#toasts")

let settings = { layout: "", target: "", layouts: [] }
let selectedFace = null
let searchRequest = null
let searchTimer = 0

async function api(path, options) {
  const response = await fetch(path, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status})`)
  }
  return body
}

const sendJson = (method, body) => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })

function element(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

function toast(message, kind = "info") {
  const node = element("div", `toast toast-${kind}`, message)
  toasts.append(node)
  // Re-open the popover so it moves above any dialog opened since the last toast.
  if (toasts.matches(":popover-open")) toasts.hidePopover()
  toasts.showPopover()
  setTimeout(() => {
    node.remove()
    if (!toasts.children.length && toasts.matches(":popover-open")) toasts.hidePopover()
  }, TOAST_MS)
}

/* Search */

function showNotice(title, text, suggestions = []) {
  results.replaceChildren()
  resultCount.textContent = ""
  $("#notice-title").textContent = title
  $("#notice-text").textContent = text
  $("#suggestions").replaceChildren(
    ...suggestions.map((name) => {
      const chip = element("button", "chip", name)
      chip.type = "button"
      chip.addEventListener("click", () => {
        queryInput.value = name
        search()
      })
      return chip
    }),
  )
  notice.hidden = false
}

function showSkeletons() {
  notice.hidden = true
  resultCount.textContent = ""
  results.replaceChildren(...Array.from({ length: 12 }, () => element("div", "skeleton")))
}

// Many tokens share a name, so the stats are part of telling them apart.
const summary = (face) => [face.stats, face.type_line].filter(Boolean).join(" · ")

function tile(face) {
  const button = element("button", "tile")
  button.type = "button"
  const frame = element("span", "tile-image")
  if (face.image_url) {
    const image = element("img")
    image.src = face.image_url
    image.alt = ""
    image.loading = "lazy"
    frame.append(image)
  } else {
    frame.textContent = "No image"
  }
  button.append(frame, element("span", "tile-name", face.name), element("span", "tile-type", summary(face)))
  button.addEventListener("click", () => openCard(face))
  return button
}

function showResults(data, query, kind) {
  if (!data.results.length) {
    const elsewhere = kind === "all" ? "Check the spelling." : "Check the spelling, or search Everything."
    showNotice(`No ${KINDS[kind].noun} match “${query}”`, elsewhere)
    return
  }
  notice.hidden = true
  const count = data.results.length
  resultCount.textContent = data.has_more
    ? `Showing the first ${count} of ${data.total_cards.toLocaleString()} cards. Add more words to narrow the search.`
    : `${count} ${count === 1 ? "result" : "results"}`
  results.replaceChildren(...data.results.map(tile))
}

async function search() {
  clearTimeout(searchTimer)
  searchRequest?.abort()
  const query = queryInput.value.trim()
  const kind = searchForm.elements.kind.value
  queryInput.placeholder = KINDS[kind].placeholder

  const url = new URL(location.href)
  url.search = query ? new URLSearchParams({ q: query, kind }) : ""
  history.replaceState(null, "", url)

  if (!query) {
    showNotice("What do you need?", "Search above, or start with a common token.", SUGGESTIONS)
    return
  }
  const request = (searchRequest = new AbortController())
  showSkeletons()
  try {
    const data = await api(`/api/search?${new URLSearchParams({ q: query, kind })}`, { signal: request.signal })
    showResults(data, query, kind)
  } catch (error) {
    if (request.signal.aborted) return
    showNotice("Search failed", error.message)
  }
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault()
  search()
})
searchForm.addEventListener("change", (event) => {
  if (event.target.name === "kind") search()
})
queryInput.addEventListener("input", () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(search, SEARCH_DEBOUNCE_MS)
})

/* Card dialog */

function layoutLabel() {
  return settings.layouts.find((layout) => layout.key === settings.layout)?.label ?? ""
}

function showPrinter() {
  const ready = Boolean(settings.target)
  $("#printer-summary").textContent = layoutLabel() || "Printer"
  $("#printer-dot").classList.toggle("is-ready", ready)
  $("#open-settings").title = ready ? `Printing to ${settings.target}` : "No printer set"

  $("#printer-line").classList.toggle("is-missing", !ready)
  $("#printer-line-text").replaceChildren(
    ...(ready ? ["Printing to ", element("code", "", settings.target), ". "] : ["No printer set. "]),
  )
  $("#change-printer").textContent = ready ? "Change" : "Set up printer"
  $("#preview-layout").textContent = layoutLabel()
  printButton.disabled = !ready
}

function loadPreview() {
  if (!selectedFace) return
  previewWell.dataset.state = "loading"
  previewImage.src = `/api/preview.png?${new URLSearchParams({
    id: selectedFace.card_id,
    face: selectedFace.index,
    layout: settings.layout,
  })}`
}
previewImage.addEventListener("load", () => (previewWell.dataset.state = "ready"))
previewImage.addEventListener("error", () => (previewWell.dataset.state = "failed"))

function openCard(face) {
  selectedFace = face
  $("#card-title").textContent = face.name
  $("#card-type").textContent = summary(face)
  $("#card-set").textContent = [face.set_name, face.artist && `Illus. ${face.artist}`].filter(Boolean).join(" · ")
  $("#card-image").src = face.image_url ?? ""
  $("#card-image").alt = face.name
  copiesInput.value = 1
  loadPreview()
  cardDialog.showModal()
}

function copies() {
  const value = Math.round(Number(copiesInput.value)) || 1
  return Math.min(MAX_COPIES, Math.max(1, value))
}
$("#copies-less").addEventListener("click", () => (copiesInput.value = Math.max(1, copies() - 1)))
$("#copies-more").addEventListener("click", () => (copiesInput.value = Math.min(MAX_COPIES, copies() + 1)))
copiesInput.addEventListener("change", () => (copiesInput.value = copies()))

printButton.addEventListener("click", async () => {
  const face = selectedFace
  const count = copies()
  printButton.disabled = true
  $("#print-label").textContent = "Printing…"
  try {
    await api("/api/print", sendJson("POST", { id: face.card_id, face: face.index, copies: count }))
    toast(`Sent ${count} × ${face.name} to the printer`)
  } catch (error) {
    toast(error.message, "error")
  } finally {
    $("#print-label").textContent = "Print"
    printButton.disabled = !settings.target
  }
})

/* Settings dialog */

function openSettings() {
  $("#layout-options").replaceChildren(
    ...settings.layouts.map((layout) => {
      const option = element("label", "option")
      const radio = element("input")
      radio.type = "radio"
      radio.name = "layout"
      radio.value = layout.key
      radio.checked = layout.key === settings.layout
      const text = element("span")
      text.append(element("strong", "", layout.label), element("small", "", layout.description))
      option.append(radio, text)
      return option
    }),
  )
  settingsForm.elements.target.value = settings.target
  settingsDialog.showModal()
}

$("#open-settings").addEventListener("click", openSettings)
$("#change-printer").addEventListener("click", openSettings)
$("#settings-close").addEventListener("click", () => settingsDialog.close())
$("#settings-cancel").addEventListener("click", () => settingsDialog.close())

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault()
  const { layout, target } = settingsForm.elements
  try {
    settings = await api("/api/settings", sendJson("PUT", { layout: layout.value, target: target.value }))
  } catch (error) {
    toast(error.message, "error")
    return
  }
  settingsDialog.close()
  showPrinter()
  if (cardDialog.open) loadPreview()
  toast("Printer settings saved")
})

/* Theme */

for (const radio of document.querySelectorAll('input[name="theme"]')) {
  radio.checked = radio.value === document.documentElement.dataset.theme
  radio.addEventListener("change", () => {
    document.documentElement.dataset.theme = radio.value
    localStorage.setItem("theme", radio.value)
  })
}

/* Start: restore the search from the URL and load the printer settings. */

const params = new URLSearchParams(location.search)
queryInput.value = params.get("q") ?? ""
if (params.get("kind") in KINDS) searchForm.elements.kind.value = params.get("kind")
search()

try {
  settings = await api("/api/settings")
} catch (error) {
  toast(`Could not load printer settings: ${error.message}`, "error")
}
showPrinter()
