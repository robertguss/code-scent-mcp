import fs from "node:fs/promises";

const REQUEST_TIMEOUT_MS = 5000;

async function main() {
  const url = process.env.DASHBOARD_URL;
  const screenshotPath = process.env.SCREENSHOT_PATH;
  const remotePort = process.env.REMOTE_PORT;

  const pageListUrl = `http://127.0.0.1:${remotePort}/json/list`;
  const pagesResponse = await fetch(pageListUrl, {
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });
  if (!pagesResponse.ok) {
    throw new Error(`Chrome page list request failed: ${pagesResponse.status}`);
  }
  const pages = await pagesResponse.json();
  const target = pages.find((page) => page.type === "page") ?? pages[0];
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let id = 0;
  const pending = new Map();

  ws.onmessage = (event) => {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch (error) {
      throw new Error(`Invalid Chrome DevTools message: ${error.message}`);
    }
    if (message.id && pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  };

  await new Promise((resolve) => {
    ws.onopen = resolve;
  });

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
    if (result.exceptionDetails) {
      throw new Error(`Runtime evaluation failed: ${result.exceptionDetails.text}`);
    }
    const evaluation = result.result;
    const remoteObject = evaluation?.result;
    return remoteObject?.value;
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
  const screenshotData = screenshot.result?.data;
  if (!screenshotData) {
    throw new Error("Chrome did not return screenshot data");
  }
  await fs.writeFile(screenshotPath, Buffer.from(screenshotData, "base64"));
  ws.close();
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
