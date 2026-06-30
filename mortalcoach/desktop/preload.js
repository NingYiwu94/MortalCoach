const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("mortalCoachElectron", {
  enabled: true,
  getVersion: () => ipcRenderer.invoke("mortalcoach:get-version"),
  openExternal: (url) => ipcRenderer.invoke("mortalcoach:open-external", url),
  checkForUpdates: () => ipcRenderer.invoke("mortalcoach:check-for-updates"),
  downloadUpdate: () => ipcRenderer.invoke("mortalcoach:download-update"),
  installUpdate: () => ipcRenderer.invoke("mortalcoach:install-update"),
  onUpdateStatus: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("mortalcoach:update-status", listener);
    return () => ipcRenderer.removeListener("mortalcoach:update-status", listener);
  },
});
