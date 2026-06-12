import fs from "node:fs";

const url = process.env.DASHBOARD_URL;
const screenshotPath = process.env.SCREENSHOT_PATH;
const remotePort = process.env.REMOTE_PORT;

const pages = await fetch(`http://127.0.0.1:${remotePort}/json/list`).then((response) =>
  response.json(),
);
const target = pages.find((page) => page.type === "page") ?? pages[0];
const ws = new WebSocket(target.webSocketDebuggerUrl);
let id = 0;
const pending = new Map();

ws.addEventListener("message", (event) => {
  const message = JSON.parse(event.data);
  if (message.id && pending.has(message.id)) {
    pending.get(message.id)(message);
    pending.delete(message.id);
  }
});

await new Promise((resolve) => ws.addEventListener("open", resolve, { once: true }));

function send(method, params = {}) {
  const commandId = ++id;
  ws.send(JSON.stringify({ id: commandId, method, params }));
  return new Promise((resolve) => pending.set(commandId, resolve));
}

async function evalValue(expression) {
  const result = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  return result.result.result.value;
}

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});
await send("Page.navigate", { url });

for (let attempt = 0; attempt < 30; attempt += 1) {
  const ready = await evalValue(
    "document.querySelectorAll('.trend-row').length >= 3" +
      " && document.querySelectorAll('.rule-toggle').length >= 1",
  );
  if (ready) {
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 250));
}

await evalValue("document.querySelector('.rule-toggle')?.click()");
for (let attempt = 0; attempt < 20; attempt += 1) {
  const updated = await evalValue(
    "document.querySelectorAll('.rule-toggle')[0]?.textContent === 'Enable'",
  );
  if (updated) {
    break;
  }
  await new Promise((resolve) => setTimeout(resolve, 250));
}

const screenshot = await send("Page.captureScreenshot", {
  format: "png",
  captureBeyondViewport: false,
});
fs.writeFileSync(screenshotPath, Buffer.from(screenshot.result.data, "base64"));
ws.close();
