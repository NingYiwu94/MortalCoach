const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("mortalCoachElectron", {
  enabled: true,
});
