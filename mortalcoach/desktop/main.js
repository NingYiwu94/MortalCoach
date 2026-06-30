const { app, BrowserWindow, Menu, ipcMain, shell } = require("electron");
const { autoUpdater } = require("electron-updater");
const childProcess = require("node:child_process");
const net = require("node:net");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const host = "127.0.0.1";
const port = Number(process.env.MORTALCOACH_PORT || "8766");
const appUrl = `http://${host}:${port}`;
let serverProcess = null;
let mainWindow = null;
let updateCheckInFlight = false;

console.log("MortalCoach Electron starting", { root, appUrl });
if (app.isPackaged) {
  app.setPath("userData", path.join(app.getPath("appData"), "MortalCoach"));
} else {
  app.setPath("userData", path.join(root, "data", "electron-profile"));
}
Menu.setApplicationMenu(null);

ipcMain.handle("mortalcoach:get-version", () => app.getVersion());

ipcMain.handle("mortalcoach:open-external", async (_event, url) => {
  const parsed = new URL(String(url || ""));
  const allowedHost = parsed.hostname === "github.com";
  const allowedPath = parsed.pathname.startsWith("/NingYiwu94/MortalCoach/releases");
  if (parsed.protocol !== "https:" || !allowedHost || !allowedPath) {
    throw new Error("Blocked external URL.");
  }
  await shell.openExternal(parsed.toString());
  return true;
});

function sendUpdateStatus(payload) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  mainWindow.webContents.send("mortalcoach:update-status", {
    currentVersion: app.getVersion(),
    ...payload,
  });
}

autoUpdater.autoDownload = false;
autoUpdater.autoInstallOnAppQuit = false;

autoUpdater.on("checking-for-update", () => {
  sendUpdateStatus({ status: "checking" });
});

autoUpdater.on("update-available", (info) => {
  sendUpdateStatus({
    status: "available",
    version: info?.version || "",
    releaseName: info?.releaseName || "",
  });
});

autoUpdater.on("update-not-available", (info) => {
  sendUpdateStatus({
    status: "not-available",
    version: info?.version || app.getVersion(),
  });
});

autoUpdater.on("download-progress", (progress) => {
  sendUpdateStatus({
    status: "downloading",
    percent: Math.max(0, Math.min(100, Math.round(progress?.percent || 0))),
    transferred: progress?.transferred || 0,
    total: progress?.total || 0,
  });
});

autoUpdater.on("update-downloaded", (info) => {
  sendUpdateStatus({
    status: "downloaded",
    version: info?.version || "",
  });
});

autoUpdater.on("error", (error) => {
  sendUpdateStatus({
    status: "error",
    message: error?.message || String(error || "Update failed."),
  });
});

ipcMain.handle("mortalcoach:check-for-updates", async () => {
  if (!app.isPackaged) {
    const payload = { status: "dev", currentVersion: app.getVersion() };
    sendUpdateStatus(payload);
    return payload;
  }
  if (updateCheckInFlight) {
    return { status: "checking", currentVersion: app.getVersion() };
  }
  updateCheckInFlight = true;
  try {
    sendUpdateStatus({ status: "checking" });
    const result = await autoUpdater.checkForUpdates();
    return {
      status: "checked",
      currentVersion: app.getVersion(),
      updateInfo: result?.updateInfo || null,
    };
  } finally {
    updateCheckInFlight = false;
  }
});

ipcMain.handle("mortalcoach:download-update", async () => {
  if (!app.isPackaged) {
    return { status: "dev", currentVersion: app.getVersion() };
  }
  sendUpdateStatus({ status: "downloading", percent: 0 });
  await autoUpdater.downloadUpdate();
  return { status: "download-started", currentVersion: app.getVersion() };
});

ipcMain.handle("mortalcoach:install-update", () => {
  if (!app.isPackaged) return false;
  autoUpdater.quitAndInstall(false, true);
  return true;
});

function isPortOpen() {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host, port });
    socket.setTimeout(300);
    socket.on("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.on("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.on("error", () => resolve(false));
  });
}

async function waitUntilReady() {
  for (let i = 0; i < 120; i += 1) {
    if (await isPortOpen()) return;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("MortalCoach local service did not start in time.");
}

async function startServerIfNeeded() {
  if (await isPortOpen()) return;
  const env = {
    ...process.env,
    MORTALCOACH_PORT: String(port),
    MORTALCOACH_DATA_DIR: path.join(app.getPath("userData"), "data"),
  };
  if (app.isPackaged) {
    const backend = path.join(process.resourcesPath, "backend", "MortalCoachBackend.exe");
    serverProcess = childProcess.spawn(backend, [], {
      cwd: path.dirname(backend),
      env,
      stdio: "ignore",
      windowsHide: true,
    });
  } else {
    const python = process.env.MORTALCOACH_PYTHON || "python";
    serverProcess = childProcess.spawn(python, ["app.py"], {
      cwd: root,
      env,
      stdio: "ignore",
      windowsHide: true,
    });
  }
  await waitUntilReady();
}

async function createWindow() {
  console.log("Preparing local service...");
  await startServerIfNeeded();
  console.log("Opening MortalCoach window...");
  const win = new BrowserWindow({
    width: 1440,
    height: 940,
    minWidth: 1120,
    minHeight: 760,
    title: "MortalCoach",
    autoHideMenuBar: true,
    backgroundColor: "#061f24",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  mainWindow = win;
  win.setMenuBarVisibility(false);
  await win.loadURL(appUrl);
  console.log("MortalCoach window loaded.");
}

function stopServer() {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
}

app.whenReady().then(createWindow).catch((error) => {
  console.error(error);
  app.quit();
});

app.on("before-quit", stopServer);

app.on("window-all-closed", () => {
  stopServer();
  app.quit();
});
