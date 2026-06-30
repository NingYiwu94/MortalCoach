// For debug, create window.MM so we can do debug from dev console
// e.g. MM.debugState()
const params = new URLSearchParams(window.location.search)
if (params.get("embed") === "1") {
  document.documentElement.classList.add("mortalcoach-embed")
  const requestedTheme = params.get("theme") === "light" ? "light" : "dark"
  document.documentElement.classList.add(`theme-${requestedTheme}`)
  const fitToMortalCoach = () => {
    const widthScale = window.innerWidth / 1260
    const heightScale = window.innerHeight / 735
    const zoom = Math.max(0.68, Math.min(1.02, Math.min(widthScale, heightScale)))
    document.documentElement.style.setProperty("--zoom", String(zoom))
  }
  fitToMortalCoach()
  window.addEventListener("resize", fitToMortalCoach)
}
import mainModule from "./index.js?d=27"
window.MM = mainModule
window.setMortalCoachTheme = mainModule.setMortalCoachTheme
window.addEventListener("message", (event) => {
  if (event.data && event.data.type === "mortalcoach-theme") {
    mainModule.setMortalCoachTheme(event.data.theme)
  }
})
