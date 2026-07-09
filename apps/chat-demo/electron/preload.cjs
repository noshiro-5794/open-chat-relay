const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("openChatRelayDesktop", {
  platform: process.platform,
  version: process.versions.electron,
});
