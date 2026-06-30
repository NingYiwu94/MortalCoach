const { app, BrowserWindow, Menu } = require("electron");
const childProcess = require("node:child_process");
const net = require("node:net");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const host = "127.0.0.1";
const port = Number(process.env.MORTALCOACH_PORT || "8766");
const appUrl = `http://${host}:${port}`;
let serverProcess = null;

console.log("MortalCoach Electron starting", { root, appUrl });
app.setPath("userData", path.join(root, "data", "electron-profile"));
Menu.setApplicationMenu(null);

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
  const python = process.env.MORTALCOACH_PYTHON || "python";
  serverProcess = childProcess.spawn(python, ["app.py"], {
    cwd: root,
    env: { ...process.env, MORTALCOACH_PORT: String(port) },
    stdio: "ignore",
    windowsHide: true,
  });
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
  win.setMenuBarVisibility(false);
  await win.loadURL(appUrl);
  console.log("MortalCoach window loaded.");
}

app.whenReady().then(createWindow).catch((error) => {
  console.error(error);
  app.quit();
});

app.on("window-all-closed", () => {
  if (serverProcess) {
    serverProcess.kill();
    serverProcess = null;
  }
  app.quit();
});
