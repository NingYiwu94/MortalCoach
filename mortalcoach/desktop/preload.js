const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("mortalCoachElectron", {
  enabled: true,
  getVersion: () => ipcRenderer.invoke("mortalcoach:get-version"),
  openExternal: (url) => ipcRenderer.invoke("mortalcoach:open-external", url),
});
